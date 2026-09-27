from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from home_cinema_control.devices.av.factory import create_av_receiver_or_none
from home_cinema_control.devices.home_assistant.media_source_power import (
    create_media_source_power_or_none,
)
from home_cinema_control.devices.oppo.playback_adapters import (
    create_oppo_playback_adapter,
)
from home_cinema_control.devices.tv.factory import create_tv_controller_or_none
from home_cinema_control.playback.ports import MediaPlayerPort
from home_cinema_control.playback.startup.orchestrator import (
    PlaybackStartupOrchestrator,
)


@dataclass(frozen=True)
class PlaybackStartupWiring:
    startup_orchestrator: PlaybackStartupOrchestrator
    media_player: MediaPlayerPort


def create_playback_startup_wiring(
    config: dict[str, Any],
        *,
        step_timer=None,
) -> PlaybackStartupWiring:
    media_player = create_oppo_playback_adapter(config, step_timer=step_timer)
    startup_orchestrator = PlaybackStartupOrchestrator(
        television=create_tv_controller_or_none(config),
        av_receiver=create_av_receiver_or_none(config),
        media_player=media_player,
        media_source_power=create_media_source_power_or_none(config),
    )
    return PlaybackStartupWiring(
        startup_orchestrator=startup_orchestrator,
        media_player=media_player,
    )
