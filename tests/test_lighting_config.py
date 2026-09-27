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


class LightingSecretsTest(unittest.TestCase):
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
        save_effective_config(self._config_path, {"lighting": {
            "enabled": True,
            "home_assistant_url": "http://ha.local:8123",
            "home_assistant_token": "secret-token",
            "entity_ids": ["light.ceiling"],
        }})

        config_data = json.loads(self._config_path.read_text())
        secrets_data = json.loads(self._secrets_path.read_text())

        self.assertNotIn("home_assistant_token", config_data["lighting"])
        self.assertEqual(["light.ceiling"], config_data["lighting"]["entity_ids"])
        self.assertEqual("secret-token", secrets_data["lighting"]["home_assistant_token"])
        self.assertEqual(
            "secret-token",
            load_effective_config(self._config_path)["lighting"]["home_assistant_token"],
        )

    def test_blank_submitted_token_keeps_stored_token(self):
        save_effective_config(self._config_path, {"lighting": {"home_assistant_token": "stored"}})

        merged = merge_existing_secrets(
            self._config_path, {"lighting": {"home_assistant_token": ""}}
        )

        self.assertEqual("stored", merged["lighting"]["home_assistant_token"])

    def test_sanitize_hides_token_and_reports_it_configured(self):
        result = sanitize_config_for_web({"lighting": {"home_assistant_token": "secret-token"}})

        self.assertNotIn("home_assistant_token", result["lighting"])
        self.assertTrue(result["lighting"]["home_assistant_token_configured"])

    def test_sanitize_reports_token_missing(self):
        result = sanitize_config_for_web({})

        self.assertFalse(result["lighting"]["home_assistant_token_configured"])

    def test_support_report_redacts_token_and_url(self):
        targets = collect_redaction_targets({"lighting": {
            "home_assistant_token": "secret-token",
            "home_assistant_url": "http://ha.local:8123",
        }})

        self.assertEqual("CREDENTIAL", targets["secret-token"])
        self.assertEqual("URL", targets["http://ha.local:8123"])


class LightingConfigModelTest(unittest.TestCase):
    def test_defaults(self):
        lighting = HccConfig().lighting

        self.assertFalse(lighting.enabled)
        self.assertEqual([], lighting.entity_ids)
        self.assertEqual("turn_off", lighting.on_playback_start)
        self.assertEqual("turn_on", lighting.on_playback_stop)

    def test_lighting_section_patch_keeps_other_sections(self):
        config = {"tv": {"enabled": True}, "lighting": {"home_assistant_url": "http://old"}}

        updated = apply_config_section(
            config, "lighting", {"entity_ids": ["light.ceiling", "switch.led_strip"]}
        )

        self.assertEqual({"enabled": True}, updated["tv"])
        self.assertEqual("http://old", updated["lighting"]["home_assistant_url"])
        self.assertEqual(
            ["light.ceiling", "switch.led_strip"], updated["lighting"]["entity_ids"]
        )


class LightingReadinessTest(unittest.TestCase):
    def _lighting(self, **overrides):
        lighting = {
            "enabled": True,
            "home_assistant_url": "http://ha.local:8123",
            "home_assistant_token_configured": True,
            "entity_ids": ["light.ceiling"],
        }
        lighting.update(overrides)
        return {"lighting": lighting}

    def _status(self, config):
        return compute_config_readiness(config)["lighting"]["status"]

    def test_disabled_by_default(self):
        self.assertEqual("disabled", self._status({}))

    def test_incomplete_without_url_token_or_entities(self):
        self.assertEqual("incomplete", self._status(self._lighting(home_assistant_url="")))
        self.assertEqual(
            "incomplete", self._status(self._lighting(home_assistant_token_configured=False))
        )
        self.assertEqual("incomplete", self._status(self._lighting(entity_ids=[])))

    def test_entity_changes_keep_verification_but_url_changes_make_it_stale(self):
        config = self._lighting()
        self.assertEqual("configured", self._status(config))

        verified = mark_section_verified(config, "lighting")
        self.assertEqual("verified", self._status(verified))

        verified["lighting"]["entity_ids"] = ["light.other"]
        self.assertEqual("verified", self._status(verified))

        verified["lighting"]["home_assistant_url"] = "http://other:8123"
        self.assertEqual("stale", self._status(verified))


if __name__ == "__main__":
    unittest.main()
