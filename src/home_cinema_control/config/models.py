from pydantic import BaseModel, ConfigDict, Field, field_validator

from home_cinema_control.media_servers.common.models import (
    MediaServerLibrary,
    MediaServerProviderType,
)


class PathMappingConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    source_path: str = ""
    player_path: str = "/"
    protocol: str = ""
    verified: bool = False


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    backup_path: str = "backup"
    language: str = "es-ES"
    status_refresh_interval_seconds: int = 5
    include_prerelease: bool = False
    version_check_interval_hours: int = 24
    update_webhook_url: str = ""
    previous_version: str = ""
    release_repository: str = "tousled/home-cinema-control"
    version_check_timeout_seconds: int = 10
    log_level: int = 0


class AvInputSource(BaseModel):
    id: int
    name: str
    param: str


class AvConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    ip: str = ""
    port: int = 23
    model: str = ""
    always_on: bool = True
    hdmi_switch_delay_seconds: float = 0.0
    power_on_command: str = ""
    hdmi_input_command: str = ""
    power_off_command: str = ""
    available_hdmi_inputs: list[AvInputSource] = Field(default_factory=list)
    player_hdmi_input: str = ""
    connection_timeout_seconds: float = 5.0
    command_timeout_seconds: float = 1.0
    tv_connected_input: str = ""

    @field_validator("available_hdmi_inputs", mode="before")
    @classmethod
    def _coerce_av_inputs(cls, v):
        result = []
        for i, item in enumerate(v or []):
            if isinstance(item, dict) and "Id" in item:
                result.append({
                    "id": item.get("Id", i),
                    "name": item.get("Name", ""),
                    "param": item.get("Param", ""),
                })
            else:
                result.append(item)
        return result


class TvConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    ip: str = ""
    mac: str = ""
    model: str = ""
    available_hdmi_inputs: list = Field(default_factory=list)
    player_hdmi_input_id: int = 0
    startup_script: str = ""
    shutdown_script: str = ""


class SonyTvConfig(TvConfig):
    """Sony-only fields. LG/Scripts configs stay plain TvConfig and never carry these.

    sony_psk is deliberately not a field here: it is a secret, merged in at runtime
    via SECRET_PATHS/secrets.json, never part of the persisted config.json schema.
    """

    sony_app_uris: dict[str, str] = Field(default_factory=dict)


class OppoConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    ip: str = ""
    observation_mode: str = "auto"
    connection_timeout_seconds: float = 10.0
    playback_start_timeout_seconds: float = 30.0
    nfs_mount_timeout_seconds: float = 30.0
    track_menu_ready_timeout_seconds: float = 8.0
    track_menu_ready_poll_interval_seconds: float = 0.5
    track_menu_query_timeout_seconds: float = 1.0
    track_selection_applied_timeout_seconds: float = 2.0
    track_selection_applied_poll_interval_seconds: float = 0.25
    api_connect_timeout_seconds: float = 1.0
    api_retry_attempts: int = 3
    autoscript: bool = False
    autoscript_unmount_timeout_seconds: float = 3.0
    always_on: bool = True
    bluray_disc_mode: bool = False
    pre_mount_smb: bool = False
    use_smb: bool = False


class SmbConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    username: str = ""
    password: str = ""


MAX_LIGHTING_FADE_SECONDS = 300.0


class LightingConfig(BaseModel):
    """Room lighting driven through Home Assistant during playback.

    home_assistant_token is deliberately not a field here: it is a secret,
    merged in at runtime via SECRET_PATHS/secrets.json, never part of the
    persisted config.json schema.
    """

    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    home_assistant_url: str = ""
    entity_ids: list[str] = Field(default_factory=list)
    on_playback_start: str = "turn_off"
    on_playback_stop: str = "turn_on"
    # Home Assistant light transition, in seconds; 0 switches instantly.
    fade_out_seconds: float = 0.0
    fade_in_seconds: float = 0.0
    timeout_seconds: float = 5.0

    @field_validator("fade_out_seconds", "fade_in_seconds", mode="before")
    @classmethod
    def _coerce_fade_seconds(cls, v):
        # A blank or invalid UI value must never break playback wiring: it
        # just means "no fade". Capped to keep a typo from dimming for hours.
        try:
            seconds = float(v)
        except (TypeError, ValueError):
            return 0.0
        if seconds != seconds:  # NaN
            return 0.0
        return min(max(seconds, 0.0), MAX_LIGHTING_FADE_SECONDS)


class TelemetryConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    installation_id: str = ""
    endpoint_url: str = ""
    ingest_key: str = ""
    consent_prompted: bool = False
    consent_reset_1_2_0: bool = False
    schema_version: int = 1
    last_heartbeat_at: str = ""
    queue_max_events: int = 100
    queue_max_age_days: int = 7


class ProviderPlaybackConfig(BaseModel):
    """What HCC needs to detect and translate playback from one provider.

    Distinct from MediaServerProviderConfig's auth fields: this comes from
    library/device detection and the Media Paths screen, not the login flow.
    See .agents/specs/2026-06-23-media-server-scoped-paths-libraries-device.md.
    """

    model_config = ConfigDict(extra="allow")

    hcc_controlled_device: str = ""
    use_all_libraries: bool = False
    path_mappings: list[PathMappingConfig] = Field(default_factory=list)
    libraries: list[MediaServerLibrary] = Field(default_factory=list)


class MediaServerProviderConfig(BaseModel):
    """A single provider's (Emby or Jellyfin) connection/auth/playback record.

    Lives at media_servers.providers[provider_type] — the dict key is the
    provider type, so this model carries no type field of its own.
    """

    model_config = ConfigDict(extra="allow")

    server_url: str = ""
    display_name: str = ""
    access_token: str = ""
    user_id: str = ""
    playback: ProviderPlaybackConfig = Field(default_factory=ProviderPlaybackConfig)


class MediaServersConfig(BaseModel):
    """Persists every configured provider's record, not just the active one.

    See .agents/specs/2026-06-23-media-server-multi-provider-config-design.md.
    """

    model_config = ConfigDict(extra="allow")

    active: MediaServerProviderType = "emby"
    providers: dict[MediaServerProviderType, MediaServerProviderConfig] = Field(
        default_factory=dict
    )


class HccConfig(BaseModel):
    """
    Validated user config loaded from disk. Does not include runtime-injected
    fields (Version, tv_dirs, av_dirs, langs, devices) — those are added by
    web runtime enrichment after loading.

    The legacy single-provider media_server field is gone: every consumer now
    reads media_servers (see
    .agents/specs/2026-06-23-media-server-multi-provider-config-design.md).
    A stale media_server key from an unmigrated config.json survives as an
    unvalidated extra field (extra="allow") until
    migrate_media_server_to_media_servers_on_disk runs at startup — it is
    never read as a typed model again.
    """

    model_config = ConfigDict(extra="allow")

    app: AppConfig = Field(default_factory=AppConfig)
    av: AvConfig = Field(default_factory=AvConfig)
    tv: TvConfig = Field(default_factory=TvConfig)
    oppo: OppoConfig = Field(default_factory=OppoConfig)
    media_servers: MediaServersConfig = Field(default_factory=MediaServersConfig)
    smb: SmbConfig = Field(default_factory=SmbConfig)
    lighting: LightingConfig = Field(default_factory=LightingConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
