import json
import os
import tempfile
import unittest
from pathlib import Path

from home_cinema_control.config.manager import (
    load_effective_config,
    merge_existing_secrets,
    sanitize_config_for_web,
    save_effective_config,
)
from home_cinema_control.config.models import HccConfig
from home_cinema_control.web.config_readiness import compute_config_readiness
from home_cinema_control.web.config_sections import apply_config_section
from home_cinema_control.web.setup_verification import mark_section_verified
from home_cinema_control.web.support_report import collect_redaction_targets

_SECRETS_ENV = "HCC_SECRETS_FILE_PATH"


class HomeAssistantSecretsTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._dir = Path(self._tmpdir.name)
        self._config_path = self._dir / "config.json"
        self._secrets_path = self._dir / "secrets.json"
        self._config_path.write_text("{}", encoding="utf-8")
        self._secrets_path.write_text("{}", encoding="utf-8")
        self._prev = os.environ.get(_SECRETS_ENV)
        os.environ[_SECRETS_ENV] = str(self._secrets_path)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop(_SECRETS_ENV, None)
        else:
            os.environ[_SECRETS_ENV] = self._prev
        self._tmpdir.cleanup()

    def test_token_is_written_to_secrets_not_config(self):
        save_effective_config(self._config_path, {
            "home_assistant": {"url": "http://ha.local:8123", "token": "secret-token"},
            "lighting": {"enabled": True, "entity_ids": ["light.ceiling"]},
        })

        config_data = json.loads(self._config_path.read_text())
        secrets_data = json.loads(self._secrets_path.read_text())

        self.assertNotIn("token", config_data["home_assistant"])
        self.assertEqual("http://ha.local:8123", config_data["home_assistant"]["url"])
        self.assertEqual(["light.ceiling"], config_data["lighting"]["entity_ids"])
        self.assertEqual("secret-token", secrets_data["home_assistant"]["token"])
        self.assertEqual(
            "secret-token",
            load_effective_config(self._config_path)["home_assistant"]["token"],
        )

    def test_blank_submitted_token_keeps_stored_token(self):
        save_effective_config(self._config_path, {"home_assistant": {"token": "stored"}})

        merged = merge_existing_secrets(
            self._config_path, {"home_assistant": {"token": ""}}
        )

        self.assertEqual("stored", merged["home_assistant"]["token"])

    def test_sanitize_hides_token_and_reports_it_configured(self):
        result = sanitize_config_for_web({"home_assistant": {"token": "secret-token"}})

        self.assertNotIn("token", result["home_assistant"])
        self.assertTrue(result["home_assistant"]["token_configured"])

    def test_sanitize_reports_token_missing(self):
        result = sanitize_config_for_web({})

        self.assertFalse(result["home_assistant"]["token_configured"])

    def test_support_report_redacts_token_and_url(self):
        targets = collect_redaction_targets({"home_assistant": {
            "token": "secret-token",
            "url": "http://ha.local:8123",
        }})

        self.assertEqual("CREDENTIAL", targets["secret-token"])
        self.assertEqual("URL", targets["http://ha.local:8123"])


class LightingConfigModelTest(unittest.TestCase):
    def test_defaults(self):
        config = HccConfig()

        self.assertEqual("", config.home_assistant.url)
        self.assertFalse(config.lighting.enabled)
        self.assertEqual([], config.lighting.entity_ids)
        self.assertEqual("turn_off", config.lighting.on_playback_start)
        self.assertEqual("turn_on", config.lighting.on_playback_stop)

    def test_lighting_section_patch_keeps_other_sections(self):
        config = {"tv": {"enabled": True}, "lighting": {"on_playback_stop": "none"}}

        updated = apply_config_section(
            config, "lighting", {"entity_ids": ["light.ceiling", "switch.led_strip"]}
        )

        self.assertEqual({"enabled": True}, updated["tv"])
        self.assertEqual("none", updated["lighting"]["on_playback_stop"])
        self.assertEqual(
            ["light.ceiling", "switch.led_strip"], updated["lighting"]["entity_ids"]
        )

    def test_home_assistant_section_patch(self):
        updated = apply_config_section(
            {"lighting": {"enabled": True}}, "home_assistant", {"url": "http://ha.local:8123"}
        )

        self.assertEqual("http://ha.local:8123", updated["home_assistant"]["url"])
        self.assertEqual({"enabled": True}, updated["lighting"])


class HomeAssistantReadinessTest(unittest.TestCase):
    def _config(self, *, url="http://ha.local:8123", token_configured=True, **lighting):
        return {
            "home_assistant": {"url": url, "token_configured": token_configured},
            "lighting": {"enabled": True, "entity_ids": ["light.ceiling"], **lighting},
        }

    def _status(self, config, section):
        return compute_config_readiness(config)[section]["status"]

    def test_disabled_by_default(self):
        self.assertEqual("disabled", self._status({}, "home_assistant"))
        self.assertEqual("disabled", self._status({}, "lighting"))

    def test_home_assistant_incomplete_without_token(self):
        self.assertEqual(
            "incomplete", self._status(self._config(token_configured=False), "home_assistant")
        )

    def test_lighting_incomplete_without_home_assistant_or_entities(self):
        self.assertEqual("incomplete", self._status(self._config(url=""), "lighting"))
        self.assertEqual(
            "incomplete", self._status(self._config(token_configured=False), "lighting")
        )
        self.assertEqual("incomplete", self._status(self._config(entity_ids=[]), "lighting"))
        self.assertEqual("configured", self._status(self._config(), "lighting"))

    def test_home_assistant_verified_then_stale_when_url_changes(self):
        config = self._config()
        self.assertEqual("configured", self._status(config, "home_assistant"))

        verified = mark_section_verified(config, "home_assistant")
        self.assertEqual("verified", self._status(verified, "home_assistant"))

        verified["lighting"]["entity_ids"] = ["light.other"]
        self.assertEqual("verified", self._status(verified, "home_assistant"))

        verified["home_assistant"]["url"] = "http://other:8123"
        self.assertEqual("stale", self._status(verified, "home_assistant"))


if __name__ == "__main__":
    unittest.main()
