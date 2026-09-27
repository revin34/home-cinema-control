from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from home_cinema_control.playback.during import (
    DuringPlaybackOrchestrator,
    PlaybackMonitoringRequest,
    PlaybackMonitoringResult,
    PlaybackMonitoringStopReason,
)
from home_cinema_control.playback.during.natural_end import was_content_played
from home_cinema_control.playback.error_handling import (
    PlaybackErrorHandler,
    PlaybackErrorRecoveryRequest,
    PlaybackErrorRecoveryResult,
)
from home_cinema_control.playback.finish import (
    FinishPlaybackOrchestrator,
    PlaybackFinishRequest,
    PlaybackFinishResult,
)
from home_cinema_control.playback.ports import RoomLightingOutputPort
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    PlaybackOutputSwitchResult,
    PlaybackStartupRequest,
    PlaybackStartupResult,
    PlayerPlaybackStartResult,
)
from home_cinema_control.playback.startup.completion import (
    PlayMediaItemRequest,
    PlaybackStartupCompletionService,
)
from home_cinema_control.playback.startup.orchestrator import PlaybackStartupOrchestrator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaybackOrchestrationRequest:
    startup_request: PlaybackStartupRequest
    startup_completion_request: PlayMediaItemRequest
    is_paused: bool = False
    is_muted: bool = False
    restore_outputs_on_finish: bool | Callable[[], bool] = True
    finish_idle_confirmation_polls: int | Callable[[], int] = 5
    on_startup_waiting: Callable[[int], None] | None = None
    on_media_source_powering_on: Callable[[], None] | None = None
    on_tracks_applying: Callable[[], None] | None = None
    on_startup_completed: Callable[[PlayerPlaybackStartResult], None] | None = None


@dataclass(frozen=True)
class PlaybackOrchestrationResult:
    startup_result: PlaybackStartupResult
    monitoring_result: PlaybackMonitoringResult | None = None
    finish_result: PlaybackFinishResult | None = None
    error_recovery_result: PlaybackErrorRecoveryResult | None = None

    @property
    def successful(self) -> bool:
        return (
            self.startup_result.successful
            and self.monitoring_result is not None
            and self.finish_result is not None
            and self.finish_result.successful
        )


class PlaybackOrchestrator:
    """Coordinates the normal playback lifecycle between phase orchestrators."""

    def __init__(
        self,
        *,
        startup_orchestrator: PlaybackStartupOrchestrator,
        startup_completion_service: PlaybackStartupCompletionService,
        during_playback_orchestrator: DuringPlaybackOrchestrator,
        finish_playback_orchestrator: FinishPlaybackOrchestrator,
        error_handler: PlaybackErrorHandler,
        room_lighting: RoomLightingOutputPort | None = None,
    ) -> None:
        self._startup_orchestrator = startup_orchestrator
        self._startup_completion_service = startup_completion_service
        self._during_playback_orchestrator = during_playback_orchestrator
        self._finish_playback_orchestrator = finish_playback_orchestrator
        self._error_handler = error_handler
        self._room_lighting = room_lighting

    def play_until_stopped(
        self,
        request: PlaybackOrchestrationRequest,
    ) -> PlaybackOrchestrationResult:
        startup_result = self._startup_orchestrator.start_playback(
            request=request.startup_request,
            on_waiting=request.on_startup_waiting,
            on_media_source_powering_on=request.on_media_source_powering_on,
        )
        self._log_startup_result(startup_result)

        if not startup_result.successful:
            recovery_result = self._recover(
                "oppo_startup_failed",
                request,
                startup_result.output_switch_result,
            )
            return PlaybackOrchestrationResult(
                startup_result=startup_result,
                error_recovery_result=recovery_result,
            )

        # Lights only change once the OPPO has confirmed playback, so a failed
        # mount/startup never leaves the room dark. Every exit after this point
        # restores them, except a normal finish that deliberately keeps the
        # room outputs as they are (restore_outputs_on_finish=False).
        room_lighting = _RoomLightingSequence(self._room_lighting)
        room_lighting.prepare_for_playback()
        restore_room_lighting = True
        try:
            result = self._play_after_startup(request, startup_result)
            if result.error_recovery_result is None:
                restore_room_lighting = _resolve_restore_outputs_on_finish(request)
            return result
        finally:
            room_lighting.finish(restore=restore_room_lighting)

    def _play_after_startup(
        self,
        request: PlaybackOrchestrationRequest,
        startup_result: PlaybackStartupResult,
    ) -> PlaybackOrchestrationResult:
        try:
            if request.on_tracks_applying is not None:
                request.on_tracks_applying()

            startup_completion_result = self._startup_completion_service.complete(
                request.startup_completion_request
            )
            if request.on_startup_completed is not None:
                request.on_startup_completed(startup_result.media_player_start_result)

            self._wire_deferred_audio_if_needed(startup_completion_result)

            monitoring_request = PlaybackMonitoringRequest(
                initial_position_seconds=(
                    startup_completion_result.start_position_seconds
                ),
                expected_duration_seconds=(
                    startup_completion_result.expected_duration_seconds
                ),
                is_paused=request.is_paused,
                is_muted=request.is_muted,
            )
            monitoring_result = self._during_playback_orchestrator.monitor_until_stopped(
                monitoring_request
            )
        except Exception:
            logger.exception("Playback during phase failed.")
            recovery_result = self._recover(
                "playback_during_failed",
                request,
                startup_result.output_switch_result,
            )
            return PlaybackOrchestrationResult(
                startup_result=startup_result,
                error_recovery_result=recovery_result,
            )

        logger.info(
            "Playback orchestration completed | final_state=%s | lifecycle_phase=%s | "
            "position_seconds=%s | duration_seconds=%s",
            monitoring_result.final_state.status.value,
            monitoring_result.final_state.lifecycle_phase.value,
            monitoring_result.position_seconds,
            monitoring_result.duration_seconds,
        )

        try:
            restore_outputs_on_finish = _resolve_restore_outputs_on_finish(request)
            finish_idle_confirmation_polls = (
                _resolve_finish_idle_confirmation_polls(request)
            )
            finish_result = self._finish_playback_orchestrator.finish(
                PlaybackFinishRequest(
                    position_seconds=monitoring_result.position_seconds,
                    duration_seconds=monitoring_result.duration_seconds,
                    final_player_state=monitoring_result.final_state,
                    previous_tv_app_id=(
                        startup_result.output_switch_result.previous_tv_app_id
                    ),
                    media_ended=(
                        monitoring_result.stop_reason
                        == PlaybackMonitoringStopReason.NATURAL_END
                    ),
                    played=was_content_played(
                        current_seconds=monitoring_result.position_seconds,
                        total_seconds=monitoring_result.duration_seconds,
                        minimum_total_seconds=(
                            monitoring_request.natural_end_minimum_total_seconds
                        ),
                    ),
                    tv_enabled=(
                        restore_outputs_on_finish
                        and request.startup_request.output_switch_request.tv_enabled
                    ),
                    av_enabled=(
                        restore_outputs_on_finish
                        and request.startup_request.output_switch_request.av_enabled
                    ),
                    max_idle_confirmation_polls=finish_idle_confirmation_polls,
                    is_paused=request.is_paused,
                    is_muted=request.is_muted,
                )
            )
        except Exception:
            logger.exception("Playback finish phase failed.")
            recovery_result = self._recover(
                "playback_finish_failed",
                request,
                startup_result.output_switch_result,
            )
            return PlaybackOrchestrationResult(
                startup_result=startup_result,
                monitoring_result=monitoring_result,
                error_recovery_result=recovery_result,
            )
        # OPPO_FINISH_IDLE_FAILED / TV_APP_RESTORE_FAILED / AV_AUDIO_RESTORE_FAILED
        # are all "warning"-severity diagnostics.
        log = logger.info if finish_result.successful else logger.warning
        log(
            "Playback finish completed | successful=%s | player_idle=%s | "
            "tv=%s | av_audio=%s | final_state=%s | lifecycle_phase=%s",
            finish_result.successful,
            finish_result.player_idle_result.status.value,
            finish_result.tv_app_result.status.value,
            finish_result.av_audio_result.status.value,
            finish_result.final_player_state.status.value,
            finish_result.final_player_state.lifecycle_phase.value,
        )
        return PlaybackOrchestrationResult(
            startup_result=startup_result,
            monitoring_result=monitoring_result,
            finish_result=finish_result,
            error_recovery_result=(
                self._recover(
                    "playback_finish_unsuccessful",
                    request,
                    startup_result.output_switch_result,
                )
                if not finish_result.successful
                else None
            ),
        )

    def _wire_deferred_audio_if_needed(self, startup_completion_result) -> None:
        pending_index = startup_completion_result.pending_audio_track_index
        if pending_index is None:
            return

        set_deferred = getattr(
            self._during_playback_orchestrator, "set_deferred_audio_selector", None
        )
        if set_deferred is None:
            logger.warning(
                "Startup audio selection failed but during orchestrator does not "
                "support deferred selection; audio track will not be applied | "
                "pending_index=%s",
                pending_index,
            )
            return

        logger.info(
            "Startup audio selection failed; scheduling deferred selection for "
            "first PLAY event | pending_index=%s",
            pending_index,
        )
        set_deferred(
            lambda: self._startup_orchestrator.select_oppo_audio_track(pending_index)
        )

    def _recover(
        self,
        reason: str,
        request: PlaybackOrchestrationRequest,
        output_switch_result: PlaybackOutputSwitchResult,
    ) -> PlaybackErrorRecoveryResult:
        return self._error_handler.recover(
            PlaybackErrorRecoveryRequest(
                reason=reason,
                previous_tv_app_id=output_switch_result.previous_tv_app_id,
                tv_enabled=request.startup_request.output_switch_request.tv_enabled,
                av_enabled=request.startup_request.output_switch_request.av_enabled,
            )
        )

    def _log_output_switch_result(
        self,
        output_switch_result: PlaybackOutputSwitchResult,
    ) -> None:
        # TV_INPUT_SWITCH_FAILED / AV_POWER_ON_FAILED / AV_INPUT_SWITCH_FAILED are
        # all "warning"-severity diagnostics (see diagnostics.py) — match that here
        # so the log level reflects what actually happened, not just INFO always.
        log = logger.info if output_switch_result.successful else logger.warning
        log(
            "Playback output switch result | successful=%s | tv=%s | "
            "av_power=%s | av_input=%s",
            output_switch_result.successful,
            output_switch_result.tv_input_result.status.value,
            output_switch_result.av_power_result.status.value,
            output_switch_result.av_input_result.status.value,
        )

    def _log_startup_result(self, startup_result: PlaybackStartupResult) -> None:
        self._log_output_switch_result(startup_result.output_switch_result)
        media_player_start_result = startup_result.media_player_start_result
        playback_state = media_player_start_result.playback_state
        # OPPO_MOUNT_FAILED / OPPO_PLAY_FAILED / OPPO_PLAYBACK_TIMEOUT are all
        # "error"-severity diagnostics — a failed OPPO startup is a real failure,
        # not routine narration.
        log = logger.info if media_player_start_result.successful else logger.error
        log(
            "OPPO playback startup result | successful=%s | media_mounted=%s | "
            "playback_command_accepted=%s | playback_started_on_device=%s | "
            "status=%s | lifecycle_phase=%s | detail=%s",
            media_player_start_result.successful,
            media_player_start_result.media_mounted,
            media_player_start_result.playback_command_accepted,
            media_player_start_result.playback_started_on_device,
            playback_state.status.value if playback_state is not None else None,
            playback_state.lifecycle_phase.value if playback_state is not None else None,
            media_player_start_result.detail,
        )


class _RoomLightingSequence:
    """Runs one playback's lighting changes off the playback thread, in order.

    A slow or unreachable Home Assistant must never delay the OPPO handoff or
    the media-server reports, so each change is queued on a single worker:
    the "restore" change always runs after the "prepare" change, however long
    the first one takes.
    """

    def __init__(self, room_lighting: RoomLightingOutputPort | None) -> None:
        self._room_lighting = room_lighting
        self._executor: ThreadPoolExecutor | None = None

    def prepare_for_playback(self) -> None:
        if self._room_lighting is None:
            return
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="room-lighting",
        )
        self._submit("prepare_for_playback", self._room_lighting.prepare_for_playback)

    def finish(self, *, restore: bool) -> None:
        if self._executor is None:
            return
        if restore:
            self._submit(
                "restore_after_playback",
                self._room_lighting.restore_after_playback,
            )
        else:
            logger.info("Keeping room lighting as is: outputs are not restored on finish.")
        self._executor.shutdown(wait=False)
        self._executor = None

    def _submit(self, step_name: str, operation: Callable[[], DeviceCommandResult]) -> None:
        future = self._executor.submit(operation)
        future.add_done_callback(
            lambda completed: _log_room_lighting_result(step_name, completed)
        )


def _log_room_lighting_result(step_name: str, future: Future) -> None:
    try:
        result = future.result()
    except Exception:
        logger.exception("Room lighting step raised | step=%s", step_name)
        return

    log = logger.warning if result.status.value == "failed" else logger.info
    log(
        "Room lighting result | step=%s | status=%s | detail=%s",
        step_name,
        result.status.value,
        result.detail,
    )


def _resolve_restore_outputs_on_finish(
    request: PlaybackOrchestrationRequest,
) -> bool:
    restore_outputs = request.restore_outputs_on_finish
    if callable(restore_outputs):
        return bool(restore_outputs())

    return bool(restore_outputs)


def _resolve_finish_idle_confirmation_polls(
    request: PlaybackOrchestrationRequest,
) -> int:
    polls = request.finish_idle_confirmation_polls
    if callable(polls):
        return max(0, int(polls()))

    return max(0, int(polls))
