#!/usr/bin/env python3
"""qBittorrent Cleanup Tool - Intelligent torrent management."""

__version__ = "2.1.0"
__author__ = "Regix"
__license__ = "MIT"

from .cleanup import QbtCleanup
from .config import Config

__all__ = ["QbtCleanup", "Config", "__version__"]