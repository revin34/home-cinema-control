# Changelog

All notable changes to this project will be documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning follows semantic versioning where practical.

## [Unreleased]

### Added

* Added native Trinnov Altitude AV receiver support over the Altitude TCP automation protocol. HCC identifies as
  `Home Cinema Control`, switches OPPO and TV-audio targets with Trinnov source/profile numbers, uses Wake-on-LAN
  after the MAC address is configured or detected from the network scan, locks Trinnov power actions until that MAC is
  available, and treats the integration as contract-tested until real Altitude hardware logs confirm it.

* Added optional room lighting control through Home Assistant. From the Room screen, configure the Home Assistant URL,
  a long-lived access token (stored in `secrets.json`), and the `light`/`switch` entities to control. HCC turns them
  off once the OPPO confirms playback has started and back on when playback ends (stop, natural end, or playback
  failure); both actions are configurable. Lights are left untouched when OPPO startup fails or when a new item
  replaces the current playback, and Home Assistant calls run off the playback thread so a slow or unreachable
  instance never delays the handoff.

### Fixed

* Updated LG webOS pairing to use HCC's own unsigned prompt manifest instead of the legacy LG test-app signature
  that newer webOS 26 firmware can reject as a blacklisted certificate. LG connections now also skip the library's
  eager software-info hydration, which newer firmware can reject with `401 insufficient permissions`. Existing LG
  setups may need to accept the pairing prompt again after updating.

* Registered HCC as a video-only playback target for Emby/Jellyfin and ignored ambient `theme.mp3` playback events
  from theme/opening plugins, so selecting a movie or series no longer routes those MP3 themes through HCC or starts
  the OPPO handoff before the actual video item is played.

* Stopped the source Emby/Jellyfin client before every OPPO handoff, including remote-control playback commands
  targeting HCC, so the TV app no longer keeps playing the same item after OPPO playback is stopped.

* Extended Emby stop cleanup to all active sessions for the same user and item, matching the existing Jellyfin
  protection, so a renewed/stale Emby TV session cannot keep playing after OPPO playback finishes.

* Blocked Emby/Jellyfin playback handoff when media-server item details cannot be loaded, such as with an expired
  Emby access token, so HCC no longer starts OPPO takeover from WebSocket-only session data and then remains stuck in
  `Loading`.

## [1.2.1] - 2026-07-08

### Fixed

* Reduced OPPO natural-end detection tolerance so HCC no longer treats playback as finished ten seconds before the
  title total while SVM3 still reports active playback. The shorter tolerance keeps the existing anti-auto-advance
  behavior but avoids the observed early stop near the end of Jellyfin/Emby playback.

* Reduced TV current-app lookup impact during playback startup: LG now uses a short current-app connection timeout,
  startup skips the lookup when TV control is disabled or missing, and HCC falls back to the configured media-server
  TV app when exact current-app detection is unavailable.

* Hid the "available version" row in Diagnostics when HCC is already up to date, so the current installed version is
  not repeated as if it were an update.

* Cleared the Diagnostics navbar update indicator when the latest version check reports that HCC is already up to
  date.

* Fixed version checks with "include pre-releases" enabled so stable releases still participate in semantic version
  ordering. Older release candidates such as `1.2.0-rc.6` no longer hide newer stable releases such as `1.2.1`, while
  future release candidates such as `1.3.0-rc.1` are still surfaced when they are the newest available version.

## [1.2.0] - 2026-07-07

### Added

* Added a "Send diagnostics" action on the Diagnostics screen for reporting bugs from non-technical installs. It
  builds a report from the support summary and recent log lines, automatically redacts IPs, MAC addresses,
  credentials, URLs, and configured folder paths, and shows the result in an editable preview before anything
  happens. Confirming copies the (possibly edited) text to the clipboard and opens a pre-filled GitHub "new issue"
  page in a new tab for the user to paste into and submit themselves — there is no backend call to GitHub, no bot
  account, and no server-side storage of the report.

* Added a Sony BRAVIA TV adapter (2013+ models) using Sony's official local REST API, authenticated with a
  Pre-Shared Key configured directly on the TV — no cloud account required, unlike the SmartThings-dependent
  Samsung path that was explored and set aside. Supports dynamic HDMI input discovery and direct switching,
  and a "detect installed apps" step in Room Setup so Emby/Jellyfin can be launched from a per-TV discovered
  app identifier instead of a hardcoded id. Current-app detection falls back to the configured media-server
  provider when the TV can't report it directly. Contract-tested against a mocked REST API; not yet validated
  on real Sony hardware.

* Added a tooltip on the Sony PSK field in Room Setup explaining where to find/set the Pre-Shared Key on the TV.

* Changed Room Setup's TV form so that switching the model dropdown clears the rest of the form (IP, MAC, detected
  inputs, PSK, app mappings) unless you switch back to the model you already have saved, in which case its
  configuration is restored instead of staying blank. HDMI input detection, "Switch to OPPO", "Detect apps" and
  "Open Emby/Jellyfin" are now disabled until "Test connection" succeeds, since none of them make sense against an
  unreachable TV. The "Open Emby/Jellyfin" action for Sony moved next to "Detect apps" (it depends on app detection,
  not HDMI detection) and now stays disabled with an explanatory message until that app is actually found among the
  TV's detected apps.

### Fixed

* Hardened OPPO SMB/CIFS mounting after `id_error`: SMB pre-mount now uses the configured SMB credentials, failed
  pre-mount attempts are logged as failures instead of "primed" successes, and SMB `id_error` no longer triggers an
  immediate second mount attempt that can further stress the OPPO control API.

* Fixed Sony BRAVIA HDMI switching confirmation noise on models that return `Illegal State` from
  `getPlayingContentInfo` immediately after a successful input change. HCC now treats that specific response as
  unavailable confirmation instead of warning like the input switch itself failed.

* Fixed a race in Room Setup's TV form where a successful "Test connection" could be silently undone: reassigning
  the form state from the server response triggered an existing watcher (async by default) that resets the
  "tested" flag on any field change, which ran after the connection test had already marked the TV as tested and
  clobbered it back to untested — leaving TV action buttons disabled even though the connection had just succeeded.

## [1.1.4] - 2026-06-30

### Fixed

* Fixed OPPO entering an unresponsive state after SMB playback when the autoscript Telnet shell was unavailable
  during unmount. The unmount failure now resolves as skipped rather than failed, preventing the error recovery
  loop from issuing repeated forced-stop commands that exhausted the OPPO's network stack and required a power
  cycle to recover.

## [1.1.3] - 2026-06-29

### Added

* Added opt-in product telemetry and roadmap feedback controls on the Diagnostics screen. Telemetry is disabled by
  default, uses a random anonymous installation ID, retries failed sends through a bounded local queue, and documents
  exactly what is sent and why. HCC never sends media titles, libraries, paths, URLs, IPs, tokens, logs, scripts, or
  custom commands in telemetry payloads.

* Added a new poll for user feedback on the Diagnostics screen. Next features can be voted on in the poll.
  The most qualified features will be implemented first.

### Fixed

* Denon and Marantz AV receivers now query their available inputs dynamically via the `SSSOD ?` TCP command instead
  of returning a fixed hardcoded list. Only inputs the receiver reports as enabled (`USE`) are shown. If the receiver
  is unreachable during detection, HCC falls back to a built-in catalog that now includes AUX 1 and AUX 2 — the two
  entries previously missing that prevented users with an OPPO connected to those inputs from selecting the correct
  source. A fixed bug in the Denon fallback list sent `GAME\n` instead of `SIGAME\n`, which would have silently
  ignored the command.

## [1.1.2] - 2026-06-27

### Fixed

* Fixed the Logs and Diagnostics copy buttons for browsers that block or hide the Clipboard API. Copying the visible
  log lines and the support summary now falls back to the browser's legacy copy path instead of showing errors such as
  `Cannot read properties of undefined (reading 'writeText')` or failing when clipboard permission changes.

## [1.1.1] - 2026-06-27

### Added

* Release tag pushes now create a GitHub Release automatically after the Docker image publishes, with release notes
  extracted from the matching `CHANGELOG.md` section and release-candidate tags falling back to their base version
  section when there is no exact RC changelog heading.
* Added mobile-friendly log sharing controls to the Logs screen: the console now defaults to the latest 100 visible
  lines, offers larger preset ranges, and can copy the currently filtered/shown lines directly to the clipboard.

### Fixed

* Fixed Jellyfin 12.0 RC1 compatibility after Jellyfin's `20260531160000_DisableLegacyAuthorization` migration disables
  legacy authorization. HCC now sends Jellyfin REST credentials through the modern
  `Authorization: MediaBrowser ... Token=...`
  header and opens the Jellyfin WebSocket with modern `Authorization` plus legacy token headers, and both modern
  `ApiKey` and legacy `api_key` query parameters. This addresses Jellyfin 12 startup failures that showed
  `403 Forbidden` during WebSocket handshake and `401` from `/Devices`, `/Library/VirtualFolders`, or
  `/Sessions/Capabilities/Full` without breaking Jellyfin 10.x WebSocket authentication.
* Fixed Diagnostics version display and rollback guidance for release-candidate Docker tags. Runtime versions produced
  by `setuptools_scm` are now shown in Docker tag form (`1.1.1-rc.1`, not `1.1.1rc1`), update-triggered rollback stores
  that tag form, and installs whose config only contains the build fallback (`0.0.0.dev0`) derive a rollback target from
  GitHub releases/tags instead of showing the fallback as a real image version.
* Fixed version checks so the "include pre-release versions" toggle selects the expected release channel: disabled shows
  the latest stable release, enabled shows the latest release candidate/pre-release when one exists.
* Fixed rollback target selection for release candidates so `1.1.1-rc.2` rolls back to `1.1.1-rc.1`, while
  `1.1.1-rc.1` prefers the same-base stable `1.1.1` over older release candidates such as `1.1.0-rc.5`.
* Updated the Docker Hub overview to mention Jellyfin support and the current log copy/download support flow.

## [1.1.0] - 2026-06-26

### Added

* Path mappings, detected libraries, the library-filter preference, and the monitored device now persist
  independently per media-server provider (`media_servers.providers[type].playback`), instead of one shared block
  used by whichever provider happened to be active. Switching between Emby and Jellyfin now shows each provider's
  own mappings/libraries/device, and switching back restores them exactly as left — the same guarantee already
  shipped for auth in 1.0.5. Includes an automatic, one-time migration of existing installs' config.
* Added toast feedback for the Media Server provider switch: a confirmation when the switch lands on an
  already-authorized provider (previously silent — the only feedback was a transient "connecting…" state), and a
  distinct message when the switch succeeds but the target provider still needs login.
* Added a provider-branded Media Server hero mark that surfaces the selected Emby/Jellyfin provider without repeating
  the server URL, user, or readiness details already shown in the configuration panels. The mark stays visible as
  setup context while the provider is pending authorization, but renders muted until the provider is authorized.
* Updated the Media Server installation screenshots to show provider selection, the Jellyfin hero mark, and the muted
  provider state shown before authorization.
* Added a compact active-provider badge to Media Paths so the detected-library and route-mapping workflow keeps the
  configured Emby/Jellyfin context visible without overloading the refresh action.
* Added a shared, provider-neutral `find_controlling_session_id` policy (`media_servers/common/models.py`) that
  resolves which client session actually issued a remote Play command, used by both Emby and Jellyfin.
* Instrumented two previously invisible OPPO startup phases — mounting the network share (`mount_oppo_network_share`,
  includes the device-list-ready wait) and waiting for the OPPO to actually report active playback
  (`wait_for_oppo_playback_active`, the QPL telnet poll after launching the file) — into the existing
  `PlaybackStartupTimer`. Before this, a slow OPPO response in either phase showed up as an unexplained gap between
  the named steps and the printed `total` in "Playback startup timing summary," with no way to tell from the log
  alone whether the OPPO, the TV/AV output switch, or something else caused it. No behavior change: both are
  optional, timer-only wrapping.
* Added a first-run modal offering to import a legacy XNOPPO `config.json` (the predecessor project this app
  replaces) on a fresh install with nothing configured yet, separate from the existing "legacy config already on
  disk" migration modal. The user picks the old `config.json` file, HCC migrates AV/TV/OPPO/playback settings the
  same way the existing migration pipeline already does, moves the Emby server URL into the new multi-provider
  config shape, and makes a best-effort live login with the file's username/password to obtain a real access token
  — if that login fails (e.g. the Emby server isn't reachable yet), the provider is just left unauthenticated, same
  as any freshly added provider, and the existing sidebar readiness indicator shows it needs attention.

### Fixed

* Fixed the Media Server setup screen treating saved provider data as live success when the active Emby/Jellyfin server
  is unavailable. The form now renders from saved config immediately instead of waiting for slow device/library
  discovery timeouts, failed device discovery is shown explicitly, affected panels no longer stay green, and the
  sidebar setup dot is downgraded while the current provider cannot be reached.
* Fixed the monitored-device selector showing blank rows when a provider returned devices in a non-canonical shape or
  without display labels. Device options are now normalized defensively and invisible rows are filtered out.
* Fixed media-server provider switches activating/restarting the runtime listener before the target provider was usable.
  Selecting an unconfigured provider now saves it as a draft only; expired or unreachable targets leave the current
  websocket listener untouched; configured targets are checked before any active-playback confirmation or listener swap.
* Fixed Jellyfin playback-startup notifications never being sent at all. Jellyfin's `Play` websocket message has the
  same gap Emby's already-shipped fix (1.0.5) covers — it never identifies the controlling client's own session,
  only the bridge's target session — but the fix was never ported to Jellyfin. Every notification silently no-opped
  with "no active source session is available."
* Fixed Jellyfin source-client cleanup at playback finish using the bridge target session when Jellyfin's `Play`
  command only provided `Id`. HCC now treats `Id` as the target session, resolves the real controlling client
  session, and sends the same double `Stop` used for Emby so the Jellyfin app clears its stale playback screen when
  the OPPO is stopped from the remote.
* Fixed Jellyfin Web/App remote-control screens remaining on a frozen playback view after OPPO remote Stop by applying
  the same best-effort double `Stop` delivery used for Emby to Jellyfin's source client session.
* Fixed Jellyfin multi-client cleanup when the same user has the web UI and mobile app open for the same HCC playback.
  HCC now resolves active Jellyfin sessions for that user, excludes its own bridge session, skips only sessions that
  explicitly report a different now-playing item, and sends best-effort double `Stop` to each stale client instead of
  only the single session that originally issued Play.
* Fixed `JellyfinClient.send_session_message` sending `Text`/`Header`/`TimeoutMs` as query-string parameters (Emby's
  shape) instead of the JSON request body Jellyfin's server actually requires, and sending an empty `data={}` body
  that omitted the `Content-Type` header entirely, which Jellyfin's server rejects with `415 Unsupported Media
  Type`. Confirmed against a real Jellyfin server's own error responses.
* Fixed `JellyfinClient.get_user_views` calling a route that does not exist (`/Users/{userId}/Views`). The real
  route is `GET /UserViews?userId=...`. Jellyfin library detection had likely never worked on any real install —
  masked by the `ModuleMediaServerSetupService` bug below, which silently absorbed the resulting failure.
* Fixed `ModuleMediaServerSetupService.load_devices`/`load_libraries`/`load_selectable_folders` discarding the
  provider module's actual return value and always returning the pre-call config unchanged. Freshly detected
  libraries, devices, and path mappings were computed correctly and then thrown away before reaching the UI, for
  both Emby and Jellyfin.
* Fixed `MediaServerLibrary` reading every library as inactive for any install whose `playback.libraries` predates
  this value object (every install before this provider-boundary refactor) — those entries use raw
  `Id`/`Name`/`Active` (capitalized) instead of the model's `id`/`name`/`active`. A model validator now normalizes
  the legacy shape instead of silently defaulting `active` to `False`.
* `find_controlling_session_id`'s Jellyfin-side session lookup now narrows server-side via the confirmed
  `controllableByUserId` query parameter instead of fetching every active session on the server for every single
  Play command.
* Fixed the existing "legacy config found" migration silently discarding `emby_server`/`user_name`/`user_password`
  from an XNOPPO-era flat `config.json` instead of migrating them — those keys were already listed as legacy
  (so they got removed) but no step ever moved the server URL anywhere first. `TV_KEY`/`TV_DeviceName` (no current
  equivalent — LG pairing now goes through a separate key store) are now dropped instead of lingering as orphaned
  fields.
* Fixed the Docker image being unable to complete a truly fresh install (no existing config volume at all):
  the multi-stage build refactor dropped `config.example.json` from the final runtime stage, so
  `ensure_config_exists()` had nothing to seed `config.json` from and crashed on every container start.
* Fixed `secrets.json` carrying a stale, empty single-provider `media_server` stub forever. It was seeded by
  default for every install before the multi-provider `media_servers.providers.*` shape existed, and was only ever
  cleaned up when the *public* config also had real legacy `media_server` data — which an XNOPPO-era flat config
  never has. It's no longer seeded for new installs, and existing installs self-heal it on the next config save or
  container restart.
* Fixed the "include pre-release versions" checkbox on the Diagnostics page never actually persisting — it was a
  local-only UI ref, never read from saved config on load and never saved when toggled, so it silently reset to
  off on every page reload. As a result the version check always ran with pre-releases excluded no matter how the
  checkbox looked, even though the backend filtering logic itself (fixed in 1.1.0-rc.2) was already correct. The
  checkbox now loads its saved state and persists immediately on toggle.
* Fixed `compose.yaml` (the file users/NAS deployments actually run) carrying both `image:` and `build:`. Several
  Docker GUIs (Portainer's "deploy stack from Git" pointed at a tag, among others) build from the compose file's
  `build:` section instead of pulling the named image — silently producing a locally-rebuilt image stamped
  `0.0.0.dev0` (the `SETUPTOOLS_SCM_PRETEND_VERSION` build-arg's fallback, since nothing sets `HCC_VERSION` in that
  flow) instead of the real, correctly-versioned image from the registry. `compose.yaml` is now pull-only; the
  `build:` section moved to a local-only, untracked override file for development.

### Changed

* Documented that Jellyfin device and library discovery (`GET /Devices`, `GET /Library/VirtualFolders`) requires an
  administrator-level Jellyfin account — both endpoints are elevation-gated server-side. See `INSTALL.md` /
  `INSTALL.en.md`'s FAQ.
* `README.md`/`README.en.md` and `INSTALL.md`/`INSTALL.en.md` updated to reflect Jellyfin as a shipped, supported
  media-server provider rather than a roadmap item.
* Documented installing/updating via Portainer (or similarly-capable web UIs) in `INSTALL.md`/`INSTALL.en.md`'s
  Docker Compose section — paste `compose.yaml` into the stack, then pin the running version via the stack's
  `HCC_VERSION` environment variable.
* Fixed `INSTALL.md`/`INSTALL.en.md` presenting Emby as the only supported media server in the requirements section
  — it never reflected Jellyfin support there, even though Jellyfin has been a shipped provider since 1.1.0-rc.1.
* All backend routes moved from `/api/*` to `/api/v1/*`, ahead of splitting `web/api_app.py`'s 800+ lines into one
  router per domain. The frontend (`api/index.js`'s base URL, plus the few hardcoded now-playing image/config-bootstrap
  paths) moved with it; the dev proxy in `vite.config.js` still matches on the `/api` prefix unchanged.

## [1.0.5] - 2026-06-22

### Fixed

* Fixed Autoscript attempting to unmount NFS-mounted shares after playback finish; the Autoscript telnet-shell
  unmount only ever applies to CIFS/SMB mounts, so NFS playback now skips this cleanup step entirely instead of
  attempting (and logging) an unmount that was never meant to run there.
* Fixed the Autoscript unmount hanging or proceeding incorrectly when the OPPO's telnet shell never sends its
  usual login prompt — this is now detected explicitly and the unmount is skipped cleanly instead.
* Fixed the Autoscript unmount reusing the SMB/NFS mount timeout (30s) instead of its own dedicated timeout, so a
  non-responsive telnet shell no longer adds a long stall after every playback finish.
* Fixed a regression in the new notification flow that could crash playback startup outright with a `TypeError`
  right after the OPPO had already started playing — the orchestrator then treated a working playback as failed,
  stopping the OPPO and marking the item unwatched in the media server even though it had played successfully.
* Fixed `OppoNetworkMountService` sending a second, redundant SMB login on top of the one already performed
  immediately before priming the SMB session, doubling back-to-back HTTP calls to the OPPO's embedded control
  server — a likely contributor to SMB mount timeouts under load.
* Fixed "Probar ruta" (path testing in Media Paths) using the SMB/NFS mount timeout instead of the dedicated
  Autoscript unmount timeout when cleaning up after a test mount, causing an unnecessary ~30s stall on every test
  pass when Autoscript is enabled.
* Fixed "Probar ruta" attempting an Autoscript unmount after testing an NFS path mapping; Autoscript only ever
  applies to CIFS/SMB mounts, and the real-playback-finish cleanup already skipped NFS — this call site now does
  too.
* Fixed playback-startup notifications being sent to HCC's own Emby session instead of the client that actually
  requested playback (web, mobile, or any client casting to HCC) — Emby's `Play` command never includes the
  originating session id, only the target's, so HCC now resolves the real controlling session by looking up the
  requesting user's other active sessions instead. Notifications now render on the device that pressed play, not
  only on the TV.
* Fixed the source Emby client's native playback never being stopped at handoff when TV and AV output switching are
  both disabled, leaving the original client and the OPPO playing the same item in parallel — stopping the source
  client no longer depends on TV switching being configured.
* Fixed the source Emby client's "now playing" screen sometimes freezing in a stale state right at handoff. Emby's
  remote playback commands are fire-and-forget with no acknowledgment or retry, so a single `Stop` is not reliably
  enough to clear it — both the handoff-time send and the playback-finish send now go through one shared
  `send_stop_with_delivery_reliability` helper that always sends twice, for every playback origin (the
  finish-time send used to only send once, which is what let the same freeze reappear for remote-control/cast
  playback after the notification session-id fix above made that Stop actually reach the real client for the
  first time).

### Added

* Added a dedicated `autoscript_unmount_timeout_seconds` config option (default 3s) instead of reusing the mount
  timeout for the Autoscript unmount step.
* Added a new playback-startup notification experience sent to the Emby client that started playback: instead of
  generic/legacy-style messages, HCC now narrates real milestones as they happen — powering on, locating the file,
  fine-tuning audio/subtitles, a single "still with you" message if startup is taking longer than usual, and a
  closing message tailored to what is actually playing (movie, episode, concert, live TV, or a generic fallback).
  Delivery remains best-effort and never blocks or fails playback.

### Changed

* Hardened `PlaybackStartupMessagingService` so no internal failure inside the notification flow (a missing
  language key, an unexpected content type, etc.) can ever propagate and abort an otherwise-working playback
  session — failures are logged and that one touchpoint is skipped instead.

### Notes

* Documented a known SMB limitation in `INSTALL.md`/`INSTALL.en.md`: some OPPO/Chinoppo players time out mounting
  SMB folders with very long names or names containing parentheses, brackets, or `+` (common in release-style
  folder names). The same content mounts fine over NFS, or over SMB once the folder/file name is shortened.

## [1.0.4] - 2026-06-21

### Fixed

* Fixed full Blu-ray / ISO playbacks not being marked as watched in the media server and the disc not stopping when
  the feature ended. End-of-content detection relied on the media server's runtime, which is missing or zero for many
  ISO/Blu-ray items; it now uses the OPPO's own reported title length (`getplayingtime` `total_time`/`cur_time`),
  which is reliable and stable across chapter changes. Playback finishes when the OPPO position reaches the title end
  (within 10s), and is marked watched when at least 90% of the title was played — independent of the media server.
* Fixed the OPPO auto-advancing to the next file in the folder after a feature ended: the previous title is now
  detected as finished (its reported total changes once it was at/near its end) and playback is stopped, instead of
  the bridge tracking the next file as if it were the same playback. The guard no longer depends on the media
  server's runtime, so it also covers ISO items that previously had no protection.
* Fixed several genuine errors being logged at WARNING level, so they now surface as ERROR in the logs screen: Emby
  device-command failures (play/pause, audio/subtitle track changes), failures loading a monitored item or building
  its playback intent, and a silently-swallowed failure when restarting the Emby WebSocket.

### Added

* Added a log-level selector (Off / Info / Debug) to the web Logs screen, so the verbosity of both the in-app logs
  and the container console can be set without editing `config.json`. The change is applied live (no restart needed).

### Changed

* End-of-content detection no longer mixes the media server's duration into the decision; the OPPO is the single
  source of truth, with a minimum-duration floor so disc menus and copyright reels are never treated as the feature.

### Tests

* Added unit coverage for the OPPO-total end-of-content, next-title and "played" thresholds, for the web log-level
  control applying live, and for log configuration; updated the polling and SVM3 observation tests to the new model.

## [1.0.3] - 2026-06-21

### Fixed

* Fixed the OPPO folder browser ("Browse OPPO") failing with a connection error on a cold player, by activating the
  OPPO's control API before talking to it — the real playback and "Probar ruta" flows already did this, the browser
  did not.
* Fixed NFS network-share mounts never retrying after a transient timeout; SMB mounts already retried once, NFS did
  not.
* Fixed pausing OPPO playback and leaving it long enough for the OPPO's own screen saver to activate causing the
  bridge to treat the session as finished — restoring the TV input and AV receiver as if the movie had ended, even
  though the user had only paused.
* Fixed the Emby source client (the TV/app a movie was started from) leaving its "now playing" screen frozen in a
  paused state for a couple of minutes after OPPO playback actually stopped.

### Changed

* Consolidated the three places that talk to the OPPO's network-mount API (real playback, "Probar ruta", "Browse
  OPPO") into a single shared sequence, so future fixes to OPPO mount handling only need to happen once.

### Tests

* Added regression coverage for OPPO network-mount activation, login, and retry behavior across all three call sites.
* Added regression coverage for playback monitoring correctly carrying a "still paused" hint across the SVM3/polling
  observation handoff, and for skipping TV/AV restore when the player is still showing its screen saver.
* Added regression coverage for clearing the stale source-client playback screen after a stop.

## [1.0.2] - 2026-06-20

### Fixed

* Fixed Emby authorization persistence so generated access tokens are kept in the private secrets file instead of being
  lost before later backend checks.
* Fixed the Emby connection test flow so it no longer restarts the backend while the configuration screen is still
  loading monitored devices and library paths.
* Fixed a UI regression where detected Emby libraries could briefly show `Failed to fetch` after a successful connection
  test.
* Kept the public API response sanitized so Emby access tokens and user ids are never exposed back to the frontend.

### Tests

* Added regression coverage to ensure Emby token configuration returns the effective internal config needed for secret
  persistence.
* Added API route coverage to ensure the Emby connection check saves verified config without triggering a full backend
  restart.

## [1.0.0] - 2026-06-19

### Added

- Added the 1.0.0 release branch policy: release candidates are tagged from `develop`, stable releases are tagged from
  `main`, and Docker `latest` is only updated by stable tags.
- Added release workflow version injection through `SETUPTOOLS_SCM_PRETEND_VERSION=<tag>`, making the Git tag the source
  of truth for the runtime version shown by the app.
- Added updated product screenshots for the redesigned setup, diagnostics, logs, and room-control experience.
- Added a dedicated Docker Hub overview (`DOCKERHUB.md`) and release workflow sync so the public image page no longer
  appears empty after publishing.
- Added OCI image metadata labels to release images for title, description, source, documentation, license, version, and
  revision.

### Changed

- Redesigned the web UI around a cinematic Control Room and Remote visual language, then extended that direction across
  configuration and support screens.
- Rebalanced the visual system away from the earlier navy/cyan direction toward graphite, blue-steel, and restrained
  brass, with warmer background imagery and subtle blue-steel ambient shadows.
- Reworked the main screen headlines and subtitles in Spanish and English so setup/support screens read like one
  coherent product instead of separate utility pages.
- Reduced configuration-screen hero typography and vertical hero height so forms feel better proportioned beside the new
  landing-style copy.
- Changed the Media Paths "Intercepted libraries" card to open by default.
- Changed the Diagnostics "Restart service" action from red danger styling to a brass service-action treatment, keeping
  red reserved for destructive actions.
- Updated README and release documentation to describe 1.0.0 as the stable product release line rather than future
  pre-release work.
- Updated Docker installation docs to show `docker run` as the fastest first-run path while keeping Docker Compose as
  the recommended path for long-running installs, updates, and rollback.

## [0.9.1] - 2026-06-18

### Added

- Added a "Current playback" info panel next to the OPPO remote, showing
  title, release year, network protocol, source server, mounted folder, file
  name, and container format for the active playback session.
- Added `playback_file_format`, `network_protocol`, and `production_year`
  fields to the active playback session and runtime status payload.
- Added source-available licensing terms and contribution guidance through
  `LICENSE`, `CONTRIBUTING.md`, Python package license metadata, and frontend
  package license metadata.
- Added Spanish and English installation guides with product screenshots for
  migration, Emby setup, OPPO setup, IP discovery, assisted/manual media path
  mapping, room setup, status, and logs.
- Added PNG brand assets for the README, app navbar, favicon, and Apple touch
  icon.

### Changed

- Redesigned the Remote Control view: a real cross-shaped D-pad, grouped and
  labeled button sections, Lucide icons replacing emoji glyphs, and an
  OLED-style live status screen.
- Reworked the Remote Control layout into the primary cinematic playback and
  control surface, with full-screen backdrop treatment, poster-led media
  details, status/protocol/format chips, route details, and a more physical
  remote body.
- Kept Control Room as the room-ready landing experience in both idle and active
  playback states, with playback reflected only through compact card/status
  indicators instead of replacing the landing with a now-playing panel.
- Reworked Control Room idle state into a full-screen room-ready landing view
  with centered setup cards, a remote-control entry point, and secondary system
  resource metadata instead of a redundant idle playback panel.
- Changed the Remote Control view's "Current playback" panel to scale
  responsively up to the same `max-width` cap used by other configuration
  screens, instead of a fixed pixel width.
- Added a soft shadow/glow transition at the bottom edge of view hero banners
  instead of a hard cut into the page background, and tuned panel glow
  intensity across the app.
- Reworked README and release documentation around HCC as an independent,
  integrated home-cinema control product, with Spanish as the default public
  entry point and English documentation kept in sync.
- Replaced the previous SVG favicon/mark direction with raster brand assets
  that match the new README and navbar identity.
- Updated `config.secrets.example.json` and `secrets.json` to match the current
  secrets layout, including Emby token/user fields and the SMB password slot.
- Updated `config.example.json` to include the public SMB username field, which
  is stored outside `secrets.json`.

### Fixed

- Fixed the "Current playback" poster leaving empty space below it instead of
  filling the height of its info column.
- Fixed stale secrets templates that still documented the removed
  `user_password`-only layout instead of the current Emby token and SMB
  credential split.

## [0.9.0] - 2026-06-18

### Added

- Added Spanish/English translations for all structured playback diagnostics
  (reason and suggestion text), replacing raw English text in the Status and
  Media Paths views.
- Added a colored, severity-filterable log viewer backed by structured JSON
  Lines logging on the backend, replacing the flat monochrome log dump.
- Added a "Restore default values" action for the OPPO advanced timeout
  settings, backed by a new `GET /api/oppo/advanced-defaults` endpoint.
- Added automatic OPPO share unmount after a real playback session ends when
  `oppo.autoscript` is enabled, matching the legacy autoscript behavior
  (previously this only ran for the "Test path" action).
- Added a guided Media Paths workflow that starts from detected media-server
  libraries, resolves the equivalent OPPO-visible path, tests it, and saves
  verified mappings without a separate "save verified" step.
- Added per-mapping network protocol selection (`nfs` or `cifs`) so mixed
  NFS/SMB libraries can coexist in the same setup.
- Added detected-library and intercepted-library panels to make it clear which
  libraries HCC will control during playback.
- Added a three-state SMB credential indicator (anonymous, username only,
  username + password) to the Media Paths SMB section, reflecting the
  configured username instead of a single "credentials saved" flag.
- Added a single in-process lock around OPPO device HTTP calls, preventing a
  second request (e.g. an impatient re-click) from racing the first into an
  `id_error`.
- Added a diagnostic hint suggesting SMB be enabled in Media Paths when an NFS
  mount fails and the share might actually be SMB/CIFS-only.
- Added section-scoped configuration save endpoints under
  `PATCH /api/config/{section}` to reduce stale full-config writes from setup
  screens.
- Added setup verification evidence for Media Server, OPPO, TV, and AV
  configuration, enabling `configured`, `verified`, and `stale` readiness
  states.
- Added a shared frontend section-save composable used by setup screens.
- Added simulated integration QA planning for mixed NFS/CIFS playback and setup
  flows before the final hardware acceptance matrix.
- Added Vitest frontend contract tests for setup section saves, intercepted
  library state, and disabled TV/AV save flows.

### Changed

- Redesigned Media Server, Media Player, Room/Sala, App Settings, Status, and
  Media Paths configuration screens around clearer setup steps and scoped save
  actions.
- Changed Media Paths playback behavior to use each mapping's selected protocol
  instead of treating the global SMB/CIFS setting as the source of truth.
- Changed `is_smb_active` to depend only on the OPPO "use SMB" toggle, no
  longer requiring stored credentials. Anonymous/guest SMB shares were
  previously downgraded to NFS silently because credentials were absent.
- Changed `smb.username` storage from `secrets.json` to `config.json`, since
  it is not sensitive, so the UI can show the configured username directly.
- Changed the SMB pre-mount option ("SMBTrick") so it actually runs during
  real playback mounts, not just the web path browser, and clarified its
  tooltip as a workaround for an OPPO SMB compatibility quirk seen with
  SMBv1 disabled on the NAS.
- Wired the existing SMB `id_error` mount retry into the web folder browser's
  mount path as well, matching the retry behavior already used by playback.
- Removed the dead `oppo.wait_nfs` setting end-to-end (config, migration, UI)
  since it had no effect on playback.
- Changed TV/AV source detection and setup test flows so they no longer
  implicitly persist full submitted configuration.
- Changed setup readiness navigation so saved/tested sections refresh without a
  full page reload.
- Changed intercepted-library selection so checkbox changes update the UI
  immediately but persist only when the user saves the library filter.
- Changed frontend configuration APIs so setup screens can only use
  section-scoped saves instead of a generic full-config save helper.
- Changed setup action verification persistence to use a shared backend helper
  across OPPO, TV, and AV test actions.
- Changed active runtime config propagation so the Emby websocket owns updating
  its nested session config.
- Replaced the legacy web server context with explicit FastAPI runtime
  dependencies and removed the old `BaseHTTPRequestHandler` web implementation
  plus its obsolete static HTML route table.
- Replaced the remaining legacy Docker web entrypoint with
  `python -m home_cinema_control.web.main` and removed `XNOPPO_CONFIG_FILE`
  compatibility.
- Removed the generic full-config `POST /api/config` endpoint so web writes go
  through section-scoped saves.
- Removed explicit legacy bridge-client filtering from Emby device discovery.
- Renamed AV, TV, and OPPO setup-control wrappers away from legacy web-control
  names and removed the old `web_control.py` modules.
- Restructured public documentation around a Spanish-default README and
  installation guide, with English mirrors, a product-oriented HCC vs legacy
  narrative, a visible roadmap for future providers/devices, a dedicated SVG
  project logo, and AVPasion kept as an external NAS/player setup reference
  instead of copying third-party forum screenshots.
- Expanded the installation guide into a visual setup walkthrough covering
  migration, Emby setup, OPPO setup, assisted/manual path mapping, optional
  room control, diagnostics, structured logs, and AVR CEC/ARC guidance.
- Updated the README and installation guides from the architecture/product
  specs to emphasize OPPO observation, interactive sync, watched/resume state,
  hardware compatibility validation, support evidence, and Docker release
  readiness as 1.0 work instead of vague future claims.
- Expanded the Media Paths installation guide into a step-by-step route mapping
  walkthrough covering required Emby libraries, NAS NFS/SMB preparation,
  OPPO-visible paths, manual mode, route states, and user-facing benefits of
  event-based OPPO observation with bounded polling fallback.
- Added focused Media Paths screenshots for intercepted-library selection,
  NFS route mapping, SMB credentials, route states, and manual mapping, and
  removed prescriptive library-interception recommendations from the guide.
- Replaced the first documentation logo with a new signal-routing HCC emblem
  and wordmark, moving the brand direction away from a generic screen/play
  icon.
- Removed the stale `oppo.default_nfs` legacy key from `config.example.json`
  so a clean install does not trigger the migration modal.

### Fixed

- Fixed NFS mappings being tested or played incorrectly when SMB/CIFS access was
  configured for another library.
- Fixed verified route mappings turning back into "review" state after page
  refresh due to unrelated library-filter saves.
- Fixed the Media Paths gate treating `verified` or `stale` Media Server/OPPO
  readiness as incomplete after the setup-verification model was introduced.
- Fixed partial setup saves so existing SMB passwords and media-server secrets
  are preserved before persistence.
- Fixed the legacy `default_nfs` flat-config migration inverting the SMB/NFS
  toggle for some pre-existing setups.
- Fixed CI coverage gaps by running frontend Vitest contract tests and excluding
  hardware-marked pytest cases by default.
- Fixed playback failure and recovery log lines always logging at `INFO`
  regardless of outcome; they now log at `WARNING`/`ERROR` matching the
  diagnostic's actual severity, so the Logs view's "errors only" filter
  surfaces real failures.
- Fixed OPPO HTTP client logging exposing credentials (e.g. SMB mount
  passwords) in plaintext inside logged request URLs.
- Fixed an unsound automatic SMB-to-NFS mount fallback that could hang for the
  full mount timeout instead of failing fast: NFS and SMB use different path
  conventions on some NAS layouts, so retrying the same path under the other
  protocol isn't valid. Real playback now mounts the mapping's selected
  protocol and fails cleanly if that fails.
- Fixed inconsistent OPPO default timeouts across the config model, example
  config, and runtime fallback defaults (connection timeout 3s → 10s, network
  mount timeout 60s → 30s — the latter applies to both NFS and SMB/CIFS
  mounts, not just NFS as its field name implies).
- Fixed narrow multi-column panels (e.g. "Last failure") overlapping their
  action buttons with the panel title at column widths between breakpoints.

## [0.8.1] - 2026-06-13

### Added

- Added an **Update** button to the Status view. When a new version is detected, the button triggers an automated
  redeploy via a configured webhook URL (Watchtower, Coolify, Portainer Business), or shows the equivalent
  `docker compose pull && docker compose up -d` command for manual execution.
- Added **rollback support**. Before triggering an update, the current version is saved to config. If a rollback
  is needed, the Status view shows the previous version and the exact pull command to restore it.
- Added a **webhook URL field** to the Status view. Users with a supported deployment platform can paste their
  redeploy webhook URL once — future updates are one click.
- Added **cached version checks**. The GitHub API is queried at most once per interval (default: 24 hours). A
  force-refresh option is available via the Check version button.
- Added a **nav badge** on the Status sidebar item that lights up when a newer version is available.
- Added `version_check_interval_hours`, `update_webhook_url`, and `previous_version` fields to `AppConfig`.
- Added `GET /version/rollback` API route returning rollback availability and instructions.
- Changed `GET /version/update` to `POST /version/update`.
- Added `force` query parameter to `GET /version/check` to bypass the version cache.
- Added `.github/workflows/release.yml` — publishes Docker images to GHCR
  (`ghcr.io/tousled/home-cinema-control`) and Docker Hub (`tousled/home-cinema-control`) on every `v*` tag push.
- Updated `compose.yaml` to reference the published image via
  `ghcr.io/tousled/home-cinema-control:${HCC_VERSION:-latest}`,
  enabling `docker compose pull` for over-the-air updates.

## [0.8.0] - 2026-06-13

### Added

- Added hardware compatibility reference — validated player models, media formats,
  and Emby versions with status badges.

### Changed

- Removed the dedicated AV configuration view and TV configuration view. Both `/av` and `/tv` routes now redirect to
  Room Setup (`/sala`), which already covers both devices. Reduces navigation surface without removing capability.
- Updated `SVM3Runtime.listen` to accept verbose observation parameters (`verbose_mode`, `initial_commands`,
  `keepalive_command`) for interface compatibility with the shared observation contract. Parameters are intentionally
  unused — SVM3 manages its own observation lifecycle independently.
- Unified button appearance across all configuration views with a shared `IconActionButton` component.
- Replaced native `<select>` elements with a reusable `FormSelect` component for consistent styling across all views.
- Added icons to the sidebar navigation for faster visual orientation.
- Added responsive mobile navigation with a collapsible sidebar for small-screen use.
- Improved action row layout in Remote and configuration views on smaller screens.
- Improved Media Paths UI with reusable sub-components and cleaner interaction patterns.
- Refined typography and spacing across all views.
- Updated favicon to SVG.

### Fixed

- Fixed playback position not being restored to Emby after a non-natural stop. When a stop event clears the watched
  state (ISO and non-ISO content), the resume point is now preserved and reported correctly.
- Fixed the network scan icon in configuration views disappearing after the first scan.

## [0.8.0] - 2026-06-11

### Added

- Added a new web application built with Vue 3 and FastAPI, replacing the
  legacy AngularJS UI. The new app is served as a compiled SPA from the same
  FastAPI server and introduces a full configuration wizard, a live remote
  control, a status dashboard, and a control room view.
- Added views: Emby configuration, Media Player (OPPO) configuration, Sala
  (TV + AV receiver) configuration, Remote control, Status, Control Room, Logs.
- Added network device scan (arp-scan) for local IP discovery. Configuration
  views with IP fields expose a scan button that discovers active devices on the
  LAN and presents them as a filterable dropdown below each IP input. Matching
  works by IP, hostname, or vendor name.
- Added reverse-DNS hostname resolution for discovered devices. Each arp-scan
  result is enriched with its mDNS/DNS hostname (first label only) in parallel
  using `socket.gethostbyaddr`. The hostname is shown instead of the raw OUI
  vendor string when available.
- Added automatic detection of the correct network interface for arp-scan by
  reading `/proc/net/route` directly — no dependency on `iproute2` or the `ip`
  binary inside the container.
- Added Emby now-playing backdrop as an ambient blurred background in Remote
  and Control Room views. Falls back to a static hero image when nothing is
  playing.
- Added Emby movie poster in Remote view (right of the controller, portrait) and
  in Status view (next to session detail rows).
- Added SMB credential management to the Emby configuration screen.
- Added a diagnostics system: playback failures now populate a `last_diagnostic`
  card in the Status view with structured failure details. The diagnostic is
  cleared automatically when a new playback session reaches the Playing state.
- Added `last_diagnostic` population for TV connection test failures, so the
  Status view shows the failure reason after a failed test even when no playback
  was attempted.
- Added self-hosted fonts, removing the runtime dependency on remote font CDNs.
- Added `HelpTooltip` default-slot support: any element passed as a child
  becomes the hover trigger instead of the default `?` icon, enabling tooltip
  behaviour on arbitrary controls (e.g. the scan button).
- Added `IpInput` reusable component encapsulating IP-field + scan-suggestion
  dropdown logic, used in both Media Player and Sala configuration views.
- Added backend unit tests for `network/devices.py`: ARP parse, header
  skipping, unknown vendor normalisation, empty output, missing arp table,
  binary not found, and IP numeric sort.

### Changed

- Replaced the legacy AngularJS web UI with the new Vue 3 SPA. The legacy
  server-rendered templates and static assets are removed from the active
  serving path.
- Network device suggestions are now presented as a focused-only dropdown
  (appears on input focus, closes on selection or blur) instead of an always-
  visible pill grid, reducing visual noise when the scan returns many devices.
- Discovered device list is deduplicated by IP address before enrichment and
  before being sent to the frontend.
- The currently configured IP for a field is always included at the top of the
  suggestion dropdown, even when the device is off and arp-scan does not detect
  it.
- Docker `compose.yaml` updated to add `network_mode: host` and
  `cap_add: [NET_RAW]` so arp-scan can send raw ARP frames from the host
  network stack.

### Fixed

- Fixed arp-scan returning an empty device list in Docker deployments. The
  container network bridge interface (`eth0`) has no IPv4 address; the scan now
  targets the host's default route interface resolved from `/proc/net/route`.
- Fixed arp-scan interface detection falling back to `ip route get 1.1.1.1`,
  which required the `iproute2` package not present in the container image.
  Interface is now read directly from the kernel routing table via
  `/proc/net/route`.
- Fixed TV connection test not populating `last_diagnostic` on failure. The
  diagnostic is now written before the HTTP error response is returned.

### Removed

- Removed the legacy AngularJS web UI (`web/` templates, static assets, and
  AngularJS-specific routes from the old web entrypoint).

## [0.7.2] - 2026-06-09

### Added

- Added Python package metadata for `home-cinema-control` using
  `pyproject.toml`, `setuptools`, and `setuptools_scm`, allowing the runtime to
  resolve the installed application version through package metadata.
- Added `requirements-build.txt` to keep package build tooling separate from
  runtime dependencies.

### Changed

- Moved the legacy web HTTP handler implementation into
  `src/home_cinema_control/web/handler.py`. The old web entrypoint now acts as the
  small process entrypoint that builds the web runtime composition and starts
  the server.
- Updated the Docker image build to install the app package in editable mode
  with explicit build tooling and `--no-build-isolation`. This keeps
  application metadata available in the container while avoiding build-time
  dependency resolution failures during deployment.

### Fixed

- Fixed production Docker/Portainer deployments failing at:
  `pip install --no-cache-dir --no-deps -e .`. The Dockerfile now installs
  package build requirements first and runs the editable install without build
  isolation.
- Fixed `tv_set_prev` route handling after moving the web handler into the
  package.

## [0.7.1] - 2026-06-09

### Added

- Added deferred audio track selection for Blu-ray ISO/full-disc content. When
  startup audio selection fails because the disc begins in the disc menu (which
  exposes only one audio track), the resolved target track index is carried
  into the `during` phase. The SVM 3 orchestrator applies the selection on the
  first `PLAY` state event, which fires when actual movie content starts and
  all audio tracks become available.

### Fixed

- Fixed `select_audio_track` not checking whether the requested track was
  already active before sending the selection command. The audio path now
  returns early with a success result when the current track matches the
  requested index, matching the behaviour already present for subtitle
  selection.
- Fixed OPPO `@UAT` events causing duplicate `AudioTrackChanged` reports to
  Emby. The OPPO sends four events per track change: `TH` (departing track),
  `TM` (arriving/loading), `UN` (channel-map transition), and a second `TM`
  (stable). `TH` and `UN` events are now filtered at translation time. The
  SVM 3 orchestrator additionally deduplicates consecutive `TM` events with
  the same track index so only one `AudioTrackChanged` event reaches Emby per
  user action.
- Fixed `finish_successful=False` appearing in the log without any indication
  of which component failed. The reporter now emits a second `WARNING` line
  with the status and detail of each finish component (`player_idle`, `tv`,
  `av_audio`) whenever the finish phase reports a failure.

### Changed

- Renamed `during` phase classes to reflect their actual roles: the two inner
  observers (`OppoSVM3ObservationDuringPlaybackOrchestrator`,
  `PollingDuringPlaybackOrchestrator`) are renamed to
  `SVM3PlaybackObservationStrategy` and `PollingPlaybackObservationStrategy`
  respectively. The coordinating class
  (`AutoObservationDuringPlaybackOrchestrator`) is renamed to
  `DuringPlaybackOrchestrator`, as it is the true orchestrator of the phase.

## [0.7.0] - 2026-06-09

### Added

- Added OPPO SVM 3 verbose mode with UTC position stream as the new default
  auto-observation path. SVM 3 provides richer event data than SVM 2 without
  requiring a persistent idle listener connection.
- Added polling fallback for SVM 3 observation: if the SVM 3 connection is
  lost mid-playback, the orchestrator retries and falls back to QPL polling
  to ensure playback state is never silently lost.

### Changed

- Hardened OPPO observation and Emby watched-state reporting: end-of-media
  detection is now more resilient to brief OPPO idle flaps and to positions
  reported slightly above the media runtime.
- Eliminated `LegacyEmbyTrackResolver`, `legacy_startup_preparation`, and the
  dispatcher round-trip from the playback application service. Track mapping
  and startup preparation now flow directly through the orchestration stack.
- TV controllers (`LgTvController`, `ScriptsTvController`) now directly
  implement `TelevisionOutputPort` via Protocol structural typing. The
  `TvOutputAdapter` wrapper is removed. Input switching is expressed as a
  `TvInputTarget(input_id, confirmation_app_id)` value object instead of a raw
  string, giving the orchestrator explicit control over confirmation behaviour.
- AV receiver adapters (Denon, Marantz, NAD, Onkyo, Yamaha, Scripts) now
  directly implement `AvReceiverOutputPort`. The `AvReceiverOutputAdapter`
  wrapper is removed. `switch_to_input(input_id)` receives the input command
  from the caller and forwards it to `AVInputRetrier`, fixing a long-standing
  bug where the adapter ignored the requested input and re-read from config.
  Error handling is centralised in `BaseAvReceiver._execute_av_operation`.

### Fixed

- Fixed Docker container producing no output in `docker logs` and Portainer log
  viewer. Python buffers stdout/stderr by default when not attached to a
  terminal; adding `PYTHONUNBUFFERED=1` to the Dockerfile forces immediate
  flush so log lines appear as they are written.
- Fixed disabled-AV and disabled-TV log lines not appearing in the application
  log when the corresponding device was configured as disabled in config.
- Fixed `AvReceiverOutputAdapter.switch_to_input` ignoring the `input_id`
  parameter and calling `change_hdmi()` which re-read the configured input from
  config. The requested input is now passed through correctly.

### Removed

- Removed `TvOutputAdapter` (`playback/device_output_adapters.py` TV section).
- Removed `AvReceiverOutputAdapter` and `playback/device_output_adapters.py`
  entirely.
- Removed `LegacyEmbyTrackResolver` and `legacy_startup_preparation`.

## [0.6.1] - 2026-06-06

### Fixed

- Fixed Docker container producing no output in `docker logs` and Portainer log
  viewer. Python buffers stdout/stderr by default when not attached to a
  terminal; adding `PYTHONUNBUFFERED=1` to the Dockerfile forces immediate
  flush so log lines appear as they are written.

## [0.6.0] - 2026-06-06

### Added

- Added OPPO verbose event bridge (`oppo.observation_mode = "oppo_verbose"`) as
  an opt-in observation path that reports OPPO-observed playback events to Emby
  in near-real-time:
  - `@UPL PAUS` → Emby `Pause`
  - `@UPL PLAY` → Emby `Unpause`
  - `@UAT` (audio track changed at OPPO) → Emby `AudioTrackChange`
  - `@UST` (subtitle track changed at OPPO) → Emby `SubtitleTrackChange`
  - `@UPL STOP` → Emby `Stopped` (idempotent with the normal finish path)
- Added `OppoTolerantHttpClient`: a raw TCP socket HTTP transport that strips
  OPPO verbose preamble lines before `HTTP/1.1`. Required because OPPO injects
  verbose events before the HTTP status line when SVM 2 is active, causing
  `requests` to fail with `BadStatusLine`.
- Added neutral observed playback event model (`playback/observed_events.py`)
  and OPPO verbose event translation (`devices/oppo/observed_events.py`).
- Added bidirectional Emby/OPPO track index mapping
  (`media_servers/emby/track_mapping.py`) so OPPO menu indexes can be reported
  as Emby stream IDs for audio and subtitle track-change events.
- Added `ObservedPlaybackEventReporter`: stateful reporter that maps OPPO menu
  indexes to Emby stream IDs using the active-session track mapper and routes
  events to the active Emby publisher.
- Added `oppo.observation_mode` selector in the OPPO web configuration screen
  (`stable` is the default; `oppo_verbose` is the experimental opt-in).
- Added Pydantic models and validation for all editable product configuration.
  Existing config is migrated automatically from the legacy flat format to the
  current nested structure on load.
- Added `update_active_tracks()` to `MediaServerPlaybackEventPublisher` and
  `PlaybackApplicationService` so interactive track changes from Emby update the
  publisher's mutable current track state before the next periodic progress
  report.

### Changed

- Moved the majority of the remaining codebase from `lib/` into
  `src/home_cinema_control/` with proper module structure and public/private
  boundaries. Legacy `lib/` modules that remain are kept only for the active
  legacy session/HTTP adapter boundary still used by the runtime.
- Extracted `EmbySessionMonitor` from the legacy Emby websocket class into an
  independently testable module at
  `src/home_cinema_control/media_servers/emby/session_monitor.py`.
- Moved `EmbyWebsocket` from `lib/Emby_ws.py` to
  `src/home_cinema_control/media_servers/emby/websocket_listener.py`. Removed
  `threading.Thread` inheritance; replaced manual reconnect loop with
  `run_forever(reconnect=10)`.
- Unified Emby progress reporting through a single
  `MediaServerPlaybackEventPublisher` that converts seconds to Emby ticks at
  the Emby boundary. Removed two thin wrapper classes
  (`MediaServerPlaybackProgressReporter` and `MediaServerPlaybackStoppedReporter`)
  that only converted units and delegated one call.
- Normalized all configuration keys to nested namespaces:
  `oppo.*`, `tv.*`, `av.*`, `app.*`, `playback.*`. Older config files are
  migrated transparently on load.
- Consolidated `EMBY_TICKS_PER_SECOND` from five definitions under three names
  to a single canonical constant in `media_servers/emby/constants.py`.
- Extracted OPPO port/protocol constants into
  `src/home_cinema_control/devices/oppo/constants.py`.
- Updated the web-reported application version to `0.6.0`.

### Fixed

- Fixed stale audio/subtitle track indices in periodic Emby `TimeUpdate`
  progress reports. The publisher previously read track IDs from a frozen
  startup snapshot; Emby responded to the stale indices with a `GeneralCommand`
  to "correct" them, which triggered another progress report, creating an
  indefinite feedback loop. The publisher now tracks mutable current indices
  updated by `update_active_tracks()` on each accepted track change.
- Fixed OPPO SVM 2 not being restored at finish cleanup when stop was initiated
  by Emby (OPPO was already idle; `STP` was not sent; without an explicit
  cleanup hook, `#QVM` still returned `@QVM OK 2` after playback ended). The
  finish cleanup step now sends `#SVM 0` independently of whether `STP` was
  needed.
- Fixed the verbose event bridge listener sending `#SVM 0` when OPPO closed the
  standalone SVM listener connection, disabling verbose mode mid-playback. The
  listener now passes `restore_verbose_mode=False`; SVM cleanup is the finish
  adapter's sole responsibility.
- Fixed Emby-initiated interactive commands (pause, audio/subtitle track change,
  seek) not capturing OPPO verbose preambles: `OppoPlaybackCommandControl` was
  creating `OppoTolerantHttpClient` without the `on_verbose_preamble` callback.
  The command control factory now reads the live `preamble_callback` from the
  active verbose adapter via `PlaybackApplicationService.active_oppo_playback`.
- Fixed the Emby authentication configuration UI to display the connected
  account username as a badge instead of an empty password field.

### Removed

- Removed `MediaServerPlaybackProgressReporter` and
  `MediaServerPlaybackStoppedReporter` (merged into `MediaServerPlaybackEventPublisher`).

### Validated

- Validated `@UAT` (audio track change on OPPO) → `AudioTrackChange` reported
  to Emby with correct stream index.
- Validated `@UPL PAUS` (OPPO remote pause) → `Pause` reported to Emby.
- Validated SVM 2 active throughout playback with startup, audio selection,
  subtitle selection, interactive commands, and finish cleanup all working
  through the tolerant HTTP transport.
- Validated SVM 0 correctly restored at finish cleanup.
- Validated stable mode (`oppo.observation_mode = "stable"`) unaffected.

### Notes

- The `oppo_verbose` mode harvests verbose events from OPPO HTTP preambles and
  QPL responses already used during playback. It does not rely on a persistent
  idle SVM listener connection — the validated OPPO/Chinoppo UDP-203 device
  closes that connection immediately after `@SVM OK 2`.
- Emby-initiated commands (pause, audio/subtitle change) may report the same
  event twice: once from the command handler and once from the OPPO verbose
  preamble. Emby is idempotent; this has no visible UX impact but may be
  refined in a future pass.
- The stable observation mode remains the default and compatibility baseline.
  Do not enable `oppo_verbose` on unknown OPPO/clone models without first
  validating that SVM 2 does not break MediaControl HTTP on that firmware.

## [0.5.1] - 2026-06-01

### Changed

- Updated the web-reported application version to `0.5.1`.
- Documented OPPO natural media-end behaviour in the public state-machine notes.

### Fixed

- Fixed natural media endings that could leave the user on a black OPPO screen
  for over a minute while QPL still reported `PLAY`.
- The during-playback orchestrator now confirms repeated end-of-media playback
  positions (`current >= total`) and reports a `NATURAL_END` stop reason.
- Final playback position is normalized to the media runtime before reporting
  stopped playback to Emby, avoiding values such as `3533 / 3529`.
- The finish orchestrator now closes OPPO playback with `STP` after a natural
  end if the player still reports an active state, then confirms idle before
  restoring LG/AV outputs.

### Validated

- Real episode-ending logs showed OPPO stuck at `PLAY` with
  `current=3533` / `total=3529` before eventually returning to `HOME_MENU`;
  this release models that state directly.
- Sending `STP` while OPPO was already idle (`SCREEN_SAVER`) returned success,
  left OPPO idle, and a follow-up NFS mount succeeded.

## [0.5.0] - 2026-05-31

### Added

- Added a parent playback orchestrator that coordinates startup, post-start
  completion, during-playback monitoring, finish, and centralized error
  recovery.
- Added a dedicated during-playback orchestrator based on OPPO QPL state
  observation and OPPO MediaControl playback time.
- Added a finish orchestrator that reports the final playback position to Emby,
  waits for OPPO to settle into an idle state, returns the LG TV to the correct
  app, and restores AV receiver TV audio.
- Added centralized playback error recovery that can stop OPPO playback with
  `STP` before restoring TV and AV outputs.
- Added active-playback replacement support: requesting another item while one
  is playing now stops the current parent flow, waits for a clean finish, and
  then starts the replacement item through the same orchestrated flow.
- Added explicit playback origins for observed TV-client playback and remote
  Emby control commands.
- Added an Emby playback command handler for PlayNow, pause/unpause, stop,
  chapter navigation, audio/subtitle changes, absolute seek, and 10-second
  forward/back remote seek commands.
- Added transport-level HTTP/TCP diagnostics with compact successful-response
  logging and richer failure logging.
- Added OPPO MediaControl handling for optical image startup cases where the
  mount endpoint fails or times out but OPPO later reports active playback.
- Added tests for playback orchestration, replacement, OPPO startup/finish,
  Emby playback command translation, and error recovery.

### Changed

- Replaced the legacy playback entry point with cleaner
  playback application/orchestration modules.
- Reworked playback startup so OPPO MediaControl startup, TV input switching,
  AV input switching, resume, audio selection, and subtitle selection are
  coordinated through the new playback flow.
- Replaced the legacy `getglobalinfo` string loop for active playback with QPL
  state monitoring.
- Changed Emby progress handling to observe OPPO frequently for local stop
  detection while throttling Emby `Progress` check-ins to the media-server
  lifecycle interval.
- Changed active replacement stop semantics to use OPPO `STP` as the playback
  close command for all media types, including ISO/Blu-ray cases.
- Changed replacement finish semantics so the old item reports stopped and
  confirms OPPO idle state without restoring TV/AV outputs before the
  replacement item starts.
- Changed TV app restoration during replacements so the original non-HDMI app is
  preserved across the whole room playback flow instead of being overwritten by
  the intermediate OPPO HDMI input.
- Changed Emby playback status messages to target the active source/control
  session instead of broadcasting messages to every user session.
- Updated the web-reported application version to `0.5.0`.

### Fixed

- Fixed `bd_is_playing` and duplicate replay failures caused by legacy
  `playother`/replay paths remounting while OPPO was already playing.
- Fixed normal stop after replacement returning the LG TV to HDMI instead of the
  Emby app.
- Fixed a UX issue where replacement temporarily returned LG/Denon to TV before
  the replacement item started.
- Fixed replacement startup being attempted before OPPO had confirmed an idle
  state after stopping the active item.
- Fixed finish success reporting so OPPO idle-confirmation failure makes the
  finish result unsuccessful.
- Fixed intermittent startup/finish failures leaving OPPO active by adding
  OPPO stop handling to centralized error recovery.
- Fixed remote seek from Emby mobile/web clients so relative seek changes OPPO
  position instead of restarting playback.
- Fixed direct Emby stop commands to send OPPO `STP` instead of home/navigation
  commands.
- Fixed stale LG monitored-session snapshots triggering duplicate playback
  requests while bridge-owned playback was already loading or playing.

### Removed

- Removed the legacy playback entry point module.
- Removed legacy `playto_file` and `playother` playback paths.
- Removed the legacy web watchdog that mutated playback state outside the
  orchestrated playback flow.
- Removed legacy Emby `/Sessions/{session}/Viewing` reporting from the active
  playback path.
- Removed unused legacy OPPO helpers that were no longer referenced by
  productive code.

### Validated

- Validated MKV playback from the LG Emby app.
- Validated ISO / Full Blu-ray playback from remote Emby control.
- Validated MKV -> ISO replacement.
- Validated ISO -> MKV replacement when OPPO MediaControl mount state was
  healthy.
- Validated final stop after replacement returning LG to `com.emby.app` and
  Denon to `SITV`.
- Validated pause, chapter navigation, absolute seek, and 10-second
  forward/back seek from the Emby mobile/web controller.
- Validated preservation of the last valid OPPO playback position when
  `getplayingtime` returns transient zero values during stop/transition.

### Notes

- OPPO MediaControl can still enter a stale NFS mount state after some
  ISO/Blu-ray replacement flows. Command-level recovery attempts tested so far
  did not restore mounting; rebooting/power-cycling OPPO remains the only
  proven recovery for that specific device-side stale state.
- Startup timing improved mainly by removing legacy replay/remount paths,
  duplicate attempts, and redundant OPPO calls. Exact before/after timing should
  be measured later from comparable runs on `main` and `develop`; current logs
  are not a controlled benchmark.
- The legacy web configuration/remote-control surface still contains OPPO
  diagnostic flows that should be modernized separately.

## [0.4.0] - 2026-05-23

### Added

- Added Python 3.14 runtime support.
- Added an AV adapter layer under `lib/devices/av`.
- Added explicit AV receiver implementations for:
  - Denon
  - Marantz
  - NAD
  - Onkyo
  - Yamaha
  - script-based AV control
- Added AV adapter selection from `config["AV_model"]`.
- Added a socket-based TCP command sender for AV receivers that use simple TCP commands.
- Added `lib/oppo_autoscript.py` to isolate OPPO Autoscript-related unmount logic.

### Changed

- Replaced the legacy AV library-copying mechanism with an adapter/factory approach.
- Replaced AV `telnetlib` usage with socket-based command sending where appropriate.
- Renamed the internal AV `check_power` operation to `power_on`, keeping the legacy `av_check_power(config)` wrapper for compatibility.
- Updated AV web setup so changing AV model no longer copies Python files or restarts the application.
- Improved AV web setup responsiveness by removing the old `/move_av` restart flow.
- Kept legacy public AV function names used by the old playback and web entrypoints, while routing implementation
  through adapters.
- Moved OPPO Autoscript unmount handling out of the legacy playback entry point.

### Removed

- Removed the old `web/libraries/AV` runtime-copying structure.
- Removed AV runtime dependence on `telnetlib`.
- Removed the `/move_av` web flow.
- Removed unnecessary AV code duplication across vendor-specific files.

### Validated

- Validated Denon control with the receiver already powered on.
- Validated Denon control with the receiver suspended/off.
- Validated AV web interface after the adapter/factory migration.
- Validated normal playback and AV HDMI switching after the migration.

### Notes

- TV still uses the legacy TV implementation path and will be migrated separately.
- OPPO HTTP calls such as `getglobalinfo()` and `getplayingtime()` still need future hardening for the case where the OPPO is powered off or unreachable.

## [0.3.0] - 2026-05-23

### Added

- Added OPPO QPL diagnostics for playback-state observation.
- Added OPPO playback-state classification for active, idle and transition states.
- Added support for additional OPPO trick-play/navigation states observed during testing:
  - `FFWD`
  - `FREV`
  - `SFWD`
  - `SREV`
  - `STEP`
- Added preservation of the last valid non-zero playback position when OPPO reports zero at stop time.
- Added cleaner debug logging around playback, QPL state observation and subtitle handling.

### Changed

- Improved subtitle handling when no subtitle is selected.
- Improved subtitle handling when Emby sends a selected subtitle stream.
- Refactored duplicated subtitle-selection logic into a shared helper.
- Fixed `/check_emby` web configuration flow.
- Simplified Emby connection checking logic.
- Reduced noisy subtitle and MediaStreams logging.
- Improved WebSocket callback handling and session logging.
- Rotated exposed LG TV key after debugging.
- Rotated exposed Emby password after debugging and validated the system afterwards.

### Fixed

- Fixed repeated subtitle-setting attempts when no subtitle was selected.
- Fixed subtitle mapping from Emby subtitle stream index to OPPO subtitle index.
- Fixed the missing `EmbyHttp` import / broken `/check_emby` flow.
- Fixed playback progress being overwritten with zero in common stop scenarios.
- Fixed several noisy debug outputs that made real playback issues harder to diagnose.

### Validated

- Validated playback without subtitles.
- Validated playback with selected subtitles.
- Validated ISO / Full Blu-ray playback.
- Validated normal movie playback.
- Validated fast-forward, rewind and pause state observation.
- Validated web configuration flow after `/check_emby` fix.

### Notes

- Experimental segment-aware progress tracking was discarded because it introduced fragile heuristics. Future progress/timeline hardening should use a dedicated tested tracker instead of adding more logic inside `playto_file`.

## [0.2.0] - 2026-05-22

### Added

- Added Docker runtime support.
- Added Portainer stack deployment support from Git.
- Added persistent Docker volume for runtime configuration.
- Added `/config/config.json` runtime configuration support.
- Added `XNOPPO_CONFIG_FILE` environment variable support.
- Added `restart: unless-stopped` runtime behaviour.
- Added first-run configuration creation from `config.example.json`.
- Added safe startup behaviour when configuration is incomplete.

### Changed

- Container now starts the web UI even when Emby/OPPO configuration is incomplete.
- Emby WebSocket startup is skipped until configuration is valid.
- Runtime configuration is no longer tied to the project root.
- Docker deployment now uses host networking for the home-cinema integration.

### Fixed

- Fixed Docker runtime startup with persistent config.
- Fixed missing configuration bootstrapping for fresh deployments.
- Fixed runtime behaviour when config is incomplete.

### Validated

- Validated Docker build and runtime deployment on ASUSTOR.
- Validated Portainer deployment from Git.
- Validated persistent configuration volume.
- Validated Emby WebSocket startup after real config was copied into the Docker volume.
- Validated playback from Docker runtime.

## [0.1.1] - 2026-05-22

### Changed

- Sanitized runtime debug logs to avoid exposing sensitive values during troubleshooting.

### Notes

- This was a small maintenance release on top of the clean independent baseline.

## [0.1.0] - 2026-05-22

### Added

- Established the clean baseline for the project.
- Added the missing `lib/playback_manager.py` to the baseline.
- Created the initial stable tag used as the reference point for later work.

### Fixed

- Fixed Emby WebSocket callback binding by correcting callback method signatures.
- Fixed callback instance usage in `lib/Emby_ws.py`.

### Notes

- This version is the stable baseline before Docker/runtime, QPL, subtitle, AV adapter and Python 3.14 work.
