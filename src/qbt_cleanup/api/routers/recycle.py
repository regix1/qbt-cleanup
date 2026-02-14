"""Recycle bin router for the qbt-cleanup web API."""

import json
import logging
import re
import shutil
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...client import QBittorrentClient
from ...config_overrides import ConfigOverrideManager
from ...resilient_move import resilient_move
from ..app_state import AppState
from ..models import ActionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


class RecycleBinItem(BaseModel):
    """Response model for a recycle bin item."""
    name: str
    path: str
    size: int
    is_dir: bool
    modified_time: float
    age_days: float
    original_path: str = ""
    is_restoring: bool = False


class RecycleBinResponse(BaseModel):
    """Response model for recycle bin listing."""
    enabled: bool
    path: str
    items: List[RecycleBinItem]
    total_size: int
    purge_after_days: int


@router.get("/recycle-bin", response_model=RecycleBinResponse)
def list_recycle_bin(request: Request) -> RecycleBinResponse:
    """List all items in the recycle bin."""
    config = ConfigOverrideManager.get_effective_config()
    recycle_config = config.recycle_bin

    if not recycle_config.enabled:
        return RecycleBinResponse(
            enabled=False,
            path=recycle_config.path,
            items=[],
            total_size=0,
            purge_after_days=recycle_config.purge_after_days,
        )

    app_state = _get_app_state(request)
    restoring = app_state.get_restoring_items()

    recycle_path = Path(recycle_config.path)
    items: List[RecycleBinItem] = []
    total_size = 0
    current_time = time.time()

    if recycle_path.exists():
        for item in sorted(recycle_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            # Skip sidecar metadata files and staging directory
            if item.name.endswith(".meta.json") or item.name.endswith(".torrent") or item.name == ".staging":
                continue
            try:
                stat = item.stat()
                if item.is_dir():
                    size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                else:
                    size = stat.st_size
                total_size += size
                age_seconds = current_time - stat.st_mtime

                # Read sidecar metadata if available
                original_path = ""
                meta_file = recycle_path / f"{item.name}.meta.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text())
                        original_path = meta.get("original_path", "")
                    except (json.JSONDecodeError, OSError):
                        pass

                items.append(RecycleBinItem(
                    name=item.name,
                    path=str(item),
                    size=size,
                    is_dir=item.is_dir(),
                    modified_time=stat.st_mtime,
                    age_days=round(age_seconds / 86400, 1),
                    original_path=original_path,
                    is_restoring=item.name in restoring,
                ))
            except OSError as e:
                logger.warning(f"Error reading recycle bin item {item}: {e}")

    return RecycleBinResponse(
        enabled=True,
        path=str(recycle_path),
        items=items,
        total_size=total_size,
        purge_after_days=recycle_config.purge_after_days,
    )


@router.delete("/recycle-bin/{item_name}", response_model=ActionResponse)
def delete_recycle_item(item_name: str) -> ActionResponse:
    """Permanently delete an item from the recycle bin."""
    config = ConfigOverrideManager.get_effective_config()
    recycle_path = Path(config.recycle_bin.path)
    item_path = recycle_path / item_name

    if not item_path.exists():
        raise HTTPException(status_code=404, detail="Item not found")

    # Security: ensure the item is actually inside the recycle bin
    try:
        item_path.resolve().relative_to(recycle_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item path")

    try:
        if item_path.is_dir():
            shutil.rmtree(item_path)
        else:
            item_path.unlink()
        # Clean up sidecar metadata
        meta_file = recycle_path / f"{item_name}.meta.json"
        if meta_file.exists():
            meta_file.unlink()
        # Clean up .torrent sidecar
        torrent_sidecar = recycle_path / f"{item_name}.torrent"
        if torrent_sidecar.exists():
            torrent_sidecar.unlink()
        logger.info(f"[Recycle Bin] Permanently deleted: {item_name}")
        return ActionResponse(success=True, message=f"Deleted {item_name}")
    except Exception as e:
        logger.error(f"[Recycle Bin] Error deleting {item_name}: {e}")
        return ActionResponse(success=False, message=f"Failed to delete: {e}")


class RestoreRequest(BaseModel):
    """Request model for restoring a recycle bin item."""
    target_path: str = ""


@router.post("/recycle-bin/{item_name}/restore", response_model=ActionResponse)
def restore_recycle_item(item_name: str, request: Request, body: RestoreRequest | None = None) -> ActionResponse:
    """Restore an item from the recycle bin to its original location."""
    config = ConfigOverrideManager.get_effective_config()
    recycle_path = Path(config.recycle_bin.path)
    item_path = recycle_path / item_name

    app_state = _get_app_state(request)

    if not item_path.exists():
        raise HTTPException(status_code=404, detail="Item not found")

    # Security: ensure the item is actually inside the recycle bin
    try:
        item_path.resolve().relative_to(recycle_path.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item path")

    # Determine restore path: body param > sidecar metadata
    original_path = ""
    if body and body.target_path:
        original_path = body.target_path
    else:
        meta_file = recycle_path / f"{item_name}.meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                original_path = meta.get("original_path", "")
            except (json.JSONDecodeError, OSError):
                pass

    if not original_path:
        raise HTTPException(
            status_code=400,
            detail="No restore path provided and no metadata found",
        )

    # Strip the timestamp prefix (YYYYMMDD_HHMMSS_) to get the original name
    original_name = re.sub(r"^\d{8}_\d{6}_", "", item_name)
    if not original_name:
        original_name = item_name

    dest_dir = Path(original_path)
    dest = dest_dir / original_name

    if dest.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Destination already exists: {dest}",
        )

    try:
        app_state.add_restoring(item_name)
        result = resilient_move(item_path, dest)

        if not result.success:
            return ActionResponse(
                success=False,
                message="Failed to restore: no files could be copied",
            )

        if result.partial:
            logger.warning(
                f"[Recycle Bin] Partial restore: {result.files_copied} files restored, "
                f"{result.files_failed} failed for {item_name}"
            )

        # Read metadata for torrent hash and category before cleanup
        torrent_hash = ""
        torrent_category = ""
        meta_file = recycle_path / f"{item_name}.meta.json"
        if meta_file.exists():
            try:
                meta_content = json.loads(meta_file.read_text())
                torrent_hash = meta_content.get("torrent_hash", "")
                torrent_category = meta_content.get("torrent_category", "")
            except (json.JSONDecodeError, OSError):
                pass
            meta_file.unlink()

        # Re-add torrent to qBittorrent if .torrent sidecar exists
        torrent_sidecar = recycle_path / f"{item_name}.torrent"
        torrent_readded = False
        if torrent_sidecar.exists():
            try:
                app_state = _get_app_state(request)
                qbt_client = QBittorrentClient(app_state.config.connection)
                if qbt_client.connect(quiet=True):
                    try:
                        torrent_data = torrent_sidecar.read_bytes()
                        add_params = {
                            "torrent_files": torrent_data,
                            "save_path": str(dest_dir),
                            "is_paused": True,
                            "use_auto_tmm": False,
                        }
                        if torrent_category:
                            add_params["category"] = torrent_category
                        add_result = qbt_client.client.torrents.add(**add_params)
                        logger.info(
                            f"[Recycle Bin] torrents.add result={add_result}, "
                            f"save_path={dest_dir}, category={torrent_category!r}, "
                            f"stored_hash={torrent_hash[:8] if torrent_hash else 'none'}"
                        )
                        time.sleep(2)

                        # Resolve the actual hash — re-added torrents may get
                        # a different hash (v1 vs v2 / hybrid BitTorrent).
                        actual_hash = torrent_hash
                        if torrent_hash:
                            check = qbt_client.client.torrents.info(torrent_hashes=torrent_hash)
                            if not check:
                                logger.info("[Recycle Bin] Stored hash not found, searching by content_path")
                                resolved_dest = str(dest.resolve())
                                for t in qbt_client.client.torrents.info():
                                    content = getattr(t, "content_path", "") or ""
                                    if content and str(Path(content).resolve()) == resolved_dest:
                                        actual_hash = t.hash
                                        logger.info(f"[Recycle Bin] Found torrent with new hash {actual_hash[:8]}")
                                        break
                        else:
                            # No stored hash — find by content_path
                            resolved_dest = str(dest.resolve())
                            for t in qbt_client.client.torrents.info():
                                content = getattr(t, "content_path", "") or ""
                                if content and str(Path(content).resolve()) == resolved_dest:
                                    actual_hash = t.hash
                                    break

                        if actual_hash:
                            qbt_client.client.torrents.recheck(torrent_hashes=actual_hash)
                            # Wait for recheck to complete before resuming
                            checking_states = {"checkingUP", "checkingDL", "checkingResumeData"}
                            for _ in range(30):
                                time.sleep(1)
                                try:
                                    info = qbt_client.client.torrents.info(torrent_hashes=actual_hash)
                                    if info and info[0].state not in checking_states:
                                        break
                                except Exception:
                                    break
                            qbt_client.client.torrents.resume(torrent_hashes=actual_hash)
                        torrent_readded = True
                        logger.info(f"[Recycle Bin] Re-added torrent to qBittorrent")
                    finally:
                        qbt_client.disconnect()
                torrent_sidecar.unlink()
            except Exception as e:
                logger.warning(f"[Recycle Bin] Could not re-add torrent: {e}")

        message = f"Restored to {dest}"
        if torrent_readded:
            message += " and re-added to qBittorrent"
        if result.partial:
            message += f" (partial: {result.files_failed} files could not be restored)"

        logger.info(f"[Recycle Bin] Restored: {item_name} -> {dest}")
        return ActionResponse(success=True, message=message)
    except Exception as e:
        logger.error(f"[Recycle Bin] Error restoring {item_name}: {e}")
        return ActionResponse(success=False, message=f"Failed to restore: {e}")
    finally:
        app_state.remove_restoring(item_name)


@router.delete("/recycle-bin", response_model=ActionResponse)
def empty_recycle_bin() -> ActionResponse:
    """Empty the entire recycle bin."""
    config = ConfigOverrideManager.get_effective_config()
    recycle_path = Path(config.recycle_bin.path)

    if not recycle_path.exists():
        return ActionResponse(success=True, message="Recycle bin is already empty")

    deleted = 0
    errors = 0
    for item in recycle_path.iterdir():
        if item.name == ".staging":
            shutil.rmtree(item, ignore_errors=True)
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            if not item.name.endswith(".meta.json"):
                deleted += 1
        except Exception as e:
            logger.error(f"[Recycle Bin] Error deleting {item.name}: {e}")
            errors += 1

    message = f"Deleted {deleted} item(s)"
    if errors > 0:
        message += f", {errors} error(s)"
    logger.info(f"[Recycle Bin] Emptied: {message}")
    return ActionResponse(success=True, message=message)
