"""Any TV Home Assistant can drive, through its `remote` entity.

Built for Android TV / Google TV sets (TCL, Philips, Hisense, ...) exposed by
Home Assistant's Android TV Remote integration, but it only relies on the
generic remote services:

- remote.turn_on             power on; with `activity`, launch an app or open
                             a URI such as an HDMI input's TV-input URI
- remote.send_command        a key such as KEYCODE_TV_INPUT_HDMI_1
- attributes.current_activity the app on screen, to return to it afterwards

Many Google TV sets (TCL among them) ignore the HDMI key codes but open an
input through its Android TV input framework URI, so an input command is
either a URI (contains "://", opened as an activity) or a key code.

Transport lives in devices/home_assistant/client.py.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from home_cinema_control.devices.home_assistant.client import (
    HomeAssistantClient,
    HomeAssistantError,
)
from home_cinema_control.devices.tv.base import BaseTvController
from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.startup.models import DeviceCommandResult

logger = logging.getLogger(__name__)

# Input presets. TCL passthrough URIs (HDMI 1 = HW15 verified on a TCL
# Google TV) come first; the generic Android key codes follow for sets that
# honour them. The setup screen lets the user test and edit the command.
_TCL_HDMI_URI = (
    "content://android.media.tv/passthrough/"
    "com.tcl.tvinput%2F.passthrough.HDMIInputService%2FHW{hw}"
)
HDMI_INPUTS = [
    {"id": _TCL_HDMI_URI.format(hw=14 + number), "name": f"HDMI {number} (TCL)"}
    for number in range(1, 5)
] + [
    {"id": f"KEYCODE_TV_INPUT_HDMI_{number}", "name": f"HDMI {number} (Android key)"}
    for number in range(1, 5)
]

# Android TV package names of the media-server apps HCC returns to.
_MEDIA_SERVER_APP_IDS = {
    "emby": "tv.emby.embyatv",
    "jellyfin": "org.jellyfin.androidtv",
}

_UNAVAILABLE_STATES = {"unavailable", "unknown", ""}
POWER_ON_WAIT_SECONDS = 20.0
POWER_ON_POLL_SECONDS = 1.0
# Android TV needs a moment after waking before it accepts input keys.
AFTER_POWER_ON_SETTLE_SECONDS = 2.0


class HomeAssistantTvController(BaseTvController):
    def __init__(
        self,
        config: dict,
        *,
        client: HomeAssistantClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(config)
        tv = config.get("tv") or {}
        self._remote_entity_id = str(tv.get("ha_remote_entity_id") or "").strip()
        self._input_command = str(tv.get("ha_input_command") or "").strip()
        self._client = client or HomeAssistantClient(config)
        self._sleep = sleep
        self._monotonic = monotonic

    def test_connection(self) -> DeviceCommandResult:
        missing = self._missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)
        try:
            entity = self._client.get_entity(self._remote_entity_id)
        except HomeAssistantError as exc:
            return DeviceCommandResult.failed(str(exc))

        state = str(entity.get("state", ""))
        if state in _UNAVAILABLE_STATES:
            return DeviceCommandResult.failed(
                f"{self._remote_entity_id} is {state or 'unknown'} in Home Assistant."
            )
        # The inputs are fixed key codes: offer them straight away instead of
        # making the user run a separate detection step.
        if not (self.config.get("tv") or {}).get("available_hdmi_inputs"):
            self.retrieve_hdmi_inputs()
        return DeviceCommandResult.success(f"{self._remote_entity_id} is {state}.")

    def retrieve_hdmi_inputs(self) -> DeviceCommandResult:
        self.config.setdefault("tv", {})["available_hdmi_inputs"] = [
            dict(source) for source in HDMI_INPUTS
        ]
        return DeviceCommandResult.success()

    def switch_to_input(self, target: TvInputTarget) -> DeviceCommandResult:
        missing = self._missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)
        # A command edited by hand wins over the selected preset.
        command = self._input_command or target.input_id
        if not command:
            return DeviceCommandResult.failed("No TV input selected.")

        power_result = self._power_on()
        if not power_result.successful:
            return power_result

        logger.info(
            "Switching TV through Home Assistant | entity=%s | command=%s",
            self._remote_entity_id,
            command,
        )
        if "://" in command:
            return self._client.call_service(
                "remote",
                "turn_on",
                {"entity_id": self._remote_entity_id, "activity": command},
            )
        return self._client.call_service(
            "remote",
            "send_command",
            {"entity_id": self._remote_entity_id, "command": command},
        )

    def launch_app(self, app_id: str | None) -> DeviceCommandResult:
        if app_id is None:
            return DeviceCommandResult.skipped("No app_id to launch.")
        missing = self._missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)

        logger.info(
            "Launching TV app through Home Assistant | entity=%s | app=%s",
            self._remote_entity_id,
            app_id,
        )
        return self._client.call_service(
            "remote",
            "turn_on",
            {"entity_id": self._remote_entity_id, "activity": app_id},
        )

    def get_current_app_id(self) -> str | None:
        if self._missing_settings():
            return None
        try:
            entity = self._client.get_entity(self._remote_entity_id)
        except HomeAssistantError:
            logger.warning("Could not read the current TV app from Home Assistant.")
            return None
        app_id = (entity.get("attributes") or {}).get("current_activity")
        return str(app_id) if app_id else None

    def media_server_app_id(self, provider_type: str) -> str | None:
        return _MEDIA_SERVER_APP_IDS.get(provider_type)

    def _power_on(self) -> DeviceCommandResult:
        try:
            was_on = self._client.get_state(self._remote_entity_id) == "on"
        except HomeAssistantError as exc:
            return DeviceCommandResult.failed(str(exc))
        if was_on:
            return DeviceCommandResult.success("TV already on.")

        result = self._client.call_service(
            "remote", "turn_on", {"entity_id": self._remote_entity_id}
        )
        if not result.successful:
            return result

        deadline = self._monotonic() + POWER_ON_WAIT_SECONDS
        while self._monotonic() < deadline:
            self._sleep(POWER_ON_POLL_SECONDS)
            try:
                if self._client.get_state(self._remote_entity_id) == "on":
                    self._sleep(AFTER_POWER_ON_SETTLE_SECONDS)
                    return DeviceCommandResult.success("TV powered on.")
            except HomeAssistantError:
                continue

        # Some integrations report state lazily; the key may still land.
        logger.warning(
            "TV did not report on within %.0fs; sending the input key anyway | entity=%s",
            POWER_ON_WAIT_SECONDS,
            self._remote_entity_id,
        )
        return DeviceCommandResult.success("TV power-on requested; state not confirmed.")

    def _missing_settings(self) -> str | None:
        missing = self._client.missing_settings()
        if missing:
            return missing
        if not self._remote_entity_id:
            return "Home Assistant remote entity not configured."
        return None
