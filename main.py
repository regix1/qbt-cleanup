#!/usr/bin/env python3
"""Main entry point for qBittorrent cleanup tool."""

import logging
import signal
import sys
import time
from threading import Event

from config import Config
from cleanup import QbtCleanup
from constants import SECONDS_PER_HOUR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Global event for manual scan triggering
manual_scan_event = Event()


def signal_handler(signum, frame):
    """Handle manual scan trigger signal."""
    logger.info("Manual scan triggered via signal")
    manual_scan_event.set()


def run_cleanup_cycle(config: Config) -> bool:
    """
    Run a single cleanup cycle.
    
    Args:
        config: Application configuration
        
    Returns:
        True if successful
    """
    try:
        cleanup = QbtCleanup(config)
        return cleanup.run()
    except Exception as e:
        logger.error(f"Unexpected error in cleanup cycle: {e}", exc_info=True)
        return False


def main():
    """Main entry point."""
    # Load configuration
    config = Config.from_environment()
    
    # Set up signal handler for manual scan
    signal.signal(signal.SIGUSR1, signal_handler)
    
    # Log startup information
    logger.info("=" * 60)
    logger.info("qBittorrent Cleanup Tool Started")
    logger.info("=" * 60)
    
    if config.schedule.run_once:
        logger.info("Mode: Run once and exit")
    else:
        logger.info(f"Mode: Run every {config.schedule.interval_hours} hours")
        logger.info("Tip: Send SIGUSR1 to trigger manual scan")
        logger.info("     docker kill --signal=SIGUSR1 qbt-cleanup")
    
    logger.info("-" * 60)
    
    # Run once mode
    if config.schedule.run_once:
        success = run_cleanup_cycle(config)
        sys.exit(0 if success else 1)
    
    # Scheduled mode
    while True:
        try:
            # Run cleanup
            run_cleanup_cycle(config)
            
            # Calculate next run time
            next_run_seconds = config.schedule.interval_hours * SECONDS_PER_HOUR
            logger.info(f"Next scheduled run in {config.schedule.interval_hours} hours")
            logger.info("-" * 60)
            
            # Wait for next run or manual trigger
            manual_scan_event.clear()
            triggered = manual_scan_event.wait(timeout=next_run_seconds)
            
            if triggered:
                logger.info("Starting manual scan...")
                logger.info("-" * 60)
            
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            logger.info("Waiting 60 seconds before retry...")
            time.sleep(60)


if __name__ == "__main__":
    main()