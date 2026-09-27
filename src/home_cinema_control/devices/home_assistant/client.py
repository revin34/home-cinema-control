"""Home Assistant REST transport shared by every HCC feature that uses it.

Owns bearer-token auth, service calls and the /api/states mapping to
HomeAssistantEntity. Features (room lighting, media-source power) build on
this client and never touch Home Assistant's wire format themselves.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import requests

from home_cinema_control.config.models import HomeAssistantConfig
from home_cinema_control.network.http import get_http_session
from home_cinema_control.playback.startup.models import DeviceCommandResult

logger = logging.getLogger(__name__)


class HomeAssistantError(Exception):
    """Home Assistant could not be reached or rejected the request."""


@dataclass(frozen=True)
class HomeAssistantEntity:
    entity_id: str
    name: str
    state: str


class HomeAssistantClient:
    def __init__(self, config: dict, *, http_session=None) -> None:
        raw = dict((config or {}).get("home_assistant") or {})
        self._token = str(raw.get("token") or "").strip()
        self._config = HomeAssistantConfig.model_validate(raw)
        self._base_url = self._config.url.strip().rstrip("/")
        self._http = http_session or get_http_session("home_assistant")

    @property
    def configured(self) -> bool:
        return self.missing_settings() is None

    def missing_settings(self) -> str | None:
        if not self._base_url:
            return "Home Assistant URL not configured."
        if not self._token:
            return "Home Assistant access token not configured."
        return None

    def test_connection(self) -> DeviceCommandResult:
        missing = self.missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)

        try:
            response = self._http.get(
                f"{self._base_url}/api/",
                headers=self._headers(),
                timeout=self._config.timeout_seconds,
                suppress_exception_log=True,
            )
        except requests.RequestException as exc:
            return DeviceCommandResult.failed(
                f"Home Assistant unreachable: {type(exc).__name__}"
            )

        if response.status_code == 401:
            return DeviceCommandResult.failed("Home Assistant rejected the access token.")
        if response.status_code >= 400:
            return DeviceCommandResult.failed(
                f"Home Assistant returned HTTP {response.status_code}."
            )
        return DeviceCommandResult.success("Home Assistant API reachable.")

    def list_entities(self, domains: Iterable[str]) -> list[HomeAssistantEntity]:
        """Entities of the given domains, sorted by name; raises HomeAssistantError."""
        wanted = set(domains)
        response = self._get("/api/states")
        entities = [
            _map_state(item)
            for item in response.json() or []
            if entity_domain(item.get("entity_id", "")) in wanted
        ]
        return sorted(entities, key=lambda entity: (entity.name.lower(), entity.entity_id))

    def get_state(self, entity_id: str) -> str:
        """Current state string of one entity; raises HomeAssistantError."""
        return str(self.get_entity(entity_id).get("state", ""))

    def get_entity(self, entity_id: str) -> dict:
        """State and attributes of one entity; raises HomeAssistantError."""
        return self._get(f"/api/states/{entity_id}").json() or {}

    def call_service(
        self,
        domain: str,
        service: str,
        data: dict,
        *,
        extra_timeout_seconds: float = 0.0,
    ) -> DeviceCommandResult:
        missing = self.missing_settings()
        if missing:
            return DeviceCommandResult.failed(missing)

        try:
            response = self._http.post(
                f"{self._base_url}/api/services/{domain}/{service}",
                headers=self._headers(),
                json=data,
                timeout=self._config.timeout_seconds + extra_timeout_seconds,
            )
        except requests.RequestException as exc:
            return DeviceCommandResult.failed(
                f"Home Assistant {domain}.{service} failed: {type(exc).__name__}"
            )

        if response.status_code >= 400:
            return DeviceCommandResult.failed(
                f"Home Assistant {domain}.{service} returned HTTP {response.status_code}."
            )
        return DeviceCommandResult.success(f"Home Assistant {domain}.{service} applied.")

    def _get(self, path: str):
        missing = self.missing_settings()
        if missing:
            raise HomeAssistantError(missing)

        try:
            response = self._http.get(
                f"{self._base_url}{path}",
                headers=self._headers(),
                timeout=self._config.timeout_seconds,
                suppress_exception_log=True,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError(
                f"Home Assistant unreachable: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            raise HomeAssistantError(f"Home Assistant returned HTTP {response.status_code}.")
        return response

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }


def entity_domain(entity_id: str) -> str:
    return str(entity_id).split(".", 1)[0]


def _map_state(item: dict) -> HomeAssistantEntity:
    entity_id = str(item.get("entity_id", ""))
    attributes = item.get("attributes") or {}
    return HomeAssistantEntity(
        entity_id=entity_id,
        name=str(attributes.get("friendly_name") or entity_id),
        state=str(item.get("state", "")),
    )
