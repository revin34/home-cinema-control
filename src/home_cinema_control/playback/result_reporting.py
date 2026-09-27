from __future__ import annotations

import logging

from home_cinema_control.playback.intent import PlaybackOrigin
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    DeviceCommandStatus,
)
from home_cinema_control.playback.notification_sender import (
    PlaybackStartMessages,
    send_playback_message,
)

logger = logging.getLogger(__name__)


def report_orchestration_result(
    *,
    playback_session,
    origin: PlaybackOrigin,
    session_id: str | None,
    media_location,
    playback_orchestration_result,
    messages: PlaybackStartMessages,
    movie: str,
) -> None:
    """Notify startup failures and log completed orchestration results."""
    oppo_playback_start_result = (
        playback_orchestration_result.startup_result.media_player_start_result
    )

    if not oppo_playback_start_result.successful:
        _notify_startup_failure(
            playback_session=playback_session,
            origin=origin,
            session_id=session_id,
            media_location=media_location,
            oppo_playback_start_result=oppo_playback_start_result,
            media_source_power_result=(
                playback_orchestration_result.startup_result.media_source_power_result
            ),
            messages=messages,
            movie=movie,
        )
        return

    if not playback_orchestration_result.successful:
        finish_result = playback_orchestration_result.finish_result
        recovery_result = playback_orchestration_result.error_recovery_result
        logger.warning(
            "Playback orchestration ended with non-startup failure | "
            "finish_successful=%s | recovery_successful=%s",
            finish_result.successful if finish_result is not None else None,
            recovery_result.successful if recovery_result is not None else None,
        )
        if finish_result is not None and not finish_result.successful:
            logger.warning(
                "Playback finish failure breakdown | player_idle=%s | player_idle_detail=%s | "
                "tv=%s | tv_detail=%s | av_audio=%s | av_audio_detail=%s",
                finish_result.player_idle_result.status.value,
                finish_result.player_idle_result.detail,
                finish_result.tv_app_result.status.value,
                finish_result.tv_app_result.detail,
                finish_result.av_audio_result.status.value,
                finish_result.av_audio_result.detail,
            )
        return

    _log_successful_orchestration(playback_orchestration_result)


def _notify_startup_failure(
    *,
    playback_session,
    origin: PlaybackOrigin,
    session_id: str | None,
    media_location,
    oppo_playback_start_result,
    media_source_power_result: DeviceCommandResult,
    messages: PlaybackStartMessages,
    movie: str,
) -> None:
    if media_source_power_result.status == DeviceCommandStatus.FAILED:
        error_message = (
            messages.error_media_source_offline
            + media_location.content_server
            + " - info:"
            + str(media_source_power_result.detail)
        )
    elif not oppo_playback_start_result.media_mounted:
        error_message = (
            messages.error_mount
            + media_location.content_server
            + "/"
            + media_location.content_directory
            + " - info:"
            + str(oppo_playback_start_result.detail)
        )
    elif not oppo_playback_start_result.playback_command_accepted:
        error_message = (
            messages.error_play
            + media_location.playback_file_name
            + " - info:"
            + str(oppo_playback_start_result.detail)
        )
    else:
        error_message = messages.timeout_play
        logger.info("Timeout Reproduciendo %s", movie)

    send_playback_message(
        playback_session,
        origin,
        session_id,
        error_message,
        timeout_ms=5000,
    )


def _log_successful_orchestration(playback_orchestration_result) -> None:
    playback_monitoring_result = playback_orchestration_result.monitoring_result
    finish_result = playback_orchestration_result.finish_result

    logger.info("-----------------------------------------------------------")
    logger.debug(
        "PlayingTime: %s de %s",
        playback_monitoring_result.position_seconds,
        playback_monitoring_result.duration_seconds,
    )
    logger.info(
        "OPPO playback monitoring result | monitoring_final_state=%s | "
        "monitoring_final_lifecycle_phase=%s | "
        "position_seconds=%s | duration_seconds=%s",
        playback_monitoring_result.final_state.status.value,
        playback_monitoring_result.final_state.lifecycle_phase.value,
        playback_monitoring_result.position_seconds,
        playback_monitoring_result.duration_seconds,
    )
    logger.info(
        "Playback finish result | successful=%s | player_idle=%s | tv=%s | "
        "av_audio=%s | final_state=%s | lifecycle_phase=%s",
        finish_result.successful,
        finish_result.player_idle_result.status.value,
        finish_result.tv_app_result.status.value,
        finish_result.av_audio_result.status.value,
        finish_result.final_player_state.status.value,
        finish_result.final_player_state.lifecycle_phase.value,
    )
