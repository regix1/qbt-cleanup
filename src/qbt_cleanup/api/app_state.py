#!/usr/bin/env python3
"""Thread-safe application state shared between the scheduler and API."""

import threading
from datetime import datetime
from typing import Optional

from ..config import Config


class AppState:
    """Thread-safe bridge between the scheduler loop and the web API.

    Holds the current configuration, scan trigger event, and last-run
    metadata so that API endpoints can read status and trigger scans
    without race conditions.
    """

    def __init__(
        self,
        config: Config,
        scan_event: threading.Event,
        orphaned_scan_event: threading.Event,
    ) -> None:
        self.config = config
        self.scan_event = scan_event
        self.orphaned_scan_event = orphaned_scan_event
        self.last_run_time: Optional[datetime] = None
        self.last_run_success: Optional[bool] = None
        self.last_run_stats: Optional[dict] = None
        self.scheduler_running: bool = False
        self.recycling_hashes: set[str] = set()
        self.restoring_items: set[str] = set()
        self.moving_hashes: set[str] = set()
        self._lock = threading.Lock()

    def update_after_run(self, success: bool, stats: Optional[dict] = None) -> None:
        """Record the result of a completed cleanup run.

        Args:
            success: Whether the run completed without errors.
            stats: Optional dictionary of run statistics.
        """
        with self._lock:
            self.last_run_time = datetime.now()
            self.last_run_success = success
            self.last_run_stats = stats
            self.scheduler_running = False

    def set_running(self) -> None:
        """Mark the scheduler as currently executing a cleanup run."""
        with self._lock:
            self.scheduler_running = True

    def update_config(self, config: Config) -> None:
        """Replace the current configuration.

        Args:
            config: The new Config instance to use.
        """
        with self._lock:
            self.config = config

    def get_status(self) -> dict:
        """Return a snapshot of the current run status.

        Returns:
            Dictionary with last_run_time, last_run_success,
            last_run_stats, and scheduler_running.
        """
        with self._lock:
            return {
                "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
                "last_run_success": self.last_run_success,
                "last_run_stats": self.last_run_stats,
                "scheduler_running": self.scheduler_running,
            }

    def add_recycling(self, torrent_hash: str) -> None:
        """Mark a torrent as currently being recycled."""
        with self._lock:
            self.recycling_hashes.add(torrent_hash)

    def remove_recycling(self, torrent_hash: str) -> None:
        """Unmark a torrent from being recycled."""
        with self._lock:
            self.recycling_hashes.discard(torrent_hash)

    def get_recycling_hashes(self) -> set[str]:
        """Return a snapshot of currently recycling torrent hashes."""
        with self._lock:
            return set(self.recycling_hashes)

    def add_restoring(self, item_name: str) -> None:
        """Mark a recycle bin item as currently being restored."""
        with self._lock:
            self.restoring_items.add(item_name)

    def remove_restoring(self, item_name: str) -> None:
        """Unmark a recycle bin item from being restored."""
        with self._lock:
            self.restoring_items.discard(item_name)

    def get_restoring_items(self) -> set[str]:
        """Return a snapshot of currently restoring item names."""
        with self._lock:
            return set(self.restoring_items)

    def add_moving(self, torrent_hash: str) -> None:
        """Mark a torrent as currently being moved."""
        with self._lock:
            self.moving_hashes.add(torrent_hash)

    def remove_moving(self, torrent_hash: str) -> None:
        """Unmark a torrent from being moved."""
        with self._lock:
            self.moving_hashes.discard(torrent_hash)

    def get_moving_hashes(self) -> set[str]:
        """Return a snapshot of currently moving torrent hashes."""
        with self._lock:
            return set(self.moving_hashes)
