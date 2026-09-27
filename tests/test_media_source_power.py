import unittest
import unittest.mock
from unittest.mock import patch

from home_cinema_control.devices.home_assistant.client import (
    HomeAssistantClient,
    HomeAssistantError,
)
from home_cinema_control.devices.home_assistant.media_source_power import (
    HomeAssistantMediaSourcePower,
    create_media_source_power_or_none,
    power_on_media_source_for_mapping,
    share_reachable,
)
from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.player_state import PlayerPlaybackStartResult
from home_cinema_control.playback.request_preparation import media_source_power_request
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    DeviceCommandStatus,
    MediaPlayerStartRequest,
    MediaSourcePowerRequest,
    PlaybackOutputSwitchRequest,
    PlaybackStartupRequest,
    PlayerMediaFileLocation,
)
from home_cinema_control.playback.startup.orchestrator import PlaybackStartupOrchestrator

_REQUEST = MediaSourcePowerRequest(
    switch_entity_ids=("switch.nas11",),
    server="nas11.local",
    network_protocol="nfs",
)


class FakeHomeAssistant:
    """Stands in for HomeAssistantClient: scripted states, recorded calls."""

    def __init__(self, states=None, *, state_error=None, service_result=None, configured=True):
        self.states = dict(states or {})
        self.state_error = state_error
        self.service_result = service_result or DeviceCommandResult.success()
        self.configured = configured
        self.services = []

    def missing_settings(self):
        return None if self.configured else "Home Assistant URL not configured."

    def get_state(self, entity_id):
        if self.state_error is not None:
            raise self.state_error
        return self.states.get(entity_id, "off")

    def call_service(self, domain, service, data, **kwargs):
        self.services.append((domain, service, data))
        return self.service_result


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _power(client, probe, *, timeout=30, poll=5, clock=None):
    clock = clock or Clock()
    config = {"media_source_power": {"wait_timeout_seconds": timeout, "poll_interval_seconds": poll}}
    return HomeAssistantMediaSourcePower(
        config,
        client=client,
        probe=probe,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    ), clock


class HomeAssistantMediaSourcePowerTest(unittest.TestCase):
    def test_already_reachable_share_skips_home_assistant(self):
        client = FakeHomeAssistant()
        power, _ = _power(client, probe=lambda server, protocol: True)

        result = power.request_power_on(_REQUEST)

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)
        self.assertEqual([], client.services)

    def test_off_switch_is_turned_on(self):
        client = FakeHomeAssistant({"switch.nas11": "off"})
        power, _ = _power(client, probe=lambda server, protocol: False)

        result = power.request_power_on(_REQUEST)

        self.assertTrue(result.successful)
        self.assertEqual(
            [("homeassistant", "turn_on", {"entity_id": "switch.nas11"})], client.services
        )

    def test_switch_already_on_is_not_toggled_while_share_boots(self):
        client = FakeHomeAssistant({"switch.nas11": "on"})
        power, _ = _power(client, probe=lambda server, protocol: False)

        result = power.request_power_on(_REQUEST)

        self.assertTrue(result.successful)
        self.assertEqual([], client.services)

    def test_power_on_fails_when_home_assistant_is_unreachable(self):
        client = FakeHomeAssistant(state_error=HomeAssistantError("unreachable"))
        power, _ = _power(client, probe=lambda server, protocol: False)

        result = power.request_power_on(_REQUEST)

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("unreachable", result.detail)

    def test_power_on_fails_when_turn_on_is_rejected(self):
        client = FakeHomeAssistant(service_result=DeviceCommandResult.failed("HTTP 500"))
        power, _ = _power(client, probe=lambda server, protocol: False)

        self.assertEqual(DeviceCommandStatus.FAILED, power.request_power_on(_REQUEST).status)

    def test_wait_returns_once_the_share_port_answers(self):
        answers = iter([False, False, True])
        client = FakeHomeAssistant({"switch.nas11": "on"})
        power, clock = _power(client, probe=lambda server, protocol: next(answers))

        result = power.wait_until_available(_REQUEST)

        self.assertTrue(result.successful)
        self.assertEqual([5, 5], clock.sleeps)
        self.assertIn("after 10s", result.detail)

    def test_wait_fails_when_nothing_comes_online(self):
        client = FakeHomeAssistant({"switch.nas11": "off"})
        power, clock = _power(client, probe=lambda server, protocol: False, timeout=12, poll=5)

        result = power.wait_until_available(_REQUEST)

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("did not come online within 12s", result.detail)
        self.assertGreaterEqual(clock.now, 12)

    def test_wait_uses_the_request_timeout_over_the_default(self):
        client = FakeHomeAssistant({"switch.nas11": "off"})
        power, clock = _power(client, probe=lambda server, protocol: False, timeout=300, poll=5)
        request = MediaSourcePowerRequest(
            switch_entity_ids=("switch.nas11",),
            server="nas11.local",
            network_protocol="nfs",
            wait_timeout_seconds=20,
        )

        result = power.wait_until_available(request)

        self.assertIn("within 20s", result.detail)
        self.assertLess(clock.now, 30)

    def test_wait_continues_when_switch_is_on_but_port_is_not_visible_from_hcc(self):
        client = FakeHomeAssistant({"switch.nas11": "on"})
        power, _ = _power(client, probe=lambda server, protocol: False, timeout=10)

        with self.assertLogs(
            "home_cinema_control.devices.home_assistant.media_source_power", "WARNING"
        ):
            result = power.wait_until_available(_REQUEST)

        self.assertTrue(result.successful)
        self.assertIn("not confirmed", result.detail)

    def test_factory_returns_none_without_home_assistant(self):
        self.assertIsNone(create_media_source_power_or_none({}))
        self.assertIsNotNone(create_media_source_power_or_none(
            {"home_assistant": {"url": "http://ha.local:8123", "token": "t"}}
        ))

    def test_real_client_is_used_by_default(self):
        power = HomeAssistantMediaSourcePower(
            {"home_assistant": {"url": "http://ha.local:8123", "token": "t"}}
        )

        self.assertIsInstance(power._client, HomeAssistantClient)


class ShareReachableTest(unittest.TestCase):
    def _probe(self, protocol, open_ports):
        attempted = []

        def fake_connect(address, timeout):
            attempted.append(address[1])
            if address[1] not in open_ports:
                raise OSError("refused")
            return _NullConnection()

        with patch(
            "home_cinema_control.devices.home_assistant.media_source_power."
            "socket.create_connection",
            side_effect=fake_connect,
        ):
            return share_reachable("nas11.local", protocol), attempted

    def test_nfs_checks_port_2049(self):
        self.assertEqual((True, [2049]), self._probe("nfs", {2049}))

    def test_smb_checks_port_445(self):
        self.assertEqual((False, [445]), self._probe("cifs", {2049}))

    def test_unknown_protocol_accepts_either_port(self):
        self.assertEqual((True, [2049, 445]), self._probe(None, {445}))


class _NullConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RecordingMediaSourcePower:
    def __init__(self, calls, *, power_on=None, wait=None):
        self.calls = calls
        self.power_on_result = power_on or DeviceCommandResult.success()
        self.wait_result = wait or DeviceCommandResult.success()

    def request_power_on(self, request):
        self.calls.append("power_on")
        return self.power_on_result

    def wait_until_available(self, request):
        self.calls.append("wait")
        return self.wait_result


class RecordingPlayer:
    def __init__(self, calls):
        self.calls = calls

    def wake_display(self):
        self.calls.append("wake_display")
        return DeviceCommandResult.success()

    def start(self, request, *, on_waiting=None):
        self.calls.append("oppo_start")
        return PlayerPlaybackStartResult(
            media_mounted=True,
            playback_command_accepted=True,
            playback_started_on_device=True,
        )


class RecordingTelevision:
    def __init__(self, calls):
        self.calls = calls

    def get_current_app_id(self):
        return None

    def media_server_app_id(self, provider_type):
        return None

    def switch_to_input(self, target):
        self.calls.append("tv_switch")
        return DeviceCommandResult.success()


def _startup_request(power_request=_REQUEST):
    return PlaybackStartupRequest(
        output_switch_request=PlaybackOutputSwitchRequest(
            tv_input=TvInputTarget(input_id="HDMI_1"),
            av_input_id=None,
            av_enabled=False,
        ),
        media_player_start_request=MediaPlayerStartRequest(
            media_location=PlayerMediaFileLocation(
                content_server="nas11.local",
                content_directory="libreria/series",
                playback_file_name="episode.mkv",
                playback_file_format="mkv",
            ),
        ),
        media_source_power_request=power_request,
    )


def _orchestrator(calls, power):
    return PlaybackStartupOrchestrator(
        television=RecordingTelevision(calls),
        av_receiver=None,
        media_player=RecordingPlayer(calls),
        media_source_power=power,
    )


class StartupOrchestratorMediaSourcePowerTest(unittest.TestCase):
    def test_nas_boots_while_outputs_switch_then_oppo_starts(self):
        calls = []
        notified = []
        orchestrator = _orchestrator(calls, RecordingMediaSourcePower(calls))

        result = orchestrator.start_playback(
            _startup_request(),
            on_media_source_powering_on=lambda: notified.append(True),
        )

        self.assertTrue(result.successful)
        self.assertEqual(
            ["power_on", "tv_switch", "wait", "wake_display", "oppo_start"], calls
        )
        self.assertEqual([True], notified)

    def test_offline_nas_fails_startup_without_starting_oppo(self):
        calls = []
        orchestrator = _orchestrator(calls, RecordingMediaSourcePower(
            calls, wait=DeviceCommandResult.failed("nas11.local did not come online")
        ))

        result = orchestrator.start_playback(_startup_request())

        self.assertFalse(result.successful)
        self.assertNotIn("oppo_start", calls)
        self.assertEqual(DeviceCommandStatus.FAILED, result.media_source_power_result.status)
        self.assertFalse(result.media_player_start_result.media_mounted)

    def test_reachable_nas_neither_waits_nor_notifies(self):
        calls = []
        notified = []
        orchestrator = _orchestrator(calls, RecordingMediaSourcePower(
            calls, power_on=DeviceCommandResult.skipped("already reachable")
        ))

        result = orchestrator.start_playback(
            _startup_request(),
            on_media_source_powering_on=lambda: notified.append(True),
        )

        self.assertTrue(result.successful)
        self.assertEqual(["power_on", "tv_switch", "oppo_start"], calls)
        self.assertEqual([], notified)

    def test_failed_power_on_request_still_waits_for_the_share(self):
        calls = []
        orchestrator = _orchestrator(calls, RecordingMediaSourcePower(
            calls, power_on=DeviceCommandResult.failed("Home Assistant unreachable")
        ))

        result = orchestrator.start_playback(_startup_request())

        self.assertTrue(result.successful)
        # Power-on was not confirmed, so the player display is left alone.
        self.assertEqual(["power_on", "tv_switch", "wait", "oppo_start"], calls)

    def test_display_wake_failure_does_not_block_playback(self):
        calls = []
        player = RecordingPlayer(calls)
        player.wake_display = lambda: (_ for _ in ()).throw(RuntimeError("OPPO busy"))
        orchestrator = PlaybackStartupOrchestrator(
            television=RecordingTelevision(calls),
            av_receiver=None,
            media_player=player,
            media_source_power=RecordingMediaSourcePower(calls),
        )

        result = orchestrator.start_playback(_startup_request())

        self.assertTrue(result.successful)
        self.assertIn("oppo_start", calls)

    def test_path_without_switch_skips_power_management(self):
        calls = []
        orchestrator = _orchestrator(calls, RecordingMediaSourcePower(calls))

        result = orchestrator.start_playback(_startup_request(power_request=None))

        self.assertTrue(result.successful)
        self.assertEqual(["tv_switch", "oppo_start"], calls)
        self.assertEqual(DeviceCommandStatus.SKIPPED, result.media_source_power_result.status)

    def test_switch_is_ignored_without_home_assistant(self):
        calls = []
        orchestrator = _orchestrator(calls, None)

        result = orchestrator.start_playback(_startup_request())

        self.assertTrue(result.successful)
        self.assertEqual(["tv_switch", "oppo_start"], calls)

    def test_power_port_exception_fails_startup_cleanly(self):
        calls = []
        power = RecordingMediaSourcePower(calls)
        power.wait_until_available = lambda request: (_ for _ in ()).throw(RuntimeError("boom"))
        orchestrator = _orchestrator(calls, power)

        result = orchestrator.start_playback(_startup_request())

        self.assertFalse(result.successful)
        self.assertIn("boom", result.media_source_power_result.detail)


class MediaSourcePowerRequestTest(unittest.TestCase):
    _LOCATION = PlayerMediaFileLocation(
        content_server="172.16.10.211",
        content_directory="datos/libreria/Peliculas/Film",
        playback_file_name="film.mkv",
        playback_file_format="mkv",
        network_protocol="nfs",
    )

    def test_uses_switch_of_the_matching_mapping(self):
        request = media_source_power_request(
            media_path="\\\\nas25\\NAS25\\Peliculas\\Film\\film.mkv",
            path_mappings=[
                {"source_path": "\\\\nas21\\NAS21\\Peliculas", "power_switch_entity_id": "switch.nas21"},
                {"source_path": "\\\\nas25\\NAS25\\Peliculas", "power_switch_entity_id": "switch.nas25"},
            ],
            media_location=self._LOCATION,
        )

        self.assertEqual(
            MediaSourcePowerRequest(
                switch_entity_ids=("switch.nas25",),
                server="172.16.10.211",
                network_protocol="nfs",
            ),
            request,
        )

    def test_uses_the_longest_timeout_of_the_matching_mappings(self):
        request = media_source_power_request(
            media_path="\\\\nas25\\NAS25\\Peliculas\\Film\\film.mkv",
            path_mappings=[
                {"source_path": "\\\\nas25\\NAS25", "power_switch_entity_id": "switch.nas25",
                 "power_wait_timeout_seconds": 90},
                {"source_path": "\\\\nas25\\NAS25\\Peliculas", "power_switch_entity_id": "switch.nas25",
                 "power_wait_timeout_seconds": "180"},
            ],
            media_location=self._LOCATION,
        )

        self.assertEqual(("switch.nas25",), request.switch_entity_ids)
        self.assertEqual(180.0, request.wait_timeout_seconds)

    def test_blank_timeout_falls_back_to_the_default(self):
        request = media_source_power_request(
            media_path="\\\\nas25\\NAS25\\film.mkv",
            path_mappings=[{"source_path": "\\\\nas25\\NAS25",
                            "power_switch_entity_id": "switch.nas25",
                            "power_wait_timeout_seconds": ""}],
            media_location=self._LOCATION,
        )

        self.assertIsNone(request.wait_timeout_seconds)

    def test_none_when_matching_mapping_has_no_switch(self):
        self.assertIsNone(media_source_power_request(
            media_path="\\\\nas21\\NAS21\\Peliculas\\film.mkv",
            path_mappings=[{"source_path": "\\\\nas21\\NAS21\\Peliculas", "power_switch_entity_id": " "}],
            media_location=self._LOCATION,
        ))

    def test_none_when_no_mapping_matches(self):
        self.assertIsNone(media_source_power_request(
            media_path="\\\\other\\film.mkv",
            path_mappings=[{"source_path": "\\\\nas21\\NAS21", "power_switch_entity_id": "switch.nas21"}],
            media_location=self._LOCATION,
        ))


class PowerOnForMappingTest(unittest.TestCase):
    _CONFIG = {"home_assistant": {"url": "http://ha.local:8123", "token": "t"}}

    def test_skipped_without_switch(self):
        result = power_on_media_source_for_mapping(
            self._CONFIG, {"player_path": "/nas11.local/libreria"}
        )

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)

    def test_skipped_without_home_assistant(self):
        result = power_on_media_source_for_mapping(
            {}, {"player_path": "/nas11.local/libreria", "power_switch_entity_id": "switch.nas11"}
        )

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)

    def test_wakes_and_waits_using_the_player_path_server(self):
        requests = []

        class FakePower:
            def request_power_on(self, request):
                requests.append(request)
                return DeviceCommandResult.success()

            def wait_until_available(self, request):
                requests.append(request)
                return DeviceCommandResult.success("nas11.local reachable after 40s.")

        with patch(
            "home_cinema_control.devices.home_assistant.media_source_power."
            "create_media_source_power_or_none",
            return_value=FakePower(),
        ):
            result = power_on_media_source_for_mapping(self._CONFIG, {
                "player_path": "/nas11.local/libreria/series",
                "protocol": "nfs",
                "power_switch_entity_id": "switch.nas11",
            })

        self.assertTrue(result.successful)
        self.assertEqual(
            MediaSourcePowerRequest(("switch.nas11",), "nas11.local", "nfs"), requests[0]
        )
        self.assertEqual(2, len(requests))


class PathsPowerOnRouteTest(unittest.TestCase):
    _MAPPING = {
        "source_path": "\\\\nas11\\libreria",
        "player_path": "/nas11.local/libreria",
        "power_switch_entity_id": "switch.nas11",
    }

    def _client(self):
        from tests.test_paths_routes import _make_client
        return _make_client()

    def test_path_test_fails_early_when_nas_stays_offline(self):
        client, runtime, _ = self._client()

        with patch(
            "home_cinema_control.web.paths_routes.power_on_media_source_for_mapping",
            return_value=DeviceCommandResult.failed("nas11.local did not come online within 300s."),
        ), patch("home_cinema_control.web.paths_routes.check_path_configuration") as check:
            resp = client.post("/api/v1/paths/test", json=self._MAPPING)

        self.assertEqual(400, resp.status_code)
        self.assertIn("did not come online", resp.json()["detail"])
        check.assert_not_called()
        self.assertEqual("media_source", runtime.set_last_diagnostic.call_args.args[0].component)

    def test_path_test_runs_after_nas_is_up(self):
        client, _, _ = self._client()

        with patch(
            "home_cinema_control.web.paths_routes.power_on_media_source_for_mapping",
            return_value=DeviceCommandResult.success(),
        ), patch(
            "home_cinema_control.web.paths_routes.check_path_configuration", return_value="OK"
        ):
            resp = client.post("/api/v1/paths/test", json=self._MAPPING)

        self.assertEqual(200, resp.status_code)

    def test_power_on_endpoint(self):
        client, _, _ = self._client()

        with patch(
            "home_cinema_control.web.paths_routes.power_on_media_source_for_mapping",
            return_value=DeviceCommandResult.success(),
        ) as power_on:
            resp = client.post("/api/v1/paths/power-on", json=self._MAPPING)

        self.assertEqual({"status": "ok"}, resp.json())
        self.assertEqual("switch.nas11", power_on.call_args.args[1]["power_switch_entity_id"])


class OppoWakeDisplayTest(unittest.TestCase):
    def test_wake_display_sends_return_key_and_waits(self):
        from home_cinema_control.devices.oppo.playback_adapters import OppoMediaPlayerAdapter

        client = unittest.mock.MagicMock()
        with patch(
            "home_cinema_control.devices.oppo.playback_adapters.OppoControlApiClient.from_config",
            return_value=client,
        ), patch(
            "home_cinema_control.devices.oppo.playback_adapters.time.sleep"
        ) as sleep:
            result = OppoMediaPlayerAdapter({"oppo": {"ip": "172.16.10.31"}}).wake_display()

        self.assertTrue(result.successful)
        client.send_remote_key.assert_called_once_with("RET")
        sleep.assert_called_once_with(1.0)


class PowerWaitTimeoutCoercionTest(unittest.TestCase):
    def test_coercion(self):
        from home_cinema_control.config.models import PathMappingConfig

        def timeout(value):
            return PathMappingConfig(power_wait_timeout_seconds=value).power_wait_timeout_seconds

        self.assertIsNone(timeout(None))
        self.assertIsNone(timeout(""))
        self.assertIsNone(timeout("abc"))
        self.assertIsNone(timeout(0))
        self.assertEqual(120.0, timeout("120"))
        self.assertEqual(10.0, timeout(3))
        self.assertEqual(1800.0, timeout(99999))


if __name__ == "__main__":
    unittest.main()
