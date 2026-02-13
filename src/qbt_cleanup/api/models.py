"""Pydantic request and response models for the qbt-cleanup web API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for the health-check endpoint."""

    status: str = "ok"
    version: str
    uptime_seconds: float


class StatusResponse(BaseModel):
    """Response model for the status endpoint."""

    version: str
    state_enabled: bool
    db_path: str
    torrent_count: int
    blacklist_count: int
    stalled_count: int
    private_count: int
    public_count: int
    last_run_time: Optional[str] = None
    last_run_success: Optional[bool] = None
    last_run_stats: Optional[dict] = None
    scheduler_running: bool
    schedule_hours: int
    dry_run: bool
    delete_files: bool


class TorrentResponse(BaseModel):
    """Response model for a single torrent entry."""

    hash: str
    name: str
    state: str
    ratio: float
    seeding_time: float
    is_private: bool
    is_paused: bool
    is_downloading: bool
    is_stalled: bool
    is_blacklisted: bool
    size: int = 0
    progress: float = 0.0
    category: str = ""
    tracker: str = ""
    added_on: int = 0
    save_path: str = ""


class BlacklistEntry(BaseModel):
    """Response model for a blacklisted torrent entry."""

    hash: str
    name: str = ""
    added_at: str
    reason: str = ""


class BlacklistAddRequest(BaseModel):
    """Request model for adding a torrent to the blacklist."""

    hash: str
    name: Optional[str] = ""
    reason: Optional[str] = ""


class TorrentDeleteRequest(BaseModel):
    """Request model for deleting a torrent."""

    hash: str
    delete_files: bool = False


class ConfigResponse(BaseModel):
    """Response model containing the full configuration."""

    connection: Dict[str, Any]
    limits: Dict[str, Any]
    behavior: Dict[str, Any]
    schedule: Dict[str, Any]
    fileflows: Dict[str, Any]
    orphaned: Dict[str, Any]
    web: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    """Request model for updating configuration overrides."""

    overrides: Dict[str, Any]


class FileFlowsStatusResponse(BaseModel):
    """Response model for the FileFlows integration status."""

    enabled: bool
    connected: bool = False
    processing: int = 0
    queue: int = 0
    processing_files: List[Dict[str, Any]] = Field(default_factory=list)


class ActionResponse(BaseModel):
    """Response model for action endpoints (scan, orphaned-scan, etc.)."""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None
