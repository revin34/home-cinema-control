from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from home_cinema_control.playback.player_state import PlayerPlaybackStartResult
from home_cinema_control.devices.tv.models import TvInputTarget


class DeviceCommandStatus(Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class DeviceCommandResult:
    status: DeviceCommandStatus
    detail: str | None = None

    @property
    def successful(self) -> bool:
        return self.status == DeviceCommandStatus.SUCCESS

    @classmethod
    def success(cls, detail: str | None = None) -> "DeviceCommandResult":
        return cls(status=DeviceCommandStatus.SUCCESS, detail=detail)

    @classmethod
    def skipped(cls, detail: str | None = None) -> "DeviceCommandResult":
        return cls(status=DeviceCommandStatus.SKIPPED, detail=detail)

    @classmethod
    def failed(cls, detail: str | None = None) -> "DeviceCommandResult":
        return cls(status=DeviceCommandStatus.FAILED, detail=detail)


@dataclass(frozen=True)
class PlaybackOutputSwitchRequest:
    tv_input: TvInputTarget
    av_input_id: str | None
    tv_enabled: bool = True
    av_enabled: bool = True
    previous_tv_app_id_override: str | None = None
    active_media_server_provider_type: str | None = None


@dataclass(frozen=True)
class PlaybackOutputSwitchResult:
    previous_tv_app_id: str | None
    tv_input_result: DeviceCommandResult
    av_power_result: DeviceCommandResult
    av_input_result: DeviceCommandResult

    @property
    def successful(self) -> bool:
        return (
                self.tv_input_result.status != DeviceCommandStatus.FAILED
            and self.av_power_result.status != DeviceCommandStatus.FAILED
            and self.av_input_result.status != DeviceCommandStatus.FAILED
        )


@dataclass(frozen=True)
class PlayerMediaFileLocation:
    content_server: str
    content_directory: str
    playback_file_name: str
    playback_file_format: str
    network_protocol: str | None = None


@dataclass(frozen=True)
class MediaPlayerStartRequest:
    media_location: PlayerMediaFileLocation
    network_protocol: str | None = None
    assume_player_already_on: bool = True
    startup_timeout_seconds: int | float = 30
    poll_interval_seconds: float = 0.5


@dataclass(frozen=True)
class MediaSourcePowerRequest:
    """Wake the server behind the media path before the OPPO mounts it.

    switch_entity_ids are the power switches of every path mapping that
    matched the media path; server/network_protocol say where the share
    must become reachable.
    """

    switch_entity_ids: tuple[str, ...]
    server: str
    network_protocol: str | None = None
    # None = use media_source_power.wait_timeout_seconds.
    wait_timeout_seconds: float | None = None


@dataclass(frozen=True)
class PlaybackStartupRequest:
    output_switch_request: PlaybackOutputSwitchRequest
    media_player_start_request: MediaPlayerStartRequest
    media_source_power_request: MediaSourcePowerRequest | None = None


@dataclass(frozen=True)
class PlaybackStartupResult:
    output_switch_result: PlaybackOutputSwitchResult
    media_player_start_result: PlayerPlaybackStartResult
    media_source_power_result: DeviceCommandResult = DeviceCommandResult(
        status=DeviceCommandStatus.SKIPPED,
        detail="No media source power switch configured.",
    )

    @property
    def successful(self) -> bool:
        return (
            self.media_source_power_result.status != DeviceCommandStatus.FAILED
            and self.output_switch_result.successful
            and self.media_player_start_result.successful
        )
