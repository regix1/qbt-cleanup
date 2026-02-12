"""FileFlows router for the qbt-cleanup web API."""

import logging

from fastapi import APIRouter, Request

from ...fileflows import FileFlowsClient
from ..app_state import AppState
from ..models import FileFlowsStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


@router.get("/fileflows/status", response_model=FileFlowsStatusResponse)
def fileflows_status(request: Request) -> FileFlowsStatusResponse:
    """Return the current FileFlows integration status.

    If FileFlows is not enabled in the configuration, returns a minimal
    response with ``enabled=False``.  Otherwise connects to the FileFlows
    API and returns processing counts and file details.
    """
    app_state = get_app_state(request)
    config = app_state.config

    if not config.fileflows.enabled:
        return FileFlowsStatusResponse(enabled=False)

    client = FileFlowsClient(config.fileflows)
    status = client._fetch_status()

    if status is None:
        return FileFlowsStatusResponse(
            enabled=True,
            connected=False,
        )

    return FileFlowsStatusResponse(
        enabled=True,
        connected=True,
        processing=status.get("processing", 0),
        queue=status.get("queue", 0),
        processing_files=status.get("processingFiles", []),
    )
