from __future__ import annotations

from home_cinema_control.config.manager import active_media_server_config
from home_cinema_control.web.setup_verification import verified_status


def compute_config_readiness(config: dict) -> dict:
    """Compute per-section setup readiness from a sanitized config dict."""
    return {
        "media_server": _media_server_readiness(config),
        "media_player": _media_player_readiness(config),
        "media_paths": _media_paths_readiness(config),
        "tv": _tv_readiness(config),
        "av": _av_readiness(config),
        "lighting": _lighting_readiness(config),
    }


def _media_server_readiness(config: dict) -> dict:
    ms = active_media_server_config(config)
    # access_token_configured is a sanitize_config_for_web display artifact:
    # on a sanitized config (the normal caller here) the real access_token is
    # already stripped, so that flag is the only surviving signal.
    if ms.model_extra.get("access_token_configured") or ms.access_token:
        return {
            "status": verified_status(config, "media_server"),
            "detail": ms.display_name or ms.server_url or "",
        }
    if ms.server_url:
        return {"status": "incomplete", "detail": "Token not configured"}
    return {"status": "incomplete", "detail": "Server URL not set"}


def _media_player_readiness(config: dict) -> dict:
    oppo = config.get("oppo") or {}
    if oppo.get("ip"):
        return {"status": verified_status(config, "media_player"), "detail": oppo["ip"]}
    return {"status": "incomplete", "detail": "OPPO IP not set"}


def _media_paths_readiness(config: dict) -> dict:
    paths = active_media_server_config(config).playback.path_mappings
    total = len(paths)
    if total == 0:
        return {"status": "incomplete", "detail": "No paths configured"}
    verified = sum(1 for p in paths if p.verified)
    if verified == total:
        return {"status": "configured", "detail": f"{verified}/{total} verified"}
    return {"status": "incomplete", "detail": f"{verified}/{total} verified"}


def _tv_readiness(config: dict) -> dict:
    tv = config.get("tv") or {}
    if not tv.get("enabled", False):
        return {"status": "disabled", "detail": "TV control disabled (optional)"}
    model = tv.get("model", "")
    if model == "LG":
        if tv.get("ip"):
            return {"status": verified_status(config, "tv"), "detail": f"{model} · {tv['ip']}"}
        return {"status": "incomplete", "detail": "IP address not set"}
    if model == "SCRIPTS":
        if tv.get("startup_script"):
            return {"status": verified_status(config, "tv"), "detail": model}
        return {"status": "incomplete", "detail": "Startup script not set"}
    if model:
        return {"status": verified_status(config, "tv"), "detail": model}
    return {"status": "incomplete", "detail": "Model not selected"}


def _av_readiness(config: dict) -> dict:
    av = config.get("av") or {}
    if not av.get("enabled", False):
        return {"status": "disabled", "detail": "AV control disabled (optional)"}
    model = av.get("model", "")
    if model == "SCRIPTS":
        if av.get("power_on_command"):
            return {"status": verified_status(config, "av"), "detail": model}
        return {"status": "incomplete", "detail": "Power on script not set"}
    if model:
        if av.get("ip"):
            return {"status": verified_status(config, "av"), "detail": f"{model} · {av['ip']}"}
        return {"status": "incomplete", "detail": "IP address not set"}
    return {"status": "incomplete", "detail": "Model not selected"}


def _lighting_readiness(config: dict) -> dict:
    lighting = config.get("lighting") or {}
    if not lighting.get("enabled", False):
        return {"status": "disabled", "detail": "Lighting control disabled (optional)"}
    if not lighting.get("home_assistant_url"):
        return {"status": "incomplete", "detail": "Home Assistant URL not set"}
    if not (
        lighting.get("home_assistant_token_configured")
        or str(lighting.get("home_assistant_token") or "").strip()
    ):
        return {"status": "incomplete", "detail": "Home Assistant token not configured"}
    entity_ids = [e for e in lighting.get("entity_ids") or [] if str(e).strip()]
    if not entity_ids:
        return {"status": "incomplete", "detail": "No lights selected"}
    return {
        "status": verified_status(config, "lighting"),
        "detail": f"Home Assistant · {len(entity_ids)} entities",
    }
