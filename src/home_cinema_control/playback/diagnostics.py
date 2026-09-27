from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from home_cinema_control.config.manager import is_smb_active


@dataclass
class PlaybackDiagnostic:
    """Structured playback diagnostic exposed to the web UI and support summary.

    `reason` and `suggestion` are user-facing. `code`, `severity`, `component`
    and `operation` are stable enough for tests, UI filtering and future support
    bundles.
    """

    code: str
    severity: str  # "error" | "warning" | "info"
    component: str  # "oppo" | "tv" | "av" | "path" | "emby" | "cleanup" | "system"
    reason: str
    suggestion: str
    operation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        data = {
            "code": self.code,
            "severity": self.severity,
            "component": self.component,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "timestamp": self.timestamp,
        }
        if self.operation:
            data["operation"] = self.operation
        if self.details:
            data["details"] = dict(self.details)
        return data


def diagnose_startup_result(
    startup_result, config: dict | None = None
) -> PlaybackDiagnostic | None:
    """Return a diagnostic from a failed PlaybackStartupResult, or None on success."""
    if startup_result.successful:
        return None

    from home_cinema_control.playback.startup.models import DeviceCommandStatus

    media_source_power = startup_result.media_source_power_result
    if media_source_power.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="MEDIA_SOURCE_POWER_ON_FAILED",
            severity="error",
            component="media_source",
            operation="media_source_power_on",
            reason=(
                "The library server did not come online: "
                f"{media_source_power.detail or 'unknown error'}"
            ),
            suggestion=(
                "Check the power switch configured for this path in Media Paths, that "
                "Home Assistant can turn it on, and that the server finishes booting "
                "within media_source_power.wait_timeout_seconds."
            ),
            details={"detail": media_source_power.detail},
        )

    output_switch = startup_result.output_switch_result

    if output_switch.tv_input_result.status == DeviceCommandStatus.FAILED:
        return _output_device_diagnostic(
            code="TV_INPUT_SWITCH_FAILED",
            component="tv",
            operation="startup_output_switch",
            reason=(
                "TV input switch failed: "
                f"{output_switch.tv_input_result.detail or 'unknown error'}"
            ),
            suggestion=(
                "Check TV IP address, TV model, remote-control permissions and "
                "the configured player HDMI input."
            ),
            details={"detail": output_switch.tv_input_result.detail},
        )

    if output_switch.av_power_result.status == DeviceCommandStatus.FAILED:
        return _output_device_diagnostic(
            code="AV_POWER_ON_FAILED",
            component="av",
            operation="startup_output_switch",
            reason=(
                "AV receiver power-on failed: "
                f"{output_switch.av_power_result.detail or 'unknown error'}"
            ),
            suggestion="Check AV receiver IP address, model and network connectivity.",
            details={"detail": output_switch.av_power_result.detail},
        )

    if output_switch.av_input_result.status == DeviceCommandStatus.FAILED:
        return _output_device_diagnostic(
            code="AV_INPUT_SWITCH_FAILED",
            component="av",
            operation="startup_output_switch",
            reason=(
                "AV receiver HDMI switch failed: "
                f"{output_switch.av_input_result.detail or 'unknown error'}"
            ),
            suggestion="Check the configured AV receiver input for the media player.",
            details={"detail": output_switch.av_input_result.detail},
        )

    oppo = startup_result.media_player_start_result
    detail = oppo.detail or ""

    if not oppo.media_mounted:
        stale_mount = _diagnose_stale_mount_if_likely(
            detail,
            operation="oppo_mount_startup",
        )
        if stale_mount is not None:
            return stale_mount

        protocol_label = "SMB/CIFS" if oppo.mount_protocol == "cifs" else "NFS"
        suggestion = (
            "Check SMB credentials, NAS SMB share permissions "
            "and that the SMB share is reachable from the OPPO."
            if oppo.mount_protocol == "cifs"
            else "Check NFS export settings, NAS NFS permissions "
            "and that the NFS share is reachable from the OPPO."
        )
        smb_not_attempted = False
        if oppo.mount_protocol == "nfs":
            suggestion = _with_smb_not_attempted_hint(suggestion, config)
            smb_not_attempted = config is not None and not is_smb_active(config)
        return PlaybackDiagnostic(
            code="OPPO_MOUNT_FAILED",
            severity="error",
            component="oppo",
            operation="oppo_mount_startup",
            reason=f"OPPO could not mount the media share via {protocol_label}. {detail}".strip(),
            suggestion=suggestion,
            details={
                "protocol": oppo.mount_protocol,
                "detail": detail,
                "smb_not_attempted": smb_not_attempted,
            },
        )

    if not oppo.playback_command_accepted:
        stale_mount = _diagnose_stale_mount_if_likely(
            detail,
            operation="oppo_play_startup",
        )
        if stale_mount is not None:
            return stale_mount

        return PlaybackDiagnostic(
            code="OPPO_PLAY_FAILED",
            severity="error",
            component="oppo",
            operation="oppo_play_startup",
            reason=f"OPPO rejected the play command. {detail}".strip(),
            suggestion="Check that the media file exists, is readable and is supported by the player.",
            details={"detail": detail},
        )

    if not oppo.playback_started_on_device:
        return PlaybackDiagnostic(
            code="OPPO_PLAYBACK_TIMEOUT",
            severity="error",
            component="oppo",
            operation="oppo_playback_start_wait",
            reason=(
                detail
                or "OPPO did not confirm playback started within the timeout period."
            ),
            suggestion=(
                "Increase the playback start timeout only if the file normally takes "
                "long to open. Otherwise verify the media path and OPPO state."
            ),
        )

    return None


def diagnose_finish_result(finish_result) -> PlaybackDiagnostic | None:
    """Return the first structured diagnostic from an unsuccessful finish phase."""
    if finish_result is None or finish_result.successful:
        return None

    from home_cinema_control.playback.startup.models import DeviceCommandStatus

    if finish_result.player_idle_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="OPPO_FINISH_IDLE_FAILED",
            severity="warning",
            component="oppo",
            operation="finish_cleanup",
            reason=(
                "OPPO did not reach/confirm idle during finish cleanup: "
                f"{finish_result.player_idle_result.detail or 'unknown error'}"
            ),
            suggestion=(
                "Check whether playback is still active on the player. If the UI is already idle, "
                "this may be a status-read failure rather than a media-path problem."
            ),
            details={"detail": finish_result.player_idle_result.detail},
        )

    if finish_result.tv_app_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="TV_APP_RESTORE_FAILED",
            severity="warning",
            component="tv",
            operation="finish_output_restore",
            reason=(
                "TV app restore failed: "
                f"{finish_result.tv_app_result.detail or 'unknown error'}"
            ),
            suggestion=(
                "Check TV network control and whether the previous app is still available. "
                "Playback has ended; this only affects room restoration."
            ),
            details={"detail": finish_result.tv_app_result.detail},
        )

    if finish_result.av_audio_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="AV_AUDIO_RESTORE_FAILED",
            severity="warning",
            component="av",
            operation="finish_output_restore",
            reason=(
                "AV receiver TV-audio restore failed: "
                f"{finish_result.av_audio_result.detail or 'unknown error'}"
            ),
            suggestion=(
                "Check AV receiver network control and the configured TV-audio input. "
                "Playback has ended; this only affects room restoration."
            ),
            details={"detail": finish_result.av_audio_result.detail},
        )

    return None


def diagnose_error_recovery_result(recovery_result) -> PlaybackDiagnostic | None:
    """Return a diagnostic when central recovery cannot restore one component."""
    if recovery_result is None or recovery_result.successful:
        return None

    from home_cinema_control.playback.startup.models import DeviceCommandStatus

    if recovery_result.player_stop_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="OPPO_ERROR_RECOVERY_FAILED",
            severity="error",
            component="cleanup",
            operation="error_recovery",
            reason=(
                "Playback error recovery could not stop or clean up the OPPO: "
                f"{recovery_result.player_stop_result.detail or 'unknown error'}"
            ),
            suggestion=(
                "Stop playback manually on the OPPO and check whether the player remains responsive "
                "before starting another item."
            ),
            details={"detail": recovery_result.player_stop_result.detail},
        )

    if recovery_result.tv_app_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="TV_ERROR_RECOVERY_FAILED",
            severity="warning",
            component="tv",
            operation="error_recovery",
            reason=(
                "Playback error recovery could not restore the TV app: "
                f"{recovery_result.tv_app_result.detail or 'unknown error'}"
            ),
            suggestion="Return to the desired TV app manually and check TV network control settings.",
            details={"detail": recovery_result.tv_app_result.detail},
        )

    if recovery_result.av_audio_result.status == DeviceCommandStatus.FAILED:
        return PlaybackDiagnostic(
            code="AV_ERROR_RECOVERY_FAILED",
            severity="warning",
            component="av",
            operation="error_recovery",
            reason=(
                "Playback error recovery could not restore AV TV audio: "
                f"{recovery_result.av_audio_result.detail or 'unknown error'}"
            ),
            suggestion="Restore the AV receiver input manually and check AV network control settings.",
            details={"detail": recovery_result.av_audio_result.detail},
        )

    return None


def diagnose_orchestration_result(
    result, config: dict | None = None
) -> PlaybackDiagnostic | None:
    """Map a full orchestration result to the most actionable diagnostic."""
    startup = diagnose_startup_result(result.startup_result, config)
    if startup is not None:
        return startup

    finish = diagnose_finish_result(result.finish_result)
    if finish is not None:
        return finish

    return diagnose_error_recovery_result(result.error_recovery_result)


def diagnose_path_error(exc: Exception) -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code="PATH_RESOLUTION_FAILED",
        severity="error",
        component="path",
        operation="media_path_resolution",
        reason=f"Media path could not be resolved: {exc}",
        suggestion=(
            "Check Media Paths configuration and ensure source paths match the "
            "media server's library paths."
        ),
        details={"error": str(exc)},
    )


def diagnose_media_server_library_paths_unavailable(reason: str) -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code="MEDIA_SERVER_LIBRARY_PATHS_UNAVAILABLE",
        severity="error",
        component="media_server",
        operation="library_path_discovery",
        reason=reason,
        suggestion="Check the media server connection and token in Media Server settings.",
    )


def diagnose_media_server_item_unavailable(reason: str) -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code="MEDIA_SERVER_ITEM_UNAVAILABLE",
        severity="error",
        component="media_server",
        operation="media_item_lookup",
        reason=f"Media server item details could not be loaded: {reason}",
        suggestion="Check the media server connection and token in Media Server settings.",
    )


def diagnose_path_inference_failed() -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code="PATH_INFERENCE_FAILED",
        severity="warning",
        component="path",
        operation="path_mapping_inference",
        reason="Cannot infer a substitution rule from the anchor mapping.",
        suggestion=(
            "Fill share paths manually, or choose an anchor mapping whose Emby server path "
            "and player-visible path share a common path component."
        ),
    )


def diagnose_path_test_failed(
    result: str, config: dict | None = None
) -> PlaybackDiagnostic:
    result = str(result or "Unknown path test failure")

    stale_mount = _diagnose_stale_mount_if_likely(
        result,
        operation="path_mount_test",
    )
    if stale_mount is not None:
        return stale_mount

    if _contains_any(result, ["oppo_unavailable", "socket", "connection refused", "timed out"]):
        return PlaybackDiagnostic(
            code="OPPO_PATH_TEST_UNAVAILABLE",
            severity="error",
            component="oppo",
            operation="path_mount_test",
            reason=f"Path test could not reach OPPO: {result}",
            suggestion="Power on the OPPO or verify its IP address before testing the media path.",
            details={"result": result},
        )

    if _contains_any(result, ["device list", "devicelist"]):
        return PlaybackDiagnostic(
            code="OPPO_DEVICE_LIST_UNAVAILABLE",
            severity="warning",
            component="oppo",
            operation="path_mount_test",
            reason=f"OPPO did not provide a network device list during path test: {result}",
            suggestion=(
                "Open the OPPO network browser once, verify the NAS/share is visible, "
                "then retry the path test."
            ),
            details={"result": result},
        )

    suggestion = _with_smb_not_attempted_hint(
        "Verify the Emby server path matches your library root and the player-visible "
        "network share path is reachable from the media player.",
        config,
    )

    return PlaybackDiagnostic(
        code="PATH_TEST_FAILED",
        severity="error",
        component="path",
        operation="path_mount_test",
        reason=f"Path test failed: {result}",
        suggestion=suggestion,
        details={
            "result": result,
            "smb_not_attempted": config is not None and not is_smb_active(config),
        },
    )


def diagnose_oppo_unavailable() -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code="OPPO_UNAVAILABLE",
        severity="error",
        component="oppo",
        operation="oppo_connectivity_check",
        reason="OPPO player was not reachable when playback was requested.",
        suggestion=(
            "Ensure the OPPO is powered on or in standby and verify the IP address in Media Player settings."
        ),
    )


def diagnose_device_action_failed(
    *,
    component: str,
    action: str,
    detail: str,
    severity: str = "warning",
) -> PlaybackDiagnostic:
    code_prefix = component.upper().replace("-", "_")
    action_code = action.upper().replace("-", "_").replace(" ", "_")
    return PlaybackDiagnostic(
        code=f"{code_prefix}_{action_code}_FAILED",
        severity=severity,
        component=component,
        operation=action,
        reason=f"{component.upper()} {action} failed: {detail or 'unknown error'}",
        suggestion="Check the device configuration and network connectivity, then retry the action.",
        details={"detail": detail},
    )


def _with_smb_not_attempted_hint(suggestion: str, config: dict | None) -> str:
    if config is None or is_smb_active(config):
        return suggestion

    return suggestion + (
        " SMB was not attempted because it is not enabled in Media Paths "
        "settings — if this share is actually SMB/CIFS-only, enable SMB "
        "there and retry."
    )


def _output_device_diagnostic(
    *,
    code: str,
    component: str,
    operation: str,
    reason: str,
    suggestion: str,
        details: dict[str, Any] | None = None,
) -> PlaybackDiagnostic:
    return PlaybackDiagnostic(
        code=code,
        severity="warning",
        component=component,
        operation=operation,
        reason=reason,
        suggestion=suggestion,
        details=details or {},
    )


def _diagnose_stale_mount_if_likely(
    detail: str,
    *,
    operation: str,
) -> PlaybackDiagnostic | None:
    if not _looks_like_stale_mount(detail):
        return None

    return PlaybackDiagnostic(
        code="OPPO_STALE_MOUNT_SUSPECTED",
        severity="warning",
        component="oppo",
        operation=operation,
        reason=(
            "OPPO network mount state may be stale. The path configuration may still be correct. "
            f"Evidence: {detail or 'mount/play request did not produce a usable mounted share'}"
        ),
        suggestion=(
            "Do not change path mappings immediately. First retry after opening the OPPO network browser, "
            "stopping current playback, or rebooting the OPPO/NAS if the share appears stuck."
        ),
        details={"classification": "suspected_stale_mount", "detail": detail},
    )


def _looks_like_stale_mount(detail: str) -> bool:
    text = str(detail or "").lower()
    if not text:
        return False

    stale_terms = [
        "stale",
        "already mounted",
        "already exists",
        "resource busy",
        "device busy",
        "mount point busy",
        "transport endpoint is not connected",
        "host is down",
        "mount request timed out",
        "timeout in mount request",
        "mount timeout",
        "mount failed after login",
        "mountsharedfolder",
        "mountnfssharedfolder",
        "did not return a mounted path",
        "no mounted share",
        "mounted share is none",
    ]
    return any(term in text for term in stale_terms)


def _contains_any(value: str, terms: list[str]) -> bool:
    text = str(value or "").lower()
    return any(term in text for term in terms)
