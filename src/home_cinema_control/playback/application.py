from __future__ import annotations

import logging
import time

from home_cinema_control.media_servers.common.playback import MediaServerPlaybackServices
from home_cinema_control.playback.active_context import ActivePlaybackRuntimeContext
from home_cinema_control.playback.content_kind import MediaContentKind
from home_cinema_control.playback.dispatch import bridge_playback_is_active
from home_cinema_control.playback.factory import create_playback_orchestrator_wiring
from home_cinema_control.playback.device_runtime import (
    ensure_oppo_control_api_available,
    log_oppo_qpl_state,
    power_down_after_playback_if_configured,
    prepare_oppo_observation_mode,
    stop_active_player_playback_before_replacement,
)
from home_cinema_control.playback.intent import PlaybackIntent, PlaybackOrigin
from home_cinema_control.playback.diagnostics import (
    diagnose_media_server_item_unavailable,
    diagnose_oppo_unavailable,
    diagnose_orchestration_result,
    diagnose_path_error,
)
from home_cinema_control.playback.media_location import PlayerMediaFileLocationError
from home_cinema_control.playback.notification_sender import (
    playback_start_messages,
    send_stop_with_delivery_reliability,
    send_playback_message,
)
from home_cinema_control.playback.observed_event_adapter import (
    configure_oppo_observed_event_reporting,
)
from home_cinema_control.playback.orchestrator import PlaybackOrchestrationRequest
from home_cinema_control.playback.request_preparation import prepare_playback_requests
from home_cinema_control.playback.result_reporting import report_orchestration_result
from home_cinema_control.playback.startup import PlaybackStartupRequest
from home_cinema_control.playback.startup.messaging import PlaybackStartupMessagingService
from home_cinema_control.playback.state import BridgePlaybackState
from home_cinema_control.playback.thread_lifecycle import PlaybackThreadLifecycle
from home_cinema_control.playback.timing import PlaybackStartupTimer


logger = logging.getLogger(__name__)
NORMAL_FINISH_IDLE_CONFIRMATION_POLLS = 5
REPLACEMENT_FINISH_IDLE_CONFIRMATION_POLLS = 60


class PlaybackApplicationService:
    """Application entrypoint for playback requests.

    Owns request-level coordination around the playback orchestrator: duplicate
    request handling, replacement threading, active publisher exposure for Emby
    command handling, and post-run cleanup. Device ordering and playback phase
    behaviour belong to the orchestrators, not here.
    """

    def __init__(
        self,
        *,
        playback_session,
        playback_state: BridgePlaybackState,
        reload_config,
            media_server_playback_services: MediaServerPlaybackServices | None = None,
            telemetry_service=None,
        stop_active_playback=None,
        sleep=time.sleep,
    ) -> None:
        self._playback_session = playback_session
        self._state = playback_state
        self._reload_config = reload_config
        self._media_server_playback_services = media_server_playback_services
        self._telemetry_service = telemetry_service
        self._stop_active_playback = stop_active_playback or (
            lambda: stop_active_player_playback_before_replacement(
                self._state, self._playback_session.config
            )
        )
        self._thread_lifecycle = PlaybackThreadLifecycle(
            start_playback=self._start_from_intent,
            reload_config=self._reload_config,
            stop_active_playback=self._stop_active_playback,
        )
        self._playback_return_tv_app_id: str | None = None
        self._sleep = sleep
        self._active_context = ActivePlaybackRuntimeContext()

    @property
    def active_publisher(self):
        return self._active_context.publisher

    @property
    def active_media_player(self):
        return self._active_context.media_player

    @property
    def active_oppo_playback(self):
        return self.active_media_player

    def request_playback_from_intent(
        self,
        intent: PlaybackIntent,
        *,
        origin: PlaybackOrigin,
    ) -> bool:
        if self._is_duplicate_intent(intent):
            logger.info(
                "Ignoring duplicate playback request | item_id=%s | playstate=%s",
                intent.media_item_id,
                self._state.playstate,
            )
            return False

        self._wait_for_loading_to_finish()
        if self._state.playstate in ("Playing", "Replay"):
            logger.info("already playing, replacing")
            return self.replace_from_intent(intent, origin=origin)

        self.start_from_intent(intent, origin=origin)
        return True

    def start_from_intent(self, intent: PlaybackIntent, *, origin: PlaybackOrigin) -> None:
        self._thread_lifecycle.start(intent, origin=origin)

    def replace_from_intent(self, intent: PlaybackIntent, *, origin: PlaybackOrigin) -> bool:
        return self._thread_lifecycle.replace(intent, origin=origin)

    def stop_active_playback_and_wait(self) -> bool:
        """Stop any in-progress playback and block until its finish/cleanup
        flow has fully completed. For callers outside normal playback
        replacement that need a clean slate before something disruptive —
        e.g. the runtime swapping the media-server listener on a provider
        switch. Returns True if anything was actually stopped.
        """
        return self._thread_lifecycle.stop_active_and_wait()

    def _is_duplicate_intent(self, intent: PlaybackIntent) -> bool:
        if not bridge_playback_is_active(self._state.playstate):
            return False
        active_session = self._state.active_session
        return active_session is not None and str(
            active_session.media_item_id
        ) == str(intent.media_item_id)

    def _wait_for_loading_to_finish(self) -> None:
        if self._state.playstate not in ("Loading", "Replay"):
            return

        logger.info("waiting for loading state to finish")

        timeout = 60
        elapsed = 0
        while self._state.playstate == "Loading" and elapsed < timeout:
            self._sleep(3)
            elapsed = elapsed + 3

    def _start_from_intent(
        self,
        intent: PlaybackIntent,
        *,
        origin: PlaybackOrigin,
    ):
        playback_session = self._playback_session
        startup_timer = PlaybackStartupTimer()
        self._state.start_loading(intent)

        session_id = intent.source_client_session_id
        messages = playback_start_messages(playback_session.lang)
        messaging = PlaybackStartupMessagingService(
            playback_session=playback_session,
            origin=origin,
            session_id=session_id,
            lang=playback_session.lang,
        )
        with startup_timer.measure_step("notify_received"):
            messaging.received()

        prepare_oppo_observation_mode(playback_session.config)
        log_oppo_qpl_state(playback_session.config, "playback_application_start")

        logger.info("playback origin: %s", origin.value)

        session_id = intent.source_client_session_id
        media_server_services = self._media_server_services()
        media_server_playback_context = media_server_services.playback_context_from_intent(
            intent
        )

        movie = ""

        with startup_timer.measure_step("process_media_server_payload"):
            try:
                item_info = playback_session.get_media_source_info(
                    playback_session.user_info["User"]["Id"],
                    intent.media_item_id,
                    intent.media_source_id,
                )
            except Exception as exc:
                logger.exception("Could not load media server item for playback handoff.")
                _diag = diagnose_media_server_item_unavailable(str(exc))
                self._record_diagnostic(_diag)
                self._emit_telemetry(
                    "playback_failed",
                    {"component": "media_server", "code": _diag.code},
                )
                _reset_bridge_playback_state(self._state, movie)
                return

        with startup_timer.measure_step("ensure_oppo_control_api_available"):
            control_api_available = ensure_oppo_control_api_available(
                playback_session.config
            )

        if not control_api_available:
            _diag = diagnose_oppo_unavailable()
            self._record_diagnostic(_diag)
            self._emit_telemetry("playback_failed", {"component": "oppo", "code": _diag.code})
            send_playback_message(
                playback_session,
                origin,
                session_id,
                messages.error_no_oppo,
            )
            _reset_bridge_playback_state(self._state, movie)
            return

        if _should_stop_source_client_before_handoff(origin):
            with startup_timer.measure_step("stop_source_client_before_handoff"):
                response_data = send_stop_with_delivery_reliability(
                    playback_session.stop_session_playback, session_id
                )

            logger.debug("stop source client response: %s", response_data)

        playback_wiring = create_playback_orchestrator_wiring(
            config=playback_session.config,
            media_server_client=playback_session.client,
            bridge_session_id=playback_session.user_info["SessionInfo"]["Id"],
            playback_context=media_server_playback_context,
            playback_event_publisher_factory=(
                media_server_services.create_playback_event_publisher
            ),
            track_resolver=media_server_services.create_track_resolver(playback_session),
            playback_state=self._state,
            step_timer=startup_timer,
        )
        self._active_context.activate(playback_wiring)

        with startup_timer.measure_step("notify_locating"):
            messaging.locating()

        try:
            with startup_timer.measure_step("resolve_media_path"):
                prepared_requests = prepare_playback_requests(
                    config=playback_session.config,
                    intent=intent,
                    item_info=item_info,
                    previous_tv_app_id_override=self._playback_return_tv_app_id,
                )
                media_location = prepared_requests.media_location
                movie = prepared_requests.movie_path
        except PlayerMediaFileLocationError as exc:
            logger.warning("Media path resolution failed: %s", exc)
            _diag = diagnose_path_error(exc)
            self._record_diagnostic(_diag)
            self._emit_telemetry("playback_failed", {"component": "path", "code": _diag.code})
            _reset_bridge_playback_state(self._state, movie)
            return

        logger.info("Servidor               : %s", media_location.content_server)
        logger.info("Fichero                : %s", media_location.playback_file_name)
        logger.info("Carpeta                : %s", media_location.content_directory)
        logger.info("-----------------------------------------------------------")
        self._state.set_active_media_location(
            media_location=media_location,
            item_info=item_info,
        )

        playback_orchestration_result = (
            playback_wiring.playback_orchestrator.play_until_stopped(
                PlaybackOrchestrationRequest(
                    startup_request=PlaybackStartupRequest(
                        output_switch_request=(
                            prepared_requests.output_switch_request
                        ),
                        media_player_start_request=(
                            prepared_requests.media_player_start_request
                        ),
                        media_source_power_request=(
                            prepared_requests.media_source_power_request
                        ),
                    ),
                    startup_completion_request=(
                        prepared_requests.startup_completion_request
                    ),
                    is_paused=False,
                    is_muted=False,
                    restore_outputs_on_finish=(
                        lambda: not self._thread_lifecycle.replacement_requested
                    ),
                    finish_idle_confirmation_polls=(
                        lambda: REPLACEMENT_FINISH_IDLE_CONFIRMATION_POLLS
                        if self._thread_lifecycle.replacement_requested
                        else NORMAL_FINISH_IDLE_CONFIRMATION_POLLS
                    ),
                    on_startup_waiting=messaging.notify_waiting,
                    on_media_source_powering_on=messaging.media_source_powering_on,
                    on_tracks_applying=messaging.tracks_applying,
                    on_startup_completed=lambda r: self._on_startup_completed(
                        r,
                        intent=intent,
                        movie=movie,
                        messaging=messaging,
                        content_kind=item_info.content_kind,
                        playback_wiring=playback_wiring,
                        startup_timer=startup_timer,
                    ),
                )
            )
        )

        report_orchestration_result(
            playback_session=playback_session,
            origin=origin,
            session_id=session_id,
            media_location=media_location,
            playback_orchestration_result=playback_orchestration_result,
            messages=messages,
            movie=movie,
        )
        diagnostic = diagnose_orchestration_result(
            playback_orchestration_result, playback_session.config
        )
        if diagnostic is not None:
            self._record_diagnostic(diagnostic)
            self._emit_telemetry(
                "playback_failed",
                {
                    "component": _telemetry_component(getattr(diagnostic, "component", "")),
                    "code": diagnostic.code,
                },
            )
        else:
            self._emit_telemetry("playback_finished")
        self._remember_playback_return_tv_app_id(playback_orchestration_result)
        self._clear_playback_return_tv_app_id_after_final_finish(
            playback_orchestration_result
        )

        self._active_context.clear()
        power_down_after_playback_if_configured(playback_session.config)
        _reset_bridge_playback_state(self._state, movie)
        return playback_orchestration_result


    def _record_diagnostic(self, diagnostic) -> None:
        record = getattr(self._state, "record_diagnostic", None)
        if callable(record):
            record(diagnostic)
        else:
            self._state.last_diagnostic = diagnostic

    def _on_startup_completed(
        self,
        _result,
        *,
        intent: PlaybackIntent,
        movie: str,
            messaging: PlaybackStartupMessagingService,
            content_kind: MediaContentKind,
        playback_wiring,
        startup_timer: PlaybackStartupTimer,
    ) -> None:
        # Critical playback-state wiring happens first and unconditionally.
        # The closing notification (messaging.action) is the very last thing
        # this method does, deliberately: PlaybackStartupMessagingService
        # already guarantees it cannot raise (see its docstring / HCC-TASK-027),
        # but ordering it last means even an unimagined future failure mode
        # there still can't prevent the playback-critical wiring above it from
        # completing. A notification bug must never be able to look like a
        # playback failure to the orchestrator.
        self._state.playstate = "Playing"
        self._state.last_diagnostic = None
        logger.debug("start_position_seconds: %s", intent.start_position_seconds)

        playback_session = self._playback_session
        logger.info("Reprodución iniciada: %s", movie)

        log_oppo_qpl_state(playback_session.config, "after_oppo_playback_start")
        startup_timer.log_summary()
        configure_oppo_observed_event_reporting(
            playback_state=self._state,
            playback_wiring=playback_wiring,
            track_mapper=self._media_server_services().create_observed_track_mapper(
                playback_session,
                playback_state=self._state,
            ),
        )
        self._emit_telemetry("playback_started")

        # Sent for every origin and regardless of TV-switching config: this is
        # the one notification that reaches whichever client started playback
        # (e.g. the Emby phone app), independent of whether HCC also drives a TV.
        messaging.action(content_kind)

    def _emit_telemetry(self, event_name: str, event: dict | None = None) -> None:
        if self._telemetry_service is None:
            return
        try:
            self._telemetry_service.emit(
                event_name,
                event=event,
                config=self._playback_session.config,
            )
        except Exception:
            logger.debug("Playback telemetry emission failed", exc_info=True)

    def _remember_playback_return_tv_app_id(self, playback_orchestration_result) -> None:
        startup_result = playback_orchestration_result.startup_result
        output_switch_result = startup_result.output_switch_result
        previous_tv_app_id = output_switch_result.previous_tv_app_id
        if previous_tv_app_id is None or _is_lg_hdmi_app_id(previous_tv_app_id):
            return

        self._playback_return_tv_app_id = previous_tv_app_id

    def _clear_playback_return_tv_app_id_after_final_finish(
        self,
        playback_orchestration_result,
    ) -> None:
        if self._thread_lifecycle.replacement_requested:
            return

        if playback_orchestration_result.finish_result is None:
            return

        self._playback_return_tv_app_id = None

    def _media_server_services(self) -> MediaServerPlaybackServices:
        if self._media_server_playback_services is None:
            raise RuntimeError("Media-server playback services are not configured.")
        return self._media_server_playback_services


def _is_lg_hdmi_app_id(app_id: str) -> bool:
    return app_id.startswith("com.webos.app.hdmi")


def _should_stop_source_client_before_handoff(origin: PlaybackOrigin) -> bool:
    # The OPPO takes over playback regardless of whether TV/AV switching is
    # configured, so the source client's own native playback must be stopped
    # either way — otherwise both end up playing the same item in parallel.
    return origin in (
        PlaybackOrigin.OBSERVED_TV_CLIENT,
        PlaybackOrigin.REMOTE_CONTROL_COMMAND,
    )


def _reset_bridge_playback_state(state: BridgePlaybackState, movie: str) -> None:
    state.finish()
    logger.info("Fin PlaybackApplicationService.start %s", movie)


def _telemetry_component(component: str) -> str:
    if component in {"oppo", "tv", "av", "path", "cleanup", "system"}:
        return component
    if component in {"emby", "jellyfin", "media_server"}:
        return "media_server"
    return "system"
