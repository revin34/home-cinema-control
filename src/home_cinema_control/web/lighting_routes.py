from fastapi import APIRouter, HTTPException

from home_cinema_control.devices.lighting.setup_control import (
    turn_lighting_off,
    turn_lighting_on,
)
from home_cinema_control.playback.diagnostics import diagnose_device_action_failed
from home_cinema_control.web.api_runtime import WebApiRuntime


def build_lighting_router(api_runtime: WebApiRuntime) -> APIRouter:
    router = APIRouter(prefix="/api/v1/lighting")

    def _fail(action: str, detail: str | None):
        api_runtime.runtime.set_last_diagnostic(diagnose_device_action_failed(
            component="lighting", action=action, detail=str(detail or "")
        ))
        raise HTTPException(status_code=400, detail=detail or f"Lighting {action} failed")

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
