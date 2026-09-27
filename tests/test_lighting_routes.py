import unittest
from unittest.mock import patch

from home_cinema_control.playback.startup.models import DeviceCommandResult
from tests.test_api_routes import _make_client

_SETUP = "home_cinema_control.web.lighting_routes"

_BODY = {
    "lighting": {
        "enabled": True,
        "home_assistant_url": "http://ha.local:8123",
        "home_assistant_token": "secret-token",
        "entity_ids": ["light.ceiling"],
    }
}


class LightingRoutesTest(unittest.TestCase):
    def test_successful_connection_test_persists_verified_config(self):
        client, _, config_service = _make_client()

        with patch(f"{_SETUP}.test_lighting_connection",
                   return_value=DeviceCommandResult.success()):
            resp = client.post("/api/v1/lighting/test-connection", json=_BODY)

        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()["verification_persisted"])
        saved = config_service.save_config.call_args.args[0]
        self.assertEqual("ok", saved["setup_verification"]["lighting"]["status"])

    def test_failed_connection_test_returns_400_and_sets_diagnostic(self):
        client, runtime, config_service = _make_client()

        with patch(f"{_SETUP}.test_lighting_connection",
                   return_value=DeviceCommandResult.failed("Home Assistant rejected the access token.")):
            resp = client.post("/api/v1/lighting/test-connection", json=_BODY)

        self.assertEqual(400, resp.status_code)
        self.assertIn("token", resp.json()["detail"])
        config_service.save_config.assert_not_called()
        diagnostic = runtime.set_last_diagnostic.call_args.args[0]
        self.assertEqual("LIGHTING_CONNECTION_TEST_FAILED", diagnostic.code)

    def test_entities_returns_detected_entities(self):
        client, _, _ = _make_client()
        entities = [{"entity_id": "light.ceiling", "name": "Techo", "state": "on"}]

        with patch(f"{_SETUP}.list_lighting_entities", return_value=entities):
            resp = client.post("/api/v1/lighting/entities", json=_BODY)

        self.assertEqual(200, resp.status_code)
        self.assertEqual({"entities": entities}, resp.json())

    def test_entities_failure_returns_400(self):
        client, _, _ = _make_client()

        with patch(f"{_SETUP}.list_lighting_entities",
                   side_effect=ValueError("Home Assistant returned HTTP 401.")):
            resp = client.post("/api/v1/lighting/entities", json=_BODY)

        self.assertEqual(400, resp.status_code)

    def test_turn_off_reports_result(self):
        client, _, _ = _make_client()

        with patch(f"{_SETUP}.turn_lighting_off",
                   return_value=DeviceCommandResult.success("ok")):
            resp = client.post("/api/v1/lighting/turn-off", json=_BODY)

        self.assertEqual(200, resp.status_code)
        self.assertEqual("success", resp.json()["status"])

    def test_turn_on_failure_returns_400(self):
        client, _, _ = _make_client()

        with patch(f"{_SETUP}.turn_lighting_on",
                   return_value=DeviceCommandResult.failed("unreachable")):
            resp = client.post("/api/v1/lighting/turn-on", json=_BODY)

        self.assertEqual(400, resp.status_code)

    def test_readiness_includes_lighting(self):
        client, _, _ = _make_client(config={
            "lighting": {
                "enabled": True,
                "home_assistant_url": "http://ha.local:8123",
                "home_assistant_token_configured": True,
                "entity_ids": ["light.ceiling", "switch.led_strip"],
            }
        })

        resp = client.get("/api/v1/config/readiness")

        self.assertEqual("configured", resp.json()["lighting"]["status"])


if __name__ == "__main__":
    unittest.main()
