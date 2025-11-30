#!/usr/bin/env python3
"""Main cleanup orchestration logic."""

import logging
from typing import Optional

from .config import Config
from .client import QBittorrentClient
from .state import StateManager
from .fileflows import FileFlowsClient
from .classifier import TorrentClassifier
from .orphaned_scanner import OrphanedFilesScanner
from .models import ClassificationResult
from .utils import truncate_name

logger = logging.getLogger(__name__)


class QbtCleanup:
    """Main cleanup orchestration class."""
    
    def __init__(self, config: Config):
        """
        Initialize cleanup orchestrator.

        Args:
            config: Application configuration
        """
        self.config = config
        self.client = QBittorrentClient(config.connection)
        self.state = StateManager()
        self.fileflows: Optional[FileFlowsClient] = None
        self.classifier: Optional[TorrentClassifier] = None
        self.orphaned_scanner: Optional[OrphanedFilesScanner] = None

        # Initialize FileFlows if enabled
        if config.fileflows.enabled:
            self.fileflows = FileFlowsClient(config.fileflows)
    
    def run(self) -> bool:
        """
        Run cleanup process.
        
        Returns:
            True if successful
        """
        try:
            # Connect to qBittorrent
            if not self.client.connect():
                return False
            
            # Test FileFlows connection if enabled
            if self.fileflows and self.fileflows.is_enabled:
                if self.fileflows.test_connection():
                    logger.info("[FileFlows] Connected")
                else:
                    logger.warning("[FileFlows] Connection failed")
                    self.fileflows = None
            
            # Initialize classifier
            self.classifier = TorrentClassifier(self.config, self.state, self.fileflows)

            # Initialize orphaned scanner if enabled
            if self.config.orphaned.enabled:
                self.orphaned_scanner = OrphanedFilesScanner(self.client)

            # Get torrents
            raw_torrents = self.client.get_torrents()
            if not raw_torrents:
                logger.info("No torrents found")
                return True

            logger.info(f"Found {len(raw_torrents)} torrents")

            # Process torrents
            torrents = [self.client.process_torrent(t) for t in raw_torrents]

            # Log torrent breakdown
            private_count = sum(1 for t in torrents if t.is_private)
            public_count = len(torrents) - private_count
            logger.info(f"Private: {private_count} | Public: {public_count}")

            # Get limits
            limits = self.client.get_qbt_limits(self.config.limits)

            # Log active features
            self._log_active_features()

            # Classify torrents
            result = self.classifier.classify(torrents, limits)

            # Delete torrents
            deletion_success = self._delete_torrents(result)

            # Run orphaned file cleanup if enabled
            orphaned_success = self._cleanup_orphaned_files()

            return deletion_success and orphaned_success
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            return False
        finally:
            self.client.disconnect()
    
    def _log_active_features(self) -> None:
        """Log active configuration features."""
        behavior = self.config.behavior

        features = []

        # Force delete
        if behavior.force_delete_private_hours > 0 or behavior.force_delete_public_hours > 0:
            features.append(f"Force delete: {behavior.force_delete_private_hours:.0f}h/{behavior.force_delete_public_hours:.0f}h")

        # Stalled cleanup
        if behavior.cleanup_stale_downloads:
            features.append(f"Stalled cleanup: {behavior.max_stalled_private_days:.0f}d/{behavior.max_stalled_public_days:.0f}d")

        # Paused only
        if behavior.check_private_paused_only or behavior.check_public_paused_only:
            paused_status = []
            if behavior.check_private_paused_only:
                paused_status.append("Private")
            if behavior.check_public_paused_only:
                paused_status.append("Public")
            features.append(f"Paused-only: {', '.join(paused_status)}")

        # Orphaned file cleanup
        if self.config.orphaned.enabled:
            features.append(f"Orphaned files: {len(self.config.orphaned.scan_dirs)} dirs")

        if features:
            logger.info(f"[Config] {' | '.join(features)}")

        # Log orphaned scan directories
        if self.config.orphaned.enabled and self.config.orphaned.scan_dirs:
            for scan_dir in self.config.orphaned.scan_dirs:
                logger.info(f"  -> Orphaned scan dir: {scan_dir}")
    
    def _delete_torrents(self, result: ClassificationResult) -> bool:
        """
        Delete torrents based on classification result.
        
        Args:
            result: Classification result
            
        Returns:
            True if successful
        """
        if result.total_deletions == 0:
            logger.info("No torrents need cleanup")
            return True
        
        # Get statistics
        stats = result.get_deletion_stats()
        
        # Collect all hashes
        all_candidates = result.to_delete + result.stalled
        hashes = [c.info.hash for c in all_candidates]
        
        # Dry run check
        if self.config.behavior.dry_run:
            logger.info(f"[DRY RUN] Would delete {len(hashes)} torrents")
            self._log_deletion_stats(stats)
            
            # Log sample torrents in dry run
            for i, candidate in enumerate(all_candidates[:5]):
                logger.info(f"  {i+1}. {truncate_name(candidate.info.name, 40)}")
            if len(all_candidates) > 5:
                logger.info(f"  ... and {len(all_candidates) - 5} more")
            
            return True
        
        # Perform deletion
        success = self.client.delete_torrents(hashes, self.config.behavior.delete_files)
        
        if success:
            action = "Deleted (with files)" if self.config.behavior.delete_files else "Removed (torrent only)"
            logger.info(f"[{action}] {len(hashes)} torrents")
            self._log_deletion_stats(stats)
        else:
            logger.error("Failed to delete torrents")
        
        return success
    
    def _log_deletion_stats(self, stats: dict) -> None:
        """Log deletion statistics."""
        parts = []

        if stats["completed"] > 0:
            parts.append(f"Completed: {stats['completed']}")

        if stats["stalled"] > 0:
            parts.append(f"Stalled: {stats['stalled']}")

        if parts:
            logger.info(f"  -> {' | '.join(parts)}")

    def _cleanup_orphaned_files(self) -> bool:
        """
        Run orphaned file cleanup if enabled and scheduled.

        Returns:
            True if successful or disabled
        """
        if not self.config.orphaned.enabled:
            return True

        if not self.orphaned_scanner:
            logger.warning("Orphaned file scanner not initialized")
            return True

        # Check if enough time has passed since last run
        from datetime import datetime, timezone, timedelta

        last_run_str = self.state.get_metadata("last_orphaned_cleanup")
        if last_run_str:
            try:
                last_run = datetime.fromisoformat(last_run_str)
                now = datetime.now(timezone.utc)
                days_since_last_run = (now - last_run).total_seconds() / 86400

                if days_since_last_run < self.config.orphaned.schedule_days:
                    logger.info(
                        f"[Orphaned Files] Skipping - last run was {days_since_last_run:.1f} days ago "
                        f"(schedule: every {self.config.orphaned.schedule_days} days)"
                    )
                    return True
            except Exception as e:
                logger.warning(f"Could not parse last orphaned cleanup time: {e}")

        try:
            logger.info(
                f"[Orphaned Files] Starting cleanup "
                f"(runs every {self.config.orphaned.schedule_days} days)"
            )

            files_removed, dirs_removed = self.orphaned_scanner.cleanup_orphaned_files(
                self.config.orphaned.scan_dirs,
                self.config.orphaned.min_age_hours,
                self.config.behavior.dry_run,
                log_dir="/config"
            )

            if files_removed > 0 or dirs_removed > 0:
                logger.info(
                    f"[Orphaned Files] Removed {files_removed} files "
                    f"and {dirs_removed} directories"
                )
            else:
                logger.info("[Orphaned Files] No orphaned files found")

            # Update last run time
            now = datetime.now(timezone.utc).isoformat()
            self.state.set_metadata("last_orphaned_cleanup", now)

            return True

        except Exception as e:
            logger.error(f"Orphaned file cleanup failed: {e}", exc_info=True)
            return False