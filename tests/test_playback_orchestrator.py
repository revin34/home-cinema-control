import unittest

from home_cinema_control.playback.player_state import (
    PlayerPlaybackLifecyclePhase,
    PlayerPlaybackStartResult,
    PlayerPlaybackState,
    PlayerPlaybackStatus,
)
from home_cinema_control.playback.during import (
    PlaybackMonitoringResult,
    PlaybackMonitoringStopReason,
)
from home_cinema_control.playback.finish import (
    PlaybackFinishResult,
)
from home_cinema_control.playback.orchestrator import (
    PlaybackOrchestrationRequest,
    PlaybackOrchestrator,
)
from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    MediaPlayerStartRequest,
    PlaybackOutputSwitchRequest,
    PlaybackOutputSwitchResult,
    PlaybackStartupRequest,
    PlaybackStartupResult,
    PlayerMediaFileLocation,
)
from home_cinema_control.playback.startup.completion import (
    PlayMediaItemRequest,
    PlayMediaItemResponse,
)


class RecordingStartupOrchestrator:
    def __init__(self, result, output_switch_result=None):
        self.result = result
        self.output_switch_result = output_switch_result or _output_switch_result()
        self.output_switch_calls = []
        self.start_calls = []

    def start_playback(self, request, *, on_waiting=None, on_media_source_powering_on=None):
        self.output_switch_calls.append(request)
        self.start_calls.append((request.media_player_start_request, on_waiting))
        return PlaybackStartupResult(
            output_switch_result=self.output_switch_result,
            media_player_start_result=self.result,
        )


class RecordingDuringPlaybackOrchestrator:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def monitor_until_stopped(self, request):
        self.requests.append(request)
        return self.result


class RecordingStartupCompletionService:
    def __init__(self, result=None):
        self.result = result or PlayMediaItemResponse(
            start_position_seconds=42,
            started_reported=True,
            seek_result=DeviceCommandResult.success(),
            audio_result=DeviceCommandResult.success(),
            subtitle_result=DeviceCommandResult.success(),
        )
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return self.result


class RecordingErrorHandler:
    def __init__(self):
        self.requests = []

    def recover(self, request):
        self.requests.append(request)
        return _recovery_result()


class RecordingFinishPlaybackOrchestrator:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def finish(self, request):
        self.requests.append(request)
        return self.result


class PlaybackOrchestratorTest(unittest.TestCase):
    def test_success_runs_startup_during_and_finish(self):
        startup_result = _startup_result(successful=True)
        monitoring_result = _monitoring_result()
        startup = RecordingStartupOrchestrator(startup_result)
        startup_completion = RecordingStartupCompletionService()
        during = RecordingDuringPlaybackOrchestrator(monitoring_result)
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        error_handler = RecordingErrorHandler()
        completed_startups = []
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=startup_completion,
            during_playback_orchestrator=during,
            finish_playback_orchestrator=finish,
            error_handler=error_handler,
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                on_startup_completed=completed_startups.append,
            )
        )

        self.assertTrue(result.successful)
        self.assertEqual([_startup_request()], startup.output_switch_calls)
        self.assertEqual(_output_switch_result(), result.startup_result.output_switch_result)
        self.assertEqual([_startup_completion_request()], startup_completion.requests)
        self.assertEqual(startup_result, completed_startups[0])
        self.assertEqual(1, len(during.requests))
        self.assertEqual(42, during.requests[0].initial_position_seconds)
        self.assertEqual(1, len(finish.requests))
        self.assertEqual(1, finish.requests[0].position_seconds)
        self.assertTrue(finish.requests[0].tv_enabled)
        self.assertTrue(finish.requests[0].av_enabled)
        self.assertFalse(finish.requests[0].media_ended)
        self.assertEqual(5, finish.requests[0].max_idle_confirmation_polls)
        self.assertEqual([], error_handler.requests)

    def test_passes_natural_media_end_to_finish_phase(self):
        startup_result = _startup_result(successful=True)
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(startup_result),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result(
                    position_seconds=10,
                    duration_seconds=10,
                    stop_reason=PlaybackMonitoringStopReason.NATURAL_END,
                )
            ),
            finish_playback_orchestrator=finish,
            error_handler=RecordingErrorHandler(),
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
            )
        )

        self.assertTrue(result.successful)
        self.assertTrue(finish.requests[0].media_ended)

    def test_can_skip_output_restore_on_finish_for_replacement(self):
        startup_result = _startup_result(successful=True)
        startup = RecordingStartupOrchestrator(startup_result)
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=finish,
            error_handler=RecordingErrorHandler(),
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                restore_outputs_on_finish=False,
            )
        )

        self.assertTrue(result.successful)
        self.assertFalse(finish.requests[0].tv_enabled)
        self.assertFalse(finish.requests[0].av_enabled)

    def test_can_use_longer_idle_confirmation_for_replacement_finish(self):
        startup_result = _startup_result(successful=True)
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(startup_result),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=finish,
            error_handler=RecordingErrorHandler(),
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                finish_idle_confirmation_polls=lambda: 60,
            )
        )

        self.assertTrue(result.successful)
        self.assertEqual(60, finish.requests[0].max_idle_confirmation_polls)

    def test_output_restore_on_finish_can_be_resolved_late(self):
        startup_result = _startup_result(successful=True)
        startup = RecordingStartupOrchestrator(startup_result)
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        restore_outputs = False
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=finish,
            error_handler=RecordingErrorHandler(),
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                restore_outputs_on_finish=lambda: restore_outputs,
            )
        )

        self.assertTrue(result.successful)
        self.assertFalse(finish.requests[0].tv_enabled)
        self.assertFalse(finish.requests[0].av_enabled)

    def test_tracks_applying_hook_fires_before_startup_completed(self):
        startup_result = _startup_result(successful=True)
        calls = []
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(startup_result),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(
                _finish_result()
            ),
            error_handler=RecordingErrorHandler(),
        )

        orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                on_tracks_applying=lambda: calls.append("tracks_applying"),
                on_startup_completed=lambda r: calls.append("startup_completed"),
            )
        )

        self.assertEqual(["tracks_applying", "startup_completed"], calls)

    def test_tracks_applying_hook_is_optional(self):
        startup_result = _startup_result(successful=True)
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(startup_result),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(
                _finish_result()
            ),
            error_handler=RecordingErrorHandler(),
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
            )
        )

        self.assertTrue(result.successful)

    def test_tracks_applying_hook_does_not_fire_when_startup_fails(self):
        startup_result = _startup_result(successful=False)
        calls = []
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(startup_result),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(
                _finish_result()
            ),
            error_handler=RecordingErrorHandler(),
        )

        orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                on_tracks_applying=lambda: calls.append("tracks_applying"),
            )
        )

        self.assertEqual([], calls)

    def test_startup_failure_recovers_and_does_not_monitor_playback(self):
        startup_result = _startup_result(successful=False)
        startup = RecordingStartupOrchestrator(startup_result)
        startup_completion = RecordingStartupCompletionService()
        during = RecordingDuringPlaybackOrchestrator(_monitoring_result())
        finish = RecordingFinishPlaybackOrchestrator(_finish_result())
        error_handler = RecordingErrorHandler()
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=startup_completion,
            during_playback_orchestrator=during,
            finish_playback_orchestrator=finish,
            error_handler=error_handler,
        )

        result = orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
            )
        )

        self.assertFalse(result.successful)
        self.assertIsNotNone(result.error_recovery_result)
        self.assertEqual([], startup_completion.requests)
        self.assertEqual([], during.requests)
        self.assertEqual([], finish.requests)
        self.assertEqual("oppo_startup_failed", error_handler.requests[0].reason)
        self.assertEqual("com.emby.app", error_handler.requests[0].previous_tv_app_id)

    def test_logs_startup_result_at_error_level_when_startup_fails(self):
        startup_result = _startup_result(successful=False)
        startup = RecordingStartupOrchestrator(startup_result)
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=RecordingDuringPlaybackOrchestrator(
                _monitoring_result()
            ),
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(
                _finish_result()
            ),
            error_handler=RecordingErrorHandler(),
        )

        with self.assertLogs(
                "home_cinema_control.playback.orchestrator", level="ERROR"
        ) as captured:
            orchestrator.play_until_stopped(
                PlaybackOrchestrationRequest(
                    startup_request=_startup_request(),
                    startup_completion_request=_startup_completion_request(),
                )
            )

        self.assertTrue(
            any("OPPO playback startup result" in line for line in captured.output)
        )

    def test_finish_failure_runs_central_recovery(self):
        startup_result = _startup_result(successful=True)
        startup = RecordingStartupOrchestrator(startup_result)
        startup_completion = RecordingStartupCompletionService(
            PlayMediaItemResponse(
                start_position_seconds=0,
                started_reported=True,
                seek_result=DeviceCommandResult.success(),
                audio_result=DeviceCommandResult.success(),
                subtitle_result=DeviceCommandResult.success(),
            )
        )
        during = RecordingDuringPlaybackOrchestrator(_monitoring_result())
        finish = RecordingFinishPlaybackOrchestrator(_finish_result(successful=False))
        error_handler = RecordingErrorHandler()
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=startup,
            startup_completion_service=startup_completion,
            during_playback_orchestrator=during,
            finish_playback_orchestrator=finish,
            error_handler=error_handler,
        )

        with self.assertLogs(
                "home_cinema_control.playback.orchestrator", level="WARNING"
        ) as captured:
            result = orchestrator.play_until_stopped(
                PlaybackOrchestrationRequest(
                    startup_request=_startup_request(),
                    startup_completion_request=_startup_completion_request(),
                )
            )

        self.assertFalse(result.successful)
        self.assertEqual("playback_finish_unsuccessful", error_handler.requests[0].reason)
        self.assertTrue(
            any("Playback finish completed" in line for line in captured.output)
        )


def _start_request():
    return MediaPlayerStartRequest(
        media_location=PlayerMediaFileLocation(
            content_server="nas",
            content_directory="Movies",
            playback_file_name="movie.mkv",
            playback_file_format="mkv",
        )
    )


def _startup_request():
    return PlaybackStartupRequest(
        output_switch_request=_output_switch_request(),
        media_player_start_request=_start_request(),
    )


def _output_switch_request():
    return PlaybackOutputSwitchRequest(
        tv_input=TvInputTarget(input_id="2"),
        av_input_id="SIMPLAY",
        tv_enabled=True,
        av_enabled=True,
    )


def _output_switch_result():
    return PlaybackOutputSwitchResult(
        previous_tv_app_id="com.emby.app",
        tv_input_result=DeviceCommandResult.success(),
        av_power_result=DeviceCommandResult.success(),
        av_input_result=DeviceCommandResult.success(),
    )


def _startup_completion_request():
    return PlayMediaItemRequest(
        start_position_seconds=42,
        source_user_id="user-1",
        media_item_id="movie-1",
        selected_source_audio_track_id=1,
        selected_source_subtitle_track_id=-1,
    )


def _startup_result(*, successful):
    return PlayerPlaybackStartResult(
        media_mounted=successful,
        playback_command_accepted=successful,
        playback_started_on_device=successful,
        playback_state=_state(PlayerPlaybackStatus.PLAY),
    )


def _monitoring_result(
    *,
    position_seconds=1,
    duration_seconds=10,
    stop_reason=PlaybackMonitoringStopReason.PLAYER_IDLE,
):
    return PlaybackMonitoringResult(
        position_seconds=position_seconds,
        duration_seconds=duration_seconds,
        final_state=_state(PlayerPlaybackStatus.STOP),
        stop_reason=stop_reason,
    )


def _finish_result(*, successful=True):
    return PlaybackFinishResult(
        media_server_stop_result=None,
        player_idle_result=(
            DeviceCommandResult.success()
            if successful
            else DeviceCommandResult.failed("oppo not idle")
        ),
        tv_app_result=(
            DeviceCommandResult.success()
            if successful
            else DeviceCommandResult.failed("tv failed")
        ),
        av_audio_result=DeviceCommandResult.success(),
        final_player_state=_state(PlayerPlaybackStatus.MEDIA_CENTER),
    )


def _state(status):
    lifecycle_phase = (
        PlayerPlaybackLifecyclePhase.ACTIVE
        if status == PlayerPlaybackStatus.PLAY
        else PlayerPlaybackLifecyclePhase.TRANSITION
    )
    return PlayerPlaybackState(
        status=status,
        lifecycle_phase=lifecycle_phase,
        raw_response=f"@OK {status.value}",
        ok=True,
    )


    def test_is_paused_flag_is_carried_into_monitoring_request(self):
        during = RecordingDuringPlaybackOrchestrator(_monitoring_result())
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(_startup_result(successful=True)),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=during,
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(_finish_result()),
            error_handler=RecordingErrorHandler(),
        )

        orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
                is_paused=True,
            )
        )

        self.assertEqual(1, len(during.requests))
        self.assertTrue(during.requests[0].is_paused)

    def test_is_paused_defaults_to_false_when_not_set(self):
        during = RecordingDuringPlaybackOrchestrator(_monitoring_result())
        orchestrator = PlaybackOrchestrator(
            startup_orchestrator=RecordingStartupOrchestrator(_startup_result(successful=True)),
            startup_completion_service=RecordingStartupCompletionService(),
            during_playback_orchestrator=during,
            finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(_finish_result()),
            error_handler=RecordingErrorHandler(),
        )

        orchestrator.play_until_stopped(
            PlaybackOrchestrationRequest(
                startup_request=_startup_request(),
                startup_completion_request=_startup_completion_request(),
            )
        )

        self.assertFalse(during.requests[0].is_paused)


def _recovery_result():
    from home_cinema_control.playback.error_handling import PlaybackErrorRecoveryResult

    return PlaybackErrorRecoveryResult(
        player_stop_result=DeviceCommandResult.success(),
        tv_app_result=DeviceCommandResult.success(),
        av_audio_result=DeviceCommandResult.success(),
    )


if __name__ == "__main__":
    unittest.main()
