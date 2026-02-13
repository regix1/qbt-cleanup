#!/usr/bin/env python3
"""qBittorrent client wrapper with enhanced functionality."""

import logging
import os
import time
from typing import Optional, List, Any, Dict, Tuple
import qbittorrentapi
import urllib3

from .constants import (
    DEFAULT_TIMEOUT, MAX_RETRY_ATTEMPTS, RETRY_DELAY, TRACKER_STATUS_DISABLED
)
from .config import LimitsConfig, ConnectionConfig
from .models import TorrentInfo

# Suppress SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class QBittorrentClient:
    """Enhanced qBittorrent client wrapper."""

    def __init__(self, config: ConnectionConfig):
        """
        Initialize client wrapper.

        Args:
            config: Connection configuration
        """
        self.config = config
        self._client: Optional[qbittorrentapi.Client] = None
        self._quiet: bool = False
        self._privacy_method_logged = False
        self._privacy_cache: Dict[str, bool] = {}

    @property
    def client(self) -> qbittorrentapi.Client:
        """Get the underlying client, connecting if needed."""
        if self._client is None:
            raise RuntimeError("Client not connected")
        return self._client

    def connect(self, *, quiet: bool = False) -> bool:
        """
        Connect to qBittorrent.

        Args:
            quiet: If True, suppress connect/disconnect log messages (for API polling).

        Returns:
            True if connection successful
        """
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                self._client = qbittorrentapi.Client(
                    host=self.config.host,
                    port=self.config.port,
                    username=self.config.username,
                    password=self.config.password,
                    VERIFY_WEBUI_CERTIFICATE=self.config.verify_ssl,
                    REQUESTS_ARGS={'timeout': DEFAULT_TIMEOUT}
                )

                # Suppress SSL logging for connection
                original_level = logging.getLogger("urllib3.connectionpool").level
                logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

                try:
                    self._client.auth_log_in()
                finally:
                    # Restore original logging level
                    logging.getLogger("urllib3.connectionpool").setLevel(original_level)

                version = self._client.app.version
                api_version = self._client.app.web_api_version
                ssl_status = "enabled" if self.config.verify_ssl else "disabled"

                self._quiet = quiet
                if not quiet:
                    logger.info(
                        f"Connected to qBittorrent {version} "
                        f"(API: {api_version}, SSL: {ssl_status})"
                    )
                else:
                    logger.debug(
                        f"Connected to qBittorrent {version} "
                        f"(API: {api_version}, SSL: {ssl_status})"
                    )
                return True

            except (qbittorrentapi.LoginFailed, qbittorrentapi.APIConnectionError) as e:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    logger.error(f"Connection failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return False
                else:
                    # Only log if not SSL-related on first attempt
                    if attempt > 0 or "SSL" not in str(e):
                        logger.warning(f"Connection attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}")
                return False

        return False

    def disconnect(self) -> None:
        """Disconnect from qBittorrent."""
        if self._client:
            try:
                self._client.auth_log_out()
                if not getattr(self, '_quiet', False):
                    logger.info("Disconnected from qBittorrent")
                else:
                    logger.debug("Disconnected from qBittorrent")
            except Exception as e:
                logger.debug(f"Logout error (ignored): {e}")
            finally:
                self._client = None
                self._quiet = False
                self._privacy_cache.clear()

    def get_torrents(self) -> Optional[List[Any]]:
        """
        Get all torrents.

        Returns:
            List of torrent objects, or None on API failure
        """
        try:
            return self.client.torrents.info()
        except qbittorrentapi.APIConnectionError as e:
            logger.error(f"API connection error fetching torrents: {e}")
            return None
        except qbittorrentapi.Forbidden403Error as e:
            logger.error(f"Authentication error fetching torrents: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching torrents: {e}")
            return None

    def is_torrent_private(self, torrent: Any) -> bool:
        """
        Check if torrent is private.

        Args:
            torrent: Torrent object

        Returns:
            True if torrent is private
        """
        torrent_hash = torrent.hash

        # Check cache
        if torrent_hash in self._privacy_cache:
            return self._privacy_cache[torrent_hash]

        is_private = False

        # Try newer API field first (qBittorrent 5.0.0+)
        if hasattr(torrent, 'isPrivate') and torrent.isPrivate is not None:
            if not self._privacy_method_logged:
                log_fn = logger.debug if self._quiet else logger.info
                log_fn("Using qBittorrent 5.0.0+ isPrivate field")
                self._privacy_method_logged = True
            is_private = torrent.isPrivate
        else:
            # Fallback to tracker message checking
            if not self._privacy_method_logged:
                log_fn = logger.debug if self._quiet else logger.info
                log_fn("Using tracker message method for privacy detection")
                self._privacy_method_logged = True

            is_private = self._check_private_via_trackers(torrent_hash)

        self._privacy_cache[torrent_hash] = is_private
        return is_private

    def _check_private_via_trackers(self, torrent_hash: str) -> bool:
        """
        Check if torrent is private via tracker messages.

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if private tracker detected
        """
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                trackers = self.client.torrents.trackers(torrent_hash=torrent_hash)
                for tracker in trackers:
                    if tracker.status == TRACKER_STATUS_DISABLED and tracker.msg and "private" in tracker.msg.lower():
                        return True
                return False
            except Exception as e:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(f"Could not detect privacy for {torrent_hash}: {e}")
                    return False
                time.sleep(0.5)
        return False

    def get_torrent_files(self, torrent_hash: str) -> List[str]:
        """
        Get list of files in a torrent.

        Args:
            torrent_hash: Torrent hash

        Returns:
            List of file paths
        """
        try:
            files = self.client.torrents.files(torrent_hash=torrent_hash)
            return [f.name for f in files]
        except Exception as e:
            logger.warning(f"Could not get files for torrent {torrent_hash}: {e}")
            return []

    def _apply_limit_overrides(self, limit_name: str, global_value: float,
                               ignore_private: bool, ignore_public: bool,
                               env_private: str, env_public: str,
                               current_private: float, current_public: float) -> Tuple[float, float]:
        """
        Apply qBittorrent limit overrides if environment variables not set.

        Args:
            limit_name: Name of limit (for logging)
            global_value: Global value from qBittorrent
            ignore_private: Whether to ignore for private torrents
            ignore_public: Whether to ignore for public torrents
            env_private: Environment variable name for private
            env_public: Environment variable name for public
            current_private: Current private value
            current_public: Current public value

        Returns:
            Tuple of (private_value, public_value)
        """
        private_value = current_private
        public_value = current_public

        if not ignore_private and os.environ.get(env_private) is None:
            private_value = global_value
        if not ignore_public and os.environ.get(env_public) is None:
            public_value = global_value

        return private_value, public_value

    def get_qbt_limits(self, limits_config: LimitsConfig) -> Tuple[float, float, float, float]:
        """
        Get ratio and time limits from qBittorrent preferences.

        Args:
            limits_config: Limits configuration

        Returns:
            Tuple of (private_ratio, private_days, public_ratio, public_days)
        """
        try:
            prefs = self.client.app.preferences
        except Exception as e:
            logger.error(f"Failed to get preferences: {e}")
            return (
                limits_config.private_ratio,
                limits_config.private_days,
                limits_config.public_ratio,
                limits_config.public_days
            )

        private_ratio = limits_config.private_ratio
        private_days = limits_config.private_days
        public_ratio = limits_config.public_ratio
        public_days = limits_config.public_days

        # Handle ratio limits
        if prefs.get("max_ratio_enabled", False):
            global_ratio = prefs.get("max_ratio", limits_config.fallback_ratio)
            private_ratio, public_ratio = self._apply_limit_overrides(
                "ratio", global_ratio,
                limits_config.ignore_qbt_ratio_private,
                limits_config.ignore_qbt_ratio_public,
                "PRIVATE_RATIO", "PUBLIC_RATIO",
                private_ratio, public_ratio
            )
            logger.info(f"Using qBittorrent ratio limits: Private={private_ratio:.1f}, Public={public_ratio:.1f}")

        # Handle time limits
        if prefs.get("max_seeding_time_enabled", False):
            global_minutes = prefs.get("max_seeding_time", limits_config.fallback_days * 24 * 60)
            global_days = global_minutes / 60 / 24
            private_days, public_days = self._apply_limit_overrides(
                "time", global_days,
                limits_config.ignore_qbt_time_private,
                limits_config.ignore_qbt_time_public,
                "PRIVATE_DAYS", "PUBLIC_DAYS",
                private_days, public_days
            )
            logger.info(f"Using qBittorrent time limits: Private={private_days:.1f}d, Public={public_days:.1f}d")

        return private_ratio, private_days, public_ratio, public_days

    def delete_torrents(self, torrent_hashes: List[str], delete_files: bool = True) -> bool:
        """
        Delete torrents.

        Args:
            torrent_hashes: List of torrent hashes to delete
            delete_files: Whether to delete files

        Returns:
            True if successful
        """
        if not torrent_hashes:
            return True

        try:
            self.client.torrents.delete(
                delete_files=delete_files,
                torrent_hashes=torrent_hashes
            )
            return True
        except qbittorrentapi.APIConnectionError as e:
            logger.error(f"API connection error deleting torrents: {e}")
            return False
        except qbittorrentapi.Forbidden403Error as e:
            logger.error(f"Permission denied deleting torrents: {e}")
            return False
        except qbittorrentapi.Conflict409Error as e:
            logger.error(f"Conflict error deleting torrents: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting torrents: {e}")
            return False

    def process_torrent(self, torrent: Any, fetch_files: bool = False) -> TorrentInfo:
        """
        Process raw torrent into TorrentInfo.

        Args:
            torrent: Raw torrent object
            fetch_files: Whether to fetch the file list (only needed for FileFlows)

        Returns:
            Processed TorrentInfo
        """
        return TorrentInfo(
            torrent=torrent,
            hash=torrent.hash,
            name=torrent.name,
            is_private=self.is_torrent_private(torrent),
            state=torrent.state,
            ratio=torrent.ratio,
            seeding_time=max(0.0, float(torrent.seeding_time)),
            files=self.get_torrent_files(torrent.hash) if fetch_files else []
        )
