#!/usr/bin/env python3
"""Main cleanup orchestration logic."""

import logging
from typing import Optional

from config import Config
from client import QBittorrentClient
from state import StateManager
from fileflows import FileFlowsClient
from classifier import TorrentClassifier
from models import ClassificationResult
from utils import truncate_name

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
                    logger.info("FileFlows integration active")
                else:
                    logger.warning("FileFlows enabled but connection failed")
                    self.fileflows = None
            
            # Initialize classifier
            self.classifier = TorrentClassifier(self.config, self.state, self.fileflows)
            
            # Get torrents
            raw_torrents = self.client.get_torrents()
            if not raw_torrents:
                logger.info("No torrents found")
                return True
            
            logger.info(f"Processing {len(raw_torrents)} torrents")
            
            # Process torrents
            torrents = [self.client.process_torrent(t) for t in raw_torrents]
            
            # Log torrent breakdown
            private_count = sum(1 for t in torrents if t.is_private)
            public_count = len(torrents) - private_count
            logger.info(f"Breakdown: {private_count} private, {public_count} public")
            
            # Get limits
            limits = self.client.get_qbt_limits(self.config.limits)
            
            # Log active features
            self._log_active_features()
            
            # Classify torrents
            result = self.classifier.classify(torrents, limits)
            
            # Delete torrents
            return self._delete_torrents(result)
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}", exc_info=True)
            return False
        finally:
            self.client.disconnect()
    
    def _log_active_features(self) -> None:
        """Log active configuration features."""
        behavior = self.config.behavior
        
        # Force delete
        if behavior.force_delete_private_hours > 0 or behavior.force_delete_public_hours > 0:
            logger.info(
                f"Force delete: Private={behavior.force_delete_private_hours:.1f}h, "
                f"Public={behavior.force_delete_public_hours:.1f}h"
            )
        
        # Stalled cleanup
        if behavior.cleanup_stale_downloads:
            logger.info(
                f"Stalled cleanup: Private={behavior.max_stalled_private_days:.1f}d, "
                f"Public={behavior.max_stalled_public_days:.1f}d"
            )
        
        # Paused only
        if behavior.check_private_paused_only or behavior.check_public_paused_only:
            logger.info(
                f"Paused-only: Private={behavior.check_private_paused_only}, "
                f"Public={behavior.check_public_paused_only}"
            )
    
    def _delete_torrents(self, result: ClassificationResult) -> bool:
        """
        Delete torrents based on classification result.
        
        Args:
            result: Classification result
            
        Returns:
            True if successful
        """
        if result.total_deletions == 0:
            logger.info("No torrents matched deletion criteria")
            return True
        
        # Get statistics
        stats = result.get_deletion_stats()
        
        # Collect all hashes
        all_candidates = result.to_delete + result.stalled
        hashes = [c.info.hash for c in all_candidates]
        
        # Dry run check
        if self.config.behavior.dry_run:
            logger.info(f"DRY RUN: Would delete {len(hashes)} torrents:")
            self._log_deletion_stats(stats)
            
            # Log individual torrents in dry run
            for candidate in all_candidates:
                logger.info(f"  - {truncate_name(candidate.info.name, 50)}: {candidate.format_reason()}")
            
            return True
        
        # Perform deletion
        success = self.client.delete_torrents(hashes, self.config.behavior.delete_files)
        
        if success:
            files_msg = " (with files)" if self.config.behavior.delete_files else " (torrents only)"
            logger.info(f"Deleted {len(hashes)} torrents{files_msg}")
            self._log_deletion_stats(stats)
        else:
            logger.error("Failed to delete torrents")
        
        return success
    
    def _log_deletion_stats(self, stats: dict) -> None:
        """Log deletion statistics."""
        if stats["completed"] > 0:
            logger.info(
                f"  Completed: {stats['completed']} "
                f"({stats['private_completed']} private, {stats['public_completed']} public)"
            )
        
        if stats["stalled"] > 0:
            logger.info(
                f"  Stalled: {stats['stalled']} "
                f"({stats['private_stalled']} private, {stats['public_stalled']} public)"
            )