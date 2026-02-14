"""FastAPI application factory."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from .app_state import AppState


def create_app(app_state: AppState) -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="qbt-cleanup",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Store app_state for dependency injection
    app.state.app_state = app_state

    # CORS for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and include routers
    from .routers import actions, blacklist, config, fileflows, notifications, recycle, status, torrents

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(torrents.router, prefix="/api", tags=["torrents"])
    app.include_router(blacklist.router, prefix="/api", tags=["blacklist"])
    app.include_router(config.router, prefix="/api", tags=["config"])
    app.include_router(actions.router, prefix="/api", tags=["actions"])
    app.include_router(fileflows.router, prefix="/api", tags=["fileflows"])
    app.include_router(notifications.router, prefix="/api", tags=["notifications"])
    app.include_router(recycle.router, prefix="/api", tags=["recycle-bin"])

    # Serve Angular SPA with deep-link support
    static_dir = "/app/web"
    if os.path.isdir(static_dir):
        index_path = os.path.join(static_dir, "index.html")

        # Mount static assets (JS/CSS/images) — does NOT handle SPA fallback
        app.mount("/assets", StaticFiles(directory=static_dir), name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            """Serve static files if they exist, otherwise index.html for Angular routing."""
            file_path = os.path.join(static_dir, full_path)
            if full_path and os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(index_path)

    return app
