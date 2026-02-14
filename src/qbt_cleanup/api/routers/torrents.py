"""Torrents router for the qbt-cleanup web API."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request

from ...client import QBittorrentClient
from ...config_overrides import ConfigOverrideManager
from ...resilient_move import resilient_move, write_move_metadata
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


def _move_torrent_to_recycle_bin(qbt_client: QBittorrentClient, torrent_hash: str) -> str:
    """Move torrent files to the recycle bin.

    Returns the recycled item name if files were successfully moved, or empty string on failure.
    Partial moves (some files copied, some missing) are considered success since
    the recycle bin is a safety net before deletion.
    """
    config = ConfigOverrideManager.get_effective_config()
    recycle_config = config.recycle_bin

    if not recycle_config.enabled:
        logger.warning("[Recycle Bin] Recycle bin is not enabled, skipping")
        return ""

    try:
        torrents = qbt_client.client.torrents.info(torrent_hashes=torrent_hash)
        if not torrents:
            logger.warning(f"[Recycle Bin] Could not find torrent {torrent_hash[:8]}")
            return ""

        torrent = torrents[0]
        content_path = getattr(torrent, "content_path", None) or getattr(torrent, "save_path", None)
        if not content_path:
            logger.warning(f"[Recycle Bin] No content path for torrent {torrent_hash[:8]}")
            return ""

        source = Path(content_path)
        if not source.exists():
            logger.warning(f"[Recycle Bin] Source path does not exist: {source}")
            return ""

        recycle_path = Path(recycle_config.path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = recycle_path / f"{timestamp}_{source.name}"
        recycle_path.mkdir(parents=True, exist_ok=True)

        result = resilient_move(source, dest)

        if result.success:
            if result.partial:
                logger.warning(
                    f"[Recycle Bin] Partial move: {result.files_copied} copied, "
                    f"{result.files_failed} skipped for {source.name}"
                )
                for rel_path, error_msg in result.errors:
                    logger.warning(f"[Recycle Bin]   Skipped: {rel_path} - {error_msg}")
            else:
                logger.info(f"[Recycle Bin] Moved to recycle bin: {source.name}")
        else:
            logger.error(f"[Recycle Bin] Failed to move any files for {source.name}")
            return ""

        write_move_metadata(recycle_path, dest.name, str(source.parent), result)

        return dest.name

    except Exception as e:
        logger.error(f"[Recycle Bin] Error moving files: {e}")
        return ""


@router.delete("/torrents", response_model=ActionResponse)
def delete_torrent(body: TorrentDeleteRequest, request: Request) -> ActionResponse:
    """Delete a torrent from qBittorrent.

    Optionally moves files to recycle bin first, or permanently deletes them.
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

        # If recycle requested, move files to recycle bin first
        recycled_name = ""
        if body.recycle:
            recycled_name = _move_torrent_to_recycle_bin(qbt_client, body.hash)
            if not recycled_name:
                return ActionResponse(
                    success=False,
                    message="Failed to move files to recycle bin. Torrent was not deleted.",
                )
            # Files have been moved to recycle bin, so delete torrent only (no files)
            success = qbt_client.delete_torrents([body.hash], False)
        else:
            success = qbt_client.delete_torrents([body.hash], body.delete_files)

        if success:
            if body.recycle:
                action = "Recycled (files moved to recycle bin)"
            elif body.delete_files:
                action = "Deleted (with files)"
            else:
                action = "Removed (torrent only)"
            logger.info(f"{action}: {body.hash[:8]}")
            data = {"recycled_name": recycled_name} if recycled_name else None
            return ActionResponse(
                success=True,
                message=f"Torrent {'moved to recycle bin' if body.recycle else 'deleted with files' if body.delete_files else 'removed'}",
                data=data,
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
