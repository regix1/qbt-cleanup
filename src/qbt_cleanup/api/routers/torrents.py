"""Torrents router for the qbt-cleanup web API."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request

from ...client import QBittorrentClient
from ...state import StateManager
from ..app_state import AppState
from ..models import ActionResponse, TorrentDeleteRequest, TorrentResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


@router.get("/torrents", response_model=List[TorrentResponse])
def list_torrents(request: Request) -> List[TorrentResponse]:
    """List all torrents with live qBittorrent data and blacklist status.

    Creates a fresh QBittorrentClient and StateManager per request.
    Returns HTTP 503 if the qBittorrent connection fails.
    """
    app_state = get_app_state(request)
    config = app_state.config

    state_mgr: StateManager | None = None
    qbt_client: QBittorrentClient | None = None

    try:
        state_mgr = StateManager()
        qbt_client = QBittorrentClient(config.connection)

        if not qbt_client.connect(quiet=True):
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to qBittorrent",
            )

        raw_torrents = qbt_client.get_torrents()
        if raw_torrents is None:
            raise HTTPException(
                status_code=503,
                detail="Failed to retrieve torrents from qBittorrent",
            )

        results: List[TorrentResponse] = []
        for torrent in raw_torrents:
            info = qbt_client.process_torrent(torrent)
            is_blacklisted = state_mgr.is_blacklisted(info.hash)
            is_unregistered = state_mgr.get_unregistered_hours(info.hash) is not None

            tracker_url = getattr(torrent, "tracker", "") or ""

            results.append(
                TorrentResponse(
                    hash=info.hash,
                    name=info.name,
                    state=info.state,
                    ratio=info.ratio,
                    seeding_time=info.seeding_time,
                    is_private=info.is_private,
                    is_paused=info.is_paused,
                    is_downloading=info.is_downloading,
                    is_stalled=info.is_stalled,
                    is_blacklisted=is_blacklisted,
                    is_unregistered=is_unregistered,
                    size=getattr(torrent, "size", 0) or 0,
                    progress=getattr(torrent, "progress", 0.0) or 0.0,
                    category=getattr(torrent, "category", "") or "",
                    tracker=tracker_url,
                    added_on=getattr(torrent, "added_on", 0) or 0,
                    save_path=getattr(torrent, "save_path", "") or "",
                )
            )

        return results
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error listing torrents: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if state_mgr is not None:
            state_mgr.close()
        if qbt_client is not None:
            qbt_client.disconnect()


@router.delete("/torrents", response_model=ActionResponse)
def delete_torrent(body: TorrentDeleteRequest, request: Request) -> ActionResponse:
    """Delete a torrent from qBittorrent.

    Optionally removes downloaded files from disk.
    """
    app_state = get_app_state(request)
    config = app_state.config

    qbt_client: QBittorrentClient | None = None

    try:
        qbt_client = QBittorrentClient(config.connection)

        if not qbt_client.connect(quiet=True):
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to qBittorrent",
            )

        success = qbt_client.delete_torrents([body.hash], body.delete_files)

        if success:
            action = "Deleted (with files)" if body.delete_files else "Removed (torrent only)"
            logger.info(f"{action}: {body.hash[:8]}")
            return ActionResponse(
                success=True,
                message=f"Torrent {'deleted with files' if body.delete_files else 'removed'}",
            )
        else:
            return ActionResponse(success=False, message="Failed to delete torrent")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error deleting torrent: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if qbt_client is not None:
            qbt_client.disconnect()
