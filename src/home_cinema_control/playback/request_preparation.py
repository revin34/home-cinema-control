from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from home_cinema_control.config.manager import (
    active_media_server_config,
    active_media_server_type,
)
from home_cinema_control.media_servers.common.playback_source import (
    MediaServerPlaybackSource,
)
from home_cinema_control.playback.intent import PlaybackIntent
from home_cinema_control.playback.media_location import (
    matching_path_mappings,
    resolve_player_media_file_location,
)
from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.startup.completion import PlayMediaItemRequest
from home_cinema_control.playback.startup.models import (
    MediaPlayerStartRequest,
    MediaSourcePowerRequest,
    PlaybackOutputSwitchRequest,
    PlayerMediaFileLocation,
)

PLAYBACK_START_POLL_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class PreparedPlaybackRequests:
    """All orchestrator request objects derived from one media-server intent.

    The application service receives a provider-mapped item plus config data.
    This value object groups the clean requests consumed by playback
    orchestrators plus the resolved media location used for user-facing
    logs/messages.
    """

    media_location: PlayerMediaFileLocation
    movie_path: str
    output_switch_request: PlaybackOutputSwitchRequest
    media_player_start_request: MediaPlayerStartRequest
    startup_completion_request: PlayMediaItemRequest
    media_source_power_request: MediaSourcePowerRequest | None = None


def prepare_playback_requests(
    *,
    config: dict[str, Any],
    intent: PlaybackIntent,
        item_info: MediaServerPlaybackSource,
    previous_tv_app_id_override: str | None,
) -> PreparedPlaybackRequests:
    """Translate config, selected media item, and playback intent into requests."""
    path_mappings = [
        mapping.model_dump()
        for mapping in active_media_server_config(config).playback.path_mappings
    ]
    media_location = resolve_player_media_file_location(
        emby_media_path=item_info.path,
        playback_file_format=item_info.container,
        path_mappings=path_mappings,
    )
    output_switch_request = _output_switch_request(
        config,
        previous_tv_app_id_override=previous_tv_app_id_override,
    )
    media_player_start_request = _media_player_start_request(
        config,
        media_location=media_location,
    )
    startup_completion_request = PlayMediaItemRequest(
        start_position_seconds=intent.start_position_seconds,
        expected_duration_seconds=item_info.duration_seconds,
        source_user_id=intent.source_user_id,
        media_item_id=intent.media_item_id,
        selected_source_audio_track_id=intent.selected_audio_track_id,
        selected_source_subtitle_track_id=intent.selected_subtitle_track_id,
    )

    return PreparedPlaybackRequests(
        media_location=media_location,
        movie_path=item_info.path,
        output_switch_request=output_switch_request,
        media_player_start_request=media_player_start_request,
        startup_completion_request=startup_completion_request,
        media_source_power_request=media_source_power_request(
            media_path=item_info.path,
            path_mappings=path_mappings,
            media_location=media_location,
        ),
    )


def media_source_power_request(
    *,
    media_path: str,
    path_mappings: list[dict[str, Any]],
    media_location: PlayerMediaFileLocation,
) -> MediaSourcePowerRequest | None:
    """The power switches of the mappings serving media_path, if any."""
    switch_entity_ids = tuple(dict.fromkeys(
        str(mapping.get("power_switch_entity_id") or "").strip()
        for mapping in matching_path_mappings(media_path, path_mappings)
        if str(mapping.get("power_switch_entity_id") or "").strip()
    ))
    if not switch_entity_ids:
        return None
    return MediaSourcePowerRequest(
        switch_entity_ids=switch_entity_ids,
        server=media_location.content_server,
        network_protocol=media_location.network_protocol,
    )


def _output_switch_request(
    config: dict[str, Any],
    *,
    previous_tv_app_id_override: str | None,
) -> PlaybackOutputSwitchRequest:
    tv = config.get("tv") or {}
    av = config.get("av") or {}

    return PlaybackOutputSwitchRequest(
        tv_input=_resolve_tv_input_target(tv),
        av_input_id=av.get("player_hdmi_input"),
        tv_enabled=tv.get("enabled") is True,
        av_enabled=av.get("enabled") is True,
        previous_tv_app_id_override=previous_tv_app_id_override,
        active_media_server_provider_type=_active_provider_type_for_tv_restore(config),
    )


def _active_provider_type_for_tv_restore(config: dict[str, Any]) -> str | None:
    if not active_media_server_config(config).server_url:
        return None
    return str(active_media_server_type(config))


def _resolve_tv_input_target(tv: dict) -> TvInputTarget:
    try:
        source_index = int(tv.get("player_hdmi_input_id", 0))
    except (ValueError, TypeError):
        return TvInputTarget(input_id="")

    sources = tv.get("available_hdmi_inputs") or []

    if not sources or not (0 <= source_index < len(sources)):
        return TvInputTarget(input_id="")

    selected = sources[source_index]
    return TvInputTarget(
        input_id=selected.get("id", ""),
        confirmation_app_id=selected.get("appId") or None,
    )


def _media_player_start_request(
    config: dict[str, Any],
    *,
    media_location: PlayerMediaFileLocation,
) -> MediaPlayerStartRequest:
    oppo = config["oppo"]

    return MediaPlayerStartRequest(
        media_location=media_location,
        network_protocol=media_location.network_protocol,
        assume_player_already_on=oppo["always_on"] is True,
        startup_timeout_seconds=oppo["playback_start_timeout_seconds"],
        poll_interval_seconds=PLAYBACK_START_POLL_INTERVAL_SECONDS,
    )
