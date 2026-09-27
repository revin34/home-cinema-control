from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from home_cinema_control.config.manager import (
    active_media_server_type,
    set_active_media_server,
    upsert_media_server_provider,
    upsert_provider_playback,
)
from home_cinema_control.config.models import PathMappingConfig
from home_cinema_control.media_servers.common.models import (
    MediaServerLibrary,
    MediaServerProviderType,
)

# Sections that are a partial field-merge into config[section]: the body holds
# only the changed keys and every other stored field must survive. They stay
# untyped dict merges on purpose — the config models use extra="allow", so an
# all-optional Pydantic body model here would only restate those models and
# re-introduce the default duplication that the Pydantic-defaulting work removed.
SIMPLE_SECTIONS = ("app", "oppo", "tv", "av", "smb", "home_assistant", "lighting")


class MediaServerSectionBody(BaseModel):
    """The media-server section wire body, in either accepted shape.

    Callers send either a {"media_server": {...}} wrapper or a bare flat dict
    (both shapes are live — see media_server_routes.py). Only the provider
    fields actually present are applied, so a body that omits server_url must
    not blank a stored server_url. Never carries access_token/user_id: those
    come only from configure_token/check_connection.
    """

    model_config = ConfigDict(extra="allow")

    type: MediaServerProviderType | None = None
    server_url: str | None = None
    display_name: str | None = None

    @classmethod
    def parse(cls, body: dict[str, Any]) -> "MediaServerSectionBody":
        source = body.get("media_server") or body
        return cls.model_validate(source)

    def provider_fields(self) -> dict[str, Any]:
        return self.model_dump(include={"server_url", "display_name"}, exclude_unset=True)


class PlaybackLibrariesSectionBody(BaseModel):
    """The libraries-selection wire body for the active provider."""

    libraries: list[MediaServerLibrary] = Field(default_factory=list)
    use_all_libraries: bool = True


class PathMappingsSectionBody(BaseModel):
    """The path-mappings wire body for the active provider."""

    path_mappings: list[PathMappingConfig] = Field(default_factory=list)


def apply_simple_section(config: dict[str, Any], section: str, body: dict[str, Any]) -> dict[str, Any]:
    """Partial-merge a flat section (app/oppo/tv/av/smb/home_assistant/lighting) into config[section]."""
    source = body.get(section) if section in body else body
    updated = {**config}
    updated[section] = {**(config.get(section) or {}), **(source or {})}
    return updated


def apply_media_server_section(config: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Upsert the target provider, make it active, and apply the optional
    monitored-device selector. Auth fields are never written here.
    """
    section = MediaServerSectionBody.parse(body)
    target_type = section.type or active_media_server_type(config)
    merged = upsert_media_server_provider(config, target_type, **section.provider_fields())
    merged = set_active_media_server(merged, target_type)

    if "playback" in body:
        # The monitored-device selector keeps the wire shape
        # {"playback": {"hcc_controlled_device": ...}} even though it now lands
        # in the provider's nested playback record. No caller sends a bare
        # top-level hcc_controlled_device, so that shape is not handled.
        device = (body.get("playback") or {}).get("hcc_controlled_device", "")
        merged = upsert_provider_playback(merged, target_type, hcc_controlled_device=device)

    return merged.model_dump()


def apply_playback_libraries_section(config: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    section = PlaybackLibrariesSectionBody.model_validate(body)
    active_type = active_media_server_type(config)
    merged = upsert_provider_playback(
        config,
        active_type,
        libraries=section.libraries,
        use_all_libraries=section.use_all_libraries,
    )
    return merged.model_dump()


def apply_path_mappings_section(config: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    section = PathMappingsSectionBody.model_validate(body)
    active_type = active_media_server_type(config)
    merged = upsert_provider_playback(config, active_type, path_mappings=section.path_mappings)
    return merged.model_dump()


def apply_network_access_section(config: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    updated = {**config}
    updated["oppo"] = {**(config.get("oppo") or {}), **(body.get("oppo") or {})}
    updated["smb"] = {**(config.get("smb") or {}), **(body.get("smb") or {})}
    if "path_mappings" in body:
        active_type = active_media_server_type(updated)
        path_mappings = [PathMappingConfig.model_validate(item) for item in body["path_mappings"]]
        updated = upsert_provider_playback(
            updated, active_type, path_mappings=path_mappings
        ).model_dump()
    return updated


_SECTION_HANDLERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    **{section: (lambda c, b, s=section: apply_simple_section(c, s, b)) for section in SIMPLE_SECTIONS},
    "media-server": apply_media_server_section,
    "playback-libraries": apply_playback_libraries_section,
    "path-mappings": apply_path_mappings_section,
    "network-access": apply_network_access_section,
}


def apply_config_section(config: dict[str, Any], section: str, body: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a config section string to its handler.

    Retained for the PATCH /config/{section} route, which receives the section
    from the URL. Internal callers that already know the section should call the
    matching apply_<section>_section handler directly.
    """
    handler = _SECTION_HANDLERS.get(section)
    if handler is None:
        raise ValueError(f"Unsupported config section: {section}")
    return handler(config, body)
