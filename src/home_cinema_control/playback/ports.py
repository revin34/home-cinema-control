from typing import Protocol, Callable

from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.player_state import (
    PlayerPlaybackPosition,
    PlayerPlaybackStartResult,
    PlayerPlaybackState,
)
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    MediaPlayerStartRequest,
    MediaSourcePowerRequest,
)


class MediaPlayerCommandPort(Protocol):
    """Media-server-facing playback command port.

    Command handlers only need the interactive control subset, not the whole
    playback startup/cleanup lifecycle.
    """

    def pause(self) -> DeviceCommandResult: ...

    def resume(self) -> DeviceCommandResult: ...

    def toggle_play_pause(self) -> DeviceCommandResult: ...

    def stop(self) -> DeviceCommandResult: ...

    def next_track(self) -> DeviceCommandResult: ...

    def previous_track(self) -> DeviceCommandResult: ...

    def get_playback_state(self) -> PlayerPlaybackState: ...

    def seek_to_position_ticks(self, position_ticks: int) -> DeviceCommandResult: ...

    def current_position_ticks(self) -> int: ...

    def select_audio_track(self, audio_index: int) -> DeviceCommandResult: ...

    def select_subtitle_track(self, subtitle_index: int) -> DeviceCommandResult: ...


class MediaPlayerPort(MediaPlayerCommandPort, Protocol):
    """Hardware media player port used by playback orchestration."""

    def start(
        self,
        request: MediaPlayerStartRequest,
        *,
        on_waiting: Callable[[int], None] | None = None,
    ) -> PlayerPlaybackStartResult: ...

    def get_playback_position(self) -> PlayerPlaybackPosition: ...

    def seek_to(self, position_ticks: int) -> DeviceCommandResult: ...

    def cleanup_after_playback_finish(self) -> DeviceCommandResult: ...


class TelevisionOutputPort(Protocol):
    def get_current_app_id(self) -> str | None:
        """Return the current TV app id, if available."""
        ...

    def media_server_app_id(self, provider_type: str) -> str | None:
        """Return this TV brand's app id for the media-server provider."""
        ...

    def switch_to_input(self, target: TvInputTarget) -> DeviceCommandResult:
        """Switch the TV to the requested input."""
        ...

    def launch_app(self, app_id: str | None) -> DeviceCommandResult:
        """Launch the requested app on the TV, or skip if app_id is None."""
        ...


class AvReceiverOutputPort(Protocol):
    def power_on(self) -> DeviceCommandResult:
        """Ensure the AV receiver is powered on."""
        ...

    def switch_to_input(self, input_id: str) -> DeviceCommandResult:
        """Switch the AV receiver to the requested input id."""
        ...

    def restore_tv_audio(self) -> DeviceCommandResult:
        """Restore the AV receiver to TV audio."""
        ...


class RoomLightingOutputPort(Protocol):
    def prepare_for_playback(self) -> DeviceCommandResult:
        """Apply the room lighting wanted while a movie is playing."""
        ...

    def restore_after_playback(self) -> DeviceCommandResult:
        """Apply the room lighting wanted once playback has ended."""
        ...


class MediaSourcePowerPort(Protocol):
    def request_power_on(self, request: MediaSourcePowerRequest) -> DeviceCommandResult:
        """Power on the media server if it is not reachable yet.

        SKIPPED means the share is already reachable (nothing to wait for);
        SUCCESS means power-on was requested; FAILED means it could not be.
        """
        ...

    def wait_until_available(self, request: MediaSourcePowerRequest) -> DeviceCommandResult:
        """Block until the media share is reachable or the wait times out."""
        ...
