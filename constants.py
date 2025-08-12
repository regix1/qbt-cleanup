#!/usr/bin/env python3
"""Constants and enumerations for qBittorrent cleanup."""

from enum import Enum, auto
from typing import Final

# Time constants
SECONDS_PER_DAY: Final[int] = 86400
SECONDS_PER_HOUR: Final[int] = 3600
MINUTES_PER_HOUR: Final[int] = 60

# Network constants
DEFAULT_TIMEOUT: Final[int] = 30
MAX_RETRY_ATTEMPTS: Final[int] = 3
RETRY_DELAY: Final[float] = 5.0

# File paths
STATE_FILE: Final[str] = "/config/qbt_cleanup_state.json"

# FileFlows constants
FILEFLOWS_RECENT_THRESHOLD_MINUTES: Final[int] = 10


class TorrentState(str, Enum):
    """qBittorrent torrent states."""
    PAUSED_UP = "pausedUP"
    PAUSED_DL = "pausedDL"
    DOWNLOADING = "downloading"
    STALLED_DL = "stalledDL"
    QUEUED_DL = "queuedDL"
    ALLOCATING = "allocating"
    META_DL = "metaDL"
    UPLOADING = "uploading"
    STALLED_UP = "stalledUP"
    QUEUED_UP = "queuedUP"
    CHECKING_UP = "checkingUP"
    CHECKING_DL = "checkingDL"
    
    @classmethod
    def paused_states(cls) -> set:
        """Return set of paused states."""
        return {cls.PAUSED_UP, cls.PAUSED_DL}
    
    @classmethod
    def downloading_states(cls) -> set:
        """Return set of downloading states."""
        return {cls.DOWNLOADING, cls.STALLED_DL, cls.QUEUED_DL, 
                cls.ALLOCATING, cls.META_DL}


class DeletionReason(str, Enum):
    """Reasons for torrent deletion."""
    RATIO_EXCEEDED = "ratio_exceeded"
    TIME_EXCEEDED = "time_exceeded"
    FORCE_DELETE = "force_delete"
    STALLED_TOO_LONG = "stalled_too_long"
    BOTH_LIMITS_EXCEEDED = "both_limits_exceeded"


class TorrentType(str, Enum):
    """Torrent privacy type."""
    PRIVATE = "private"
    PUBLIC = "public"