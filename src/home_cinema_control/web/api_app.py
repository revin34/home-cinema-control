import logging
import threading

from fastapi import APIRouter, BackgroundTasks, Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response

from home_cinema_control.media_servers.common.provider import MediaServerProviderFactory
from home_cinema_control.network.devices import discover_local_devices
from home_cinema_control.runtime import configure_logging
from home_cinema_control.web.api_runtime import WebApiRuntime
from home_cinema_control.web.av_routes import build_av_router
from home_cinema_control.web.config_sections import apply_config_section
from home_cinema_control.web.lighting_routes import build_lighting_router
from home_cinema_control.web.media_server_routes import build_media_server_router
from home_cinema_control.web.migration import (
    apply_migration,
    import_legacy_config,
    is_migration_available,
    start_fresh,
)
from home_cinema_control.web.config_readiness import compute_config_readiness
from home_cinema_control.web.oppo_routes import build_oppo_router
from home_cinema_control.web.paths_routes import build_paths_router
from home_cinema_control.web.static_assets import read_binary_asset
from home_cinema_control.web.support_report import build_diagnostic_report, clamp_log_lines
from home_cinema_control.web.telemetry_routes import build_telemetry_router
from home_cinema_control.web.tv_routes import build_tv_router
from home_cinema_control.web.version_routes import build_version_router


def create_api_app(api_runtime: WebApiRuntime) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None)
    media_server_provider_factory = MediaServerProviderFactory()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    router = APIRouter(prefix="/api/v1")

    # --- config ---

    @router.get("/config")
    def get_config():
        config = api_runtime.config_service.load_config()
        return api_runtime.config_service.sanitize(config)

    @router.get("/config/readiness")
    def get_config_readiness():
        config = api_runtime.config_service.load_config()
        sanitized = api_runtime.config_service.sanitize(config)
        return compute_config_readiness(sanitized)

    @router.patch("/config/{section}")
    def save_config_section(section: str, body: dict):
        try:
            config = api_runtime.config_service.load_config()
            updated = apply_config_section(config, section, body)
            updated = api_runtime.config_service.prepare_submitted_config(updated)
            api_runtime.config_service.save_config(updated)
            _emit_telemetry_async(api_runtime)
            if section == "app":
                # Logging is configured once at startup; re-apply it here so a
                # log-level change from the web takes effect live, not only after
                # a restart.
                try:
                    configure_logging(updated, api_runtime.log_file)
                except Exception:
                    logging.exception(
                        "Failed to re-apply logging configuration after config change"
                    )
            return api_runtime.config_service.sanitize(updated)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except HTTPException:
            raise
        except Exception as exc:
            logging.exception("save_config_section failed")
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/config/smb/clear")
    def clear_smb_creds():
        try:
            api_runtime.config_service.clear_smb_credentials()
            return {"ok": True}
        except Exception as exc:
            logging.exception("clear_smb_creds failed")
            raise HTTPException(status_code=400, detail=str(exc))

    # --- system ---

    @router.get("/state")
    def get_state():
        return api_runtime.config_service.sanitize(api_runtime.runtime.get_state())

    @router.get("/logs")
    def get_logs():
        try:
            body = read_binary_asset(api_runtime.log_file)
        except FileNotFoundError:
            body = b""
        return PlainTextResponse(body.decode("utf-8", errors="replace"))

    @router.post("/diagnostics/clear")
    def clear_diagnostics():
        api_runtime.runtime.clear_last_diagnostic()
        return {"ok": True}

    def _support_summary_payload(raw_config: dict) -> dict:
        sanitized_config = api_runtime.config_service.sanitize(raw_config)
        summary = api_runtime.runtime.get_support_summary()
        summary["config_readiness"] = compute_config_readiness(sanitized_config)
        return api_runtime.config_service.sanitize(summary)

    @router.get("/support/summary")
    def support_summary():
        return _support_summary_payload(api_runtime.config_service.load_config())

    @router.get("/support/report")
    def support_report(lines: int | None = None):
        try:
            raw_config = api_runtime.config_service.load_config()
            sanitized_summary = _support_summary_payload(raw_config)
            try:
                raw_log_bytes = read_binary_asset(api_runtime.log_file)
            except FileNotFoundError:
                raw_log_bytes = b""
            result = build_diagnostic_report(
                config=raw_config,
                sanitized_summary=sanitized_summary,
                raw_log_text=raw_log_bytes.decode("utf-8", errors="replace"),
                max_lines=clamp_log_lines(lines),
            )
            return {
                "report": result.report,
                "redaction_count": result.redaction_count,
                "log_lines_included": result.log_lines_included,
            }
        except Exception as exc:
            logging.exception("support_report failed")
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/restart")
    def restart(background_tasks: BackgroundTasks):
        background_tasks.add_task(api_runtime.runtime.restart_process)
        return {"ok": True}

    # --- migration ---

    @router.get("/migration/status")
    def migration_status():
        return {"available": is_migration_available(api_runtime.config_file)}

    @router.post("/migration/apply")
    def migration_apply():
        try:
            apply_migration(api_runtime.config_file)
            return {"ok": True}
        except Exception:
            logging.exception("Migration apply failed")
            raise HTTPException(status_code=500, detail="Migration failed")

    @router.post("/migration/skip")
    def migration_skip():
        try:
            start_fresh(api_runtime.config_file)
            return {"ok": True}
        except Exception:
            logging.exception("Migration skip failed")
            raise HTTPException(status_code=500, detail="Could not create fresh config")

    @router.post("/migration/import-legacy")
    def migration_import_legacy(payload: dict = Body(...)):
        try:
            import_legacy_config(api_runtime.config_file, payload)
            return {"ok": True}
        except ValueError:
            raise HTTPException(status_code=400, detail="Not a recognizable legacy config")
        except Exception:
            logging.exception("Legacy config import failed")
            raise HTTPException(status_code=500, detail="Import failed")

    # --- network ---

    @router.get("/network/devices")
    def network_devices():
        return discover_local_devices()

    # --- playback ---

    @router.post("/playback/start")
    def playback_start(body: dict):
        api_runtime.runtime.start_movie(body)
        return {"ok": True}

    # media_server_router is included before the generic `router`: it
    # registers the literal /config/media-server path, which must win over
    # router's catch-all PATCH /config/{section} for that one section.
    # Starlette matches routes in registration order, not by specificity.
    app.include_router(
        build_media_server_router(api_runtime, media_server_provider_factory)
    )
    app.include_router(router)
    app.include_router(build_tv_router(api_runtime))
    app.include_router(build_av_router(api_runtime))
    app.include_router(build_lighting_router(api_runtime))
    app.include_router(build_oppo_router(api_runtime))
    app.include_router(build_paths_router(api_runtime, media_server_provider_factory))
    app.include_router(build_version_router(api_runtime))
    app.include_router(build_telemetry_router(api_runtime))

    # --- SPA static files ---
    dist_dir = api_runtime.frontend_dist_dir

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if dist_dir.exists():
            candidate = dist_dir / full_path
            if candidate.exists() and candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(dist_dir / "index.html"))
        return Response("Frontend not built. Run: cd frontend && npm run build", status_code=503)

    return app


def _emit_telemetry_async(api_runtime: WebApiRuntime) -> None:
    if api_runtime.telemetry is None:
        return
    threading.Thread(
        target=api_runtime.telemetry.emit,
        args=("heartbeat",),
        daemon=True,
    ).start()
