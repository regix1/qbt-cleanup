#!/usr/bin/env python3
"""Data models for qBittorrent cleanup."""

from dataclasses import dataclass, field
from typing import Any, Optional, List

from .constants import DeletionReason, TorrentType, TorrentState, SECONDS_PER_DAY


@dataclass
class TorrentInfo:
    """Processed torrent information."""
    torrent: Any  # qbittorrentapi torrent object
    hash: str
    name: str
    is_private: bool
    state: str
    ratio: float
    seeding_time: float  # in seconds
    files: List[str] = field(default_factory=list)
    
    @property
    def torrent_type(self) -> TorrentType:
        """Get torrent type."""
        return TorrentType.PRIVATE if self.is_private else TorrentType.PUBLIC
    
    @property
    def is_paused(self) -> bool:
        """Check if torrent is paused."""
        return self.state in TorrentState.paused_states()

    @property
    def is_downloading(self) -> bool:
        """Check if torrent is downloading."""
        return self.state in TorrentState.downloading_states()

    @property
    def is_stalled(self) -> bool:
        """Check if torrent is stalled."""
        return self.state == TorrentState.STALLED_DL.value


@dataclass
class TorrentLimits:
    """Limits for a specific torrent type."""
    ratio: float
    days: float
    
    @property
    def seconds(self) -> float:
        """Get time limit in seconds."""
        return self.days * SECONDS_PER_DAY


@dataclass
class DeletionCandidate:
    """Torrent marked for deletion."""
    info: TorrentInfo
    reason: DeletionReason
    limits: TorrentLimits
    excess_time_hours: Optional[float] = None  # For force delete
    stalled_days: Optional[float] = None  # For stalled downloads
    
    def format_reason(self) -> str:
        """Format deletion reason for logging."""
        parts = [f"state={self.info.state}"]
        
        if self.reason == DeletionReason.STALLED_TOO_LONG:
            parts.append(f"stalled={self.stalled_days:.1f}/{self.limits.days:.1f}d")
        else:
            parts.append(f"ratio={self.info.ratio:.2f}/{self.limits.ratio:.2f}")
            parts.append(f"time={self.info.seeding_time/SECONDS_PER_DAY:.1f}/{self.limits.days:.1f}d")
            
            if self.reason == DeletionReason.FORCE_DELETE and self.excess_time_hours:
                parts.append(f"excess={self.excess_time_hours:.1f}h")
        
        return ", ".join(parts)


@dataclass
class ClassificationResult:
    """Result of torrent classification."""
    to_delete: List[DeletionCandidate] = field(default_factory=list)
    stalled: List[DeletionCandidate] = field(default_factory=list)
    paused_not_ready: List[TorrentInfo] = field(default_factory=list)
    protected_by_fileflows: List[TorrentInfo] = field(default_factory=list)
    
    @property
    def total_deletions(self) -> int:
        """Total number of torrents to delete."""
        return len(self.to_delete) + len(self.stalled)
    
    def get_deletion_stats(self) -> dict:
        """Get deletion statistics."""
        stats = {
            "total": self.total_deletions,
            "completed": len(self.to_delete),
            "stalled": len(self.stalled),
            "private_completed": sum(1 for c in self.to_delete if c.info.is_private),
            "public_completed": sum(1 for c in self.to_delete if not c.info.is_private),
            "private_stalled": sum(1 for c in self.stalled if c.info.is_private),
            "public_stalled": sum(1 for c in self.stalled if not c.info.is_private),
        }
        return stats