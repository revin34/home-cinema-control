import logging

from fastapi import APIRouter, HTTPException

from home_cinema_control.devices.home_assistant.client import HomeAssistantError
from home_cinema_control.devices.home_assistant.setup_control import (
    list_home_assistant_entities,
    test_home_assistant_connection,
)
from home_cinema_control.playback.diagnostics import diagnose_device_action_failed
from home_cinema_control.web.api_runtime import WebApiRuntime
from home_cinema_control.web.setup_verification import mark_section_verified

# Entity domains the UI may ask for: lights for room lighting, switches and
# input_booleans for media-source power. Anything else is rejected so the
# endpoint cannot be used to enumerate a whole Home Assistant install.
ALLOWED_ENTITY_DOMAINS = {"light", "switch", "input_boolean"}


def build_home_assistant_router(api_runtime: WebApiRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/home-assistant")

    def _fail(action: str, detail: str | None):
        api_runtime.runtime.set_last_diagnostic(diagnose_device_action_failed(
            component="home_assistant", action=action, detail=str(detail or "")
        ))
        raise HTTPException(status_code=400, detail=detail or f"Home Assistant {action} failed")

    @router.post("/test-connection")
    def home_assistant_test_connection(body: dict):
        body = api_runtime.config_service.prepare_submitted_config(body)
        result = test_home_assistant_connection(body)
        if not result.successful:
            _fail("connection test", result.detail)

        logging.info(
            "Home Assistant test connection succeeded | url=%s",
            (body.get("home_assistant") or {}).get("url", ""),
        )
        # A successful test proves the submitted URL and token work, so
        # persist them (the token lands in secrets.json).
        verified_config = mark_section_verified(body, "home_assistant")
        api_runtime.config_service.save_config(verified_config)
        return {
            "status": "ok",
            "verification_persisted": True,
            "home_assistant": api_runtime.config_service.sanitize(verified_config).get(
                "home_assistant", {}
            ),
        }

    @router.post("/entities")
    def home_assistant_entities(body: dict, domains: str = "light,switch"):
        requested = {domain.strip() for domain in domains.split(",") if domain.strip()}
        if not requested or not requested <= ALLOWED_ENTITY_DOMAINS:
            raise HTTPException(status_code=400, detail="Unsupported entity domains")

        body = api_runtime.config_service.prepare_submitted_config(body)
        try:
            return {"entities": list_home_assistant_entities(body, sorted(requested))}
        except HomeAssistantError as exc:
            _fail("detect entities", str(exc))

    return router
