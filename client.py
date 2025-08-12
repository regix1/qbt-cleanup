#!/usr/bin/env python3
"""qBittorrent client wrapper with enhanced functionality."""

import logging
import time
from typing import Optional, List, Any, Dict, Tuple
import qbittorrentapi
import os
from constants import DEFAULT_TIMEOUT, MAX_RETRY_ATTEMPTS, RETRY_DELAY
from config import ConnectionConfig, LimitsConfig
from models import TorrentInfo

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
        self._privacy_method_logged = False
        self._privacy_cache: Dict[str, bool] = {}
    
    @property
    def client(self) -> qbittorrentapi.Client:
        """Get the underlying client, connecting if needed."""
        if self._client is None:
            raise RuntimeError("Client not connected")
        return self._client
    
    def connect(self) -> bool:
        """
        Connect to qBittorrent.
        
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
                
                self._client.auth_log_in()
                
                version = self._client.app.version
                api_version = self._client.app.web_api_version
                ssl_status = "enabled" if self.config.verify_ssl else "disabled"
                
                logger.info(
                    f"Connected to qBittorrent {version} "
                    f"(API: {api_version}, SSL: {ssl_status})"
                )
                return True
                
            except (qbittorrentapi.LoginFailed, qbittorrentapi.APIConnectionError) as e:
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    logger.error(f"Connection failed after {MAX_RETRY_ATTEMPTS} attempts: {e}")
                    return False
                else:
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
                logger.info("Disconnected from qBittorrent")
            except Exception:
                pass  # Ignore logout errors
            finally:
                self._client = None
                self._privacy_cache.clear()
    
    def get_torrents(self) -> List[Any]:
        """
        Get all torrents.
        
        Returns:
            List of torrent objects
        """
        try:
            return self.client.torrents.info()
        except Exception as e:
            logger.error(f"Failed to fetch torrents: {e}")
            return []
    
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
                logger.info("Using qBittorrent 5.0.0+ isPrivate field")
                self._privacy_method_logged = True
            is_private = torrent.isPrivate
        else:
            # Fallback to tracker message checking
            if not self._privacy_method_logged:
                logger.info("Using tracker message method for privacy detection")
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
                    if tracker.status == 0 and tracker.msg and "private" in tracker.msg.lower():
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
            
            if not limits_config.ignore_qbt_ratio_private and os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio
            if not limits_config.ignore_qbt_ratio_public and os.environ.get("NONPRIVATE_RATIO") is None:
                public_ratio = global_ratio
            
            logger.info(f"Using qBittorrent ratio limits: Private={private_ratio:.1f}, Public={public_ratio:.1f}")
        
        # Handle time limits
        if prefs.get("max_seeding_time_enabled", False):
            global_minutes = prefs.get("max_seeding_time", limits_config.fallback_days * 24 * 60)
            global_days = global_minutes / 60 / 24
            
            if not limits_config.ignore_qbt_time_private and os.environ.get("PRIVATE_DAYS") is None:
                private_days = global_days
            if not limits_config.ignore_qbt_time_public and os.environ.get("NONPRIVATE_DAYS") is None:
                public_days = global_days
            
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
        except Exception as e:
            logger.error(f"Failed to delete torrents: {e}")
            return False
    
    def process_torrent(self, torrent: Any) -> TorrentInfo:
        """
        Process raw torrent into TorrentInfo.
        
        Args:
            torrent: Raw torrent object
            
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
            seeding_time=torrent.seeding_time,
            files=self.get_torrent_files(torrent.hash)
        )