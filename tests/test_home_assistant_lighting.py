import unittest

import requests

from home_cinema_control.devices.home_assistant.client import HomeAssistantClient
from home_cinema_control.devices.lighting.factory import (
    create_lighting_controller_or_none,
)
from home_cinema_control.devices.lighting.home_assistant import (
    HomeAssistantLightingController,
)
from home_cinema_control.playback.startup.models import DeviceCommandStatus
from tests.home_assistant_fakes import FakeResponse, RecordingHttpSession


def _config(*, token="secret-token", **overrides):
    lighting = {
        "enabled": True,
        "entity_ids": ["light.ceiling", "switch.led_strip"],
        "on_playback_start": "turn_off",
        "on_playback_stop": "turn_on",
    }
    lighting.update(overrides)
    return {
        "home_assistant": {
            "url": "http://ha.local:8123/",
            "token": token,
            "timeout_seconds": 3,
        },
        "lighting": lighting,
    }


def _controller(config, http):
    return HomeAssistantLightingController(
        config, client=HomeAssistantClient(config, http_session=http)
    )


class HomeAssistantLightingControllerTest(unittest.TestCase):
    def test_prepare_for_playback_calls_configured_service_per_domain(self):
        http = RecordingHttpSession()
        controller = _controller(_config(), http)

        result = controller.prepare_for_playback()

        self.assertTrue(result.successful)
        self.assertEqual(
            [
                ("http://ha.local:8123/api/services/light/turn_off",
                 {"entity_id": ["light.ceiling"]}),
                ("http://ha.local:8123/api/services/homeassistant/turn_off",
                 {"entity_id": ["switch.led_strip"]}),
            ],
            [(url, kwargs["json"]) for _, url, kwargs in http.calls],
        )
        _, _, kwargs = http.calls[0]
        self.assertEqual("Bearer secret-token", kwargs["headers"]["Authorization"])
        self.assertEqual(3, kwargs["timeout"])

    def test_restore_after_playback_uses_stop_action(self):
        http = RecordingHttpSession()
        controller = _controller(_config(), http)

        controller.restore_after_playback()

        self.assertEqual(
            ["/api/services/light/turn_on", "/api/services/homeassistant/turn_on"],
            [url.removeprefix("http://ha.local:8123") for _, url, _ in http.calls],
        )

    def test_fade_out_is_sent_as_light_transition_when_turning_off(self):
        http = RecordingHttpSession()
        controller = _controller(_config(fade_out_seconds=4, fade_in_seconds=2.5), http)

        result = controller.prepare_for_playback()

        light_call, switch_call = http.calls
        self.assertEqual(
            {"entity_id": ["light.ceiling"], "transition": 4.0}, light_call[2]["json"]
        )
        # The request timeout leaves room for integrations that only answer
        # once the transition has finished.
        self.assertEqual(7.0, light_call[2]["timeout"])
        # Switches do not accept transition; sending it would fail the call.
        self.assertEqual({"entity_id": ["switch.led_strip"]}, switch_call[2]["json"])
        self.assertIn("4s fade", result.detail)

    def test_fade_in_is_sent_as_light_transition_when_turning_on(self):
        http = RecordingHttpSession()
        controller = _controller(_config(fade_out_seconds=4, fade_in_seconds=2.5), http)

        controller.restore_after_playback()

        self.assertEqual(2.5, http.calls[0][2]["json"]["transition"])

    def test_manual_buttons_use_the_same_fade(self):
        http = RecordingHttpSession()
        controller = _controller(_config(fade_out_seconds=3, entity_ids=["light.ceiling"]), http)

        controller.turn_off()

        self.assertEqual(3.0, http.calls[0][2]["json"]["transition"])

    def test_zero_fade_sends_no_transition(self):
        http = RecordingHttpSession()
        controller = _controller(_config(fade_out_seconds=0, entity_ids=["light.ceiling"]), http)

        controller.turn_off()

        self.assertNotIn("transition", http.calls[0][2]["json"])

    def test_blank_or_invalid_fade_values_mean_no_fade(self):
        for value in ("", None, "abc", -5, float("nan")):
            with self.subTest(value=value):
                http = RecordingHttpSession()
                controller = _controller(
                    _config(fade_out_seconds=value, entity_ids=["light.ceiling"]), http
                )

                self.assertTrue(controller.turn_off().successful)
                self.assertNotIn("transition", http.calls[0][2]["json"])

    def test_fade_is_capped(self):
        http = RecordingHttpSession()
        controller = _controller(
            _config(fade_in_seconds=99999, entity_ids=["light.ceiling"]), http
        )

        controller.turn_on()

        self.assertEqual(300.0, http.calls[0][2]["json"]["transition"])

    def test_only_switches_use_generic_service_without_transition(self):
        http = RecordingHttpSession()
        controller = _controller(_config(fade_out_seconds=5, entity_ids=["switch.led_strip"]), http)

        controller.turn_off()

        self.assertEqual(1, len(http.calls))
        self.assertTrue(http.calls[0][1].endswith("/api/services/homeassistant/turn_off"))
        self.assertEqual({"entity_id": ["switch.led_strip"]}, http.calls[0][2]["json"])

    def test_none_action_skips_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = _controller(_config(on_playback_stop="none"), http)

        result = controller.restore_after_playback()

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)
        self.assertEqual([], http.calls)

    def test_unknown_action_fails_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = _controller(_config(on_playback_start="blink"), http)

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertEqual([], http.calls)

    def test_missing_token_fails_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = _controller(_config(token=""), http)

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("token", result.detail)
        self.assertEqual([], http.calls)

    def test_no_entities_is_skipped(self):
        http = RecordingHttpSession()
        controller = _controller(_config(entity_ids=["  "]), http)

        result = controller.turn_off()

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)
        self.assertEqual([], http.calls)

    def test_http_error_status_is_reported_as_failure(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=500))
        controller = _controller(_config(), http)

        result = controller.turn_on()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("500", result.detail)

    def test_network_error_is_reported_as_failure_not_raised(self):
        http = RecordingHttpSession(error=requests.ConnectionError("refused"))
        controller = _controller(_config(), http)

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("ConnectionError", result.detail)


class LightingFactoryTest(unittest.TestCase):
    def test_returns_none_when_disabled(self):
        self.assertIsNone(create_lighting_controller_or_none(_config(enabled=False)))
        self.assertIsNone(create_lighting_controller_or_none({}))

    def test_returns_controller_when_enabled(self):
        self.assertIsInstance(
            create_lighting_controller_or_none(_config()),
            HomeAssistantLightingController,
        )


if __name__ == "__main__":
    unittest.main()
