import json
import os
import shutil
from pathlib import Path

from home_cinema_control.config.migration import (
    _remove_legacy_flat_keys,
    reset_telemetry_consent_for_1_2_0,
)
from home_cinema_control.config.models import HccConfig, MediaServerProviderConfig
from home_cinema_control.media_servers.common.models import MediaServerProviderType


CONFIG_ENV_VAR = "HCC_CONFIG_FILE"
SECRETS_ENV_VAR = "HCC_SECRETS_FILE_PATH"

DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_SECRETS_FILE = "secrets.json"

EXAMPLE_CONFIG_FILE = "config.example.json"

SECRET_PATHS = {
    ("user_password",),
    ("smb", "password"),
    ("tv", "sony_psk"),
    ("lighting", "home_assistant_token"),
}

SENSITIVE_WEB_CONFIG_PATHS = set(SECRET_PATHS)

# media_servers.providers is keyed by provider type (emby/jellyfin/...), so its
# secret fields cannot be expressed as a static SECRET_PATHS tuple the way
# media_server's can. _split_media_server_provider_secrets/
# _merge_media_server_provider_secrets/_sanitize_media_server_providers handle
# this per dict key instead.
MEDIA_SERVER_PROVIDER_SECRET_FIELDS = ("access_token", "user_id")


def merge_existing_secrets(config_path: Path | str, config: dict) -> dict:
    """
    Return config with persisted secrets filled in for any secret path
    that is absent or empty in the submitted config.

    Submitted non-empty values always win so that newly entered credentials
    are not overwritten by the empty placeholders stored on first install.
    """
    config_path = Path(config_path)
    secrets = load_secrets(config_path)

    merged_config = _deep_merge({}, config)
    for path in SECRET_PATHS:
        submitted = str(_get_nested(merged_config, path, "") or "").strip()
        if not submitted:
            existing = str(_get_nested(secrets, path, "") or "").strip()
            if existing:
                _set_nested(merged_config, path, existing)

    _merge_media_server_provider_secrets(merged_config, secrets)
    _remove_legacy_flat_keys(merged_config)
    return merged_config


def sanitize_config_for_web(config: dict) -> dict:
    """
    Remove sensitive values before returning config to the web UI.

    The UI receives media_server.access_token_configured so it can show that
    Emby token authentication is configured without receiving the token or user id.

    smb.username is not a secret and is returned as-is so the UI can show which
    account is configured. smb.password_configured reports whether a password is
    stored, without exposing it, so the UI can distinguish the three SMB
    credential states: none, username only, or username + password.

    tv.sony_psk_configured reports whether a Sony Pre-Shared Key is stored, the
    same way smb.password_configured does for SMB, so the Sony TV form can show
    "already configured" instead of always rendering an empty field.

    lighting.home_assistant_token_configured does the same for the Home
    Assistant long-lived access token.
    """
    safe_config = _deep_merge({}, config)

    _sanitize_media_server_providers(safe_config, config)

    password_configured = bool(
        str(_get_nested(config, ("smb", "password"), "")).strip()
    )
    sony_psk_configured = bool(
        str(_get_nested(config, ("tv", "sony_psk"), "")).strip()
    )
    home_assistant_token_configured = bool(
        str(_get_nested(config, ("lighting", "home_assistant_token"), "")).strip()
    )

    for path in SENSITIVE_WEB_CONFIG_PATHS:
        _pop_nested(safe_config, path)

    safe_smb = safe_config.setdefault("smb", {})
    safe_smb["username"] = str(_get_nested(config, ("smb", "username"), "") or "")
    safe_smb["password_configured"] = password_configured

    safe_tv = safe_config.setdefault("tv", {})
    safe_tv["sony_psk_configured"] = sony_psk_configured

    safe_lighting = safe_config.setdefault("lighting", {})
    safe_lighting["home_assistant_token_configured"] = home_assistant_token_configured

    _remove_legacy_flat_keys(safe_config)

    return safe_config


def is_smb_active(config: dict) -> bool:
    """True when SMB/CIFS is the user-selected network protocol for the OPPO mount.

    Credentials are optional: the OPPO supports anonymous SMB shares, so the
    with-id vs. without-id mount choice is made separately, downstream, based
    on whether credentials happen to be present.
    """
    return bool(config.get("oppo", {}).get("use_smb", False))


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_FILE)


def get_secrets_path(config_path: Path | str | None = None) -> Path:
    configured_path = os.environ.get(SECRETS_ENV_VAR)

    if configured_path:
        return Path(configured_path)

    if config_path is None:
        config_path = get_config_path()

    return Path(config_path).with_name(DEFAULT_SECRETS_FILE)


def ensure_config_exists() -> Path:
    config_path = get_config_path()

    if not config_path.exists():
        _create_config_file(config_path)

    ensure_secrets_exists(config_path)

    return config_path


def ensure_secrets_exists(config_path: Path | str | None = None) -> Path:
    if config_path is None:
        config_path = get_config_path()
    else:
        config_path = Path(config_path)

    secrets_path = get_secrets_path(config_path)

    if secrets_path.exists():
        return secrets_path

    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(secrets_path, _default_secrets())
    _chmod_private(secrets_path)

    print(f"Secrets file created at {secrets_path}. Keep this file private.")
    return secrets_path


def load_effective_config(config_path: Path | str | None = None) -> dict:
    """
    Load the internal runtime config.

    Internal code receives app config + secrets merged together:

    config.json:
      media_server.server_url
      media_server.display_name
      media_server.access_token_configured

    secrets.json:
      media_server.access_token
      media_server.user_id
    """
    if config_path is None:
        config_path = ensure_config_exists()
    else:
        config_path = Path(config_path)
        ensure_secrets_exists(config_path)

    public_config = _read_json(config_path)
    secrets = load_secrets(config_path)

    effective_config = _deep_merge(public_config, secrets)
    return HccConfig.model_validate(effective_config).model_dump()


def load_public_config(config_path: Path | str | None = None) -> dict:
    """
    Load config safe to expose to the web UI.
    """
    effective_config = load_effective_config(config_path)
    return sanitize_config_for_web(effective_config)


def load_secrets(config_path: Path | str | None = None) -> dict:
    """
    Load secrets from the configured secrets file.

    There is intentionally no runtime fallback to user_password or
    config.secrets.json. Emby authentication is token-only.
    """
    if config_path is None:
        config_path = get_config_path()
    else:
        config_path = Path(config_path)

    return _read_json(get_secrets_path(config_path))


def save_effective_config(config_path: Path | str, config: dict) -> None:
    """
    Save app config and secrets separately.

    Sensitive nested values are written to secrets.json. Public values are
    written to config.json. If the web UI saves only public config, existing
    secrets are preserved.
    """
    config_path = Path(config_path)
    secrets_path = ensure_secrets_exists(config_path)

    public_config = _deep_merge({}, config)
    existing_secrets = load_secrets(config_path)
    secrets = _deep_merge({}, existing_secrets)

    for path in SECRET_PATHS:
        value = _pop_nested(public_config, path)

        if value not in (None, ""):
            _set_nested(secrets, path, value)

    _split_media_server_provider_secrets(public_config, secrets)

    # smb.username moved from secrets.json to config.json (it is not a secret).
    # Drop any leftover copy so a stale secrets.json value can no longer win
    # over a fresher config.json value during load_effective_config's merge.
    _pop_nested(secrets, ("smb", "username"))

    _remove_sensitive_paths(public_config)
    _remove_legacy_flat_keys(public_config)
    _remove_legacy_flat_keys(secrets)
    _drop_empty_legacy_media_server_secret(secrets)

    _write_json(config_path, public_config)
    _write_json(secrets_path, secrets)
    _chmod_private(secrets_path)


def clear_smb_credentials(config_path: Path | str) -> None:
    """Explicitly wipe stored SMB credentials.

    The password lives in secrets.json; the username lives in config.json
    (it is not a secret). Both are cleared so neither resurfaces later.
    """
    config_path = Path(config_path)
    secrets_path = ensure_secrets_exists(config_path)

    secrets = load_secrets(config_path)
    _set_nested(secrets, ("smb", "password"), "")
    _pop_nested(secrets, ("smb", "username"))
    _write_json(secrets_path, secrets)
    _chmod_private(secrets_path)

    public_config = _read_json(config_path)
    _set_nested(public_config, ("smb", "username"), "")
    _write_json(config_path, public_config)



def migrate_secrets_from_config(config_path: Path | str) -> None:
    """
    No-op kept temporarily only to avoid breaking any old caller.

    The app no longer supports migrating or using user_password at runtime.
    Emby authentication is token-only through secrets.json.
    """
    return None


def get_media_server_provider(
        config: HccConfig | dict, provider_type: MediaServerProviderType
) -> MediaServerProviderConfig:
    """Return the stored record for provider_type, or an empty one if absent."""
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )
    return validated.media_servers.providers.get(
        provider_type, MediaServerProviderConfig()
    )


def active_media_server_config(config: HccConfig | dict) -> MediaServerProviderConfig:
    """Return the provider record for the active provider type.

    Accepts a validated HccConfig or a raw dict (validates internally in the
    latter case via HccConfig.model_validate(config)) — but always returns the typed
    MediaServerProviderConfig, never a dict. Sugar for
    get_media_server_provider(config, active type).
    """
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )
    return get_media_server_provider(validated, validated.media_servers.active)


def active_media_server_type(config: HccConfig | dict) -> MediaServerProviderType:
    """The active provider's type string alone, for consumers that need to
    dispatch on it (provider.py's factory, the TV app id) rather than read the
    full provider record.
    """
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )
    return validated.media_servers.active


def upsert_media_server_provider(
        config: HccConfig | dict,
        provider_type: MediaServerProviderType,
        **fields,
) -> HccConfig:
    """Return a copy of config with provider_type's record updated by **fields.

    Unspecified fields on an existing record are left untouched (a partial
    update, e.g. only access_token), not reset to defaults.
    """
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )

    existing = validated.media_servers.providers.get(
        provider_type, MediaServerProviderConfig()
    )
    updated_providers = dict(validated.media_servers.providers)
    updated_providers[provider_type] = existing.model_copy(update=fields)

    updated_media_servers = validated.media_servers.model_copy(
        update={"providers": updated_providers}
    )
    return validated.model_copy(update={"media_servers": updated_media_servers})


def upsert_provider_playback(
        config: HccConfig | dict,
        provider_type: MediaServerProviderType,
        **fields,
) -> HccConfig:
    """Partial-update provider_type's playback sub-record by **fields.

    Leaves other playback fields and the provider's auth fields untouched —
    upsert_media_server_provider's model_copy(update=...) would otherwise
    replace the whole playback sub-object wholesale.
    """
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )
    provider = get_media_server_provider(validated, provider_type)
    new_playback = provider.playback.model_copy(update=fields)
    return upsert_media_server_provider(validated, provider_type, playback=new_playback)


def set_active_media_server(
        config: HccConfig | dict, provider_type: MediaServerProviderType
) -> HccConfig:
    """Return a copy of config with media_servers.active set to provider_type.

    Does not touch the provider's own record — pair with
    upsert_media_server_provider when a caller needs both (switching to a
    provider while also writing fresh credentials for it, e.g.
    configure_token, or the provider-switch flow in web/api_app.py).
    """
    validated = (
        config if isinstance(config, HccConfig) else HccConfig.model_validate(config)
    )
    return validated.model_copy(
        update={
            "media_servers": validated.media_servers.model_copy(
                update={"active": provider_type}
            )
        }
    )


def is_configured(config: HccConfig | dict) -> bool:
    provider = active_media_server_config(config)

    server_url = provider.server_url.strip()
    access_token = provider.access_token.strip()
    user_id = provider.user_id.strip()

    if not server_url or not access_token or not user_id:
        return False

    return server_url.startswith(("http://", "https://"))


def _drop_empty_legacy_media_server_secret(secrets: dict) -> bool:
    """Drop the old single-provider secrets.media_server stub once it holds
    nothing real. _default_secrets() seeded this shape for every install
    before media_servers.providers.* existed; migrate_media_server_to_media_servers
    only migrates it when the public config side also has real legacy data,
    so an install whose secrets.media_server was already blank (the common
    case: fresh installs, or any config never on the old single-provider
    shape) never gets it cleaned up. Return True if something was dropped.
    """
    old_secret = secrets.get("media_server")
    if not isinstance(old_secret, dict):
        return False
    if old_secret.get("access_token") or old_secret.get("user_id"):
        return False
    secrets.pop("media_server", None)
    return True


def migrate_media_server_to_media_servers(public_config: dict, secrets: dict) -> bool:
    """Transform the old single media_server block into media_servers, in
    place on both dicts. Return True if a migration was performed.

    Triggered by whether media_server still holds real data (server_url or
    display_name) — deliberately NOT by whether media_servers is already
    present. media_servers is a declared HccConfig field with its own
    Pydantic default, and has existed since before this function was wired
    into web/main.py — any unrelated config save in that window could already
    have written the bare default ({"active": "emby", "providers": {}}) to
    disk via model_dump(). A presence check would then treat that as "already
    migrated" forever and strand the real data in media_server. No-op if
    media_server has nothing real left (fresh install, or an already-drained
    leftover). Pure in-memory transform — see
    migrate_media_server_to_media_servers_on_disk for the file-level wrapper
    with backups, called once at startup from web/main.py.
    """
    old_public = public_config.get("media_server")
    has_real_legacy_data = isinstance(old_public, dict) and bool(
        old_public.get("server_url") or old_public.get("display_name")
    )
    if not has_real_legacy_data:
        return False

    provider_type = old_public.get("type", "emby")

    media_servers = public_config.setdefault("media_servers", {})
    providers = media_servers.setdefault("providers", {})
    providers[provider_type] = {
        "server_url": old_public.get("server_url", ""),
        "display_name": old_public.get("display_name", ""),
    }

    has_other_real_provider = any(
        ptype != provider_type
        and isinstance(provider, dict)
        and (provider.get("server_url") or provider.get("display_name"))
        for ptype, provider in providers.items()
    )
    if not has_other_real_provider:
        # media_servers.active was only ever sitting at its Pydantic default
        # (nothing real configured under the new shape yet) — the legacy
        # type is the only real answer. If some other provider already has
        # real data, leave active alone rather than silently flipping it.
        media_servers["active"] = provider_type

    public_config.pop("media_server", None)

    old_secret = secrets.get("media_server")
    if isinstance(old_secret, dict):
        secret_providers = secrets.setdefault("media_servers", {}).setdefault(
            "providers", {}
        )
        secret_providers[provider_type] = {
            "access_token": old_secret.get("access_token", ""),
            "user_id": old_secret.get("user_id", ""),
        }
        secrets.pop("media_server", None)

    return True


def migrate_media_server_to_media_servers_on_disk(config_path: Path | str) -> bool:
    """File-level wrapper around migrate_media_server_to_media_servers: reads
    config.json/secrets.json, writes a .bak-migrate backup of both before
    transforming, then persists the result. Return True if a migration was
    performed (and therefore backups were written).

    Called once at startup from web/main.py, after ensure_config_exists().
    """
    config_path = Path(config_path)
    secrets_path = get_secrets_path(config_path)

    public_config = _read_json(config_path)
    old_public = public_config.get("media_server")
    has_real_legacy_data = isinstance(old_public, dict) and bool(
        old_public.get("server_url") or old_public.get("display_name")
    )

    secrets = _read_json(secrets_path)

    if not has_real_legacy_data:
        # Mirrors migrate_media_server_to_media_servers's own trigger
        # condition exactly — gating on "media_servers already present"
        # instead would skip real data forever once an unrelated save has
        # already written that field's bare Pydantic default to disk.
        # Still worth a pass to drop a stale, empty secrets.media_server
        # stub (see _drop_empty_legacy_media_server_secret) — that doesn't
        # need a backup since nothing real is lost.
        if _drop_empty_legacy_media_server_secret(secrets):
            _write_json(secrets_path, secrets)
            _chmod_private(secrets_path)
        return False

    _backup_file(config_path, ".bak-migrate")
    _backup_file(secrets_path, ".bak-migrate")

    migrate_media_server_to_media_servers(public_config, secrets)
    _drop_empty_legacy_media_server_secret(secrets)

    _write_json(config_path, public_config)
    _write_json(secrets_path, secrets)
    _chmod_private(secrets_path)
    return True


_PLAYBACK_LEGACY_FIELDS = (
    "path_mappings",
    "libraries",
    "use_all_libraries",
    "hcc_controlled_device",
)


def migrate_playback_to_media_servers(public_config: dict) -> bool:
    """Return True if a migration was performed.

    Moves the four fields from the old flat playback block into the active
    provider's playback entry under media_servers.providers. Public config
    only — none of these four fields are secrets, unlike the auth migration.
    Separate function from migrate_media_server_to_media_servers, gated on its
    own evidence (playback still has any of the four fields), not on whether
    media_servers already exists — see the spec's Migration section for why.
    """
    old_playback = public_config.get("playback")
    has_legacy_data = isinstance(old_playback, dict) and any(
        field in old_playback for field in _PLAYBACK_LEGACY_FIELDS
    )
    if not has_legacy_data:
        return False

    media_servers = public_config.setdefault(
        "media_servers", {"active": "emby", "providers": {}}
    )
    active_type = media_servers.get("active", "emby")
    provider = media_servers.setdefault("providers", {}).setdefault(active_type, {})
    playback = provider.setdefault("playback", {})
    for field in _PLAYBACK_LEGACY_FIELDS:
        if field in old_playback:
            playback[field] = old_playback.pop(field)

    if not old_playback:
        public_config.pop("playback", None)

    return True


def migrate_playback_to_media_servers_on_disk(config_path: Path | str) -> bool:
    """File-level wrapper around migrate_playback_to_media_servers: reads
    config.json, writes a .bak-migrate-playback backup before transforming,
    then persists the result. Return True if a migration was performed.

    Called once at startup from web/main.py, immediately after
    migrate_media_server_to_media_servers_on_disk.
    """
    config_path = Path(config_path)
    public_config = _read_json(config_path)

    old_playback = public_config.get("playback")
    has_legacy_data = isinstance(old_playback, dict) and any(
        field in old_playback for field in _PLAYBACK_LEGACY_FIELDS
    )
    if not has_legacy_data:
        return False

    _backup_file(config_path, ".bak-migrate-playback")
    migrate_playback_to_media_servers(public_config)
    _write_json(config_path, public_config)
    return True


def reset_telemetry_consent_for_1_2_0_on_disk(config_path: Path | str) -> bool:
    """File-level wrapper around reset_telemetry_consent_for_1_2_0.

    Called once at startup from web/main.py.
    """
    config_path = Path(config_path)
    public_config = _read_json(config_path)

    if not reset_telemetry_consent_for_1_2_0(public_config):
        return False

    _write_json(config_path, public_config)
    return True


def _backup_file(path: Path, suffix: str) -> None:
    if not path.exists():
        return

    shutil.copyfile(path, path.with_name(path.name + suffix))


def _create_config_file(config_path: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Use CWD: in Docker the process root is /app, and in development it is the
    # project checkout root; both contain config.example.json.
    base = Path.cwd()
    legacy_config_path = base / DEFAULT_CONFIG_FILE
    example_path = base / EXAMPLE_CONFIG_FILE

    if legacy_config_path.exists() and legacy_config_path.resolve() != config_path.resolve():
        shutil.copyfile(legacy_config_path, config_path)
        print(
            f"Existing config found at {legacy_config_path}. "
            f"Copied it to {config_path}. Original file was left untouched."
        )
        return

    if not example_path.exists():
        raise FileNotFoundError(f"Missing {EXAMPLE_CONFIG_FILE}; cannot create default config")

    shutil.copyfile(example_path, config_path)
    print(f"Config file created at {config_path}. Complete setup from the web UI.")


def _default_secrets() -> dict:
    return {
        "smb": {
            "password": "",
        },
    }


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
        file.write("\n")


def _chmod_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except PermissionError:
        print(f"Could not chmod {path}; continuing without changing permissions.")


def _get_nested(data: dict, path: tuple[str, ...], default=None):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def _set_nested(data: dict, path: tuple[str, ...], value) -> None:
    current = data

    for key in path[:-1]:
        current = current.setdefault(key, {})

    current[path[-1]] = value


def _pop_nested(data: dict, path: tuple[str, ...]):
    current = data

    for key in path[:-1]:
        current = current.get(key)

        if not isinstance(current, dict):
            return None

    return current.pop(path[-1], None)


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge two dicts into a new dict with no shared nested-dict references.

    A shallow `dict(base)` plus direct assignment would let a caller's
    in-place pop/set on the result (e.g. moving a secret out of the public
    config in save_effective_config) silently mutate the original `base` or
    `override` dict too, since they'd still share the same nested object.
    """
    merged = {
        key: _deep_merge({}, value) if isinstance(value, dict) else value
        for key, value in base.items()
    }

    for key, value in override.items():
        if isinstance(value, dict):
            existing = merged.get(key)
            merged[key] = _deep_merge(
                existing if isinstance(existing, dict) else {}, value
            )
        else:
            merged[key] = value

    return merged


def _remove_sensitive_paths(config: dict) -> None:
    for path in SENSITIVE_WEB_CONFIG_PATHS:
        _pop_nested(config, path)


def _merge_media_server_provider_secrets(merged_config: dict, secrets: dict) -> None:
    """Fill blank access_token/user_id in each media_servers.providers entry
    from secrets, in place on merged_config.

    Read-side counterpart of _split_media_server_provider_secrets, used by
    merge_existing_secrets the same way the SECRET_PATHS loop above is: a
    submitted blank value never overwrites an already-stored secret.
    load_effective_config does not need this — its plain _deep_merge already
    merges media_servers.providers key-by-key since it is a nested dict, same
    as any other config section.
    """
    providers = merged_config.get("media_servers", {}).get("providers")
    if not isinstance(providers, dict):
        return

    secret_providers = secrets.get("media_servers", {}).get("providers") or {}

    for provider_type, provider in providers.items():
        if not isinstance(provider, dict):
            continue

        secret_entry = secret_providers.get(provider_type) or {}
        for field in MEDIA_SERVER_PROVIDER_SECRET_FIELDS:
            submitted = str(provider.get(field, "") or "").strip()
            if not submitted:
                existing = str(secret_entry.get(field, "") or "").strip()
                if existing:
                    provider[field] = existing


def _split_media_server_provider_secrets(public_config: dict, secrets: dict) -> None:
    """Move access_token/user_id out of each media_servers.providers entry into
    secrets, in place on both dicts, replacing them with access_token_configured.

    Write-side counterpart of _merge_media_server_provider_secrets. Mirrors what
    the SECRET_PATHS loop in save_effective_config does for media_server, but
    per dict key since provider type is not a fixed path segment a static
    SECRET_PATHS tuple can express.
    """
    providers = public_config.get("media_servers", {}).get("providers")
    if not isinstance(providers, dict):
        return

    secret_providers = secrets.setdefault("media_servers", {}).setdefault(
        "providers", {}
    )

    for provider_type, provider in providers.items():
        if not isinstance(provider, dict):
            continue

        secret_entry = secret_providers.setdefault(provider_type, {})
        for field in MEDIA_SERVER_PROVIDER_SECRET_FIELDS:
            value = provider.pop(field, None)
            if value not in (None, ""):
                secret_entry[field] = value

        provider["access_token_configured"] = bool(
            str(secret_entry.get("access_token", "")).strip()
        )


def _sanitize_media_server_providers(safe_config: dict, original_config: dict) -> None:
    """Per-provider equivalent of the single media_server access_token_configured
    flag above: every entry in media_servers.providers gets its own flag, with
    access_token/user_id stripped — for every provider, not just the active
    one, so an inactive-but-configured provider's token is never sent to the
    frontend either.
    """
    providers = safe_config.get("media_servers", {}).get("providers")
    if not isinstance(providers, dict):
        return

    original_providers = (
            original_config.get("media_servers", {}).get("providers") or {}
    )

    for provider_type, provider in providers.items():
        if not isinstance(provider, dict):
            continue

        original_provider = original_providers.get(provider_type) or {}
        provider["access_token_configured"] = bool(
            str(original_provider.get("access_token", "")).strip()
            or provider.get("access_token_configured") is True
        )
        provider.pop("access_token", None)
        provider.pop("user_id", None)
