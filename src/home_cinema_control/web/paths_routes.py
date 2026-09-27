import logging

import requests as _requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from home_cinema_control.devices.home_assistant.media_source_power import (
    power_on_media_source_for_mapping,
)
from home_cinema_control.devices.oppo.setup_control import browse_network_folder
from home_cinema_control.playback.diagnostics import (
    diagnose_device_action_failed,
    diagnose_path_inference_failed,
    diagnose_path_test_failed,
)
from home_cinema_control.playback.path_mapping_inference import infer_player_paths
from home_cinema_control.web.api_runtime import WebApiRuntime
from home_cinema_control.web.media_server_setup import media_server_setup_service
from home_cinema_control.web.path_config import check_path_configuration, preview_path_mapping


def build_paths_router(api_runtime: WebApiRuntime, media_server_provider_factory) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/path-mapping-suggestions")
    def post_path_mapping_suggestions(body: dict):
        anchor = body.get("anchor") or {}
        candidates = body.get("candidates") or []
        anchor_source = anchor.get("source_path", "")
        anchor_share = anchor.get("share_path", "")
        try:
            pairs = infer_player_paths(anchor_source, anchor_share, candidates)
            return [
                {"source_path": src, "share_path": share}
                for src, share in pairs
            ]
        except ValueError as exc:
            api_runtime.runtime.set_last_diagnostic(diagnose_path_inference_failed())
            raise HTTPException(status_code=422, detail=str(exc))

    @router.get("/paths/refresh")
    def paths_refresh():
        config = api_runtime.config_service.load_config()
        config = media_server_setup_service(
            media_server_provider_factory,
            config,
        ).load_selectable_folders(config)
        return api_runtime.config_service.sanitize(config)

    @router.post("/paths/preview")
    def paths_preview(body: dict):
        try:
            return preview_path_mapping(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    def _power_on_media_source(config: dict, mapping: dict) -> JSONResponse | None:
        """Wake the path's NAS; a JSONResponse error when it stays offline."""
        power_result = power_on_media_source_for_mapping(config, mapping)
        if power_result.status.value != "failed":
            return None
        diagnostic = diagnose_device_action_failed(
            component="media_source",
            action="power on",
            detail=str(power_result.detail),
            severity="error",
        )
        api_runtime.runtime.set_last_diagnostic(diagnostic)
        return JSONResponse(
            status_code=400,
            content={"detail": diagnostic.reason, "diagnostic": diagnostic.to_dict()},
        )

    @router.post("/paths/power-on")
    def paths_power_on(body: dict):
        config = api_runtime.config_service.load_config()
        error = _power_on_media_source(config, body)
        if error is not None:
            return error
        return {"status": "ok"}

    @router.post("/paths/test")
    def paths_test(body: dict):
        config = api_runtime.config_service.load_config()
        # The OPPO can only mount the share once its NAS is up.
        error = _power_on_media_source(config, body)
        if error is not None:
            return error
        result = check_path_configuration(config, body)
        if result == "OK":
            return body
        diagnostic = diagnose_path_test_failed(result, config)
        api_runtime.runtime.set_last_diagnostic(diagnostic)
        return JSONResponse(
            status_code=400,
            content={"detail": diagnostic.reason, "diagnostic": diagnostic.to_dict()},
        )

    @router.post("/paths/navigate")
    def paths_navigate(body: dict):
        config = api_runtime.config_service.load_config()
        path = body.get("path", "/")
        protocol = body.get("protocol")
        try:
            result = browse_network_folder(path, config, protocol=protocol)
            logging.debug("paths_navigate | chars=%s", len(str(result)))
            return result
        except (_requests.exceptions.ConnectTimeout, _requests.exceptions.ConnectionError) as exc:
            logging.warning("paths_navigate: OPPO unreachable | path=%s | error=%s", path, exc)
            raise HTTPException(status_code=503, detail="OPPO unreachable")
        except Exception as exc:
            logging.warning("paths_navigate failed | path=%s | error=%s", path, exc)
            raise HTTPException(status_code=502, detail=str(exc))

    return router
