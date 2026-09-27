"""Room lighting through Home Assistant.

Turns the configured light/switch entities on or off around playback, with
the light `transition` used for fades. Transport lives in
devices/home_assistant/client.py.
"""

from __future__ import annotations

import logging

from home_cinema_control.config.models import LightingConfig
from home_cinema_control.devices.home_assistant.client import (
    HomeAssistantClient,
    entity_domain,
)
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


class HomeAssistantLightingController:
    """Turns the configured Home Assistant entities on/off around playback."""

    def __init__(self, config: dict, *, client: HomeAssistantClient | None = None) -> None:
        self._config = LightingConfig.model_validate(dict((config or {}).get("lighting") or {}))
        self._entity_ids = [
            entity_id.strip()
            for entity_id in self._config.entity_ids
            if str(entity_id or "").strip()
        ]
        self._client = client or HomeAssistantClient(config)

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

    # --- internals ---

    def _apply_action(self, action: str, phase: str) -> DeviceCommandResult:
        if action == LIGHTING_ACTION_NONE:
            return DeviceCommandResult.skipped(f"No lighting action configured for {phase}.")
        if action not in (LIGHTING_ACTION_TURN_ON, LIGHTING_ACTION_TURN_OFF):
            return DeviceCommandResult.failed(
                f"Unsupported lighting action for {phase}: {action}"
            )

        logger.info(
            "Applying room lighting for %s | action=%s | fade=%ss | entities=%s",
            phase,
            action,
            f"{self._fade_seconds(action):g}",
            ",".join(self._entity_ids),
        )
        return self._call_service(action)

    def _call_service(self, service: str) -> DeviceCommandResult:
        missing = self._client.missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)
        if not self._entity_ids:
            return DeviceCommandResult.skipped("No lighting entities configured.")

        fade_seconds = self._fade_seconds(service)
        failures = []
        for domain, payload in self._service_calls(fade_seconds):
            result = self._client.call_service(
                domain,
                service,
                payload,
                # Some integrations only answer once the transition is done.
                extra_timeout_seconds=fade_seconds,
            )
            if not result.successful:
                failures.append(result.detail)

        if failures:
            return DeviceCommandResult.failed("; ".join(failures))
        fade_detail = f" with {fade_seconds:g}s fade" if fade_seconds else ""
        return DeviceCommandResult.success(
            f"Home Assistant {service} applied to {len(self._entity_ids)} entities"
            f"{fade_detail}."
        )

    def _fade_seconds(self, service: str) -> float:
        if service == LIGHTING_ACTION_TURN_OFF:
            return self._config.fade_out_seconds
        return self._config.fade_in_seconds

    def _service_calls(self, fade_seconds: float) -> list[tuple[str, dict]]:
        """Group entities into one Home Assistant service call per target.

        Only the light domain accepts `transition`: sending it to a switch
        makes Home Assistant reject the whole call. Lights therefore go
        through light.<service> (with the fade), everything else through the
        generic homeassistant.<service>.
        """
        lights = [e for e in self._entity_ids if entity_domain(e) == "light"]
        others = [e for e in self._entity_ids if entity_domain(e) != "light"]

        calls = []
        if lights:
            payload = {"entity_id": lights}
            if fade_seconds:
                payload["transition"] = fade_seconds
            calls.append(("light", payload))
        if others:
            calls.append(("homeassistant", {"entity_id": others}))
        return calls
