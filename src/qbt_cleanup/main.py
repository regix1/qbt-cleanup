#!/usr/bin/env python3
"""Main entry point for qBittorrent cleanup tool."""

import logging
import os
import signal
import socket
import sys
import threading
import time
from threading import Event
from datetime import datetime, timedelta

import uvicorn

from .config import Config
from .cleanup import QbtCleanup
from .config_overrides import ConfigOverrideManager
from .constants import SECONDS_PER_HOUR
from .api import create_app
from .api.app_state import AppState


def _get_display_host() -> str:
    """Get a meaningful display IP when bound to 0.0.0.0.

    Priority: WEB_DISPLAY_HOST env var > local routable IP > hostname lookup > fallback.
    """
    env_host = os.environ.get("WEB_DISPLAY_HOST")
    if env_host:
        return env_host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        return "127.0.0.1"


# Custom log formatter with colors and clean text
class PrettyFormatter(logging.Formatter):
    """Custom formatter with colors and clean text output."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m',     # Reset
        'BOLD': '\033[1m',      # Bold
        'DIM': '\033[2m',       # Dim
    }

    def __init__(self, use_colors=True):
        """Initialize formatter."""
        self.use_colors = use_colors and sys.stdout.isatty()
        super().__init__()

    def format(self, record):
        """Format log record with colors."""
        # Get color for level
        levelname = record.levelname
        color = self.COLORS.get(levelname, '')
        reset = self.COLORS['RESET'] if self.use_colors else ''

        # Format time
        time_str = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')

        # Build the formatted message
        if self.use_colors:
            # Colored output
            if levelname in ('ERROR', 'CRITICAL'):
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}[{levelname}]{reset} {record.getMessage()}"
            elif levelname == 'WARNING':
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}[WARN]{reset} {record.getMessage()}"
            elif levelname == 'INFO':
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {record.getMessage()}"
            else:
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} [{levelname}] {record.getMessage()}"
        else:
            # Plain output
            formatted = f"{time_str} [{levelname:5}] {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


# Configure logging with pretty formatter
def setup_logging(debug=False):
    """Set up logging with pretty formatting."""
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler with pretty formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(PrettyFormatter(use_colors=True))

    # Set levels
    if debug:
        root_logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)
        console_handler.setLevel(logging.INFO)
        # Suppress some noisy loggers
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('qbittorrentapi').setLevel(logging.WARNING)
        logging.getLogger('uvicorn').setLevel(logging.WARNING)

    root_logger.addHandler(console_handler)


# Global events for manual scan triggering
manual_scan_event = Event()
orphaned_scan_event = Event()


def signal_handler(signum, frame):
    """Handle manual scan trigger signal."""
    logger.info("Manual scan triggered via signal")
    manual_scan_event.set()


def print_banner():
    """Print a startup banner."""
    from . import __version__
    banner = f"""
================================================================
          qBittorrent Cleanup Tool v{__version__}
================================================================"""
    print(banner)


def run_cleanup_cycle(config: Config, force_orphaned: bool = False) -> bool:
    """
    Run a single cleanup cycle.

    Args:
        config: Application configuration
        force_orphaned: If True, bypass the orphaned scan schedule check.

    Returns:
        True if successful
    """
    try:
        logger.info("Starting cleanup cycle...")
        cleanup = QbtCleanup(config)
        result = cleanup.run(force_orphaned=force_orphaned)
        if result:
            logger.info("Cleanup cycle completed successfully")
        else:
            logger.warning("Cleanup cycle completed with issues")
        return result
    except Exception as e:
        logger.error(f"Cleanup cycle failed: {e}", exc_info=True)
        return False


# Set up module logger
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    # Set up pretty logging
    setup_logging(debug=False)

    # Print banner
    print_banner()

    # Load configuration
    config = Config.from_environment()

    # Create shared application state
    app_state = AppState(config, manual_scan_event, orphaned_scan_event)

    # Set up signal handler for manual scan (SIGUSR1 is Unix-only)
    if hasattr(signal, 'SIGUSR1'):
        signal.signal(signal.SIGUSR1, signal_handler)

    # Start web UI if enabled
    if config.web.enabled:
        app = create_app(app_state)
        web_thread = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={"host": config.web.host, "port": config.web.port, "log_level": "warning"},
            daemon=True,
        )
        web_thread.start()
        display_host = config.web.host
        if display_host == "0.0.0.0":
            display_host = _get_display_host()
        logger.info(f"Web UI started on http://{display_host}:{config.web.port}")

    # Log startup information
    if config.schedule.run_once:
        logger.info(f"Mode: Single run")
    else:
        logger.info(f"Mode: Scheduled (every {config.schedule.interval_hours}h)")
        logger.info(f"Manual trigger: docker kill --signal=SIGUSR1 qbt-cleanup")

    print("-" * 64)

    # Run once mode
    if config.schedule.run_once:
        app_state.set_running()
        success = run_cleanup_cycle(config)
        app_state.update_after_run(success)
        if success:
            logger.info("Exiting successfully")
        else:
            logger.error("Exiting with errors")
        sys.exit(0 if success else 1)

    # Scheduled mode
    while True:
        try:
            # Reload config from overrides at the start of each cycle
            config = ConfigOverrideManager.get_effective_config()
            app_state.update_config(config)

            # Check if an orphaned scan was manually requested
            force_orphaned = app_state.orphaned_scan_event.is_set()
            app_state.orphaned_scan_event.clear()

            # Run cleanup
            app_state.set_running()
            success = run_cleanup_cycle(config, force_orphaned=force_orphaned)
            app_state.update_after_run(success)

            # Calculate next run time
            next_run_seconds = config.schedule.interval_hours * SECONDS_PER_HOUR
            next_run_time = datetime.now() + timedelta(seconds=next_run_seconds)
            logger.info(f"Next run: {next_run_time.strftime('%H:%M:%S')} ({config.schedule.interval_hours}h)")
            print("-" * 64)

            # Wait for next run or manual trigger
            app_state.scan_event.clear()
            triggered = app_state.scan_event.wait(timeout=next_run_seconds)

            if triggered:
                logger.info("Manual scan requested")
                print("-" * 64)

        except KeyboardInterrupt:
            logger.info("Shutdown requested - goodbye")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)


if __name__ == "__main__":
    main()
