import threading
import unittest

from home_cinema_control.playback.orchestrator import (
    PlaybackOrchestrationRequest,
    PlaybackOrchestrator,
)
from home_cinema_control.playback.startup.models import DeviceCommandResult
from tests.test_playback_orchestrator import (
    RecordingDuringPlaybackOrchestrator,
    RecordingErrorHandler,
    RecordingFinishPlaybackOrchestrator,
    RecordingStartupCompletionService,
    RecordingStartupOrchestrator,
    _finish_result,
    _monitoring_result,
    _startup_completion_request,
    _startup_request,
    _startup_result,
)


class RecordingRoomLighting:
    def __init__(self, *, prepare_gate=None):
        self.calls = []
        self._prepare_gate = prepare_gate
        self._changed = threading.Condition()

    def prepare_for_playback(self):
        if self._prepare_gate is not None:
            self._prepare_gate.wait(timeout=2)
        return self._record("prepare")

    def restore_after_playback(self):
        return self._record("restore")

    def wait_for_calls(self, count, timeout=2):
        with self._changed:
            self._changed.wait_for(lambda: len(self.calls) >= count, timeout=timeout)
        return list(self.calls)

    def _record(self, name):
        with self._changed:
            self.calls.append(name)
            self._changed.notify_all()
        return DeviceCommandResult.success()


class RaisingDuringPlaybackOrchestrator:
    def monitor_until_stopped(self, request):
        raise RuntimeError("observation lost")


def _orchestrator(
    lighting,
    *,
    startup_successful=True,
    during=None,
    finish_result=None,
):
    return PlaybackOrchestrator(
        startup_orchestrator=RecordingStartupOrchestrator(
            _startup_result(successful=startup_successful)
        ),
        startup_completion_service=RecordingStartupCompletionService(),
        during_playback_orchestrator=(
            during or RecordingDuringPlaybackOrchestrator(_monitoring_result())
        ),
        finish_playback_orchestrator=RecordingFinishPlaybackOrchestrator(
            finish_result or _finish_result()
        ),
        error_handler=RecordingErrorHandler(),
        room_lighting=lighting,
    )


def _request(**overrides):
    return PlaybackOrchestrationRequest(
        startup_request=_startup_request(),
        startup_completion_request=_startup_completion_request(),
        **overrides,
    )


class PlaybackOrchestratorRoomLightingTest(unittest.TestCase):
    def test_lights_are_prepared_then_restored_around_normal_playback(self):
        lighting = RecordingRoomLighting()

        result = _orchestrator(lighting).play_until_stopped(_request())

        self.assertTrue(result.successful)
        self.assertEqual(["prepare", "restore"], lighting.wait_for_calls(2))

    def test_lights_are_untouched_when_oppo_startup_fails(self):
        lighting = RecordingRoomLighting()

        _orchestrator(lighting, startup_successful=False).play_until_stopped(_request())

        self.assertEqual([], lighting.wait_for_calls(1, timeout=0.2))

    def test_lights_are_restored_when_during_phase_fails(self):
        lighting = RecordingRoomLighting()

        result = _orchestrator(
            lighting, during=RaisingDuringPlaybackOrchestrator()
        ).play_until_stopped(_request())

        self.assertIsNotNone(result.error_recovery_result)
        self.assertEqual(["prepare", "restore"], lighting.wait_for_calls(2))

    def test_lights_are_restored_when_finish_is_unsuccessful_even_for_replacement(self):
        lighting = RecordingRoomLighting()

        _orchestrator(
            lighting, finish_result=_finish_result(successful=False)
        ).play_until_stopped(_request(restore_outputs_on_finish=False))

        self.assertEqual(["prepare", "restore"], lighting.wait_for_calls(2))

    def test_lights_stay_as_they_are_when_playback_is_replaced(self):
        lighting = RecordingRoomLighting()

        _orchestrator(lighting).play_until_stopped(
            _request(restore_outputs_on_finish=lambda: False)
        )

        self.assertEqual(["prepare"], lighting.wait_for_calls(2, timeout=0.2))

    def test_slow_lighting_does_not_block_playback_and_keeps_order(self):
        gate = threading.Event()
        lighting = RecordingRoomLighting(prepare_gate=gate)

        result = _orchestrator(lighting).play_until_stopped(_request())

        # Playback finished while the "prepare" call was still blocked.
        self.assertTrue(result.successful)
        self.assertEqual([], lighting.calls)
        gate.set()
        self.assertEqual(["prepare", "restore"], lighting.wait_for_calls(2))

    def test_orchestrator_without_room_lighting_still_works(self):
        result = _orchestrator(None).play_until_stopped(_request())

        self.assertTrue(result.successful)


if __name__ == "__main__":
    unittest.main()
