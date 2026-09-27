import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from home_cinema_control.playback.diagnostics import diagnose_startup_result
from home_cinema_control.playback.intent import PlaybackOrigin
from home_cinema_control.playback.notification_sender import playback_start_messages
from home_cinema_control.playback.player_state import PlayerPlaybackStartResult
from home_cinema_control.playback.result_reporting import report_orchestration_result
from home_cinema_control.playback.startup.messaging import PlaybackStartupMessagingService
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    PlaybackOutputSwitchResult,
    PlaybackStartupResult,
    PlayerMediaFileLocation,
)

_LANG = {
    "msg-playback-timeout": "timeout",
    "msg-playback-error-play": "play error ",
    "msg-playback-error-mount": "mount error ",
    "msg-playback-error-no-oppo": "no oppo",
    "msg-playback-error-media-source-offline": "server offline ",
    "msg-startup-powering-on-media-source": "powering on the library server",
}


def _startup_result(media_source_power_result):
    return PlaybackStartupResult(
        output_switch_result=PlaybackOutputSwitchResult(
            previous_tv_app_id=None,
            tv_input_result=DeviceCommandResult.success(),
            av_power_result=DeviceCommandResult.success(),
            av_input_result=DeviceCommandResult.success(),
        ),
        media_player_start_result=PlayerPlaybackStartResult(
            media_mounted=False,
            playback_command_accepted=False,
            playback_started_on_device=False,
            detail="nas11.local did not come online within 300s.",
        ),
        media_source_power_result=media_source_power_result,
    )


class MediaSourcePowerReportingTest(unittest.TestCase):
    def test_offline_server_gets_its_own_diagnostic(self):
        diagnostic = diagnose_startup_result(_startup_result(
            DeviceCommandResult.failed("nas11.local did not come online within 300s.")
        ))

        self.assertEqual("MEDIA_SOURCE_POWER_ON_FAILED", diagnostic.code)
        self.assertEqual("media_source", diagnostic.component)
        self.assertIn("did not come online", diagnostic.reason)

    def test_offline_server_message_is_sent_instead_of_mount_error(self):
        location = PlayerMediaFileLocation(
            content_server="nas11.local",
            content_directory="libreria/series",
            playback_file_name="episode.mkv",
            playback_file_format="mkv",
        )
        result = SimpleNamespace(startup_result=_startup_result(
            DeviceCommandResult.failed("nas11.local did not come online within 300s.")
        ))

        with patch(
            "home_cinema_control.playback.result_reporting.send_playback_message"
        ) as send:
            report_orchestration_result(
                playback_session=MagicMock(),
                origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND,
                session_id="session-1",
                media_location=location,
                playback_orchestration_result=result,
                messages=playback_start_messages(_LANG),
                movie="episode.mkv",
            )

        message = send.call_args.args[3]
        self.assertTrue(message.startswith("server offline nas11.local"))

    def test_messages_fall_back_when_language_file_lacks_the_new_key(self):
        lang = {key: value for key, value in _LANG.items()
                if key != "msg-playback-error-media-source-offline"}

        self.assertEqual(
            "Could not power on the server ",
            playback_start_messages(lang).error_media_source_offline,
        )

    def test_powering_on_touchpoint_is_sent(self):
        with patch(
            "home_cinema_control.playback.startup.messaging.send_playback_message"
        ) as send:
            PlaybackStartupMessagingService(
                playback_session=MagicMock(),
                origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND,
                session_id="session-1",
                lang=_LANG,
            ).media_source_powering_on()

        self.assertEqual("powering on the library server", send.call_args.args[3])

    def test_powering_on_touchpoint_never_raises(self):
        PlaybackStartupMessagingService(
            playback_session=MagicMock(),
            origin=PlaybackOrigin.REMOTE_CONTROL_COMMAND,
            session_id="session-1",
            lang={},
        ).media_source_powering_on()


if __name__ == "__main__":
    unittest.main()
