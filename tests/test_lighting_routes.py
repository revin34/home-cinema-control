import unittest
from unittest.mock import patch

from home_cinema_control.devices.home_assistant.client import HomeAssistantError
from home_cinema_control.playback.startup.models import DeviceCommandResult
from tests.test_api_routes import _make_client

_HA = "home_cinema_control.web.home_assistant_routes"
_LIGHTING = "home_cinema_control.web.lighting_routes"

_BODY = {
    "home_assistant": {"url": "http://ha.local:8123", "token": "secret-token"},
    "lighting": {"enabled": True, "entity_ids": ["light.ceiling"]},
}


class HomeAssistantRoutesTest(unittest.TestCase):
    def test_successful_connection_test_persists_verified_config(self):
        client, _, config_service = _make_client()

        with patch(f"{_HA}.test_home_assistant_connection",
                   return_value=DeviceCommandResult.success()):
            resp = client.post("/api/v1/home-assistant/test-connection", json=_BODY)

        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()["verification_persisted"])
        saved = config_service.save_config.call_args.args[0]
        self.assertEqual("ok", saved["setup_verification"]["home_assistant"]["status"])

    def test_failed_connection_test_returns_400_and_sets_diagnostic(self):
        client, runtime, config_service = _make_client()

        with patch(f"{_HA}.test_home_assistant_connection",
                   return_value=DeviceCommandResult.failed("Home Assistant rejected the access token.")):
            resp = client.post("/api/v1/home-assistant/test-connection", json=_BODY)

        self.assertEqual(400, resp.status_code)
        self.assertIn("token", resp.json()["detail"])
        config_service.save_config.assert_not_called()
        diagnostic = runtime.set_last_diagnostic.call_args.args[0]
        self.assertEqual("HOME_ASSISTANT_CONNECTION_TEST_FAILED", diagnostic.code)

    def test_entities_uses_requested_domains(self):
        client, _, _ = _make_client()
        entities = [{"entity_id": "switch.nas11", "name": "nas11", "state": "off"}]

        with patch(f"{_HA}.list_home_assistant_entities", return_value=entities) as listing:
            resp = client.post(
                "/api/v1/home-assistant/entities?domains=switch,input_boolean", json=_BODY
            )

        self.assertEqual(200, resp.status_code)
        self.assertEqual({"entities": entities}, resp.json())
        self.assertEqual(["input_boolean", "switch"], listing.call_args.args[1])

    def test_entities_defaults_to_lighting_domains(self):
        client, _, _ = _make_client()

        with patch(f"{_HA}.list_home_assistant_entities", return_value=[]) as listing:
            client.post("/api/v1/home-assistant/entities", json=_BODY)

        self.assertEqual(["light", "switch"], listing.call_args.args[1])

    def test_entities_rejects_unsupported_domains(self):
        client, _, _ = _make_client()

        resp = client.post("/api/v1/home-assistant/entities?domains=lock", json=_BODY)

        self.assertEqual(400, resp.status_code)

    def test_entities_failure_returns_400(self):
        client, _, _ = _make_client()

        with patch(f"{_HA}.list_home_assistant_entities",
                   side_effect=HomeAssistantError("Home Assistant returned HTTP 401.")):
            resp = client.post("/api/v1/home-assistant/entities", json=_BODY)

        self.assertEqual(400, resp.status_code)


class LightingRoutesTest(unittest.TestCase):
    def test_turn_off_reports_result(self):
        client, _, _ = _make_client()

        with patch(f"{_LIGHTING}.turn_lighting_off",
                   return_value=DeviceCommandResult.success("ok")):
            resp = client.post("/api/v1/lighting/turn-off", json=_BODY)

        self.assertEqual(200, resp.status_code)
        self.assertEqual("success", resp.json()["status"])

    def test_turn_on_failure_returns_400(self):
        client, _, _ = _make_client()

        with patch(f"{_LIGHTING}.turn_lighting_on",
                   return_value=DeviceCommandResult.failed("unreachable")):
            resp = client.post("/api/v1/lighting/turn-on", json=_BODY)

        self.assertEqual(400, resp.status_code)

    def test_readiness_includes_home_assistant_and_lighting(self):
        client, _, _ = _make_client(config={
            "home_assistant": {"url": "http://ha.local:8123", "token_configured": True},
            "lighting": {"enabled": True, "entity_ids": ["light.ceiling", "switch.led_strip"]},
        })

        data = client.get("/api/v1/config/readiness").json()

        self.assertEqual("configured", data["home_assistant"]["status"])
        self.assertEqual("configured", data["lighting"]["status"])


if __name__ == "__main__":
    unittest.main()
