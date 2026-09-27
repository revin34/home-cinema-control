from __future__ import annotations

import logging
import time
from typing import Callable

from home_cinema_control.playback.player_state import (
    PlayerPlaybackPosition,
    PlayerPlaybackStartResult,
    PlayerPlaybackState,
)
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    DeviceCommandStatus,
    MediaSourcePowerRequest,
    PlaybackOutputSwitchRequest,
    PlaybackOutputSwitchResult,
    PlaybackStartupRequest,
    PlaybackStartupResult,
    MediaPlayerStartRequest,
)
from home_cinema_control.playback.ports import (
    AvReceiverOutputPort,
    MediaPlayerPort,
    MediaSourcePowerPort,
    TelevisionOutputPort,
)

logger = logging.getLogger(__name__)


class PlaybackStartupOrchestrator:
    def __init__(
        self,
        *,
            television: TelevisionOutputPort | None,
            av_receiver: AvReceiverOutputPort | None,
        media_player: MediaPlayerPort,
        media_source_power: MediaSourcePowerPort | None = None,
    ) -> None:
        self._television = television
        self._av_receiver = av_receiver
        self._media_player = media_player
        self._media_source_power = media_source_power

    def start_playback(
        self,
        request: PlaybackStartupRequest,
        *,
        on_waiting: Callable[[int], None] | None = None,
        on_media_source_powering_on: Callable[[], None] | None = None,
    ) -> PlaybackStartupResult:
        # Ask for the NAS first so it boots while the TV and AV switch over;
        # only the OPPO mount has to wait for it.
        power_on_result = self._measure_output_switch_step(
            "request_media_source_power_on",
            lambda: self._request_media_source_power_on(request.media_source_power_request),
        )
        if power_on_result.successful and on_media_source_powering_on is not None:
            on_media_source_powering_on()

        output_switch_result = self.switch_playback_output_to_oppo(
            request.output_switch_request
        )
        logger.info(
            "Playback output switch result | successful=%s | tv=%s | "
            "av_power=%s | av_input=%s",
            output_switch_result.successful,
            output_switch_result.tv_input_result.status.value,
            output_switch_result.av_power_result.status.value,
            output_switch_result.av_input_result.status.value,
        )

        media_source_power_result = self._measure_output_switch_step(
            "wait_for_media_source",
            lambda: self._wait_for_media_source(
                request.media_source_power_request, power_on_result
            ),
        )
        log = (
            logger.error
            if media_source_power_result.status == DeviceCommandStatus.FAILED
            else logger.info
        )
        log(
            "Media source power result | status=%s | detail=%s",
            media_source_power_result.status.value,
            media_source_power_result.detail,
        )
        if media_source_power_result.status == DeviceCommandStatus.FAILED:
            return PlaybackStartupResult(
                output_switch_result=output_switch_result,
                media_player_start_result=PlayerPlaybackStartResult(
                    media_mounted=False,
                    playback_command_accepted=False,
                    playback_started_on_device=False,
                    detail=media_source_power_result.detail,
                ),
                media_source_power_result=media_source_power_result,
            )

        if power_on_result.successful:
            # The player sat idle while the NAS booted and may be in its
            # screensaver, which would keep covering the picture once
            # playback starts.
            self._wake_player_display()

        media_player_start_result = self.start_oppo_playback(
            request=request.media_player_start_request,
            on_waiting=on_waiting,
        )

        return PlaybackStartupResult(
            output_switch_result=output_switch_result,
            media_player_start_result=media_player_start_result,
            media_source_power_result=media_source_power_result,
        )

    def _wake_player_display(self) -> None:
        try:
            result = self._measure_output_switch_step(
                "wake_player_display", self._media_player.wake_display
            )
        except Exception:
            logger.exception("Could not wake the player display; continuing.")
            return
        logger.info(
            "Player display wake after media source power-on | status=%s | detail=%s",
            result.status.value,
            result.detail,
        )

    def _request_media_source_power_on(
        self,
        request: MediaSourcePowerRequest | None,
    ) -> DeviceCommandResult:
        if request is None or not request.switch_entity_ids:
            return DeviceCommandResult.skipped("No media source power switch configured.")
        if self._media_source_power is None:
            return DeviceCommandResult.skipped(
                "Home Assistant not configured; media source power switch ignored."
            )
        try:
            return self._media_source_power.request_power_on(request)
        except Exception as exc:
            logger.exception("Media source power-on request raised.")
            return DeviceCommandResult.failed(
                f"Media source power-on failed: {type(exc).__name__}: {exc}"
            )

    def _wait_for_media_source(
        self,
        request: MediaSourcePowerRequest | None,
        power_on_result: DeviceCommandResult,
    ) -> DeviceCommandResult:
        # Nothing configured, or the share was already reachable.
        if power_on_result.status == DeviceCommandStatus.SKIPPED:
            return power_on_result
        # A failed request is still waited on: Home Assistant may be down
        # while the NAS is booting (or was started by hand) anyway.
        try:
            return self._media_source_power.wait_until_available(request)
        except Exception as exc:
            logger.exception("Waiting for media source raised.")
            return DeviceCommandResult.failed(
                f"Media source wait failed: {type(exc).__name__}: {exc}"
            )

    def switch_playback_output_to_oppo(
        self,
        request: PlaybackOutputSwitchRequest,
    ) -> PlaybackOutputSwitchResult:
        previous_tv_app_id = self._previous_tv_app_id(request)
        tv_input_result = self._measure_output_switch_step(
            "switch_tv_to_oppo_input",
            lambda: self._switch_tv_to_oppo_input(request),
        )

        if tv_input_result.status == DeviceCommandStatus.FAILED:
            logger.warning(
                "Skipping AV input switch because TV input switch failed | detail=%s",
                tv_input_result.detail,
            )

            return PlaybackOutputSwitchResult(
                previous_tv_app_id=previous_tv_app_id,
                tv_input_result=tv_input_result,
                av_power_result=DeviceCommandResult.skipped("TV input switch failed."),
                av_input_result=DeviceCommandResult.skipped("TV input switch failed."),
            )

        av_power_result = self._measure_output_switch_step(
            "power_on_av_receiver",
            lambda: self._power_on_av_receiver(request),
        )
        av_input_result = self._measure_output_switch_step(
            "switch_av_receiver_to_oppo_input",
            lambda: self._switch_av_receiver_to_oppo_input(
                request,
                av_power_result,
            ),
        )

        return PlaybackOutputSwitchResult(
            previous_tv_app_id=previous_tv_app_id,
            tv_input_result=tv_input_result,
            av_power_result=av_power_result,
            av_input_result=av_input_result,
        )

    def start_oppo_playback(
        self,
        *,
        request: MediaPlayerStartRequest,
        on_waiting: Callable[[int], None] | None = None,
    ) -> PlayerPlaybackStartResult:
        return self._media_player.start(
            request,
            on_waiting=on_waiting,
        )

    def get_oppo_playback_position(self) -> PlayerPlaybackPosition:
        return self._media_player.get_playback_position()

    def get_oppo_playback_state(self) -> PlayerPlaybackState:
        return self._media_player.get_playback_state()

    def seek_oppo_to(self, position_ticks: int) -> DeviceCommandResult:
        return self._media_player.seek_to(position_ticks)

    def select_oppo_audio_track(self, audio_index: int) -> DeviceCommandResult:
        return self._media_player.select_audio_track(audio_index)

    def select_oppo_subtitle_track(self, subtitle_index: int) -> DeviceCommandResult:
        return self._media_player.select_subtitle_track(subtitle_index)

    def _get_current_tv_app_id(self) -> str | None:
        if self._television is None:
            return None
        try:
            return self._television.get_current_app_id()
        except Exception:
            logger.exception(
                "Could not read current TV app id before switching output."
            )
            return None

    def _previous_tv_app_id(self, request: PlaybackOutputSwitchRequest) -> str | None:
        if request.previous_tv_app_id_override is not None:
            logger.info(
                "Using preserved TV return app for playback output switch | app_id=%s",
                request.previous_tv_app_id_override,
            )
            return request.previous_tv_app_id_override

        if not request.tv_enabled:
            logger.info("Skipping current TV app read: TV control is disabled.")
            return None

        if self._television is None:
            logger.info("Skipping current TV app read: no TV adapter configured.")
            return None

        current_app_id = self._measure_output_switch_step(
            "read_current_tv_app",
            self._get_current_tv_app_id,
        )
        if current_app_id is not None:
            logger.info("Using exact TV return app | app_id=%s", current_app_id)
            return current_app_id

        fallback_app_id = self._fallback_tv_app_id(request)
        if fallback_app_id is None:
            logger.info(
                "No TV return app available | provider=%s",
                request.active_media_server_provider_type,
            )
            return None

        logger.info(
            "Using fallback TV return app | provider=%s | app_id=%s",
            request.active_media_server_provider_type,
            fallback_app_id,
        )
        return fallback_app_id

    def _fallback_tv_app_id(self, request: PlaybackOutputSwitchRequest) -> str | None:
        if self._television is None:
            return None

        provider_type = request.active_media_server_provider_type
        if provider_type is None:
            return None

        try:
            return self._television.media_server_app_id(provider_type)
        except Exception:
            logger.exception(
                "Could not resolve fallback TV app id for provider | provider=%s",
                provider_type,
            )
            return None

    def _measure_output_switch_step(self, step_name: str, operation: Callable):
        started_at = time.perf_counter()
        result = operation()
        logger.info(
            "Playback output switch timing | step=%s | elapsed=%.3fs",
            step_name,
            time.perf_counter() - started_at,
        )
        return result

    def _switch_tv_to_oppo_input(
        self,
        request: PlaybackOutputSwitchRequest,
    ) -> DeviceCommandResult:
        if not request.tv_enabled:
            logger.info("Skipping TV input switch: TV control is disabled.")
            return DeviceCommandResult.skipped("TV input switching is disabled.")

        if self._television is None:
            logger.info("Skipping TV input switch: no TV adapter configured.")
            return DeviceCommandResult.skipped("TV adapter not configured.")

        logger.info(
            "Switching TV to OPPO input | input_id=%s", request.tv_input.input_id
        )
        return self._television.switch_to_input(request.tv_input)

    def _power_on_av_receiver(
        self,
        request: PlaybackOutputSwitchRequest,
    ) -> DeviceCommandResult:
        if not request.av_enabled:
            logger.info("Skipping AV receiver power-on: AV control is disabled.")
            return DeviceCommandResult.skipped("AV receiver switching is disabled.")

        if self._av_receiver is None:
            return DeviceCommandResult.skipped("No AV receiver adapter configured.")

        logger.info("Ensuring AV receiver is powered on.")
        return self._av_receiver.power_on()

    def _switch_av_receiver_to_oppo_input(
        self,
        request: PlaybackOutputSwitchRequest,
        av_power_result: DeviceCommandResult,
    ) -> DeviceCommandResult:
        if not request.av_enabled:
            logger.info("Skipping AV receiver input switch: AV control is disabled.")
            return DeviceCommandResult.skipped("AV receiver switching is disabled.")

        if self._av_receiver is None:
            return DeviceCommandResult.skipped("No AV receiver adapter configured.")

        if request.av_input_id is None:
            return DeviceCommandResult.skipped("No AV receiver input configured.")

        if not av_power_result.successful:
            return DeviceCommandResult.failed(
                f"AV receiver power-on failed: {av_power_result.detail}"
            )

        logger.info(
            "Switching AV receiver to OPPO input | input_id=%s",
            request.av_input_id,
        )
        return self._av_receiver.switch_to_input(request.av_input_id)
