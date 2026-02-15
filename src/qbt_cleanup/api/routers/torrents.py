"""Torrents router for the qbt-cleanup web API."""

from __future__ import annotations

import logging
import os
import shutil
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
from ..models import (
    ActionResponse,
    CategoriesResponse,
    CategoryInfo,
    TorrentDeleteRequest,
    TorrentHashRequest,
    TorrentMoveRequest,
    TorrentResponse,
)

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
    recycling = app_state.get_recycling_hashes()
    moving = app_state.get_moving_hashes()

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
                    is_recycling=info.hash in recycling,
                    is_moving=info.hash in moving,
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



@router.get("/torrents/categories", response_model=CategoriesResponse)
def list_categories(request: Request) -> CategoriesResponse:
    """List all qBittorrent categories with their save paths."""
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

        raw_categories = qbt_client.client.torrent_categories.categories
        categories = [
            CategoryInfo(name=name, save_path=info.get("savePath", ""))
            for name, info in raw_categories.items()
        ]
        categories.sort(key=lambda c: c.name)

        return CategoriesResponse(categories=categories)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error listing categories: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if qbt_client is not None:
            qbt_client.disconnect()


@router.post("/torrents/pause", response_model=ActionResponse)
def pause_torrent(body: TorrentHashRequest, request: Request) -> ActionResponse:
    """Pause/stop a torrent."""
    app_state = get_app_state(request)
    config = app_state.config
    qbt_client: QBittorrentClient | None = None

    try:
        qbt_client = QBittorrentClient(config.connection)
        if not qbt_client.connect(quiet=True):
            raise HTTPException(status_code=503, detail="Unable to connect to qBittorrent")

        qbt_client.client.torrents.pause(torrent_hashes=body.hash)
        logger.info(f"Paused torrent {body.hash[:8]}")
        return ActionResponse(success=True, message="Torrent paused")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error pausing torrent: {exc}")
        return ActionResponse(success=False, message=str(exc))
    finally:
        if qbt_client is not None:
            qbt_client.disconnect()


@router.post("/torrents/resume", response_model=ActionResponse)
def resume_torrent(body: TorrentHashRequest, request: Request) -> ActionResponse:
    """Resume/start a torrent."""
    app_state = get_app_state(request)
    config = app_state.config
    qbt_client: QBittorrentClient | None = None

    try:
        qbt_client = QBittorrentClient(config.connection)
        if not qbt_client.connect(quiet=True):
            raise HTTPException(status_code=503, detail="Unable to connect to qBittorrent")

        qbt_client.client.torrents.resume(torrent_hashes=body.hash)
        logger.info(f"Resumed torrent {body.hash[:8]}")
        return ActionResponse(success=True, message="Torrent resumed")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error resuming torrent: {exc}")
        return ActionResponse(success=False, message=str(exc))
    finally:
        if qbt_client is not None:
            qbt_client.disconnect()


@router.post("/torrents/move", response_model=ActionResponse)
def move_torrent(body: TorrentMoveRequest, request: Request) -> ActionResponse:
    """Move a torrent by changing its category or setting a new location."""
    app_state = get_app_state(request)
    config = app_state.config

    if not body.category and not body.location:
        return ActionResponse(success=False, message="Either category or location must be provided")

    app_state.add_moving(body.hash)
    qbt_client: QBittorrentClient | None = None

    try:
        qbt_client = QBittorrentClient(config.connection)

        if not qbt_client.connect(quiet=True):
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to qBittorrent",
            )

        if body.category:
            qbt_client.client.torrents.set_category(
                category=body.category, torrent_hashes=body.hash,
            )
            qbt_client.client.torrents.set_auto_management(
                enable=True, torrent_hashes=body.hash,
            )
            logger.info(f"Moved torrent {body.hash[:8]} to category '{body.category}'")
            return ActionResponse(
                success=True,
                message=f"Torrent moved to category '{body.category}'",
            )
        else:
            qbt_client.client.torrents.set_location(
                location=body.location, torrent_hashes=body.hash,
            )
            logger.info(f"Moved torrent {body.hash[:8]} to '{body.location}'")
            return ActionResponse(
                success=True,
                message=f"Torrent moved to '{body.location}'",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error moving torrent: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        app_state.remove_moving(body.hash)
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

        # Pause the torrent so qBittorrent releases file handles
        try:
            qbt_client.client.torrents.pause(torrent_hashes=torrent_hash)
            time.sleep(1)  # brief delay for file handles to release
        except Exception as e:
            logger.warning(f"[Recycle Bin] Could not pause torrent: {e}")

        # Export .torrent file for re-adding on restore
        torrent_file_data = None
        try:
            torrent_file_data = qbt_client.client.torrents.export(torrent_hash=torrent_hash)
        except Exception as e:
            logger.warning(f"[Recycle Bin] Could not export .torrent file: {e}")

        recycle_path = Path(recycle_config.path)
        staging_path = recycle_path / ".staging"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        item_name = f"{timestamp}_{source.name}"
        staging_dest = staging_path / item_name
        final_dest = recycle_path / item_name
        staging_path.mkdir(parents=True, exist_ok=True)

        # Copy to staging first so the item doesn't appear in the recycle bin
        # until the copy is fully complete
        result = resilient_move(source, staging_dest)

        if result.success:
            if result.partial:
                logger.warning(
                    f"[Recycle Bin] Partial move: {result.files_copied} copied, "
                    f"{result.files_failed} skipped for {source.name}"
                )
                for rel_path, error_msg in result.errors:
                    logger.warning(f"[Recycle Bin]   Skipped: {rel_path} - {error_msg}")
            # Atomically move from staging to recycle bin (same filesystem)
            try:
                os.rename(str(staging_dest), str(final_dest))
            except OSError as e:
                logger.error(f"[Recycle Bin] Failed to move from staging: {e}")
                return ""
            logger.info(f"[Recycle Bin] Moved to recycle bin: {source.name}")
        else:
            logger.error(f"[Recycle Bin] Failed to move any files for {source.name}")
            # Clean up empty staging dir
            try:
                shutil.rmtree(str(staging_dest), ignore_errors=True)
            except Exception:
                pass
            return ""

        torrent_category = getattr(torrent, "category", "") or ""
        write_move_metadata(
            recycle_path, item_name, str(source.parent), result,
            torrent_hash=torrent_hash, torrent_category=torrent_category,
        )

        # Save .torrent file for re-adding on restore
        if torrent_file_data:
            try:
                torrent_sidecar = recycle_path / f"{item_name}.torrent"
                torrent_sidecar.write_bytes(torrent_file_data)
            except OSError as e:
                logger.warning(f"[Recycle Bin] Failed to save .torrent file: {e}")

        return item_name

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
            app_state.add_recycling(body.hash)
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
        app_state.remove_recycling(body.hash)
        if qbt_client is not None:
            qbt_client.disconnect()
