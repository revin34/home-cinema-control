import logging

import requests
from fastapi import APIRouter, HTTPException

from home_cinema_control.devices.lighting.setup_control import (
    list_lighting_entities,
    test_lighting_connection,
    turn_lighting_off,
    turn_lighting_on,
)
from home_cinema_control.playback.diagnostics import diagnose_device_action_failed
from home_cinema_control.web.api_runtime import WebApiRuntime
from home_cinema_control.web.setup_verification import mark_section_verified


def build_lighting_router(api_runtime: WebApiRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/lighting")

    def _fail(action: str, detail: str | None):
        api_runtime.runtime.set_last_diagnostic(diagnose_device_action_failed(
            component="lighting", action=action, detail=str(detail or "")
        ))
        raise HTTPException(status_code=400, detail=detail or f"Lighting {action} failed")

    @router.post("/test-connection")
    def lighting_test_connection(body: dict):
        body = api_runtime.config_service.prepare_submitted_config(body)
        result = test_lighting_connection(body)
        if not result.successful:
            _fail("connection test", result.detail)

        lighting = body.get("lighting") or {}
        logging.info(
            "Lighting test connection succeeded | url=%s | entities=%s",
            lighting.get("home_assistant_url", ""),
            len(lighting.get("entity_ids") or []),
        )
        # Like the TV test: a successful test proves the submitted URL and
        # token work, so persist them (the token lands in secrets.json).
        verified_config = mark_section_verified(body, "lighting")
        api_runtime.config_service.save_config(verified_config)
        return {
            "status": "ok",
            "verification_persisted": True,
            "lighting": api_runtime.config_service.sanitize(verified_config).get("lighting", {}),
        }

    @router.post("/entities")
    def lighting_entities(body: dict):
        body = api_runtime.config_service.prepare_submitted_config(body)
        try:
            return {"entities": list_lighting_entities(body)}
        except (ValueError, requests.RequestException) as exc:
            _fail("detect entities", str(exc))

    @router.post("/turn-on")
    def lighting_turn_on(body: dict):
        body = api_runtime.config_service.prepare_submitted_config(body)
        result = turn_lighting_on(body)
        if result.status.value == "failed":
            _fail("turn on", result.detail)
        return {"status": result.status.value, "detail": result.detail}

    @router.post("/turn-off")
    def lighting_turn_off(body: dict):
        body = api_runtime.config_service.prepare_submitted_config(body)
        result = turn_lighting_off(body)
        if result.status.value == "failed":
            _fail("turn off", result.detail)
        return {"status": result.status.value, "detail": result.detail}

    return router
