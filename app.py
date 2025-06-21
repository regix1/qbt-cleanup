#!/usr/bin/env python3
import logging
import os
import sys
import time
import signal
import json
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any, Optional
import requests
from pathlib import Path

import qbittorrentapi

# ─── Constants ─────────────────────────────────────────────────────────────
SECONDS_PER_DAY = 86400
DEFAULT_TIMEOUT = 30
MAX_SEARCH_ATTEMPTS = 3
STATE_FILE = "/config/qbt_cleanup_state.json"

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
        self.qb_verify_ssl = self._get_bool("QB_VERIFY_SSL", False)
        
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
        
        # Force delete settings for non-paused torrents that meet criteria
        self.force_delete_after_hours = float(os.environ.get("FORCE_DELETE_AFTER_HOURS", "0"))  # 0 = disabled
        self.force_delete_private_after_hours = float(os.environ.get("FORCE_DELETE_PRIVATE_AFTER_HOURS", str(self.force_delete_after_hours)))
        self.force_delete_nonprivate_after_hours = float(os.environ.get("FORCE_DELETE_NONPRIVATE_AFTER_HOURS", str(self.force_delete_after_hours)))
        
        # Stale download cleanup settings - now based on stalled time
        self.cleanup_stale_downloads = self._get_bool("CLEANUP_STALE_DOWNLOADS", False)
        self.max_stalled_days = float(os.environ.get("MAX_STALLED_DAYS", "3"))
        self.max_stalled_private_days = float(os.environ.get("MAX_STALLED_PRIVATE_DAYS", str(self.max_stalled_days)))
        self.max_stalled_nonprivate_days = float(os.environ.get("MAX_STALLED_NONPRIVATE_DAYS", str(self.max_stalled_days)))
        
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


class StateManager:
    """Manages persistent state for tracking torrent status over time."""
    
    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        self.state = self._load_state()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"Loaded state for {len(state.get('torrents', {}))} torrents")
                    return state
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")
        
        return {"torrents": {}, "last_update": None}
    
    def _save_state(self) -> None:
        """Save state to file."""
        try:
            self.state["last_update"] = datetime.now(timezone.utc).isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"Saved state for {len(self.state['torrents'])} torrents")
        except Exception as e:
            logger.warning(f"Failed to save state file: {e}")
    
    def update_torrent_state(self, torrent_hash: str, current_state: str) -> None:
        """Update the state of a torrent and track stall time."""
        now = datetime.now(timezone.utc).isoformat()
        
        if torrent_hash not in self.state["torrents"]:
            self.state["torrents"][torrent_hash] = {
                "first_seen": now,
                "current_state": current_state,
                "state_since": now,
                "stalled_since": None
            }
        else:
            torrent_data = self.state["torrents"][torrent_hash]
            previous_state = torrent_data.get("current_state")
            
            # State changed
            if previous_state != current_state:
                torrent_data["current_state"] = current_state
                torrent_data["state_since"] = now
                
                # Track when stalling starts/stops
                if current_state == "stalledDL":
                    if not torrent_data.get("stalled_since"):
                        torrent_data["stalled_since"] = now
                        logger.debug(f"Torrent {torrent_hash[:8]} entered stalled state")
                else:
                    if torrent_data.get("stalled_since"):
                        logger.debug(f"Torrent {torrent_hash[:8]} exited stalled state")
                        torrent_data["stalled_since"] = None
    
    def get_stalled_duration_days(self, torrent_hash: str) -> float:
        """Get how many days a torrent has been continuously stalled."""
        if torrent_hash not in self.state["torrents"]:
            return 0.0
        
        torrent_data = self.state["torrents"][torrent_hash]
        stalled_since = torrent_data.get("stalled_since")
        
        if not stalled_since:
            return 0.0
        
        try:
            stalled_start = datetime.fromisoformat(stalled_since)
            now = datetime.now(timezone.utc)
            duration = (now - stalled_start).total_seconds() / SECONDS_PER_DAY
            return duration
        except Exception as e:
            logger.warning(f"Error calculating stalled duration for {torrent_hash}: {e}")
            return 0.0
    
    def cleanup_old_torrents(self, current_hashes: List[str]) -> None:
        """Remove state for torrents that no longer exist."""
        old_hashes = set(self.state["torrents"].keys()) - set(current_hashes)
        for hash_to_remove in old_hashes:
            del self.state["torrents"][hash_to_remove]
        
        if old_hashes:
            logger.debug(f"Cleaned up state for {len(old_hashes)} removed torrents")
    
    def save(self) -> None:
        """Save current state to file."""
        self._save_state()


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
        self.state_manager = StateManager()
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
                    VERIFY_WEBUI_CERTIFICATE=self.config.qb_verify_ssl,
                    REQUESTS_ARGS=dict(timeout=DEFAULT_TIMEOUT),
                )
                self.client.auth_log_in()
                ver = self.client.app.version
                api_v = self.client.app.web_api_version
                ssl_status = "enabled" if self.config.qb_verify_ssl else "disabled"
                logger.info(f"Connected to qBittorrent {ver} (API: {api_v}) - SSL verification {ssl_status}")
                
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

    def get_torrent_files(self, torrent_hash: str) -> List[str]:
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
                         nonprivate_ratio: float, nonprivate_days: float) -> Tuple[List[Tuple], List[Tuple], List[Tuple]]:
        """Classify torrents for deletion and identify paused torrents not ready."""
        sec_priv = private_days * SECONDS_PER_DAY
        sec_nonpriv = nonprivate_days * SECONDS_PER_DAY
        
        torrents_to_delete = []
        paused_not_ready = []
        stale_downloads = []
        fileflows_processing = []
        
        # Get FileFlows processing files once and cache them
        processing_files = []
        if self.fileflows:
            processing_files = self.fileflows.get_processing_files()
        
        # Build processing paths cache
        processing_paths = set()
        if processing_files:
            for file_info in processing_files:
                if 'RelativePath' in file_info and file_info['RelativePath']:
                    processing_paths.add(file_info['RelativePath'])
                if 'Name' in file_info and file_info['Name']:
                    processing_paths.add(file_info['Name'])
            logger.info(f"FileFlows is processing {len(processing_files)} files ({len(processing_paths)} paths cached for matching)")
        
        # Update state for all torrents and clean up old ones
        current_hashes = [t.hash for t in torrents]
        self.state_manager.cleanup_old_torrents(current_hashes)
        
        for torrent in torrents:
            is_priv = self.is_private(torrent)
            paused = torrent.state in ("pausedUP", "pausedDL")
            downloading = torrent.state in ("downloading", "stalledDL", "queuedDL", "allocating", "metaDL")
            
            # Update state tracking
            self.state_manager.update_torrent_state(torrent.hash, torrent.state)
            
            # Check for stale downloads - now based on stall time
            if self.config.cleanup_stale_downloads and torrent.state == "stalledDL":
                max_stalled_days = self.config.max_stalled_private_days if is_priv else self.config.max_stalled_nonprivate_days
                stalled_days = self.state_manager.get_stalled_duration_days(torrent.hash)
                
                if stalled_days > max_stalled_days:
                    # Check if FileFlows is processing this torrent
                    if self._is_torrent_being_processed_cached(torrent, processing_paths):
                        logger.info(
                            f"→ skipping stalled download (FileFlows processing): {torrent.name[:60]!r} "
                            f"(priv={is_priv}, state={torrent.state}, "
                            f"stalled={stalled_days:.1f}/{max_stalled_days:.1f}d)"
                        )
                    else:
                        stale_downloads.append((torrent, is_priv, max_stalled_days, stalled_days))
                        logger.info(
                            f"→ delete stalled download: {torrent.name[:60]!r} "
                            f"(priv={is_priv}, state={torrent.state}, "
                            f"stalled={stalled_days:.1f}/{max_stalled_days:.1f}d)"
                        )
                continue  # Skip further processing for stalled downloads
            
            # Skip other downloading states from seeding/completed logic
            if downloading and torrent.state != "stalledDL":
                continue
            
            # Skip seeding/completed torrents if requiring paused-only and not paused
            if ((is_priv and self.config.check_private_paused_only and not paused) or 
                (not is_priv and self.config.check_nonprivate_paused_only and not paused)):
                
                # Check for force delete if torrent meets criteria but isn't paused
                ratio_limit = private_ratio if is_priv else nonprivate_ratio
                time_limit = sec_priv if is_priv else sec_nonpriv
                force_hours = self.config.force_delete_private_after_hours if is_priv else self.config.force_delete_nonprivate_after_hours
                
                if force_hours > 0 and (torrent.ratio >= ratio_limit or torrent.seeding_time >= time_limit):
                    # Check if torrent has been over limits long enough for force delete
                    excess_time_hours = max(
                        (torrent.seeding_time - time_limit) / 3600 if torrent.seeding_time >= time_limit else 0,
                        # For ratio, we estimate based on how far over the limit we are
                        # This is imperfect but gives a reasonable approximation
                        ((torrent.ratio - ratio_limit) / ratio_limit * time_limit / 3600) if torrent.ratio >= ratio_limit else 0
                    )
                    
                    if excess_time_hours >= force_hours:
                        # Check if FileFlows is processing this torrent
                        if self._is_torrent_being_processed_cached(torrent, processing_paths):
                            logger.info(
                                f"→ skipping force delete (FileFlows processing): {torrent.name[:60]!r} "
                                f"(priv={is_priv}, state={torrent.state}, "
                                f"ratio={torrent.ratio:.2f}/{ratio_limit:.2f}, "
                                f"time={torrent.seeding_time/SECONDS_PER_DAY:.1f}/{time_limit/SECONDS_PER_DAY:.1f}d, "
                                f"excess={excess_time_hours:.1f}/{force_hours:.1f}h)"
                            )
                        else:
                            torrents_to_delete.append((torrent, is_priv, ratio_limit, time_limit))
                            logger.info(
                                f"→ force delete (non-paused): {torrent.name[:60]!r} "
                                f"(priv={is_priv}, state={torrent.state}, "
                                f"ratio={torrent.ratio:.2f}/{ratio_limit:.2f}, "
                                f"time={torrent.seeding_time/SECONDS_PER_DAY:.1f}/{time_limit/SECONDS_PER_DAY:.1f}d, "
                                f"excess={excess_time_hours:.1f}/{force_hours:.1f}h)"
                            )
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
        
        # Save state after processing all torrents
        self.state_manager.save()
        
        # Log status
        if fileflows_processing:
            logger.info(f"{len(fileflows_processing)} torrents skipped due to FileFlows processing")
        if stale_downloads:
            logger.info(f"{len(stale_downloads)} stalled downloads found for deletion")
        
        return torrents_to_delete, paused_not_ready, stale_downloads
    
    def _is_torrent_being_processed_cached(self, torrent: Any, processing_paths: set) -> bool:
        """Check if torrent matches any FileFlows processing files using cached data."""
        if not processing_paths:
            return False
        
        try:
            torrent_files = self.get_torrent_files(torrent.hash)
            if not torrent_files:
                return False
            
            # Simple filename matching
            for file_path in torrent_files:
                file_name = Path(file_path).name
                file_stem = Path(file_path).stem  # Without extension
                
                for proc_path in processing_paths:
                    proc_file_name = Path(proc_path).name
                    proc_file_stem = Path(proc_path).stem
                    
                    # Exact filename match or stem match
                    if file_name == proc_file_name or file_stem == proc_file_stem:
                        logger.info(f"✅ FileFlows protection: Match found - {file_name}")
                        return True
            
            return False
        except Exception as e:
            logger.warning(f"Error checking FileFlows status for {torrent.name}: {e}")
            return False
    
    def delete_torrents(self, torrents_to_delete: List[Tuple], stale_downloads: List[Tuple]) -> bool:
        """Delete the specified torrents."""
        all_deletions = torrents_to_delete + stale_downloads
        
        if not all_deletions:
            logger.info("No torrents matched deletion criteria")
            return True
        
        # Count by type
        completed_priv = sum(1 for _, is_priv, *_ in torrents_to_delete if is_priv)
        completed_nonpriv = len(torrents_to_delete) - completed_priv
        stale_priv = sum(1 for _, is_priv, *_ in stale_downloads if is_priv)
        stale_nonpriv = len(stale_downloads) - stale_priv
        
        hashes = [torrent.hash for torrent, *_ in all_deletions]
        
        if self.config.dry_run:
            logger.info(f"DRY RUN: would delete {len(hashes)} torrents:")
            logger.info(f"  Completed: {len(torrents_to_delete)} ({completed_priv} priv, {completed_nonpriv} non‑priv)")
            logger.info(f"  Stalled downloads: {len(stale_downloads)} ({stale_priv} priv, {stale_nonpriv} non‑priv)")
            return True
        
        try:
            self.client.torrents.delete(
                delete_files=self.config.delete_files,
                torrent_hashes=hashes
            )
            
            logger.info(f"Deleted {len(hashes)} torrents" + (" +files" if self.config.delete_files else ""))
            logger.info(f"  Completed: {len(torrents_to_delete)} ({completed_priv} priv, {completed_nonpriv} non‑priv)")
            logger.info(f"  Stalled downloads: {len(stale_downloads)} ({stale_priv} priv, {stale_nonpriv} non‑priv)")
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
            
            # Log configuration for new features
            if self.config.force_delete_private_after_hours > 0 or self.config.force_delete_nonprivate_after_hours > 0:
                logger.info(f"Force delete enabled: Private={self.config.force_delete_private_after_hours:.1f}h, Non-private={self.config.force_delete_nonprivate_after_hours:.1f}h")
            
            if self.config.cleanup_stale_downloads:
                logger.info(f"Stalled download cleanup enabled: Private={self.config.max_stalled_private_days:.1f}d, Non-private={self.config.max_stalled_nonprivate_days:.1f}d")
            
            # Classify torrents
            torrents_to_delete, paused_not_ready, stale_downloads = self.classify_torrents(
                torrents, private_ratio, private_days, nonprivate_ratio, nonprivate_days
            )
            
            # Log paused-but-not-ready
            if paused_not_ready:
                logger.info(f"{len(paused_not_ready)} paused torrents not yet at their limits")
            
            # Delete torrents
            return self.delete_torrents(torrents_to_delete, stale_downloads)
            
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