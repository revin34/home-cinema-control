from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from home_cinema_control.config.manager import (
    active_media_server_config,
    active_media_server_type,
)


VERIFICATION_CONFIG_KEY = "setup_verification"


def section_fingerprint(section: str, config: dict[str, Any]) -> str:
    payload = _section_payload(section, config)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def mark_section_verified(config: dict[str, Any], section: str) -> dict[str, Any]:
    updated = {**config}
    verification = dict(updated.get(VERIFICATION_CONFIG_KEY) or {})
    verification[section] = {
        "status": "ok",
        "fingerprint": section_fingerprint(section, updated),
        "verified_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    updated[VERIFICATION_CONFIG_KEY] = verification
    return updated


def maybe_mark_section_verified(
    saved_config: dict[str, Any],
    submitted_config: dict[str, Any],
    section: str,
) -> tuple[dict[str, Any], bool]:
    if section_fingerprint(section, saved_config) != section_fingerprint(section, submitted_config):
        return saved_config, False

    return mark_section_verified(saved_config, section), True


def verified_status(config: dict[str, Any], section: str) -> str:
    record = (config.get(VERIFICATION_CONFIG_KEY) or {}).get(section) or {}
    if record.get("status") != "ok":
        return "configured"
    if record.get("fingerprint") == section_fingerprint(section, config):
        return "verified"
    return "stale"


def _section_payload(section: str, config: dict[str, Any]) -> dict[str, Any]:
    if section == "media_server":
        media_server = active_media_server_config(config)
        return {
            "type": active_media_server_type(config),
            "server_url": media_server.server_url,
            "display_name": media_server.display_name,
            "access_token_configured": bool(
                media_server.model_extra.get("access_token_configured")
                or media_server.access_token.strip()
            ),
            "hcc_controlled_device": media_server.playback.hcc_controlled_device,
        }

    if section == "media_player":
        oppo = config.get("oppo") or {}
        return {
            "ip": oppo.get("ip", ""),
            "connection_timeout_seconds": oppo.get("connection_timeout_seconds"),
            "playback_start_timeout_seconds": oppo.get("playback_start_timeout_seconds"),
            "nfs_mount_timeout_seconds": oppo.get("nfs_mount_timeout_seconds"),
        }

    if section == "tv":
        tv = config.get("tv") or {}
        return {
            "enabled": bool(tv.get("enabled", False)),
            "model": tv.get("model", ""),
            "ip": tv.get("ip", ""),
            "startup_script": tv.get("startup_script", ""),
            "shutdown_script": tv.get("shutdown_script", ""),
        }

    if section == "av":
        av = config.get("av") or {}
        return {
            "enabled": bool(av.get("enabled", False)),
            "model": av.get("model", ""),
            "ip": av.get("ip", ""),
            "power_on_command": av.get("power_on_command", ""),
            "hdmi_input_command": av.get("hdmi_input_command", ""),
            "power_off_command": av.get("power_off_command", ""),
        }

    if section == "home_assistant":
        return {"url": (config.get("home_assistant") or {}).get("url", "")}

    return {section: config.get(section)}
