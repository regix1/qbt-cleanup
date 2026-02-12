"""Actions router for the qbt-cleanup web API."""

import logging

from fastapi import APIRouter, Request

from ..app_state import AppState
from ..models import ActionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


@router.post("/actions/scan", response_model=ActionResponse)
def trigger_scan(request: Request) -> ActionResponse:
    """Trigger a manual cleanup scan.

    Sets the scan event so the scheduler loop picks it up on its next
    wait cycle.
    """
    app_state = get_app_state(request)
    app_state.scan_event.set()
    logger.info("Manual scan triggered via API")

    return ActionResponse(
        success=True,
        message="Scan triggered successfully",
    )


@router.post("/actions/orphaned-scan", response_model=ActionResponse)
def trigger_orphaned_scan(request: Request) -> ActionResponse:
    """Trigger an orphaned file scan.

    Sets both the orphaned scan event (to force bypass schedule) and
    the regular scan event (to wake the scheduler loop).
    """
    app_state = get_app_state(request)
    app_state.orphaned_scan_event.set()
    app_state.scan_event.set()
    logger.info("Orphaned file scan triggered via API")

    return ActionResponse(
        success=True,
        message="Orphaned file scan triggered successfully",
    )
