import unittest

from home_cinema_control.devices.home_assistant.client import HomeAssistantError
from home_cinema_control.devices.tv.adapters.home_assistant import (
    HDMI_INPUTS,
    HomeAssistantTvController,
)
from home_cinema_control.devices.tv.factory import (
    create_tv_controller,
    get_supported_tv_models,
)
from home_cinema_control.devices.tv.models import TvInputTarget
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    DeviceCommandStatus,
)
from home_cinema_control.web.config_readiness import compute_config_readiness


class FakeHomeAssistant:
    def __init__(self, states=None, *, activity="com.tcl.tv", error=None, configured=True):
        # states: successive "on"/"off" answers for the remote entity.
        self.states = list(states or ["on"])
        self.activity = activity
        self.error = error
        self.configured = configured
        self.services = []

    def missing_settings(self):
        return None if self.configured else "Home Assistant URL not configured."

    def get_state(self, entity_id):
        return self.get_entity(entity_id)["state"]

    def get_entity(self, entity_id):
        if self.error is not None:
            raise self.error
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return {"entity_id": entity_id, "state": state,
                "attributes": {"current_activity": self.activity}}

    def call_service(self, domain, service, data, **kwargs):
        self.services.append((domain, service, data))
        return DeviceCommandResult.success()


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _controller(client, *, entity="remote.cine_tv"):
    clock = Clock()
    config = {"tv": {"enabled": True, "model": "HOME_ASSISTANT", "ha_remote_entity_id": entity}}
    return HomeAssistantTvController(
        config, client=client, sleep=clock.sleep, monotonic=clock.monotonic
    ), clock, config


class HomeAssistantTvControllerTest(unittest.TestCase):
    def test_is_offered_as_a_tv_model(self):
        self.assertIn("HOME_ASSISTANT", get_supported_tv_models())
        self.assertIsInstance(
            create_tv_controller({"tv": {"model": "home_assistant"}}), HomeAssistantTvController
        )

    def test_connection_ok_when_remote_entity_is_available(self):
        controller, _, config = _controller(FakeHomeAssistant(["off"]))

        self.assertTrue(controller.test_connection().successful)
        self.assertEqual(HDMI_INPUTS, config["tv"]["available_hdmi_inputs"])

    def test_connection_fails_when_entity_unavailable_or_missing(self):
        unavailable, _, _ = _controller(FakeHomeAssistant(["unavailable"]))
        no_entity, _, _ = _controller(FakeHomeAssistant(), entity="")
        no_ha, _, _ = _controller(FakeHomeAssistant(configured=False))
        unreachable, _, _ = _controller(FakeHomeAssistant(error=HomeAssistantError("down")))

        for controller in (unavailable, no_entity, no_ha, unreachable):
            with self.subTest(controller=controller):
                self.assertEqual(DeviceCommandStatus.FAILED, controller.test_connection().status)

    def test_inputs_are_hdmi_key_codes(self):
        controller, _, config = _controller(FakeHomeAssistant())

        controller.retrieve_hdmi_inputs()

        self.assertEqual(HDMI_INPUTS, config["tv"]["available_hdmi_inputs"])
        self.assertEqual(
            {"id": "content://android.media.tv/passthrough/"
                   "com.tcl.tvinput%2F.passthrough.HDMIInputService%2FHW15",
             "name": "HDMI 1 (TCL)"},
            config["tv"]["available_hdmi_inputs"][0],
        )
        self.assertEqual(
            {"id": "KEYCODE_TV_INPUT_HDMI_2", "name": "HDMI 2 (Android key)"},
            config["tv"]["available_hdmi_inputs"][5],
        )

    def test_switch_when_tv_is_on_sends_only_the_input_key(self):
        client = FakeHomeAssistant(["on"])
        controller, _, _ = _controller(client)

        result = controller.switch_to_input(TvInputTarget("KEYCODE_TV_INPUT_HDMI_2"))

        self.assertTrue(result.successful)
        self.assertEqual(
            [("remote", "send_command",
              {"entity_id": "remote.cine_tv", "command": "KEYCODE_TV_INPUT_HDMI_2"})],
            client.services,
        )

    def test_switch_powers_on_waits_then_sends_the_input_key(self):
        client = FakeHomeAssistant(["off", "off", "off", "on"])
        controller, clock, _ = _controller(client)

        result = controller.switch_to_input(TvInputTarget("KEYCODE_TV_INPUT_HDMI_1"))

        self.assertTrue(result.successful)
        self.assertEqual(
            [("remote", "turn_on", {"entity_id": "remote.cine_tv"}),
             ("remote", "send_command",
              {"entity_id": "remote.cine_tv", "command": "KEYCODE_TV_INPUT_HDMI_1"})],
            client.services,
        )
        self.assertEqual([1.0, 1.0, 1.0, 2.0], clock.sleeps)

    def test_switch_still_sends_the_key_if_power_state_never_confirms(self):
        client = FakeHomeAssistant(["off"])
        controller, clock, _ = _controller(client)

        with self.assertLogs(
            "home_cinema_control.devices.tv.adapters.home_assistant", "WARNING"
        ):
            result = controller.switch_to_input(TvInputTarget("KEYCODE_TV_INPUT_HDMI_1"))

        self.assertTrue(result.successful)
        self.assertEqual("send_command", client.services[-1][1])
        self.assertGreaterEqual(clock.now, 20)

    def test_switch_opens_tv_input_uris_as_an_activity(self):
        client = FakeHomeAssistant(["on"])
        controller, _, _ = _controller(client)
        uri = HDMI_INPUTS[0]["id"]

        result = controller.switch_to_input(TvInputTarget(uri))

        self.assertTrue(result.successful)
        self.assertEqual(
            [("remote", "turn_on", {"entity_id": "remote.cine_tv", "activity": uri})],
            client.services,
        )

    def test_hand_edited_input_command_wins_over_the_preset(self):
        client = FakeHomeAssistant(["on"])
        controller, _, config = _controller(client)
        config["tv"]["ha_input_command"] = " content://custom/input "
        controller = HomeAssistantTvController(config, client=client)

        controller.switch_to_input(TvInputTarget("KEYCODE_TV_INPUT_HDMI_1"))

        self.assertEqual(
            ("remote", "turn_on", {"entity_id": "remote.cine_tv", "activity": "content://custom/input"}),
            client.services[-1],
        )

    def test_switch_without_selected_input_fails(self):
        controller, _, _ = _controller(FakeHomeAssistant())

        self.assertEqual(
            DeviceCommandStatus.FAILED, controller.switch_to_input(TvInputTarget("")).status
        )

    def test_launch_app_uses_remote_activity(self):
        client = FakeHomeAssistant()
        controller, _, _ = _controller(client)

        self.assertTrue(controller.launch_app("tv.emby.embyatv").successful)
        self.assertEqual(
            [("remote", "turn_on",
              {"entity_id": "remote.cine_tv", "activity": "tv.emby.embyatv"})],
            client.services,
        )

    def test_launch_without_app_is_skipped(self):
        client = FakeHomeAssistant()
        controller, _, _ = _controller(client)

        self.assertEqual(DeviceCommandStatus.SKIPPED, controller.launch_app(None).status)
        self.assertEqual([], client.services)

    def test_current_app_comes_from_current_activity(self):
        controller, _, _ = _controller(FakeHomeAssistant(activity="tv.emby.embyatv"))

        self.assertEqual("tv.emby.embyatv", controller.get_current_app_id())

    def test_current_app_is_none_when_home_assistant_fails(self):
        controller, _, _ = _controller(FakeHomeAssistant(error=HomeAssistantError("down")))

        self.assertIsNone(controller.get_current_app_id())

    def test_media_server_apps(self):
        controller, _, _ = _controller(FakeHomeAssistant())

        self.assertEqual("tv.emby.embyatv", controller.media_server_app_id("emby"))
        self.assertEqual("org.jellyfin.androidtv", controller.media_server_app_id("jellyfin"))
        self.assertIsNone(controller.media_server_app_id("plex"))


class HomeAssistantTvReadinessTest(unittest.TestCase):
    def _status(self, *, token=True, entity="remote.cine_tv"):
        config = {
            "home_assistant": {"url": "http://ha.local:8123", "token_configured": token},
            "tv": {"enabled": True, "model": "HOME_ASSISTANT", "ha_remote_entity_id": entity},
        }
        return compute_config_readiness(config)["tv"]["status"]

    def test_readiness(self):
        self.assertEqual("configured", self._status())
        self.assertEqual("incomplete", self._status(entity=""))
        self.assertEqual("incomplete", self._status(token=False))


if __name__ == "__main__":
    unittest.main()
