import unittest

import requests

from home_cinema_control.devices.lighting.factory import (
    create_lighting_controller_or_none,
)
from home_cinema_control.devices.lighting.home_assistant import (
    HomeAssistantLightingController,
    LightingEntity,
)
from home_cinema_control.playback.startup.models import DeviceCommandStatus


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class RecordingHttpSession:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        return self._record("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._record("POST", url, kwargs)

    def _record(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def _config(**overrides):
    lighting = {
        "enabled": True,
        "home_assistant_url": "http://ha.local:8123/",
        "home_assistant_token": "secret-token",
        "entity_ids": ["light.ceiling", "switch.led_strip"],
        "on_playback_start": "turn_off",
        "on_playback_stop": "turn_on",
        "timeout_seconds": 3,
    }
    lighting.update(overrides)
    return {"lighting": lighting}


class HomeAssistantLightingControllerTest(unittest.TestCase):
    def test_prepare_for_playback_calls_configured_service_on_all_entities(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(_config(), http_session=http)

        result = controller.prepare_for_playback()

        self.assertTrue(result.successful)
        method, url, kwargs = http.calls[0]
        self.assertEqual("POST", method)
        self.assertEqual("http://ha.local:8123/api/services/homeassistant/turn_off", url)
        self.assertEqual({"entity_id": ["light.ceiling", "switch.led_strip"]}, kwargs["json"])
        self.assertEqual("Bearer secret-token", kwargs["headers"]["Authorization"])
        self.assertEqual(3, kwargs["timeout"])

    def test_restore_after_playback_uses_stop_action(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(_config(), http_session=http)

        controller.restore_after_playback()

        self.assertTrue(http.calls[0][1].endswith("/api/services/homeassistant/turn_on"))

    def test_none_action_skips_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(
            _config(on_playback_stop="none"), http_session=http
        )

        result = controller.restore_after_playback()

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)
        self.assertEqual([], http.calls)

    def test_unknown_action_fails_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(
            _config(on_playback_start="blink"), http_session=http
        )

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertEqual([], http.calls)

    def test_missing_token_fails_without_calling_home_assistant(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(
            _config(home_assistant_token=""), http_session=http
        )

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("token", result.detail)
        self.assertEqual([], http.calls)

    def test_no_entities_is_skipped(self):
        http = RecordingHttpSession()
        controller = HomeAssistantLightingController(
            _config(entity_ids=["  "]), http_session=http
        )

        result = controller.turn_off()

        self.assertEqual(DeviceCommandStatus.SKIPPED, result.status)
        self.assertEqual([], http.calls)

    def test_http_error_status_is_reported_as_failure(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=500))
        controller = HomeAssistantLightingController(_config(), http_session=http)

        result = controller.turn_on()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("500", result.detail)

    def test_network_error_is_reported_as_failure_not_raised(self):
        http = RecordingHttpSession(error=requests.ConnectionError("refused"))
        controller = HomeAssistantLightingController(_config(), http_session=http)

        result = controller.prepare_for_playback()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("ConnectionError", result.detail)

    def test_connection_test_reports_rejected_token(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=401))
        controller = HomeAssistantLightingController(_config(), http_session=http)

        result = controller.test_connection()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("token", result.detail)
        self.assertEqual("http://ha.local:8123/api/", http.calls[0][1])

    def test_connection_test_succeeds_on_api_running(self):
        http = RecordingHttpSession(response=FakeResponse(payload={"message": "API running."}))
        controller = HomeAssistantLightingController(_config(), http_session=http)

        self.assertTrue(controller.test_connection().successful)

    def test_list_entities_keeps_only_lights_and_switches_sorted_by_name(self):
        http = RecordingHttpSession(response=FakeResponse(payload=[
            {"entity_id": "switch.led_strip", "state": "off",
             "attributes": {"friendly_name": "Tira LED"}},
            {"entity_id": "sensor.temperature", "state": "21",
             "attributes": {"friendly_name": "Temperatura"}},
            {"entity_id": "light.ceiling", "state": "on",
             "attributes": {"friendly_name": "Luces techo"}},
            {"entity_id": "light.no_name", "state": "off", "attributes": {}},
        ]))
        controller = HomeAssistantLightingController(_config(), http_session=http)

        entities = controller.list_entities()

        self.assertEqual(
            [
                LightingEntity("light.no_name", "light.no_name", "off"),
                LightingEntity("light.ceiling", "Luces techo", "on"),
                LightingEntity("switch.led_strip", "Tira LED", "off"),
            ],
            entities,
        )
        self.assertEqual("http://ha.local:8123/api/states", http.calls[0][1])


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
