from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from home_cinema_control.devices.lighting.factory import (
    create_lighting_controller_or_none,
)
from home_cinema_control.devices.oppo.playback_command_control import (
    create_oppo_total_seconds_reader,
)
from home_cinema_control.devices.oppo.observation_mode import (
    OppoObservationMode,
    resolve_oppo_observation_mode,
)
from home_cinema_control.playback.time_units import TICKS_PER_SECOND
from home_cinema_control.playback.during import (
    DuringPlaybackOrchestrator,
    PollingPlaybackObservationStrategy,
)
from home_cinema_control.playback.error_handling import create_playback_error_handler
from home_cinema_control.playback.finish.factory import create_finish_playback_orchestrator
from home_cinema_control.playback.orchestrator import PlaybackOrchestrator
from home_cinema_control.playback.startup.completion import (
    OppoStartupCompletionPlayer,
    PlaybackTrackResolver,
    PlaybackStartupCompletionService,
    StartupStepTimer,
)
from home_cinema_control.playback.state import BridgePlaybackState
from home_cinema_control.playback.startup.factory import (
    PlaybackStartupWiring,
    create_playback_startup_wiring,
)


@dataclass(frozen=True)
class PlaybackOrchestratorWiring:
    startup_wiring: PlaybackStartupWiring
    playback_event_publisher: Any
    during_playback_orchestrator: DuringPlaybackOrchestrator
    playback_orchestrator: PlaybackOrchestrator


class PlaybackSessionStateSyncProgressReporter:
    """Keeps bridge playstate aligned with OPPO progress reports."""

    def __init__(self, *, playback_state: BridgePlaybackState, progress_reporter) -> None:
        self._state = playback_state
        self._progress_reporter = progress_reporter
        self._last_is_paused: bool | None = None

    def progress(
        self,
        *,
        position_seconds: int,
        duration_seconds: int,
        is_paused: bool = False,
        is_muted: bool = False,
        force: bool = False,
    ):
        previous_is_paused = self._last_is_paused
        self._last_is_paused = is_paused
        self._state.playstate = "Paused" if is_paused else "Playing"

        if previous_is_paused is True and not is_paused:
            self._progress_reporter.report_event(
                "Unpause",
                position_ticks=position_seconds * TICKS_PER_SECOND,
                runtime_ticks=duration_seconds * TICKS_PER_SECOND,
                is_paused=False,
                is_muted=is_muted,
            )

        return self._progress_reporter.progress(
            position_seconds=position_seconds,
            duration_seconds=duration_seconds,
            is_paused=is_paused,
            is_muted=is_muted,
            force=force,
        )


def create_playback_orchestrator_wiring(
    *,
    config: dict[str, Any],
    media_server_client,
    bridge_session_id: str,
        playback_context,
        playback_event_publisher_factory,
    track_resolver: PlaybackTrackResolver,
    playback_state: BridgePlaybackState | None = None,
    step_timer: StartupStepTimer | None = None,
) -> PlaybackOrchestratorWiring:
    startup_wiring = create_playback_startup_wiring(config, step_timer=step_timer)
    playback_event_publisher = playback_event_publisher_factory(
        media_server_client,
        bridge_session_id=bridge_session_id,
        context=playback_context,
    )
    progress_reporter = playback_event_publisher
    if playback_state is not None:
        progress_reporter = PlaybackSessionStateSyncProgressReporter(
            playback_state=playback_state,
            progress_reporter=playback_event_publisher,
        )

    during_playback_orchestrator = create_during_playback_orchestrator(
        config=config,
        media_player=startup_wiring.media_player,
        progress_reporter=progress_reporter,
    )
    finish_playback_orchestrator = create_finish_playback_orchestrator(
        config,
        playback_event_publisher,
        media_player=startup_wiring.media_player,
    )
    startup_completion_service = PlaybackStartupCompletionService(
        started_reporter=playback_event_publisher,
        player=OppoStartupCompletionPlayer(startup_wiring.startup_orchestrator),
        track_resolver=track_resolver,
        step_timer=step_timer,
    )
    playback_orchestrator = PlaybackOrchestrator(
        startup_orchestrator=startup_wiring.startup_orchestrator,
        startup_completion_service=startup_completion_service,
        during_playback_orchestrator=during_playback_orchestrator,
        finish_playback_orchestrator=finish_playback_orchestrator,
        error_handler=create_playback_error_handler(
            config,
            media_player=startup_wiring.media_player,
        ),
        room_lighting=create_lighting_controller_or_none(config),
    )

    return PlaybackOrchestratorWiring(
        startup_wiring=startup_wiring,
        playback_event_publisher=playback_event_publisher,
        during_playback_orchestrator=during_playback_orchestrator,
        playback_orchestrator=playback_orchestrator,
    )


def create_during_playback_orchestrator(
    *,
    config: dict[str, Any],
    media_player,
    progress_reporter,
) -> DuringPlaybackOrchestrator:
    polling_orchestrator = PollingPlaybackObservationStrategy(
        media_player=media_player,
        progress_reporter=progress_reporter,
    )

    if resolve_oppo_observation_mode(config) == OppoObservationMode.POLLING:
        return polling_orchestrator

    return DuringPlaybackOrchestrator(
        config=config,
        polling_orchestrator=polling_orchestrator,
        progress_reporter=progress_reporter,
        oppo_total_provider=create_oppo_total_seconds_reader(config),
    )
