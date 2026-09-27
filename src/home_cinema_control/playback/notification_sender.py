from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from home_cinema_control.playback.intent import PlaybackOrigin

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaybackStartMessages:
    """User-visible failure/timeout messages sent back to the source client.

    Success-path startup narration (the six touchpoints) lives in
    `playback/startup/messaging.py` — this is only the error/timeout vocabulary,
    deliberately kept separate so real failures are never dressed in the
    success-path's cinematic tone.
    """

    timeout_play: str
    error_mount: str
    error_play: str
    error_no_oppo: str
    error_media_source_offline: str


def playback_start_messages(lang: dict) -> PlaybackStartMessages:
    return PlaybackStartMessages(
        timeout_play=lang["msg-playback-timeout"],
        error_mount=lang["msg-playback-error-mount"],
        error_play=lang["msg-playback-error-play"],
        error_no_oppo=lang["msg-playback-error-no-oppo"],
        # .get: a language file predating this message must not break playback.
        error_media_source_offline=lang.get(
            "msg-playback-error-media-source-offline", "Could not power on the server "
        ),
    )


def send_playback_message(
    playback_session,
    origin: PlaybackOrigin,
    session_id: str | None,
    message: str,
    timeout_ms: int | None = None,
) -> None:
    """Send a user-visible playback message to the source client when present.

    Best-effort: any failure to deliver the message (e.g. a network error
    talking to the media server) is logged and swallowed here, never
    propagated, so notification delivery can never fail playback startup.
    """
    if not session_id:
        logger.info(
            "Skipping playback message; no active source session is available | "
            "origin=%s | text=%s",
            origin.value,
            message,
        )
        return

    try:
        if timeout_ms is None:
            playback_session.notify_session(session_id, message)
        else:
            playback_session.notify_session(session_id, message, timeout_ms)
    except Exception:
        logger.exception(
            "Failed to send playback message to source session | "
            "origin=%s | session_id=%s | text=%s",
            origin.value,
            session_id,
            message,
        )


def send_with_delivery_reliability(
        send_command: Callable[[str], object],
        session_id: str | None,
        *,
        command_name: str,
) -> object | None:
    """Send a remote command to the source client twice, best-effort.

    Emby's remote playback commands are fire-and-forget over the client's
    websocket connection — confirmed against upstream Jellyfin source (which
    shares the same session/command protocol design): no acknowledgment, no
    retry, and the server's own session state is only updated when the client
    separately reports back. See
    `.agents/tasks/26-p2-emby-source-client-keeps-stale-paused-playback-screen.md`.
    A dropped Stop leaves the source client's own "now playing" screen frozen
    until Emby's session list eventually expires it client-side. Sending it
    twice, immediately, is the minimal mitigation available for a protocol
    with no delivery guarantee — not a workaround for a bug HCC could
    otherwise fix. This is the one place that owns that redundancy: every
    caller that needs the source client's screen to actually clear (handoff,
    and playback finish, for every `PlaybackOrigin`) calls this once and gets
    both sends — a caller doing its own single send and expecting this
    function to merely add a second one is the gap that let the screen freeze
    return for the `REMOTE_CONTROL_COMMAND` origin (see CHANGELOG).

    Returns the first send's response (or `None` if there was no session id,
    or the first send raised).
    """
    if not session_id:
        return None

    response = None
    try:
        response = send_command(session_id)
    except Exception:
        logger.warning(
            "Could not send %s for delivery reliability | session_id=%s",
            command_name,
            session_id,
            exc_info=True,
        )

    try:
        send_command(session_id)
    except Exception:
        logger.warning(
            "Could not resend %s for delivery reliability | session_id=%s",
            command_name,
            session_id,
            exc_info=True,
        )

    return response


def send_stop_with_delivery_reliability(
        stop_session_playback: Callable[[str], object],
        session_id: str | None,
) -> object | None:
    """Send a remote Stop to the source client twice, best-effort."""
    return send_with_delivery_reliability(
        stop_session_playback,
        session_id,
        command_name="Stop",
    )
