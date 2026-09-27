"""Power on the server behind a media path through Home Assistant.

A path mapping may name a Home Assistant switch (typically a Wake-on-LAN
switch) that powers its NAS. Before the OPPO mounts the share, HCC turns that
switch on and waits until the share's port accepts connections: a NAS that
answers ping can still be seconds away from serving NFS/SMB.
"""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable

from home_cinema_control.config.models import MediaSourcePowerConfig
from home_cinema_control.devices.home_assistant.client import (
    HomeAssistantClient,
    HomeAssistantError,
)
from home_cinema_control.playback.startup.models import (
    DeviceCommandResult,
    MediaSourcePowerRequest,
)

logger = logging.getLogger(__name__)

_SHARE_PORTS = {"nfs": (2049,), "cifs": (445,), "smb": (445,)}
_ANY_SHARE_PORT = (2049, 445)
_PROBE_TIMEOUT_SECONDS = 1.0


def share_reachable(server: str, network_protocol: str | None) -> bool:
    """True when the server accepts TCP connections on its file-share port."""
    ports = _SHARE_PORTS.get(str(network_protocol or "").lower(), _ANY_SHARE_PORT)
    for port in ports:
        try:
            with socket.create_connection((server, port), timeout=_PROBE_TIMEOUT_SECONDS):
                return True
        except OSError:
            continue
    return False


class HomeAssistantMediaSourcePower:
    def __init__(
        self,
        config: dict,
        *,
        client: HomeAssistantClient | None = None,
        probe: Callable[[str, str | None], bool] = share_reachable,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = MediaSourcePowerConfig.model_validate(
            dict((config or {}).get("media_source_power") or {})
        )
        self._client = client or HomeAssistantClient(config)
        self._probe = probe
        self._sleep = sleep
        self._monotonic = monotonic

    @property
    def configured(self) -> bool:
        return self._client.configured

    def request_power_on(self, request: MediaSourcePowerRequest) -> DeviceCommandResult:
        if self._probe(request.server, request.network_protocol):
            return DeviceCommandResult.skipped(f"{request.server} is already reachable.")

        missing = self._client.missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)

        requested, already_on, failures = [], [], []
        for entity_id in request.switch_entity_ids:
            try:
                state = self._client.get_state(entity_id)
            except HomeAssistantError as exc:
                failures.append(f"{entity_id}: {exc}")
                continue

            if state == "on":
                # Switch reports on but the share is not up yet: still booting.
                already_on.append(entity_id)
                continue

            result = self._client.call_service(
                "homeassistant", "turn_on", {"entity_id": entity_id}
            )
            if result.successful:
                requested.append(entity_id)
            else:
                failures.append(f"{entity_id}: {result.detail}")

        logger.info(
            "Media source power-on | server=%s | requested=%s | already_on=%s | failures=%s",
            request.server,
            ",".join(requested),
            ",".join(already_on),
            "; ".join(failures),
        )
        if failures and not (requested or already_on):
            return DeviceCommandResult.failed("; ".join(failures))
        return DeviceCommandResult.success(
            f"Power on requested for {request.server} "
            f"({', '.join(requested + already_on)})."
        )

    def wait_until_available(self, request: MediaSourcePowerRequest) -> DeviceCommandResult:
        started_at = self._monotonic()
        deadline = started_at + self._config.wait_timeout_seconds
        switch_seen_on = False

        while True:
            if self._probe(request.server, request.network_protocol):
                return DeviceCommandResult.success(
                    f"{request.server} reachable after "
                    f"{self._monotonic() - started_at:.0f}s."
                )

            switch_seen_on = switch_seen_on or self._any_switch_on(request)
            if self._monotonic() >= deadline:
                break
            self._sleep(self._config.poll_interval_seconds)

        if switch_seen_on:
            # HCC may simply not be able to reach the share port (another
            # VLAN, firewall); the OPPO can. Let it try instead of failing.
            logger.warning(
                "Media source switch is on but the share port was not reachable from "
                "HCC within %.0fs; continuing with OPPO mount | server=%s",
                self._config.wait_timeout_seconds,
                request.server,
            )
            return DeviceCommandResult.success(
                f"{request.server} switch is on; share not confirmed from HCC."
            )

        return DeviceCommandResult.failed(
            f"{request.server} did not come online within "
            f"{self._config.wait_timeout_seconds:.0f}s."
        )

    def _any_switch_on(self, request: MediaSourcePowerRequest) -> bool:
        for entity_id in request.switch_entity_ids:
            try:
                if self._client.get_state(entity_id) == "on":
                    return True
            except HomeAssistantError:
                continue
        return False


def create_media_source_power_or_none(config: dict) -> HomeAssistantMediaSourcePower | None:
    """None when Home Assistant is not configured: the feature is optional."""
    power = HomeAssistantMediaSourcePower(config)
    return power if power.configured else None


def power_on_media_source_for_mapping(config: dict, mapping: dict) -> DeviceCommandResult:
    """Setup action: wake the server behind one path mapping and wait for it.

    Used before testing or browsing a path whose NAS may be off. SKIPPED when
    the mapping has no switch, Home Assistant is not configured, or the share
    is already reachable.
    """
    switch_entity_id = str(mapping.get("power_switch_entity_id") or "").strip()
    server = _player_path_server(str(mapping.get("player_path") or ""))
    if not switch_entity_id or not server:
        return DeviceCommandResult.skipped("No power switch configured for this path.")

    power = create_media_source_power_or_none(config)
    if power is None:
        return DeviceCommandResult.skipped("Home Assistant not configured.")

    request = MediaSourcePowerRequest(
        switch_entity_ids=(switch_entity_id,),
        server=server,
        network_protocol=mapping.get("protocol") or None,
    )
    power_on_result = power.request_power_on(request)
    if power_on_result.status.value == "skipped":
        return power_on_result
    return power.wait_until_available(request)


def _player_path_server(player_path: str) -> str:
    """Server part of a player path such as /172.16.10.211/share/folder."""
    normalized = player_path.replace("\\", "/").strip("/")
    return normalized.split("/", 1)[0] if normalized else ""
