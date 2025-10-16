#!/usr/bin/env python3
"""Torrent classification logic."""

import logging
from typing import List, Optional, Tuple

from .config import Config
from .models import (
    TorrentInfo, TorrentLimits, DeletionCandidate, 
    ClassificationResult, DeletionReason
)
from .state import StateManager
from .fileflows import FileFlowsClient
from .constants import SECONDS_PER_DAY, SECONDS_PER_HOUR
from .utils import truncate_name

logger = logging.getLogger(__name__)


class TorrentClassifier:
    """Classifies torrents for deletion based on configured criteria."""
    
    def __init__(self, config: Config, state_manager: StateManager, 
                 fileflows: Optional[FileFlowsClient] = None):
        """
        Initialize classifier.
        
        Args:
            config: Application configuration
            state_manager: State manager for persistence
            fileflows: Optional FileFlows client
        """
        self.config = config
        self.state = state_manager
        self.fileflows = fileflows
    
    def classify(self, torrents: List[TorrentInfo], 
                 limits: Tuple[float, float, float, float]) -> ClassificationResult:
        """
        Classify torrents for deletion.
        
        Args:
            torrents: List of torrent information
            limits: Tuple of (private_ratio, private_days, public_ratio, public_days)
            
        Returns:
            Classification result
        """
        private_ratio, private_days, public_ratio, public_days = limits
        
        # Build FileFlows cache if enabled
        if self.fileflows and self.fileflows.is_enabled:
            self.fileflows.build_processing_cache()
        
        # Update state for all torrents
        current_hashes = [t.hash for t in torrents]
        self.state.cleanup_old_torrents(current_hashes)

        # Check blacklist count
        blacklist_count = len(self.state.get_blacklist())
        if blacklist_count > 0:
            logger.info(f"Blacklist protection: {blacklist_count} torrent(s)")

        result = ClassificationResult()

        for torrent in torrents:
            # Update state tracking
            self.state.update_torrent_state(torrent.hash, torrent.state)

            # Check if blacklisted
            if self.state.is_blacklisted(torrent.hash):
                logger.debug(f"Skipping blacklisted torrent: {truncate_name(torrent.name)}")
                continue

            # Check for stalled downloads first
            if self._check_stalled_download(torrent, result):
                continue
            
            # Skip active downloads (except stalled)
            if torrent.is_downloading and not torrent.is_stalled:
                continue
            
            # Get limits for this torrent type
            limits = self._get_torrent_limits(torrent, private_ratio, private_days, 
                                             public_ratio, public_days)
            
            # Check if meets deletion criteria
            self._check_deletion_criteria(torrent, limits, result)
        
        # Save state after processing (for SQLite this is mostly a no-op)
        self.state.save()
        
        # Log summary
        self._log_classification_summary(result)
        
        return result
    
    def _get_torrent_limits(self, torrent: TorrentInfo, private_ratio: float, 
                           private_days: float, public_ratio: float, 
                           public_days: float) -> TorrentLimits:
        """Get applicable limits for a torrent."""
        if torrent.is_private:
            return TorrentLimits(ratio=private_ratio, days=private_days)
        else:
            return TorrentLimits(ratio=public_ratio, days=public_days)
    
    def _check_stalled_download(self, torrent: TorrentInfo, 
                               result: ClassificationResult) -> bool:
        """
        Check if torrent is a stalled download that should be deleted.
        
        Returns:
            True if handled as stalled download
        """
        if not self.config.behavior.cleanup_stale_downloads:
            return False
        
        if not torrent.is_stalled:
            return False
        
        # Get stalled duration
        stalled_days = self.state.get_stalled_duration_days(torrent.hash)
        
        # Get limit for this torrent type
        if torrent.is_private:
            max_days = self.config.behavior.max_stalled_private_days
        else:
            max_days = self.config.behavior.max_stalled_public_days
        
        if max_days <= 0 or stalled_days <= max_days:
            return False
        
        # Check FileFlows protection
        if self._is_protected_by_fileflows(torrent):
            logger.info(
                f"→ skipping stalled (FileFlows): {truncate_name(torrent.name)} "
                f"(priv={torrent.is_private}, stalled={stalled_days:.1f}/{max_days:.1f}d)"
            )
            result.protected_by_fileflows.append(torrent)
            return True
        
        # Mark for deletion
        candidate = DeletionCandidate(
            info=torrent,
            reason=DeletionReason.STALLED_TOO_LONG,
            limits=TorrentLimits(ratio=0, days=max_days),
            stalled_days=stalled_days
        )
        result.stalled.append(candidate)
        
        logger.info(
            f"→ delete stalled: {truncate_name(torrent.name)} "
            f"(priv={torrent.is_private}, stalled={stalled_days:.1f}/{max_days:.1f}d)"
        )
        
        return True
    
    def _check_deletion_criteria(self, torrent: TorrentInfo, limits: TorrentLimits,
                                result: ClassificationResult) -> None:
        """Check if torrent meets deletion criteria."""
        meets_ratio = torrent.ratio >= limits.ratio
        meets_time = torrent.seeding_time >= limits.seconds
        meets_criteria = meets_ratio or meets_time
        
        # Determine if we should check this torrent
        if torrent.is_private:
            paused_only = self.config.behavior.check_private_paused_only
            force_hours = self.config.behavior.force_delete_private_hours
        else:
            paused_only = self.config.behavior.check_public_paused_only
            force_hours = self.config.behavior.force_delete_public_hours
        
        # Skip if requires paused and not paused (unless force delete applies)
        if paused_only and not torrent.is_paused:
            if meets_criteria and force_hours > 0:
                self._check_force_delete(torrent, limits, force_hours, result)
            return
        
        # Check standard deletion
        if meets_criteria:
            # Check FileFlows protection
            if self._is_protected_by_fileflows(torrent):
                logger.info(
                    f"→ skipping (FileFlows): {truncate_name(torrent.name)} "
                    f"({self._format_limits_status(torrent, limits)})"
                )
                result.protected_by_fileflows.append(torrent)
                return
            
            # Determine reason
            if meets_ratio and meets_time:
                reason = DeletionReason.BOTH_LIMITS_EXCEEDED
            elif meets_ratio:
                reason = DeletionReason.RATIO_EXCEEDED
            else:
                reason = DeletionReason.TIME_EXCEEDED
            
            candidate = DeletionCandidate(
                info=torrent,
                reason=reason,
                limits=limits
            )
            result.to_delete.append(candidate)
            
            logger.info(
                f"→ delete: {truncate_name(torrent.name)} "
                f"({self._format_limits_status(torrent, limits)})"
            )
        elif torrent.is_paused:
            # Paused but not ready
            result.paused_not_ready.append(torrent)
    
    def _check_force_delete(self, torrent: TorrentInfo, limits: TorrentLimits,
                           force_hours: float, result: ClassificationResult) -> None:
        """Check if torrent qualifies for force deletion."""
        # Calculate excess time
        excess_hours = self._calculate_excess_time(torrent, limits)
        
        if excess_hours < force_hours:
            return
        
        # Check FileFlows protection
        if self._is_protected_by_fileflows(torrent):
            logger.info(
                f"→ skipping force delete (FileFlows): {truncate_name(torrent.name)} "
                f"({self._format_limits_status(torrent, limits)}, "
                f"excess={excess_hours:.1f}/{force_hours:.1f}h)"
            )
            result.protected_by_fileflows.append(torrent)
            return
        
        candidate = DeletionCandidate(
            info=torrent,
            reason=DeletionReason.FORCE_DELETE,
            limits=limits,
            excess_time_hours=excess_hours
        )
        result.to_delete.append(candidate)
        
        logger.info(
            f"→ force delete: {truncate_name(torrent.name)} "
            f"({self._format_limits_status(torrent, limits)}, "
            f"excess={excess_hours:.1f}/{force_hours:.1f}h)"
        )
    
    def _calculate_excess_time(self, torrent: TorrentInfo, limits: TorrentLimits) -> float:
        """Calculate how long torrent has exceeded limits (in hours)."""
        time_excess = 0.0
        ratio_excess = 0.0
        
        if torrent.seeding_time >= limits.seconds:
            time_excess = (torrent.seeding_time - limits.seconds) / SECONDS_PER_HOUR
        
        if torrent.ratio >= limits.ratio and limits.ratio > 0:
            # Estimate based on ratio overage
            ratio_overage = (torrent.ratio - limits.ratio) / limits.ratio
            ratio_excess = ratio_overage * limits.seconds / SECONDS_PER_HOUR
        
        return max(time_excess, ratio_excess)
    
    def _is_protected_by_fileflows(self, torrent: TorrentInfo) -> bool:
        """Check if torrent is protected by FileFlows processing."""
        if not self.fileflows or not self.fileflows.is_enabled:
            return False
        
        return self.fileflows.is_torrent_protected(torrent.files)
    
    def _format_limits_status(self, torrent: TorrentInfo, limits: TorrentLimits) -> str:
        """Format torrent status vs limits for logging."""
        parts = [
            f"priv={torrent.is_private}",
            f"state={torrent.state}",
            f"ratio={torrent.ratio:.2f}/{limits.ratio:.2f}",
            f"time={torrent.seeding_time/SECONDS_PER_DAY:.1f}/{limits.days:.1f}d"
        ]
        return ", ".join(parts)
    
    def _log_classification_summary(self, result: ClassificationResult) -> None:
        """Log classification summary."""
        if result.protected_by_fileflows:
            logger.info(f"{len(result.protected_by_fileflows)} torrents protected by FileFlows")
        
        if result.stalled:
            logger.info(f"{len(result.stalled)} stalled downloads found for deletion")
        
        if result.paused_not_ready:
            logger.info(f"{len(result.paused_not_ready)} paused torrents not yet at limits")