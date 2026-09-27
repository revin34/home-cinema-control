"""Home Assistant adapter for room lighting.

Owns the Home Assistant REST transport: bearer-token auth, the
/api/services/homeassistant/<service> call, and the /api/states mapping to
HCC's LightingEntity. Nothing outside this module sees Home Assistant's wire
format.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from home_cinema_control.config.models import LightingConfig
from home_cinema_control.network.http import get_http_session
from home_cinema_control.playback.startup.models import DeviceCommandResult

logger = logging.getLogger(__name__)

LIGHTING_ACTION_TURN_ON = "turn_on"
LIGHTING_ACTION_TURN_OFF = "turn_off"
LIGHTING_ACTION_NONE = "none"
LIGHTING_ACTIONS = (
    LIGHTING_ACTION_TURN_OFF,
    LIGHTING_ACTION_TURN_ON,
    LIGHTING_ACTION_NONE,
)

# Domains whose entities make sense as room lighting. A LED strip is often
# exposed as a switch rather than a light, so both are offered.
LIGHTING_ENTITY_DOMAINS = ("light", "switch")


@dataclass(frozen=True)
class LightingEntity:
    entity_id: str
    name: str
    state: str


class HomeAssistantLightingController:
    """Turns the configured Home Assistant entities on/off around playback."""

    def __init__(self, config: dict, *, http_session=None) -> None:
        raw = dict((config or {}).get("lighting") or {})
        self._token = str(raw.get("home_assistant_token") or "").strip()
        self._config = LightingConfig.model_validate(raw)
        self._base_url = self._config.home_assistant_url.strip().rstrip("/")
        self._entity_ids = [
            entity_id.strip()
            for entity_id in self._config.entity_ids
            if str(entity_id or "").strip()
        ]
        self._http = http_session or get_http_session("home_assistant")

    # --- RoomLightingOutputPort ---

    def prepare_for_playback(self) -> DeviceCommandResult:
        return self._apply_action(self._config.on_playback_start, "playback start")

    def restore_after_playback(self) -> DeviceCommandResult:
        return self._apply_action(self._config.on_playback_stop, "playback stop")

    # --- setup actions ---

    def turn_on(self) -> DeviceCommandResult:
        return self._call_service(LIGHTING_ACTION_TURN_ON)

    def turn_off(self) -> DeviceCommandResult:
        return self._call_service(LIGHTING_ACTION_TURN_OFF)

    def test_connection(self) -> DeviceCommandResult:
        missing = self._missing_connection_settings()
        if missing:
            return DeviceCommandResult.failed(missing)

        try:
            response = self._http.get(
                f"{self._base_url}/api/",
                headers=self._headers(),
                timeout=self._config.timeout_seconds,
                suppress_exception_log=True,
            )
        except requests.RequestException as exc:
            return DeviceCommandResult.failed(
                f"Home Assistant unreachable: {type(exc).__name__}"
            )

        if response.status_code == 401:
            return DeviceCommandResult.failed("Home Assistant rejected the access token.")
        if response.status_code >= 400:
            return DeviceCommandResult.failed(
                f"Home Assistant returned HTTP {response.status_code}."
            )
        return DeviceCommandResult.success("Home Assistant API reachable.")

    def list_entities(self) -> list[LightingEntity]:
        """Return light/switch entities; raises on connection or auth failure."""
        missing = self._missing_connection_settings()
        if missing:
            raise ValueError(missing)

        response = self._http.get(
            f"{self._base_url}/api/states",
            headers=self._headers(),
            timeout=self._config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise ValueError(f"Home Assistant returned HTTP {response.status_code}.")

        entities = [
            _map_state(item)
            for item in response.json() or []
            if _entity_domain(item.get("entity_id", "")) in LIGHTING_ENTITY_DOMAINS
        ]
        return sorted(entities, key=lambda entity: (entity.name.lower(), entity.entity_id))

    # --- internals ---

    def _apply_action(self, action: str, phase: str) -> DeviceCommandResult:
        if action == LIGHTING_ACTION_NONE:
            return DeviceCommandResult.skipped(f"No lighting action configured for {phase}.")
        if action not in (LIGHTING_ACTION_TURN_ON, LIGHTING_ACTION_TURN_OFF):
            return DeviceCommandResult.failed(
                f"Unsupported lighting action for {phase}: {action}"
            )

        logger.info(
            "Applying room lighting for %s | action=%s | entities=%s",
            phase,
            action,
            ",".join(self._entity_ids),
        )
        return self._call_service(action)

    def _call_service(self, service: str) -> DeviceCommandResult:
        missing = self._missing_connection_settings()
        if missing:
            return DeviceCommandResult.failed(missing)
        if not self._entity_ids:
            return DeviceCommandResult.skipped("No lighting entities configured.")

        try:
            response = self._http.post(
                f"{self._base_url}/api/services/homeassistant/{service}",
                headers=self._headers(),
                json={"entity_id": self._entity_ids},
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as exc:
            return DeviceCommandResult.failed(
                f"Home Assistant {service} failed: {type(exc).__name__}"
            )

        if response.status_code >= 400:
            return DeviceCommandResult.failed(
                f"Home Assistant {service} returned HTTP {response.status_code}."
            )
        return DeviceCommandResult.success(
            f"Home Assistant {service} applied to {len(self._entity_ids)} entities."
        )

    def _missing_connection_settings(self) -> str | None:
        if not self._base_url:
            return "Home Assistant URL not configured."
        if not self._token:
            return "Home Assistant access token not configured."
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }


def _entity_domain(entity_id: str) -> str:
    return str(entity_id).split(".", 1)[0]


def _map_state(item: dict) -> LightingEntity:
    entity_id = str(item.get("entity_id", ""))
    attributes = item.get("attributes") or {}
    return LightingEntity(
        entity_id=entity_id,
        name=str(attributes.get("friendly_name") or entity_id),
        state=str(item.get("state", "")),
    )
