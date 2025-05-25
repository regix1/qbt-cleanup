#!/usr/bin/env python3
import logging
import os
import sys
import time
import signal
from datetime import datetime, timezone, timedelta
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
        self.fileflows_auto_fix_names = self._get_bool("FILEFLOWS_AUTO_FIX_NAMES", True)
    
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
        self.client = None  # Will be set by QbtCleanup
    
    def is_enabled(self) -> bool:
        """Check if FileFlows integration is enabled."""
        return self.config.fileflows_enabled
    
    def test_connection(self) -> bool:
        """Test connection to FileFlows API."""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=self.timeout)
            logger.debug(f"FileFlows connection test: {response.status_code} from {self.base_url}/status")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"FileFlows connection test failed: {e} (URL: {self.base_url})")
            return False
    
    def auto_fix_truncated_names(self, processing_files: List[Dict[str, Any]]) -> None:
        """
        Automatically fix truncated torrent names in qBittorrent to match FileFlows filenames.
        This improves future matching reliability.
        """
        if not processing_files or not self.client:
            return
            
        try:
            # Get all torrents to find potential matches for renaming
            torrents = self.client.torrents.info()
            
            for file_info in processing_files:
                # Get the FileFlows filename (without extension)
                ff_relative_path = file_info.get('RelativePath', '')
                ff_name_field = file_info.get('Name', '')
                
                # Try both RelativePath and Name fields
                for ff_path in [ff_relative_path, ff_name_field]:
                    if not ff_path:
                        continue
                        
                    ff_filename = Path(ff_path).name
                    ff_stem = Path(ff_path).stem  # Without extension
                    
                    # Look for qBittorrent torrents with truncated names that might match
                    for torrent in torrents:
                        qbt_name = torrent.name  # Keep using .name for auto-fix since we're comparing against the displayed name
                        
                        # Skip if names already match or qBt name is longer
                        if qbt_name == ff_stem or len(qbt_name) >= len(ff_stem):
                            continue
                            
                        # Check if qBt name appears to be a truncated version of FileFlows name
                        if (len(qbt_name) > 40 and  # Only rename reasonably long names
                            ff_stem.startswith(qbt_name) and  # FileFlows name starts with qBt name
                            len(ff_stem) - len(qbt_name) < 50):  # Not too different in length
                            
                            logger.info(f"Auto-fixing truncated torrent name:")
                            logger.info(f"  Old: '{qbt_name}'")
                            logger.info(f"  New: '{ff_stem}'")
                            
                            try:
                                # Rename the torrent in qBittorrent
                                self.client.torrents.rename(torrent_hash=torrent.hash, new_torrent_name=ff_stem)
                                logger.info(f"✅ Successfully renamed torrent {torrent.hash[:8]}")
                                
                            except Exception as e:
                                logger.warning(f"Failed to rename torrent {torrent.hash[:8]}: {e}")
                                
        except Exception as e:
            logger.warning(f"Error during auto-fix of truncated names: {e}")

    def get_processing_files(self) -> List[Dict[str, Any]]:
        """Get list of files currently being processed by FileFlows."""
        try:
            # Get all files and filter for actively processing ones only
            response = requests.get(f"{self.base_url}/library-file", timeout=self.timeout)
            if response.status_code == 200:
                all_files = response.json()
                # Filter for files that are currently processing or recently processed
                processing_files = []
                for file_info in all_files:
                    status = file_info.get('Status', -1)
                    processing_started = file_info.get('ProcessingStarted', '')
                    processing_ended = file_info.get('ProcessingEnded', '')
                    
                    # Check if actively processing (Status 2) regardless of end time
                    # OR if it finished processing very recently (within last 10 minutes)
                    is_actively_processing = status == 2
                    
                    # Also protect files that finished very recently (FileFlows may not update status immediately)
                    is_recently_processed = False
                    if status == 1 and processing_ended and processing_ended != "1970-01-01T00:00:00Z":
                        try:
                            end_time = datetime.fromisoformat(processing_ended.replace('Z', '+00:00'))
                            now = datetime.now(timezone.utc)
                            # Protect files that finished in the last 10 minutes
                            is_recently_processed = (now - end_time) < timedelta(minutes=10)
                        except:
                            pass
                    
                    if is_actively_processing or is_recently_processed:
                        processing_files.append(file_info)
                        
                logger.debug(f"Found {len(processing_files)} actively/recently processing files in FileFlows")
                return processing_files
            else:
                logger.warning(f"FileFlows API returned status {response.status_code}")
                return []
        except Exception as e:
            logger.warning(f"Failed to get FileFlows processing files: {e}")
            return []


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
                    self.fileflows.client = self.client  # Set the client reference
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
                    trackers = self.client.torrents.trackers(torrent_hash=torrent_hash)
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
    
    def get_torrent_full_name(self, torrent: Any) -> str:
        """Get the full torrent name from properties."""
        try:
            # Get the full name from properties
            properties = torrent.properties
            # Properties might contain 'name' or other fields with the full name
            if hasattr(properties, 'name') and properties.name:
                return properties.name
        except Exception as e:
            logger.debug(f"Could not get properties for torrent {torrent.hash}: {e}")
        
        # Return empty string if no full name available
        return ""

    def get_torrent_files(self, torrent_hash: str) -> List[str]:
        """Get list of files in a torrent."""
        try:
            files = self.client.torrents.files(torrent_hash=torrent_hash)
            return [f.name for f in files]
        except Exception as e:
            logger.warning(f"Could not get files for torrent {torrent_hash}: {e}")
            return []
        """Get list of files in a torrent."""
        try:
            files = self.client.torrents.files(torrent_hash=torrent_hash)
            return [f.name for f in files]
        except Exception as e:
            logger.warning(f"Could not get files for torrent {torrent_hash}: {e}")
            return []
    
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
        
        # Get FileFlows processing files once and cache them
        processing_files = []
        if self.fileflows:
            processing_files = self.fileflows.get_processing_files()
            
            # Auto-fix truncated torrent names to improve matching
            if self.config.fileflows_auto_fix_names and processing_files:
                logger.info(f"Auto-fixing truncated torrent names for {len(processing_files)} processing files...")
                self.fileflows.auto_fix_truncated_names(processing_files)
        
        # Build processing paths cache
        processing_paths = set()
        if processing_files:
            for file_info in processing_files:
                if 'RelativePath' in file_info and file_info['RelativePath']:
                    processing_paths.add(file_info['RelativePath'])
                if 'Name' in file_info and file_info['Name']:
                    processing_paths.add(file_info['Name'])
            logger.info(f"FileFlows is currently processing {len(processing_paths)} files")
        
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
                # Check if FileFlows is processing this torrent (using cached data)
                if self._is_torrent_being_processed_cached(torrent, processing_paths):
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
    
    def _is_torrent_being_processed_cached(self, torrent: Any, processing_paths: set) -> bool:
        """Check if torrent matches any FileFlows processing files using cached data."""
        if not processing_paths:
            return False
        
        try:
            torrent_files = self.get_torrent_files(torrent.hash)
            if not torrent_files:
                return False
            
            # Check for matching files using multiple strategies
            for file_path in torrent_files:
                file_name = Path(file_path).name
                file_stem = Path(file_path).stem  # Without extension
                
                for proc_path in processing_paths:
                    proc_file_name = Path(proc_path).name
                    proc_file_stem = Path(proc_path).stem
                    
                    # Strategy 1: Exact filename match
                    if file_name == proc_file_name:
                        logger.info(f"✅ FileFlows protection: Exact filename match - {file_name}")
                        return True
                    
                    # Strategy 2: Stem match (without extension)
                    if file_stem == proc_file_stem and len(file_stem) > 20:
                        logger.info(f"✅ FileFlows protection: Stem match - {file_stem}")
                        return True
                    
                    # Strategy 3: Handle truncated names - check if FileFlows name starts with qBittorrent name
                    if len(file_stem) > 30 and proc_file_stem.startswith(file_stem):
                        logger.info(f"✅ FileFlows protection: Prefix match - {file_stem}")
                        return True
                    
                    # Strategy 4: Handle mid-word truncation (like "AVC" -> "A")
                    if len(file_stem) > 40:
                        # Find the longest common prefix
                        common_len = 0
                        for i, (c1, c2) in enumerate(zip(file_stem, proc_file_stem)):
                            if c1 == c2:
                                common_len = i + 1
                            else:
                                break
                        
                        # If the common prefix is most of the qBittorrent name and long enough
                        if common_len >= len(file_stem) * 0.9 and common_len > 50:
                            logger.info(f"✅ FileFlows protection: Truncation match - {file_stem[:common_len]}...")
                            return True
            
            return False
        except Exception as e:
            logger.warning(f"Error checking FileFlows status for {torrent.name}: {e}")
            return False
    
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
            self.client.torrents.delete(
                delete_files=self.config.delete_files,
                torrent_hashes=hashes
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