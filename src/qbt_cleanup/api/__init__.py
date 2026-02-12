"""FastAPI application factory."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    from .routers import actions, blacklist, config, fileflows, status, torrents

    app.include_router(status.router, prefix="/api", tags=["status"])
    app.include_router(torrents.router, prefix="/api", tags=["torrents"])
    app.include_router(blacklist.router, prefix="/api", tags=["blacklist"])
    app.include_router(config.router, prefix="/api", tags=["config"])
    app.include_router(actions.router, prefix="/api", tags=["actions"])
    app.include_router(fileflows.router, prefix="/api", tags=["fileflows"])

    # Mount static files for Angular SPA (must be last - catch-all)
    static_dir = "/app/web"
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
