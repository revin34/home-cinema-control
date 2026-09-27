from __future__ import annotations

import logging
import time
from typing import Any

from home_cinema_control.devices.oppo.constants import OPPO_TELNET_PORT
from home_cinema_control.devices.oppo.control_api_client import OppoControlApiClient
from home_cinema_control.devices.oppo.media_control_playback import (
    OppoMediaControlPlayback,
)
from home_cinema_control.devices.oppo.playback_status_client import (
    OppoPlaybackStatusClient,
)
from home_cinema_control.devices.oppo.remote_control import send_stop_playback
from home_cinema_control.devices.oppo.telnet_shell import unmount_oppo_path
from home_cinema_control.playback.player_state import (
    PlayerPlaybackPosition,
    PlayerPlaybackStartResult,
    PlayerPlaybackState,
)
from home_cinema_control.playback.ports import MediaPlayerPort
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    MediaPlayerStartRequest,
)

logger = logging.getLogger(__name__)

# Time for the OPPO to leave its screensaver before the mount request.
WAKE_DISPLAY_SETTLE_SECONDS = 1.0


def create_oppo_playback_adapter(
    config: dict[str, Any], *, step_timer=None
) -> MediaPlayerPort:
    logger.info("Creating OPPO media player adapter.")
    return OppoMediaPlayerAdapter(config, step_timer=step_timer)


class OppoMediaPlayerAdapter(MediaPlayerPort):
    """OPPO media player adapter backed by MediaControl HTTP + QPL."""

    def __init__(self, config: dict[str, Any], *, step_timer=None) -> None:
        self._config = config
        self._playback = OppoMediaControlPlayback(config, step_timer=step_timer)
        self._last_mounted_path: str | None = None

    def start(
        self,
        request: MediaPlayerStartRequest,
        *,
        on_waiting=None,
    ) -> PlayerPlaybackStartResult:
        result = self._playback.start_playback(request, on_waiting=on_waiting)
        self._last_mounted_path = result.mounted_path
        return result

    def get_playback_state(self) -> PlayerPlaybackState:
        result = self._playback_status_client().query_playback_state()
        return PlayerPlaybackState(
            status=result.status,
            lifecycle_phase=result.lifecycle_phase,
            raw_response=result.raw_response,
            ok=result.ok,
        )

    def get_playback_position(self) -> PlayerPlaybackPosition:
        return self._playback.get_playback_position()

    def seek_to(self, position_ticks: int) -> DeviceCommandResult:
        return self._playback.seek_to(position_ticks)

    def select_audio_track(self, audio_index: int) -> DeviceCommandResult:
        return self._playback.select_audio_track(audio_index)

    def select_subtitle_track(self, subtitle_index: int) -> DeviceCommandResult:
        return self._playback.select_subtitle_track(subtitle_index)

    def stop(self) -> DeviceCommandResult:
        try:
            response = send_stop_playback(self._config)
            return DeviceCommandResult.success(f"OPPO playback stop sent: {response}")
        except Exception as exc:
            logger.exception("Unable to stop OPPO playback.")
            return DeviceCommandResult.failed(
                f"OPPO playback stop failed: {type(exc).__name__}: {exc}"
            )

    def pause(self) -> DeviceCommandResult:
        return self._send_remote_key("PAU")

    def resume(self) -> DeviceCommandResult:
        return self._send_remote_key("PLA")

    def toggle_play_pause(self) -> DeviceCommandResult:
        return self._send_remote_key("PAU")

    def wake_display(self) -> DeviceCommandResult:
        # RET (Return) is the one key verified to dismiss the OPPO screensaver;
        # query commands (QPW) and NOP do not. On the idle home screen it does
        # nothing, inside a menu it goes back one level.
        result = self._send_remote_key("RET")
        if result.successful:
            time.sleep(WAKE_DISPLAY_SETTLE_SECONDS)
        return result

    def next_track(self) -> DeviceCommandResult:
        return self._send_remote_key("NXT")

    def previous_track(self) -> DeviceCommandResult:
        return self._send_remote_key("PRE")

    def _send_remote_key(self, key: str) -> DeviceCommandResult:
        try:
            response = OppoControlApiClient.from_config(self._config).send_remote_key(
                key
            )
            return DeviceCommandResult.success(f"OPPO remote key sent: {response}")
        except Exception as exc:
            return DeviceCommandResult.failed(
                f"OPPO remote key failed: {type(exc).__name__}: {exc}"
            )

    def seek_to_position_ticks(self, position_ticks: int) -> DeviceCommandResult:
        return self.seek_to(position_ticks)

    def current_position_ticks(self) -> int:
        from home_cinema_control.playback.time_units import seconds_to_ticks

        return seconds_to_ticks(self.get_playback_position().current_seconds)

    def cleanup_after_playback_finish(self) -> DeviceCommandResult:
        oppo = self._config["oppo"]

        if not oppo.get("autoscript", False):
            return DeviceCommandResult.skipped(
                "Autoscript is disabled; no unmount needed after playback finish."
            )

        mount_path = self._last_mounted_path
        if not mount_path:
            return DeviceCommandResult.skipped(
                "No mounted share recorded for this playback session."
            )

        if not mount_path.startswith("/mnt/cifs"):
            return DeviceCommandResult.skipped(
                "Autoscript unmount only applies to CIFS/SMB mounts; leaving "
                f"{mount_path} in place."
            )

        try:
            # unmount_oppo_path catches its own connection/telnet errors and
            # reports them as a `False` return rather than raising; only an
            # unexpected mount_path shape raises (defends against unmounting
            # something other than what we just mounted).
            unmounted = unmount_oppo_path(
                host=oppo["ip"],
                port=int(self._config.get("OPPO_Port", OPPO_TELNET_PORT)),
                mount_path=mount_path,
                timeout=oppo.get("autoscript_unmount_timeout_seconds", 3),
            )
        except Exception as exc:
            logger.exception("Unable to unmount OPPO share after playback finish.")
            return DeviceCommandResult.failed(
                f"OPPO autoscript unmount failed: {type(exc).__name__}: {exc}"
            )

        if not unmounted:
            logger.warning(
                "OPPO autoscript shell not available; skipping unmount | mount_path=%s",
                mount_path,
            )
            return DeviceCommandResult.skipped(
                f"OPPO autoscript shell not available; unmount of {mount_path} skipped."
            )

        logger.info(
            "Unmounted OPPO share after playback finish (autoscript) | "
            "mount_path=%s",
            mount_path,
        )
        return DeviceCommandResult.success(
            f"Unmounted {mount_path} after playback finish (autoscript)."
        )

    def _playback_status_client(self) -> OppoPlaybackStatusClient:
        oppo = self._config["oppo"]
        return OppoPlaybackStatusClient(
            host=oppo["ip"],
            port=int(self._config.get("OPPO_Port", OPPO_TELNET_PORT)),
            timeout=float(oppo.get("connection_timeout_seconds", 3)),
        )
