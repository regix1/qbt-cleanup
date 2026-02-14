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
from .notifier import Notifier, CleanupSummary

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

        # Initialize notifier
        notify_config = config.notifications
        self.notifier = Notifier(
            enabled=notify_config.enabled,
            urls=notify_config.urls,
            on_delete=notify_config.on_delete,
            on_error=notify_config.on_error,
            on_orphaned=notify_config.on_orphaned,
        )
    
    def run(self, force_orphaned: bool = False) -> bool:
        """
        Run cleanup process.

        Args:
            force_orphaned: If True, bypass the orphaned scan schedule check.

        Returns:
            True if successful
        """
        # Create summary tracker
        summary = CleanupSummary()

        try:
            # Connect to qBittorrent
            if not self.client.connect():
                return False
            
            # Test FileFlows connection and build initial cache
            if self.fileflows and self.fileflows.is_enabled:
                if not self.fileflows.test_connection():
                    logger.warning("[FileFlows] Connection failed")
                    self.fileflows = None
            
            # Initialize classifier
            self.classifier = TorrentClassifier(self.config, self.state, self.fileflows)

            # Initialize orphaned scanner if enabled
            if self.config.orphaned.enabled:
                self.orphaned_scanner = OrphanedFilesScanner(self.client)

            # Get torrents
            raw_torrents = self.client.get_torrents()
            if raw_torrents is None:
                logger.error("Failed to fetch torrents from qBittorrent")
                return False
            if not raw_torrents:
                logger.info("No torrents found")
                return True

            logger.info(f"Found {len(raw_torrents)} torrents")

            # Process torrents (only fetch file lists when FileFlows needs them)
            fetch_files = self.fileflows is not None
            torrents = [self.client.process_torrent(t, fetch_files=fetch_files) for t in raw_torrents]

            # Log torrent breakdown
            private_count = sum(1 for t in torrents if t.is_private)
            public_count = len(torrents) - private_count
            logger.info(f"Private: {private_count} | Public: {public_count}")

            # Get limits
            limits = self.client.get_qbt_limits(self.config.limits)

            # Log active features
            self._log_active_features()

            # Check for unregistered torrents
            unregistered_hashes: list[str] = []
            if self.config.behavior.cleanup_unregistered:
                unregistered_hashes = self._check_unregistered_torrents(torrents, summary)

            # Classify torrents
            result = self.classifier.classify(torrents, limits)

            # Recheck paused torrents with errors
            if self.config.behavior.recheck_paused:
                self._recheck_paused_torrents(torrents, summary)

            # Delete torrents
            deletion_success = self._delete_torrents(result)

            # Update summary with deletion stats
            if result.total_deletions > 0:
                stats = result.get_deletion_stats()
                summary.total_checked = len(torrents)
                summary.total_deleted = stats["total"]
                summary.private_deleted = stats["private_completed"] + stats["private_stalled"]
                summary.public_deleted = stats["public_completed"] + stats["public_stalled"]
                summary.stalled_deleted = stats["stalled"]
            else:
                summary.total_checked = len(torrents)

            # Run orphaned file cleanup if enabled
            orphaned_success = self._cleanup_orphaned_files(force=force_orphaned, summary=summary)

            # Purge expired recycle bin entries
            if self.config.recycle_bin.enabled:
                self._purge_recycle_bin()

            # Send notification
            self.notifier.notify_scan_complete(summary)

            return deletion_success and orphaned_success
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            self.notifier.notify_error(str(e))
            return False
        finally:
            self.client.disconnect()
            self.state.close()
    
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

        # Unregistered cleanup
        if behavior.cleanup_unregistered:
            features.append(f"Unregistered cleanup: {behavior.unregistered_grace_hours:.0f}h grace")

        # Recheck paused
        if behavior.recheck_paused:
            features.append("Recheck paused")

        # Notifications
        if self.config.notifications.enabled:
            features.append("Notifications")

        # Recycle bin
        if self.config.recycle_bin.enabled:
            features.append(f"Recycle bin: {self.config.recycle_bin.purge_after_days}d retention")

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

        # Move files to recycle bin if enabled
        if self.config.recycle_bin.enabled and self.config.behavior.delete_files:
            self._move_to_recycle_bin(all_candidates)

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

        if stats.get("unregistered", 0) > 0:
            parts.append(f"Unregistered: {stats['unregistered']}")

        if parts:
            logger.info(f"  -> {' | '.join(parts)}")

    def _cleanup_orphaned_files(self, force: bool = False, summary: Optional[CleanupSummary] = None) -> bool:
        """
        Run orphaned file cleanup if enabled and scheduled.

        Args:
            force: If True, bypass the schedule check (for manual triggers).
            summary: Optional cleanup summary to update with results.

        Returns:
            True if successful or disabled
        """
        if not self.config.orphaned.enabled:
            return True

        if not self.orphaned_scanner:
            logger.warning("Orphaned file scanner not initialized")
            return True

        from datetime import datetime, timezone

        # Check if enough time has passed since last run (skip check when forced)
        if not force:
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
        else:
            logger.info("[Orphaned Files] Manual scan requested - bypassing schedule check")

        try:
            logger.info(
                f"[Orphaned Files] Starting cleanup "
                f"(runs every {self.config.orphaned.schedule_days} days)"
            )

            files_removed, dirs_removed = self.orphaned_scanner.cleanup_orphaned_files(
                self.config.orphaned.scan_dirs,
                self.config.orphaned.min_age_hours,
                self.config.behavior.dry_run,
                log_dir="/config",
                exclude_patterns=self.config.orphaned.exclude_patterns,
            )

            if summary is not None:
                summary.orphaned_files_removed = files_removed
                summary.orphaned_dirs_removed = dirs_removed

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

    def _check_unregistered_torrents(self, torrents: list, summary: CleanupSummary) -> list[str]:
        """Check for and handle unregistered torrents.

        Args:
            torrents: List of TorrentInfo objects
            summary: Cleanup summary to update

        Returns:
            List of unregistered torrent hashes that were deleted
        """
        from .constants import DeletionReason
        from .utils import truncate_name

        grace_hours = self.config.behavior.unregistered_grace_hours
        deleted_hashes: list[str] = []

        logger.info(f"[Unregistered] Checking torrents (grace period: {grace_hours:.0f}h)")

        for torrent in torrents:
            if self.state.is_blacklisted(torrent.hash):
                continue

            if not self.client.is_torrent_unregistered(torrent.hash):
                # Torrent is fine - clear any previous unregistered state
                self.state.clear_unregistered(torrent.hash)
                continue

            # Mark as unregistered (first time) or get existing duration
            self.state.mark_unregistered(torrent.hash)
            hours = self.state.get_unregistered_hours(torrent.hash)

            if hours is None:
                continue

            if hours < grace_hours:
                logger.info(
                    f"[Unregistered] {truncate_name(torrent.name, 40)} "
                    f"- seen for {hours:.1f}h (grace: {grace_hours:.0f}h)"
                )
                continue

            # Grace period exceeded - delete
            if self.config.behavior.dry_run:
                logger.info(
                    f"[DRY RUN] Would delete unregistered: "
                    f"{truncate_name(torrent.name, 40)} ({hours:.1f}h)"
                )
            else:
                logger.info(
                    f"[Unregistered] Deleting: {truncate_name(torrent.name, 40)} "
                    f"(unregistered for {hours:.1f}h)"
                )
                success = self.client.delete_torrents(
                    [torrent.hash], self.config.behavior.delete_files
                )
                if success:
                    deleted_hashes.append(torrent.hash)

        if deleted_hashes:
            summary.unregistered_deleted = len(deleted_hashes)
            logger.info(f"[Unregistered] Deleted {len(deleted_hashes)} torrent(s)")

        # Clean up state for torrents that no longer exist
        current_hashes = [t.hash for t in torrents]
        self.state.cleanup_unregistered(current_hashes)

        return deleted_hashes

    def _recheck_paused_torrents(self, torrents: list, summary: CleanupSummary) -> None:
        """Recheck paused torrents with errors and resume if complete.

        Sorts by smallest first to prioritize quick rechecks.

        Args:
            torrents: List of TorrentInfo objects
            summary: Cleanup summary to update
        """
        from .constants import TorrentState
        from .utils import truncate_name

        # Find paused torrents with error states
        error_states = {TorrentState.PAUSED_DL.value}
        paused_with_errors = [
            t for t in torrents
            if t.state in error_states and hasattr(t.torrent, 'size') and t.torrent.size > 0
        ]

        if not paused_with_errors:
            return

        # Sort by size (smallest first)
        paused_with_errors.sort(key=lambda t: t.torrent.size)

        logger.info(f"[Recheck] Found {len(paused_with_errors)} paused torrent(s) to recheck")

        if self.config.behavior.dry_run:
            for torrent in paused_with_errors[:5]:
                size_mb = torrent.torrent.size / (1024 * 1024)
                logger.info(
                    f"[DRY RUN] Would recheck: {truncate_name(torrent.name, 40)} "
                    f"({size_mb:.0f} MB)"
                )
            if len(paused_with_errors) > 5:
                logger.info(f"  ... and {len(paused_with_errors) - 5} more")
            return

        hashes = [t.hash for t in paused_with_errors]
        if self.client.recheck_torrents(hashes):
            summary.rechecked_torrents = len(hashes)
            logger.info(f"[Recheck] Initiated recheck for {len(hashes)} torrent(s)")

    def _purge_recycle_bin(self) -> None:
        """Purge expired files from the recycle bin."""
        import shutil
        from pathlib import Path

        recycle_path = Path(self.config.recycle_bin.path)
        if not recycle_path.exists():
            return

        purge_days = self.config.recycle_bin.purge_after_days
        import time
        current_time = time.time()
        purge_seconds = purge_days * 86400
        purged_count = 0

        try:
            for item in recycle_path.iterdir():
                try:
                    mtime = item.stat().st_mtime
                    age_seconds = current_time - mtime

                    if age_seconds >= purge_seconds:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                        purged_count += 1
                except OSError as e:
                    logger.warning(f"[Recycle Bin] Error purging {item}: {e}")

            if purged_count > 0:
                logger.info(f"[Recycle Bin] Purged {purged_count} expired item(s)")
        except Exception as e:
            logger.error(f"[Recycle Bin] Purge failed: {e}")

    def _move_to_recycle_bin(self, candidates: list) -> None:
        """Move torrent files to the recycle bin before deletion.

        Args:
            candidates: List of DeletionCandidate objects
        """
        import os
        from pathlib import Path
        from datetime import datetime
        from .resilient_move import resilient_move, write_move_metadata

        recycle_path = Path(self.config.recycle_bin.path)
        staging_path = recycle_path / ".staging"
        staging_path.mkdir(parents=True, exist_ok=True)

        for candidate in candidates:
            torrent = candidate.info.torrent
            save_path = getattr(torrent, 'content_path', None) or getattr(torrent, 'save_path', None)

            if not save_path:
                continue

            source = Path(save_path)
            if not source.exists():
                continue

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in candidate.info.name[:50])
            item_name = f"{timestamp}_{safe_name}"
            staging_dest = staging_path / item_name
            final_dest = recycle_path / item_name

            result = resilient_move(source, staging_dest, remove_source=False)
            if result.success:
                if result.partial:
                    logger.warning(
                        f"[Recycle Bin] Partial save: {result.files_copied}/{result.files_copied + result.files_failed} "
                        f"files for {candidate.info.name}"
                    )
                try:
                    os.rename(str(staging_dest), str(final_dest))
                    logger.debug(f"[Recycle Bin] Saved: {candidate.info.name}")
                    write_move_metadata(recycle_path, item_name, str(source.parent), result)
                except OSError as e:
                    logger.warning(f"[Recycle Bin] Failed to move from staging: {e}")
            else:
                logger.warning(f"[Recycle Bin] Failed to save {candidate.info.name}")
                shutil.rmtree(str(staging_dest), ignore_errors=True)