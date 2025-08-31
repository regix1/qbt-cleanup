#!/usr/bin/env python3
"""Main entry point for qBittorrent cleanup tool."""

import logging
import signal
import sys
import time
from threading import Event
from datetime import datetime, timedelta

from .config import Config
from .cleanup import QbtCleanup
from .constants import SECONDS_PER_HOUR

# Custom log formatter with colors and symbols
class PrettyFormatter(logging.Formatter):
    """Custom formatter with colors and symbols for prettier output."""
    
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
    
    # Log level symbols
    SYMBOLS = {
        'DEBUG': '🔍',
        'INFO': '✔',
        'WARNING': '⚠',
        'ERROR': '✗',
        'CRITICAL': '💀',
    }
    
    def __init__(self, use_colors=True, use_symbols=True):
        """Initialize formatter."""
        self.use_colors = use_colors and sys.stdout.isatty()
        self.use_symbols = use_symbols
        super().__init__()
    
    def format(self, record):
        """Format log record with colors and symbols."""
        # Get color and symbol for level
        levelname = record.levelname
        color = self.COLORS.get(levelname, '')
        reset = self.COLORS['RESET'] if self.use_colors else ''
        symbol = self.SYMBOLS.get(levelname, '•') if self.use_symbols else ''
        
        # Format time
        time_str = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        
        # Build the formatted message
        if self.use_colors:
            # Colored output
            if levelname in ('ERROR', 'CRITICAL'):
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}{symbol} {levelname:8}{reset} {record.getMessage()}"
            elif levelname == 'WARNING':
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}{symbol} {levelname:8}{reset} {record.getMessage()}"
            elif record.name == '__main__':
                # Main module messages in bold
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}{symbol}{reset} {self.COLORS['BOLD']}{record.getMessage()}{reset}"
            else:
                formatted = f"{self.COLORS['DIM']}{time_str}{reset} {color}{symbol}{reset} {record.getMessage()}"
        else:
            # Plain output
            formatted = f"{time_str} {symbol} {levelname:8} {record.getMessage()}"
        
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
    console_handler.setFormatter(PrettyFormatter(use_colors=True, use_symbols=True))
    
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
    
    root_logger.addHandler(console_handler)


# Global event for manual scan triggering
manual_scan_event = Event()


def signal_handler(signum, frame):
    """Handle manual scan trigger signal."""
    logger.info("Manual scan triggered via signal")
    manual_scan_event.set()


def print_banner():
    """Print a nice startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════╗
║          🧹 qBittorrent Cleanup Tool v2.1 🧹            ║
╚══════════════════════════════════════════════════════════╝"""
    print(banner)


def run_cleanup_cycle(config: Config) -> bool:
    """
    Run a single cleanup cycle.
    
    Args:
        config: Application configuration
        
    Returns:
        True if successful
    """
    try:
        logger.info("Starting cleanup cycle...")
        cleanup = QbtCleanup(config)
        result = cleanup.run()
        if result:
            logger.info("Cleanup cycle completed successfully 🎉")
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
    
    # Set up signal handler for manual scan
    signal.signal(signal.SIGUSR1, signal_handler)
    
    # Log startup information
    if config.schedule.run_once:
        logger.info(f"Mode: Single run")
    else:
        logger.info(f"Mode: Scheduled (every {config.schedule.interval_hours}h)")
        logger.info(f"Manual trigger: docker kill --signal=SIGUSR1 qbt-cleanup")
    
    print("─" * 60)
    
    # Run once mode
    if config.schedule.run_once:
        success = run_cleanup_cycle(config)
        if success:
            logger.info("Exiting successfully")
        else:
            logger.error("Exiting with errors")
        sys.exit(0 if success else 1)
    
    # Scheduled mode
    while True:
        try:
            # Run cleanup
            run_cleanup_cycle(config)
            
            # Calculate next run time
            next_run_seconds = config.schedule.interval_hours * SECONDS_PER_HOUR
            next_run_time = datetime.now() + timedelta(seconds=next_run_seconds)
            logger.info(f"Next run: {next_run_time.strftime('%H:%M:%S')} ({config.schedule.interval_hours}h)")
            print("─" * 60)
            
            # Wait for next run or manual trigger
            manual_scan_event.clear()
            triggered = manual_scan_event.wait(timeout=next_run_seconds)
            
            if triggered:
                logger.info("Manual scan requested 🚀")
                print("─" * 60)
            
        except KeyboardInterrupt:
            logger.info("Shutdown requested - goodbye! 👋")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            logger.info("Retrying in 60 seconds...")
            time.sleep(60)


if __name__ == "__main__":
    main()