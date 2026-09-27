import unittest

import requests

from home_cinema_control.devices.home_assistant.client import (
    HomeAssistantClient,
    HomeAssistantEntity,
    HomeAssistantError,
)
from home_cinema_control.playback.startup.models import DeviceCommandStatus
from tests.home_assistant_fakes import FakeResponse, RecordingHttpSession


def _client(http, *, url="http://ha.local:8123/", token="secret-token"):
    config = {"home_assistant": {"url": url, "token": token, "timeout_seconds": 3}}
    return HomeAssistantClient(config, http_session=http)


class HomeAssistantClientTest(unittest.TestCase):
    def test_connection_test_reports_rejected_token(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=401))

        result = _client(http).test_connection()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("token", result.detail)
        self.assertEqual("http://ha.local:8123/api/", http.calls[0][1])
        self.assertEqual("Bearer secret-token", http.calls[0][2]["headers"]["Authorization"])

    def test_connection_test_succeeds_on_api_running(self):
        http = RecordingHttpSession(response=FakeResponse(payload={"message": "API running."}))

        self.assertTrue(_client(http).test_connection().successful)

    def test_connection_test_reports_unreachable(self):
        http = RecordingHttpSession(error=requests.ConnectionError("refused"))

        result = _client(http).test_connection()

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("unreachable", result.detail)

    def test_missing_settings_fail_without_calling_home_assistant(self):
        http = RecordingHttpSession()

        self.assertIn("URL", _client(http, url="").test_connection().detail)
        self.assertIn("token", _client(http, token="").test_connection().detail)
        self.assertFalse(_client(http, token="").configured)
        self.assertEqual([], http.calls)

    def test_list_entities_filters_by_domain_and_sorts_by_name(self):
        http = RecordingHttpSession(response=FakeResponse(payload=[
            {"entity_id": "switch.led_strip", "state": "off",
             "attributes": {"friendly_name": "Tira LED"}},
            {"entity_id": "sensor.temperature", "state": "21",
             "attributes": {"friendly_name": "Temperatura"}},
            {"entity_id": "light.ceiling", "state": "on",
             "attributes": {"friendly_name": "Luces techo"}},
            {"entity_id": "light.no_name", "state": "off", "attributes": {}},
        ]))

        entities = _client(http).list_entities(["light", "switch"])

        self.assertEqual(
            [
                HomeAssistantEntity("light.no_name", "light.no_name", "off"),
                HomeAssistantEntity("light.ceiling", "Luces techo", "on"),
                HomeAssistantEntity("switch.led_strip", "Tira LED", "off"),
            ],
            entities,
        )
        self.assertEqual("http://ha.local:8123/api/states", http.calls[0][1])

    def test_list_entities_raises_on_http_error(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=401))

        with self.assertRaises(HomeAssistantError):
            _client(http).list_entities(["light"])

    def test_get_state_reads_one_entity(self):
        http = RecordingHttpSession(response=FakeResponse(
            payload={"entity_id": "switch.nas11", "state": "on"}
        ))

        self.assertEqual("on", _client(http).get_state("switch.nas11"))
        self.assertEqual("http://ha.local:8123/api/states/switch.nas11", http.calls[0][1])

    def test_get_state_raises_when_unreachable(self):
        http = RecordingHttpSession(error=requests.ConnectTimeout("slow"))

        with self.assertRaises(HomeAssistantError):
            _client(http).get_state("switch.nas11")

    def test_call_service_posts_payload_with_extra_timeout(self):
        http = RecordingHttpSession()

        result = _client(http).call_service(
            "switch", "turn_on", {"entity_id": "switch.nas11"}, extra_timeout_seconds=2
        )

        self.assertTrue(result.successful)
        method, url, kwargs = http.calls[0]
        self.assertEqual("POST", method)
        self.assertEqual("http://ha.local:8123/api/services/switch/turn_on", url)
        self.assertEqual({"entity_id": "switch.nas11"}, kwargs["json"])
        self.assertEqual(5, kwargs["timeout"])

    def test_call_service_reports_http_error(self):
        http = RecordingHttpSession(response=FakeResponse(status_code=500))

        result = _client(http).call_service("light", "turn_on", {"entity_id": ["light.a"]})

        self.assertEqual(DeviceCommandStatus.FAILED, result.status)
        self.assertIn("500", result.detail)


if __name__ == "__main__":
    unittest.main()
