#!/usr/bin/env python3
"""Configuration management for qBittorrent cleanup."""

import os
from dataclasses import dataclass, field
from typing import Optional

from .utils import parse_bool, parse_float, parse_int


@dataclass
class ConnectionConfig:
    """qBittorrent connection configuration."""
    host: str = field(default_factory=lambda: os.environ.get("QB_HOST", "localhost"))
    port: int = field(default_factory=lambda: parse_int("QB_PORT", 8080))
    username: str = field(default_factory=lambda: os.environ.get("QB_USERNAME", "admin"))
    password: str = field(default_factory=lambda: os.environ.get("QB_PASSWORD", "adminadmin"))
    verify_ssl: bool = field(default_factory=lambda: parse_bool("QB_VERIFY_SSL", False))


@dataclass
class LimitsConfig:
    """Torrent cleanup limits configuration."""
    # Fallback values
    fallback_ratio: float = field(default_factory=lambda: parse_float("FALLBACK_RATIO", 1.0, 0))
    fallback_days: float = field(default_factory=lambda: parse_float("FALLBACK_DAYS", 7.0, 0))
    
    # Private torrent limits
    private_ratio: float = field(init=False)
    private_days: float = field(init=False)
    
    # Public torrent limits  
    public_ratio: float = field(init=False)
    public_days: float = field(init=False)
    
    # Override flags for qBittorrent settings
    ignore_qbt_ratio_private: bool = field(default_factory=lambda: parse_bool("IGNORE_QBT_RATIO_PRIVATE", False))
    ignore_qbt_ratio_public: bool = field(default_factory=lambda: parse_bool("IGNORE_QBT_RATIO_PUBLIC", False))
    ignore_qbt_time_private: bool = field(default_factory=lambda: parse_bool("IGNORE_QBT_TIME_PRIVATE", False))
    ignore_qbt_time_public: bool = field(default_factory=lambda: parse_bool("IGNORE_QBT_TIME_PUBLIC", False))
    
    def __post_init__(self):
        """Initialize derived values after dataclass creation."""
        self.private_ratio = parse_float("PRIVATE_RATIO", self.fallback_ratio, 0)
        self.private_days = parse_float("PRIVATE_DAYS", self.fallback_days, 0)
        self.public_ratio = parse_float("PUBLIC_RATIO", self.fallback_ratio, 0)
        self.public_days = parse_float("PUBLIC_DAYS", self.fallback_days, 0)


@dataclass 
class BehaviorConfig:
    """Cleanup behavior configuration."""
    delete_files: bool = field(default_factory=lambda: parse_bool("DELETE_FILES", True))
    dry_run: bool = field(default_factory=lambda: parse_bool("DRY_RUN", False))
    
    # Paused-only checking
    check_paused_only: bool = field(default_factory=lambda: parse_bool("CHECK_PAUSED_ONLY", False))
    check_private_paused_only: bool = field(init=False)
    check_public_paused_only: bool = field(init=False)
    
    # Force delete settings
    force_delete_hours: float = field(default_factory=lambda: parse_float("FORCE_DELETE_AFTER_HOURS", 0, 0))
    force_delete_private_hours: float = field(init=False)
    force_delete_public_hours: float = field(init=False)
    
    # Stalled download cleanup
    cleanup_stale_downloads: bool = field(default_factory=lambda: parse_bool("CLEANUP_STALE_DOWNLOADS", False))
    max_stalled_days: float = field(default_factory=lambda: parse_float("MAX_STALLED_DAYS", 3.0, 0))
    max_stalled_private_days: float = field(init=False)
    max_stalled_public_days: float = field(init=False)
    
    def __post_init__(self):
        """Initialize derived values after dataclass creation."""
        # Paused-only settings
        default_paused = self.check_paused_only
        self.check_private_paused_only = parse_bool("CHECK_PRIVATE_PAUSED_ONLY", default_paused)
        self.check_public_paused_only = parse_bool("CHECK_PUBLIC_PAUSED_ONLY", default_paused)
        
        # Force delete settings
        default_force = self.force_delete_hours
        self.force_delete_private_hours = parse_float("FORCE_DELETE_PRIVATE_AFTER_HOURS", default_force, 0)
        self.force_delete_public_hours = parse_float("FORCE_DELETE_PUBLIC_AFTER_HOURS", default_force, 0)
        
        # Stalled settings
        default_stalled = self.max_stalled_days
        self.max_stalled_private_days = parse_float("MAX_STALLED_PRIVATE_DAYS", default_stalled, 0)
        self.max_stalled_public_days = parse_float("MAX_STALLED_PUBLIC_DAYS", default_stalled, 0)


@dataclass
class ScheduleConfig:
    """Schedule configuration."""
    interval_hours: int = field(default_factory=lambda: parse_int("SCHEDULE_HOURS", 24, 1))
    run_once: bool = field(default_factory=lambda: parse_bool("RUN_ONCE", False))


@dataclass
class FileFlowsConfig:
    """FileFlows integration configuration."""
    enabled: bool = field(default_factory=lambda: parse_bool("FILEFLOWS_ENABLED", False))
    host: str = field(default_factory=lambda: os.environ.get("FILEFLOWS_HOST", "localhost"))
    port: int = field(default_factory=lambda: parse_int("FILEFLOWS_PORT", 19200))
    timeout: int = field(default_factory=lambda: parse_int("FILEFLOWS_TIMEOUT", 10, 1))


@dataclass
class OrphanedFilesConfig:
    """Orphaned files cleanup configuration."""
    enabled: bool = field(default_factory=lambda: parse_bool("CLEANUP_ORPHANED_FILES", False))
    scan_dirs: list[str] = field(default_factory=lambda: [
        d.strip() for d in os.environ.get("ORPHANED_SCAN_DIRS", "").split(",") if d.strip()
    ])
    min_age_hours: float = field(default_factory=lambda: parse_float("ORPHANED_MIN_AGE_HOURS", 1.0, 0))
    schedule_days: int = field(default_factory=lambda: parse_int("ORPHANED_SCHEDULE_DAYS", 7, 1))


@dataclass
class Config:
    """Main configuration container."""
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    behavior: BehaviorConfig = field(default_factory=BehaviorConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    fileflows: FileFlowsConfig = field(default_factory=FileFlowsConfig)
    orphaned: OrphanedFilesConfig = field(default_factory=OrphanedFilesConfig)
    
    @classmethod
    def from_environment(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()