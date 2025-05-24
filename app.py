#!/usr/bin/env python3
import logging
import os
import sys
import time
import signal
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional
import requests
from pathlib import Path

import qbittorrentapi

# ─── Constants ─────────────────────────────────────────────────────────────
SECONDS_PER_DAY = 86400
DEFAULT_TIMEOUT = 30
MAX_SEARCH_ATTEMPTS = 3

# ─── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("qbt-cleanup")


class QbtConfig:
    """Configuration class for qBittorrent cleanup settings."""
    
    def __init__(self):
        # Connection settings
        self.qb_host = os.environ.get("QB_HOST", "localhost")
        self.qb_port = int(os.environ.get("QB_PORT", "8080"))
        self.qb_username = os.environ.get("QB_USERNAME", "admin")
        self.qb_password = os.environ.get("QB_PASSWORD", "adminadmin")
        
        # Fallback cleanup settings
        self.fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
        self.fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))
        
        # Private vs non‑private settings
        self.private_ratio = float(os.environ.get("PRIVATE_RATIO", str(self.fallback_ratio)))
        self.private_days = float(os.environ.get("PRIVATE_DAYS", str(self.fallback_days)))
        self.nonprivate_ratio = float(os.environ.get("NONPRIVATE_RATIO", str(self.fallback_ratio)))
        self.nonprivate_days = float(os.environ.get("NONPRIVATE_DAYS", str(self.fallback_days)))
        
        # Overrides for using qB limits
        self.ignore_qbt_ratio_private = self._get_bool("IGNORE_QBT_RATIO_PRIVATE", False)
        self.ignore_qbt_ratio_nonprivate = self._get_bool("IGNORE_QBT_RATIO_NONPRIVATE", False)
        self.ignore_qbt_time_private = self._get_bool("IGNORE_QBT_TIME_PRIVATE", False)
        self.ignore_qbt_time_nonprivate = self._get_bool("IGNORE_QBT_TIME_NONPRIVATE", False)
        
        # Operation settings
        self.delete_files = self._get_bool("DELETE_FILES", True)
        self.dry_run = self._get_bool("DRY_RUN", False)
        
        # Paused-only flags
        self.check_paused_only = self._get_bool("CHECK_PAUSED_ONLY", False)
        self.check_private_paused_only = self._get_bool("CHECK_PRIVATE_PAUSED_ONLY", self.check_paused_only)
        self.check_nonprivate_paused_only = self._get_bool("CHECK_NONPRIVATE_PAUSED_ONLY", self.check_paused_only)
        
        # Schedule settings
        self.interval_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
        self.run_once = self._get_bool("RUN_ONCE", False)
        
        # FileFlows integration settings
        self.fileflows_enabled = self._get_bool("FILEFLOWS_ENABLED", False)
        self.fileflows_host = os.environ.get("FILEFLOWS_HOST", "localhost")
        self.fileflows_port = int(os.environ.get("FILEFLOWS_PORT", "19200"))
        self.fileflows_timeout = int(os.environ.get("FILEFLOWS_TIMEOUT", "10"))
    
    @staticmethod
    def _get_bool(env_var: str, default: bool) -> bool:
        """Parse boolean environment variable."""
        return os.environ.get(env_var, str(default)).lower() == "true"


class FileFlowsClient:
    """Client for FileFlows API integration."""
    
    def __init__(self, config: QbtConfig):
        self.config = config
        self.base_url = f"http://{config.fileflows_host}:{config.fileflows_port}/api"
        self.timeout = config.fileflows_timeout
        self._processing_cache: Dict[str, bool] = {}
    
    def is_enabled(self) -> bool:
        """Check if FileFlows integration is enabled."""
        return self.config.fileflows_enabled
    
    def test_connection(self) -> bool:
        """Test connection to FileFlows API."""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=self.timeout)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"FileFlows connection test failed: {e}")
            return False
    
    def get_processing_files(self) -> List[Dict[str, Any]]:
        """Get list of files currently being processed by FileFlows."""
        try:
            # Get files with processing status
            # Status 0 = unprocessed (queued)
            # Status 1 = processing 
            # Status 2 = currently processing (active)
            response = requests.get(
                f"{self.base_url}/library-file", 
                params={"status": "0,1,2"}, 
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"FileFlows API returned status {response.status_code}")
                return []
        except Exception as e:
            logger.warning(f"Failed to get FileFlows processing files: {e}")
            return []
    
    def is_torrent_being_processed(self, torrent_path: str, torrent_files: List[str]) -> bool:
        """
        Check if any files from this torrent are currently being processed by FileFlows.
        
        Args:
            torrent_path: The save path of the torrent
            torrent_files: List of file paths within the torrent
        """
        if not self.is_enabled():
            return False
        
        # Use cache key based on torrent path
        cache_key = torrent_path
        if cache_key in self._processing_cache:
            return self._processing_cache[cache_key]
        
        processing_files = self.get_processing_files()
        if not processing_files:
            self._processing_cache[cache_key] = False
            return False
        
        # Create set of processing file paths for faster lookup
        processing_paths = set()
        for file_info in processing_files:
            # Check if file is actually being processed (not completed)
            processing_ended = file_info.get('ProcessingEnded', '')
            is_processing = (processing_ended == "1970-01-01T00:00:00Z" or 
                           processing_ended == "" or 
                           file_info.get('Status') in [0, 1, 2])
            
            if is_processing:
                if 'RelativePath' in file_info:
                    processing_paths.add(file_info['RelativePath'])
                if 'Name' in file_info:
                    processing_paths.add(file_info['Name'])
                if 'OutputPath' in file_info and file_info['OutputPath']:
                    processing_paths.add(file_info['OutputPath'])
        
        logger.debug(f"FileFlows processing {len(processing_paths)} files for torrent check: {torrent_path}")
        
        # Check if any torrent files are being processed
        torrent_base_path = Path(torrent_path)
        for file_path in torrent_files:
            full_path = str(torrent_base_path / file_path)
            
            # Check direct path match
            if full_path in processing_paths:
                logger.info(f"FileFlows is processing: {file_path}")
                self._processing_cache[cache_key] = True
                return True
            
            # Check if torrent name/directory matches any processing path
            torrent_name = Path(file_path).parts[0] if '/' in file_path else Path(file_path).stem
            for proc_path in processing_paths:
                if torrent_name in proc_path:
                    logger.info(f"FileFlows is processing torrent content: {torrent_name}")
                    self._processing_cache[cache_key] = True
                    return True
            
            # For .rar files, check if extracted files might be processing
            if file_path.lower().endswith('.rar'):
                # Check if any processing file starts with the .rar file's directory
                rar_dir = str(Path(full_path).parent)
                for proc_path in processing_paths:
                    if proc_path.startswith(rar_dir):
                        logger.info(f"FileFlows is processing extracted content from: {file_path}")
                        self._processing_cache[cache_key] = True
                        return True
        
        self._processing_cache[cache_key] = False
        return False
    
    def clear_cache(self):
        """Clear the processing cache."""
        self._processing_cache.clear()


class QbtCleanup:
    """Main cleanup class for qBittorrent torrents."""
    
    def __init__(self, config: QbtConfig):
        self.config = config
        self.client: Optional[qbittorrentapi.Client] = None
        self.fileflows: Optional[FileFlowsClient] = None
        self._private_cache: Dict[str, bool] = {}
        self._privacy_method_logged = False
    
    def connect(self) -> bool:
        """Connect to qBittorrent client and optionally FileFlows."""
        for attempt in range(3):
            try:
                self.client = qbittorrentapi.Client(
                    host=self.config.qb_host,
                    port=self.config.qb_port,
                    username=self.config.qb_username,
                    password=self.config.qb_password,
                    VERIFY_WEBUI_CERTIFICATE=False,
                    REQUESTS_ARGS=dict(timeout=DEFAULT_TIMEOUT),
                )
                self.client.auth_log_in()
                ver = self.client.app.version
                api_v = self.client.app.web_api_version
                logger.info(f"Connected to qBittorrent {ver} (API: {api_v})")
                
                # Initialize FileFlows if enabled
                if self.config.fileflows_enabled:
                    self.fileflows = FileFlowsClient(self.config)
                    if self.fileflows.test_connection():
                        logger.info("FileFlows integration enabled and connected")
                    else:
                        logger.warning("FileFlows integration enabled but connection failed")
                        self.fileflows = None
                
                return True
            except (qbittorrentapi.LoginFailed, qbittorrentapi.APIConnectionError) as e:
                if attempt == 2:  # Last attempt
                    logger.error(f"Connection failed after 3 attempts: {e}")
                    return False
                else:
                    logger.warning(f"Connection attempt {attempt + 1} failed, retrying in 5s: {e}")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}")
                return False
        return False
    
    def disconnect(self) -> None:
        """Disconnect from qBittorrent client."""
        if self.client:
            try:
                self.client.auth_log_out()
                logger.info("Logged out from qBittorrent")
            except Exception:
                pass  # Ignore logout errors
    
    def is_private(self, torrent: Any) -> bool:
        """
        Check if torrent is private, with caching.
        Uses isPrivate field for qBittorrent 5.0.0+ or tracker message checking for older versions.
        """
        torrent_hash = torrent.hash
        if torrent_hash in self._private_cache:
            return self._private_cache[torrent_hash]
        
        is_priv = False
        
        # Try newer API first (qBittorrent 5.0.0+)
        if hasattr(torrent, 'isPrivate') and torrent.isPrivate is not None:
            if not self._privacy_method_logged:
                logger.info("Using qBittorrent 5.0.0+ isPrivate field for privacy detection")
                self._privacy_method_logged = True
            is_priv = torrent.isPrivate
        else:
            # Fall back to tracker message checking for older versions
            if not self._privacy_method_logged:
                logger.info("Using tracker message method for privacy detection (qBittorrent < 5.0.0)")
                self._privacy_method_logged = True
            for attempt in range(MAX_SEARCH_ATTEMPTS):
                try:
                    trackers = self.client.torrents.trackers(hash=torrent_hash)
                    for tracker in trackers:
                        if tracker.status == 0 and tracker.msg and "private" in tracker.msg.lower():
                            is_priv = True
                            break
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt == MAX_SEARCH_ATTEMPTS - 1:
                        logger.warning(f"Could not detect privacy for torrent {torrent_hash}: {e}")
                    else:
                        time.sleep(0.5)  # Brief delay before retry
        
        self._private_cache[torrent_hash] = is_priv
        return is_priv
    
    def get_torrent_files(self, torrent_hash: str) -> List[str]:
        """Get list of files in a torrent."""
        try:
            files = self.client.torrents.files(hash=torrent_hash)
            return [f.name for f in files]
        except Exception as e:
            logger.warning(f"Could not get files for torrent {torrent_hash}: {e}")
            return []
    
    def is_torrent_processing_in_fileflows(self, torrent: Any) -> bool:
        """Check if torrent files are being processed by FileFlows."""
        if not self.fileflows:
            return False
        
        try:
            torrent_files = self.get_torrent_files(torrent.hash)
            return self.fileflows.is_torrent_being_processed(torrent.save_path, torrent_files)
        except Exception as e:
            logger.warning(f"Error checking FileFlows status for {torrent.name}: {e}")
            return False
    
    def get_qbt_limits(self) -> Tuple[float, float, float, float]:
        """Get ratio and time limits from qBittorrent preferences."""
        try:
            prefs = self.client.app.preferences
        except Exception as e:
            logger.error(f"Failed to get preferences: {e}")
            return (self.config.private_ratio, self.config.private_days, 
                   self.config.nonprivate_ratio, self.config.nonprivate_days)
        
        private_ratio = self.config.private_ratio
        private_days = self.config.private_days
        nonprivate_ratio = self.config.nonprivate_ratio
        nonprivate_days = self.config.nonprivate_days
        
        # Handle ratio limits
        if prefs.get("max_ratio_enabled", False):
            global_ratio = prefs.get("max_ratio", self.config.fallback_ratio)
            if not self.config.ignore_qbt_ratio_private and os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio
            if not self.config.ignore_qbt_ratio_nonprivate and os.environ.get("NONPRIVATE_RATIO") is None:
                nonprivate_ratio = global_ratio
            logger.info(f"Using qBittorrent ratio limits: Private={private_ratio}, Non-private={nonprivate_ratio}")
        else:
            logger.info(f"No qBittorrent ratio limit, using fallback: {self.config.fallback_ratio}")
        
        # Handle time limits
        if prefs.get("max_seeding_time_enabled", False):
            global_minutes = prefs.get("max_seeding_time", self.config.fallback_days * 24 * 60)
            global_days = global_minutes / 60 / 24
            if not self.config.ignore_qbt_time_private and os.environ.get("PRIVATE_DAYS") is None:
                private_days = global_days
            if not self.config.ignore_qbt_time_nonprivate and os.environ.get("NONPRIVATE_DAYS") is None:
                nonprivate_days = global_days
            logger.info(f"Using qBittorrent time limits: Private={private_days:.1f}d, Non-private={nonprivate_days:.1f}d")
        else:
            logger.info(f"No qBittorrent time limit, using fallback: {self.config.fallback_days:.1f}d")
        
        return private_ratio, private_days, nonprivate_ratio, nonprivate_days
    
    def classify_torrents(self, torrents: List[Any], private_ratio: float, private_days: float, 
                         nonprivate_ratio: float, nonprivate_days: float) -> Tuple[List[Tuple], List[Tuple]]:
        """Classify torrents for deletion and identify paused torrents not ready."""
        sec_priv = private_days * SECONDS_PER_DAY
        sec_nonpriv = nonprivate_days * SECONDS_PER_DAY
        
        torrents_to_delete = []
        paused_not_ready = []
        fileflows_processing = []
        
        # Clear FileFlows cache for fresh status
        if self.fileflows:
            self.fileflows.clear_cache()
        
        for torrent in torrents:
            is_priv = self.is_private(torrent)
            paused = torrent.state in ("pausedUP", "pausedDL")
            
            # Skip if requiring paused-only and not paused
            if ((is_priv and self.config.check_private_paused_only and not paused) or 
                (not is_priv and self.config.check_nonprivate_paused_only and not paused)):
                continue
            
            ratio_limit = private_ratio if is_priv else nonprivate_ratio
            time_limit = sec_priv if is_priv else sec_nonpriv
            
            # Check if torrent meets deletion criteria
            meets_criteria = torrent.ratio >= ratio_limit or torrent.seeding_time >= time_limit
            
            if meets_criteria:
                # Check if FileFlows is processing this torrent
                if self.is_torrent_processing_in_fileflows(torrent):
                    fileflows_processing.append((torrent, is_priv, ratio_limit, time_limit))
                    logger.info(
                        f"→ skipping (FileFlows processing): {torrent.name[:60]!r} "
                        f"(priv={is_priv}, state={torrent.state}, "
                        f"ratio={torrent.ratio:.2f}/{ratio_limit:.2f}, "
                        f"time={torrent.seeding_time/SECONDS_PER_DAY:.1f}/{time_limit/SECONDS_PER_DAY:.1f}d)"
                    )
                else:
                    torrents_to_delete.append((torrent, is_priv, ratio_limit, time_limit))
                    logger.info(
                        f"→ delete: {torrent.name[:60]!r} "
                        f"(priv={is_priv}, state={torrent.state}, "
                        f"ratio={torrent.ratio:.2f}/{ratio_limit:.2f}, "
                        f"time={torrent.seeding_time/SECONDS_PER_DAY:.1f}/{time_limit/SECONDS_PER_DAY:.1f}d)"
                    )
            elif paused:
                paused_not_ready.append((torrent, is_priv, ratio_limit, time_limit))
        
        # Log FileFlows processing status
        if fileflows_processing:
            logger.info(f"{len(fileflows_processing)} torrents skipped due to FileFlows processing")
        
        return torrents_to_delete, paused_not_ready
    
    def delete_torrents(self, torrents_to_delete: List[Tuple]) -> bool:
        """Delete the specified torrents."""
        if not torrents_to_delete:
            logger.info("No torrents matched deletion criteria")
            return True
        
        priv_count = sum(1 for _, is_priv, *_ in torrents_to_delete if is_priv)
        nonpriv_count = len(torrents_to_delete) - priv_count
        hashes = [torrent.hash for torrent, *_ in torrents_to_delete]
        
        if self.config.dry_run:
            logger.info(f"DRY RUN: would delete {len(hashes)} ({priv_count} priv, {nonpriv_count} non‑priv)")
            return True
        
        try:
            # Try newer API parameter name first
            try:
                self.client.torrents.delete(
                    delete_files=self.config.delete_files,
                    torrent_hashes=hashes
                )
            except Exception:
                # Fall back to older API parameter name
                self.client.torrents.delete(
                    delete_files=self.config.delete_files,
                    hashes=hashes
                )
            
            logger.info(
                f"Deleted {len(hashes)} torrents ({priv_count} priv, {nonpriv_count} non‑priv)"
                + (" +files" if self.config.delete_files else "")
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete torrents: {e}")
            return False
    
    def run_cleanup(self) -> bool:
        """Main cleanup logic."""
        if not self.connect():
            return False
        
        try:
            # Get limits from qBittorrent
            private_ratio, private_days, nonprivate_ratio, nonprivate_days = self.get_qbt_limits()
            
            # Fetch torrents
            try:
                torrents = self.client.torrents.info()
            except Exception as e:
                logger.error(f"Failed to fetch torrents: {e}")
                return False
            
            logger.info(f"Fetched {len(torrents)} torrents")
            
            # Count private/non-private for logging
            private_count = sum(1 for t in torrents if self.is_private(t))
            nonprivate_count = len(torrents) - private_count
            logger.info(f"Torrent breakdown: {private_count} private, {nonprivate_count} non‑private")
            
            # Classify torrents
            torrents_to_delete, paused_not_ready = self.classify_torrents(
                torrents, private_ratio, private_days, nonprivate_ratio, nonprivate_days
            )
            
            # Log paused-but-not-ready
            if paused_not_ready:
                logger.info(f"{len(paused_not_ready)} paused torrents not yet at their limits")
            
            # Delete torrents
            return self.delete_torrents(torrents_to_delete)
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False
        finally:
            self.disconnect()


def main():
    """Main entry point."""
    config = QbtConfig()
    cleanup = QbtCleanup(config)
    
    # Flag to trigger manual scan
    manual_scan_requested = {"value": False}
    
    def signal_handler(signum, frame):
        """Handle manual scan trigger signal."""
        logger.info("Manual scan triggered via signal")
        manual_scan_requested["value"] = True
    
    # Set up signal handler for manual scan trigger
    signal.signal(signal.SIGUSR1, signal_handler)
    
    logger.info("qBittorrent Cleanup Container started")
    logger.info(f"Schedule: {'Run once' if config.run_once else f'Every {config.interval_hours}h'}")
    logger.info("Send SIGUSR1 signal to trigger manual scan: docker kill --signal=SIGUSR1 qbt-cleanup")
    
    if config.run_once:
        success = cleanup.run_cleanup()
        sys.exit(0 if success else 1)
    else:
        while True:
            try:
                cleanup.run_cleanup()
                logger.info(f"Next run in {config.interval_hours}h. Sleeping…")
                
                # Sleep with periodic checks for manual scan trigger
                sleep_duration = config.interval_hours * 3600
                sleep_interval = 60  # Check every minute for manual trigger
                
                for _ in range(0, sleep_duration, sleep_interval):
                    if manual_scan_requested["value"]:
                        logger.info("Manual scan requested, interrupting sleep")
                        manual_scan_requested["value"] = False
                        break
                    time.sleep(min(sleep_interval, sleep_duration))
                    sleep_duration -= sleep_interval
                    if sleep_duration <= 0:
                        break
                        
            except KeyboardInterrupt:
                logger.info("Interrupted; exiting")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Uncaught error in main loop: {e}")
                time.sleep(60)


if __name__ == "__main__":
    main()