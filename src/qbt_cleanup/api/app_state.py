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

    def __init__(self, config: Config, scan_event: threading.Event) -> None:
        self.config = config
        self.scan_event = scan_event
        self.last_run_time: Optional[datetime] = None
        self.last_run_success: Optional[bool] = None
        self.last_run_stats: Optional[dict] = None
        self.scheduler_running: bool = False
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
