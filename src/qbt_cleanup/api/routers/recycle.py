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

from ...config_overrides import ConfigOverrideManager
from ..models import ActionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class RecycleBinItem(BaseModel):
    """Response model for a recycle bin item."""
    name: str
    path: str
    size: int
    is_dir: bool
    modified_time: float
    age_days: float
    original_path: str = ""


class RecycleBinResponse(BaseModel):
    """Response model for recycle bin listing."""
    enabled: bool
    path: str
    items: List[RecycleBinItem]
    total_size: int
    purge_after_days: int


@router.get("/recycle-bin", response_model=RecycleBinResponse)
def list_recycle_bin() -> RecycleBinResponse:
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

    recycle_path = Path(recycle_config.path)
    items: List[RecycleBinItem] = []
    total_size = 0
    current_time = time.time()

    if recycle_path.exists():
        for item in sorted(recycle_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            # Skip sidecar metadata files
            if item.name.endswith(".meta.json"):
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
        logger.info(f"[Recycle Bin] Permanently deleted: {item_name}")
        return ActionResponse(success=True, message=f"Deleted {item_name}")
    except Exception as e:
        logger.error(f"[Recycle Bin] Error deleting {item_name}: {e}")
        return ActionResponse(success=False, message=f"Failed to delete: {e}")


@router.post("/recycle-bin/{item_name}/restore", response_model=ActionResponse)
def restore_recycle_item(item_name: str) -> ActionResponse:
    """Restore an item from the recycle bin to its original location."""
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

    # Read sidecar metadata
    meta_file = recycle_path / f"{item_name}.meta.json"
    if not meta_file.exists():
        raise HTTPException(
            status_code=400,
            detail="No metadata found — cannot determine original location",
        )

    try:
        meta = json.loads(meta_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid metadata: {e}")

    original_path = meta.get("original_path", "")
    if not original_path:
        raise HTTPException(status_code=400, detail="No original path in metadata")

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
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item_path), str(dest))
        meta_file.unlink()
        logger.info(f"[Recycle Bin] Restored: {item_name} -> {dest}")
        return ActionResponse(success=True, message=f"Restored to {dest}")
    except Exception as e:
        logger.error(f"[Recycle Bin] Error restoring {item_name}: {e}")
        return ActionResponse(success=False, message=f"Failed to restore: {e}")


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
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            deleted += 1
        except Exception as e:
            logger.error(f"[Recycle Bin] Error deleting {item.name}: {e}")
            errors += 1

    message = f"Deleted {deleted} item(s)"
    if errors > 0:
        message += f", {errors} error(s)"
    logger.info(f"[Recycle Bin] Emptied: {message}")
    return ActionResponse(success=True, message=message)
