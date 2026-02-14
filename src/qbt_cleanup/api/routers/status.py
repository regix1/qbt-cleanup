"""Status and health-check router for the qbt-cleanup web API."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Request

from ... import __version__
from ...client import QBittorrentClient
from ...state import StateManager
from ..app_state import AppState
from ..models import HealthResponse, StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_start_time = time.time()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health-check endpoint."""
    return HealthResponse(
        status="ok",
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@router.get("/status", response_model=StatusResponse)
def status(request: Request) -> StatusResponse:
    """Dashboard status endpoint.

    Creates fresh StateManager and QBittorrentClient connections per request,
    gathers live torrent counts and merges them with the scheduler state.
    """
    app_state = get_app_state(request)
    config = app_state.config

    state_mgr: StateManager | None = None
    qbt_client: QBittorrentClient | None = None

    torrent_count = 0
    stalled_count = 0
    unregistered_count = 0
    private_count = 0
    public_count = 0
    blacklist_count = 0
    state_enabled = False
    db_path = ""

    try:
        state_mgr = StateManager()
        state_enabled = state_mgr.state_enabled
        db_path = state_mgr.state_file

        # Get blacklist count
        blacklist_entries = state_mgr.get_blacklist()
        blacklist_count = len(blacklist_entries)
    except Exception as exc:
        logger.warning(f"Could not connect to state database: {exc}")
    finally:
        if state_mgr is not None:
            state_mgr.close()
            state_mgr = None

    try:
        qbt_client = QBittorrentClient(config.connection)

        # Connect and gather torrent stats
        if qbt_client.connect(quiet=True):
            torrents = qbt_client.get_torrents()
            if torrents is not None:
                torrent_count = len(torrents)
                for torrent in torrents:
                    info = qbt_client.process_torrent(torrent)
                    if info.is_private:
                        private_count += 1
                    else:
                        public_count += 1
                    if info.is_stalled:
                        stalled_count += 1
        else:
            logger.warning("Could not connect to qBittorrent - returning partial status")
    except Exception as exc:
        logger.warning(f"Error fetching torrent data: {exc}")
    finally:
        if qbt_client is not None:
            qbt_client.disconnect()

    # Get unregistered count from state database
    try:
        state_mgr = StateManager()
        unregistered_count = state_mgr.count_unregistered()
    except Exception as exc:
        logger.warning(f"Could not count unregistered torrents: {exc}")
    finally:
        if state_mgr is not None:
            state_mgr.close()
            state_mgr = None

    # Merge scheduler status - this should always succeed
    run_status = app_state.get_status()

    return StatusResponse(
        version=__version__,
        state_enabled=state_enabled,
        db_path=db_path,
        torrent_count=torrent_count,
        blacklist_count=blacklist_count,
        stalled_count=stalled_count,
        unregistered_count=unregistered_count,
        private_count=private_count,
        public_count=public_count,
        last_run_time=run_status["last_run_time"],
        last_run_success=run_status["last_run_success"],
        last_run_stats=run_status["last_run_stats"],
        scheduler_running=run_status["scheduler_running"],
        schedule_hours=config.schedule.interval_hours,
        dry_run=config.behavior.dry_run,
        delete_files=config.behavior.delete_files,
    )
