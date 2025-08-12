#!/usr/bin/env python3
"""State management for persistent torrent tracking."""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

from constants import STATE_FILE

logger = logging.getLogger(__name__)


class StateManager:
    """Manages persistent state for tracking torrent status over time."""
    
    def __init__(self, state_file: str = STATE_FILE):
        """
        Initialize state manager.
        
        Args:
            state_file: Path to state file
        """
        self.state_file = state_file
        self.state: Dict[str, Any] = self._load_state()
        self._ensure_state_dir()
    
    def _ensure_state_dir(self) -> None:
        """Ensure state file directory exists."""
        state_dir = Path(self.state_file).parent
        state_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    logger.debug(f"Loaded state for {len(state.get('torrents', {}))} torrents")
                    return state
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted state file, starting fresh: {e}")
        except Exception as e:
            logger.warning(f"Failed to load state file: {e}")
        
        return {"torrents": {}, "last_update": None}
    
    def save(self) -> bool:
        """
        Save state to file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.state["last_update"] = datetime.now(timezone.utc).isoformat()
            
            # Write to temp file first for atomicity
            temp_file = f"{self.state_file}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            
            # Atomic rename
            os.replace(temp_file, self.state_file)
            
            logger.debug(f"Saved state for {len(self.state['torrents'])} torrents")
            return True
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")
            return False
    
    def update_torrent_state(self, torrent_hash: str, current_state: str) -> None:
        """
        Update the state of a torrent and track stall time.
        
        Args:
            torrent_hash: Torrent hash
            current_state: Current torrent state
        """
        now = datetime.now(timezone.utc).isoformat()
        
        if torrent_hash not in self.state["torrents"]:
            # New torrent
            self.state["torrents"][torrent_hash] = {
                "first_seen": now,
                "current_state": current_state,
                "state_since": now,
                "stalled_since": now if current_state == "stalledDL" else None
            }
            logger.debug(f"Tracking new torrent {torrent_hash[:8]}")
        else:
            torrent_data = self.state["torrents"][torrent_hash]
            previous_state = torrent_data.get("current_state")
            
            # State changed
            if previous_state != current_state:
                torrent_data["current_state"] = current_state
                torrent_data["state_since"] = now
                
                # Track stalling transitions
                if current_state == "stalledDL":
                    if not torrent_data.get("stalled_since"):
                        torrent_data["stalled_since"] = now
                        logger.debug(f"Torrent {torrent_hash[:8]} entered stalled state")
                else:
                    if torrent_data.get("stalled_since"):
                        logger.debug(f"Torrent {torrent_hash[:8]} exited stalled state")
                        torrent_data["stalled_since"] = None
    
    def get_stalled_duration_days(self, torrent_hash: str) -> float:
        """
        Get how many days a torrent has been continuously stalled.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            Days stalled (0 if not stalled)
        """
        if torrent_hash not in self.state["torrents"]:
            return 0.0
        
        torrent_data = self.state["torrents"][torrent_hash]
        stalled_since = torrent_data.get("stalled_since")
        
        if not stalled_since:
            return 0.0
        
        try:
            stalled_start = datetime.fromisoformat(stalled_since)
            if stalled_start.tzinfo is None:
                stalled_start = stalled_start.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            duration = (now - stalled_start).total_seconds() / 86400
            return max(0, duration)
        except Exception as e:
            logger.warning(f"Error calculating stalled duration for {torrent_hash}: {e}")
            return 0.0
    
    def cleanup_old_torrents(self, current_hashes: List[str]) -> int:
        """
        Remove state for torrents that no longer exist.
        
        Args:
            current_hashes: List of current torrent hashes
            
        Returns:
            Number of cleaned up torrents
        """
        current_set = set(current_hashes)
        old_hashes = set(self.state["torrents"].keys()) - current_set
        
        for hash_to_remove in old_hashes:
            del self.state["torrents"][hash_to_remove]
        
        if old_hashes:
            logger.debug(f"Cleaned up state for {len(old_hashes)} removed torrents")
        
        return len(old_hashes)
    
    def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get stored information for a torrent.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            Torrent state info or None
        """
        return self.state["torrents"].get(torrent_hash)