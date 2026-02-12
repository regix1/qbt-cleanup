"""Blacklist router for the qbt-cleanup web API."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request

from ...state import StateManager
from ..app_state import AppState
from ..models import ActionResponse, BlacklistAddRequest, BlacklistEntry

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


@router.get("/blacklist", response_model=List[BlacklistEntry])
def get_blacklist() -> List[BlacklistEntry]:
    """Return all blacklisted torrent entries."""
    state_mgr: StateManager | None = None
    try:
        state_mgr = StateManager()
        entries = state_mgr.get_blacklist()
        return [
            BlacklistEntry(
                hash=entry["hash"],
                name=entry.get("name", ""),
                added_at=entry["added_at"],
                reason=entry.get("reason", ""),
            )
            for entry in entries
        ]
    except Exception as exc:
        logger.error(f"Error retrieving blacklist: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if state_mgr is not None:
            state_mgr.close()


@router.post("/blacklist", response_model=ActionResponse)
def add_to_blacklist(body: BlacklistAddRequest) -> ActionResponse:
    """Add a torrent to the blacklist."""
    state_mgr: StateManager | None = None
    try:
        state_mgr = StateManager()
        success = state_mgr.add_to_blacklist(
            torrent_hash=body.hash,
            name=body.name or "",
            reason=body.reason or "",
        )
        if success:
            return ActionResponse(
                success=True,
                message=f"Torrent {body.hash} added to blacklist",
            )
        return ActionResponse(
            success=False,
            message=f"Failed to add torrent {body.hash} to blacklist",
        )
    except Exception as exc:
        logger.error(f"Error adding to blacklist: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if state_mgr is not None:
            state_mgr.close()


@router.delete("/blacklist/{hash}", response_model=ActionResponse)
def remove_from_blacklist(hash: str) -> ActionResponse:
    """Remove a single torrent from the blacklist by hash."""
    state_mgr: StateManager | None = None
    try:
        state_mgr = StateManager()
        success = state_mgr.remove_from_blacklist(hash)
        if success:
            return ActionResponse(
                success=True,
                message=f"Torrent {hash} removed from blacklist",
            )
        return ActionResponse(
            success=False,
            message=f"Torrent {hash} not found in blacklist",
        )
    except Exception as exc:
        logger.error(f"Error removing from blacklist: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if state_mgr is not None:
            state_mgr.close()


@router.delete("/blacklist", response_model=ActionResponse)
def clear_blacklist() -> ActionResponse:
    """Clear all entries from the blacklist."""
    state_mgr: StateManager | None = None
    try:
        state_mgr = StateManager()
        success = state_mgr.clear_blacklist()
        if success:
            return ActionResponse(
                success=True,
                message="Blacklist cleared",
            )
        return ActionResponse(
            success=False,
            message="Failed to clear blacklist",
        )
    except Exception as exc:
        logger.error(f"Error clearing blacklist: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if state_mgr is not None:
            state_mgr.close()
