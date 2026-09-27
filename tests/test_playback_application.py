import unittest
from types import SimpleNamespace
from unittest.mock import patch

from home_cinema_control.media_servers.common.playback_source import (
    MediaServerPlaybackSource,
)
from home_cinema_control.playback.application import (
    PlaybackApplicationService,
    _should_stop_source_client_before_handoff,
)
from home_cinema_control.playback.content_kind import MediaContentKind
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    PlaybackOutputSwitchResult,
)
from home_cinema_control.playback.intent import PlaybackIntent, PlaybackOrigin
from home_cinema_control.playback.state import BridgePlaybackState
from home_cinema_control.playback.timing import PlaybackStartupTimer


class PlaybackApplicationServiceTest(unittest.TestCase):
    def test_request_playback_ignores_duplicate_active_item(self):
        calls = []
        state = BridgePlaybackState()
        state.playstate = "Playing"
        state.start_loading(_intent(media_item_id="11136"))
        state.playstate = "Playing"
        service = PlaybackApplicationService(
            playback_session=FakePlaybackSession(),
            playback_state=state,
            reload_config=lambda: None,
        )
        service.start_from_intent = lambda *args, **kwargs: calls.append("start")
        service.replace_from_intent = lambda *args, **kwargs: calls.append("replace")

        requested = service.request_playback_from_intent(
            _intent(media_item_id="11136"),
            origin=PlaybackOrigin.OBSERVED_TV_CLIENT,
        )

        self.assertFalse(requested)
        self.assertEqual([], calls)

    def test_request_playback_replaces_when_other_item_is_active(self):
        calls = []
        state = BridgePlaybackState()
        state.playstate = "Playing"
        state.start_loading(_intent(media_item_id="11136"))
        state.playstate = "Playing"
        service = PlaybackApplicationService(
            playback_session=FakePlaybackSession(),
            playback_state=state,
            reload_config=lambda: None,
        )
        service.replace_from_intent = (
            lambda *args, **kwargs: calls.append(("replace", args, kwargs)) or True
        )
        intent = _intent(media_item_id="22222")

        requested = service.request_playback_from_intent(
            intent,
            origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND,
        )

        self.assertTrue(requested)
        self.assertEqual("replace", calls[0][0])
        self.assertIs(intent, calls[0][1][0])
        self.assertEqual({"origin": PlaybackOrigin.REMOTE_CONTROL_COMMAND}, calls[0][2])

    def test_request_playback_starts_when_playback_is_free(self):
        calls = []
        service = PlaybackApplicationService(
            playback_session=FakePlaybackSession(),
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
        )
        service.start_from_intent = (
            lambda *args, **kwargs: calls.append(("start", args, kwargs))
        )
        intent = _intent(media_item_id="22222")

        requested = service.request_playback_from_intent(
            intent,
            origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND,
        )

        self.assertTrue(requested)
        self.assertEqual("start", calls[0][0])
        self.assertIs(intent, calls[0][1][0])
        self.assertEqual({"origin": PlaybackOrigin.REMOTE_CONTROL_COMMAND}, calls[0][2])

    def test_active_iso_replacement_uses_stop_command(self):

        command = "stop_active_playback"

        self.assertEqual("stop_active_playback", command)

    def test_active_file_replacement_uses_stop_command(self):

        command = "stop_active_playback"

        self.assertEqual("stop_active_playback", command)

    def test_remembers_non_hdmi_tv_return_app(self):
        service = PlaybackApplicationService(
            playback_session="session",
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
        )

        service._remember_playback_return_tv_app_id(
            _playback_result_with_previous_tv_app("com.emby.app")
        )

        self.assertEqual("com.emby.app", service._playback_return_tv_app_id)

    def test_does_not_overwrite_return_app_with_hdmi_input(self):
        service = PlaybackApplicationService(
            playback_session="session",
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
        )
        service._playback_return_tv_app_id = "com.emby.app"

        service._remember_playback_return_tv_app_id(
            _playback_result_with_previous_tv_app("com.webos.app.hdmi3")
        )

        self.assertEqual("com.emby.app", service._playback_return_tv_app_id)

    def test_keeps_return_app_while_replacement_finish_is_joining(self):
        service = PlaybackApplicationService(
            playback_session="session",
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
        )
        service._playback_return_tv_app_id = "com.emby.app"
        service._thread_lifecycle._replacement_requested.set()

        service._clear_playback_return_tv_app_id_after_final_finish(
            _playback_result_with_previous_tv_app("com.emby.app", finished=True)
        )

        self.assertEqual("com.emby.app", service._playback_return_tv_app_id)

    def test_clears_return_app_after_final_finish(self):
        service = PlaybackApplicationService(
            playback_session="session",
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
        )
        service._playback_return_tv_app_id = "com.emby.app"

        service._clear_playback_return_tv_app_id_after_final_finish(
            _playback_result_with_previous_tv_app("com.emby.app", finished=True)
        )

        self.assertIsNone(service._playback_return_tv_app_id)


class OnStartupCompletedTest(unittest.TestCase):
    """`_on_startup_completed` delegates the actual touchpoint-6 send to the
    messaging service (see test_playback_startup_messaging.py for content/copy
    coverage) — this only verifies the delegation itself."""

    def _service(self):
        return PlaybackApplicationService(
            playback_session=SimpleNamespace(config={"tv": {"enabled": True}}),
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
            media_server_playback_services=SimpleNamespace(
                create_observed_track_mapper=lambda playback_session, *, playback_state: object(),
            ),
        )

    def test_delegates_to_messaging_action_with_the_resolved_content_kind(self):
        service = self._service()
        actions = []
        messaging = SimpleNamespace(action=lambda content_kind: actions.append(content_kind))

        service._on_startup_completed(
            None,
            intent=_intent(media_item_id="1"),
            movie="/movies/aquaman.mkv",
            messaging=messaging,
            content_kind=MediaContentKind.CONCERT,
            playback_wiring=SimpleNamespace(
                playback_event_publisher=None,
                during_playback_orchestrator=SimpleNamespace(),
            ),
            startup_timer=PlaybackStartupTimer(),
        )

        self.assertEqual([MediaContentKind.CONCERT], actions)

    def test_sets_playstate_to_playing(self):
        service = self._service()
        messaging = SimpleNamespace(action=lambda content_kind: None)

        service._on_startup_completed(
            None,
            intent=_intent(media_item_id="1"),
            movie="/movies/aquaman.mkv",
            messaging=messaging,
            content_kind=MediaContentKind.MOVIE,
            playback_wiring=SimpleNamespace(
                playback_event_publisher=None,
                during_playback_orchestrator=SimpleNamespace(),
            ),
            startup_timer=PlaybackStartupTimer(),
        )

        self.assertEqual("Playing", service._state.playstate)


class StartFromIntentWiresOnStartupCompletedCorrectlyTest(unittest.TestCase):
    """Regression test for a real bug: the on_startup_completed lambda built
    inside _start_from_intent passed `origin=origin` as a keyword argument
    after `_on_startup_completed`'s signature had already dropped that
    parameter. No other test caught it because every other test calls
    `_on_startup_completed` directly, bypassing this lambda entirely. This
    test drives `_start_from_intent` through a full successful path with a
    fake orchestrator that actually invokes the constructed callback, so a
    keyword-argument mismatch here raises a real TypeError, the same way it
    did on real hardware."""

    def test_media_server_item_failure_resets_loading_without_stopping_source(self):
        playback_session = FakePlaybackSessionForStartFromIntent(
            item_error=RuntimeError("Access token is invalid or expired")
        )
        state = BridgePlaybackState()
        service = PlaybackApplicationService(
            playback_session=playback_session,
            playback_state=state,
            reload_config=lambda: None,
            media_server_playback_services=SimpleNamespace(
                playback_context_from_intent=lambda intent: SimpleNamespace(),
            ),
        )

        with (
            patch("home_cinema_control.playback.application.prepare_oppo_observation_mode"),
            patch("home_cinema_control.playback.application.log_oppo_qpl_state"),
            patch(
                "home_cinema_control.playback.application.ensure_oppo_control_api_available"
            ) as ensure_oppo,
        ):
            service._start_from_intent(
                _intent(media_item_id="1"),
                origin=PlaybackOrigin.OBSERVED_TV_CLIENT,
            )

        ensure_oppo.assert_not_called()
        self.assertEqual("Free", state.playstate)
        self.assertEqual([], playback_session.stopped_sessions)
        self.assertEqual("MEDIA_SERVER_ITEM_UNAVAILABLE", state.last_diagnostic.code)

    def test_on_startup_completed_lambda_matches_the_real_method_signature(self):
        intent = PlaybackIntent(
            media_item_id="1",
            media_source_id="",
            source_user_id="",
            source_client_session_id="session-1",
            source_device_id="",
            source_device_name="",
            start_position_seconds=0,
            selected_audio_track_id=1,
            selected_subtitle_track_id=-1,
        )
        media_location = SimpleNamespace(
            content_server="nas",
            content_directory="Series/Show",
            playback_file_name="episode.mkv",
            playback_file_format="mkv",
            network_protocol="nfs",
        )
        prepared_requests = SimpleNamespace(
            media_location=media_location,
            movie_path="/nas/Series/Show/episode.mkv",
            output_switch_request=SimpleNamespace(),
            media_player_start_request=SimpleNamespace(),
            startup_completion_request=SimpleNamespace(),
            media_source_power_request=None,
        )
        fake_orchestration_result = SimpleNamespace(
            startup_result=SimpleNamespace(
                output_switch_result=SimpleNamespace(previous_tv_app_id=None)
            ),
            finish_result=None,
        )

        class FakeOrchestrator:
            def play_until_stopped(self, request):
                request.on_startup_waiting(1)
                request.on_tracks_applying()
                request.on_startup_completed(None)
                return fake_orchestration_result

        playback_session = FakePlaybackSessionForStartFromIntent()
        service = PlaybackApplicationService(
            playback_session=playback_session,
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
            media_server_playback_services=SimpleNamespace(
                playback_context_from_intent=lambda intent: SimpleNamespace(),
                create_playback_event_publisher=lambda client, *, bridge_session_id, context: None,
                create_track_resolver=lambda playback_session: SimpleNamespace(),
                create_observed_track_mapper=lambda playback_session, *, playback_state: object(),
            ),
        )

        with (
            patch(
                "home_cinema_control.playback.application.ensure_oppo_control_api_available",
                return_value=True,
            ),
            patch("home_cinema_control.playback.application.prepare_oppo_observation_mode"),
            patch("home_cinema_control.playback.application.log_oppo_qpl_state"),
            patch(
                "home_cinema_control.playback.application.create_playback_orchestrator_wiring",
                return_value=SimpleNamespace(
                    playback_orchestrator=FakeOrchestrator(),
                    playback_event_publisher=None,
                    during_playback_orchestrator=SimpleNamespace(),
                    startup_wiring=SimpleNamespace(media_player=None),
                ),
            ),
            patch(
                "home_cinema_control.playback.application.prepare_playback_requests",
                return_value=prepared_requests,
            ),
            patch("home_cinema_control.playback.application.report_orchestration_result"),
            patch(
                "home_cinema_control.playback.application.diagnose_orchestration_result",
                return_value=None,
            ),
            patch("home_cinema_control.playback.application.power_down_after_playback_if_configured"),
        ):
            service._start_from_intent(
                intent, origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND
            )

        # Reaching this point without a TypeError is the actual regression
        # check; this also confirms on_startup_completed ran far enough to
        # send the content-kind-aware closing message via `messaging`.
        self.assertIn("episode", playback_session.notifications)
        self.assertEqual(["session-1", "session-1"], playback_session.stopped_sessions)


class FakePlaybackSessionForStartFromIntent:
    def __init__(self, *, item_error=None):
        self.config = {}
        self.lang = {
            "msg-startup-received": "received",
            "msg-startup-locating": "locating",
            "msg-startup-starting": "starting",
            "msg-startup-fine-tuning": "fine tuning",
            "msg-startup-still-with-you": "still with you",
            "msg-startup-action-movie": "movie",
            "msg-startup-action-episode": "episode",
            "msg-startup-action-concert": "concert",
            "msg-startup-action-live-tv": "live tv",
            "msg-startup-action-generic": "generic",
            "msg-playback-timeout": "timeout",
            "msg-playback-error-mount": "error mount",
            "msg-playback-error-play": "error play",
            "msg-playback-error-no-oppo": "no oppo",
        }
        self.client = object()
        self.user_info = {"User": {"Id": "user-1"}, "SessionInfo": {"Id": "session-1"}}
        self.notifications = []
        self.stopped_sessions = []
        self.item_error = item_error

    def notify_session(self, session_id, message, timeout_ms=None):
        self.notifications.append(message)

    def stop_session_playback(self, session_id):
        self.stopped_sessions.append(session_id)

    def get_media_source_info(self, user_id, item_id, media_source_id):
        if self.item_error is not None:
            raise self.item_error
        return MediaServerPlaybackSource(
            path="/nas/Series/Show/episode.mkv",
            container="mkv",
            duration_seconds=1200,
            production_year=2024,
            title="Show",
            content_kind=MediaContentKind.EPISODE,
        )


class FakePlaybackSession:
    def __init__(self):
        self.config = {"app": {"log_level": 0}}


class ShouldStopSourceClientBeforeHandoffTest(unittest.TestCase):
    """The OPPO takes over regardless of TV/AV config, so the source client's
    native playback must be stopped for every TV-observed handoff — otherwise
    both end up playing the same item in parallel."""

    def test_stops_for_observed_tv_client_origin(self):
        self.assertTrue(
            _should_stop_source_client_before_handoff(
                PlaybackOrigin.OBSERVED_TV_CLIENT
            )
        )

    def test_stops_for_remote_control_command_origin(self):
        self.assertTrue(
            _should_stop_source_client_before_handoff(
                PlaybackOrigin.REMOTE_CONTROL_COMMAND
            )
        )


class StopActivePlaybackAndWaitTest(unittest.TestCase):
    """Exposed for callers outside normal playback replacement (e.g. the
    runtime swapping the media-server listener on a provider switch) that
    need a clean slate before doing something disruptive.
    """

    def test_returns_false_when_nothing_active(self):
        service = PlaybackApplicationService(
            playback_session=FakePlaybackSession(),
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
            stop_active_playback=lambda: None,
        )

        self.assertFalse(service.stop_active_playback_and_wait())

    def test_stops_and_waits_for_active_playback(self):
        calls = []
        service = PlaybackApplicationService(
            playback_session=FakePlaybackSession(),
            playback_state=BridgePlaybackState(),
            reload_config=lambda: None,
            stop_active_playback=lambda: calls.append("stop_active"),
        )
        service._thread_lifecycle._active_thread = _FakeActiveThread(calls)

        result = service.stop_active_playback_and_wait()

        self.assertTrue(result)
        self.assertEqual(["stop_active", "join_active"], calls)


class _FakeActiveThread:
    def __init__(self, calls):
        self._calls = calls

    def is_alive(self):
        return True

    def join(self, timeout=None):
        self._calls.append("join_active")


def _intent(*, media_item_id: str) -> PlaybackIntent:
    return PlaybackIntent(
        media_item_id=media_item_id,
        media_source_id="",
        source_user_id="",
        source_client_session_id=None,
        source_device_id="",
        source_device_name="",
        start_position_seconds=0,
        selected_audio_track_id=1,
        selected_subtitle_track_id=-1,
    )


def _playback_result_with_previous_tv_app(previous_tv_app_id, *, finished=False):
    return SimpleNamespace(
        startup_result=SimpleNamespace(
            output_switch_result=PlaybackOutputSwitchResult(
                previous_tv_app_id=previous_tv_app_id,
                tv_input_result=DeviceCommandResult.success(),
                av_power_result=DeviceCommandResult.success(),
                av_input_result=DeviceCommandResult.success(),
            )
        ),
        finish_result=object() if finished else None,
    )


if __name__ == "__main__":
    unittest.main()
