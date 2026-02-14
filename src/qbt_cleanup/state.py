#!/usr/bin/env python3
"""State management for persistent torrent tracking using SQLite for performance."""

import sqlite3
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
from contextlib import contextmanager

from .constants import STATE_FILE, TorrentState, SECONDS_PER_DAY

logger = logging.getLogger(__name__)


class StateManager:
    """Manages persistent state for tracking torrent status over time using SQLite."""

    def __init__(self, state_file: str = STATE_FILE):
        """
        Initialize state manager with SQLite backend.

        Args:
            state_file: Path to state file (will use .db extension)
        """
        # Change extension to .db
        base_path = os.path.splitext(state_file)[0]
        self.state_file = f"{base_path}.db"
        self.state_enabled = True
        self._connection = None
        self._in_batch = False  # Track if we're in a batch operation
        self._ensure_state_dir()
        self._init_database()
        self._migrate_from_json()

    @contextmanager
    def batch(self):
        """
        Context manager for batching multiple operations into a single transaction.

        Usage:
            with state.batch():
                for torrent in torrents:
                    state.update_torrent_state(torrent.hash, torrent.state)
            # Commits on exit
        """
        if not self.state_enabled:
            yield
            return

        self._in_batch = True
        try:
            yield
            if self._connection:
                self._connection.commit()
        except Exception:
            if self._connection:
                self._connection.rollback()
            raise
        finally:
            self._in_batch = False
    
    def _ensure_state_dir(self) -> None:
        """Ensure state file directory exists and is writable."""
        try:
            state_dir = Path(self.state_file).parent
            state_dir.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions
            test_file = state_dir / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                logger.warning(f"State directory not writable: {e}")
                logger.warning("State persistence disabled - tracking will reset on restart")
                self.state_enabled = False
        except Exception as e:
            logger.warning(f"Could not ensure state directory: {e}")
            self.state_enabled = False
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(self.state_file, timeout=10.0)
            self._connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._connection.execute("PRAGMA journal_mode=WAL")
            # Optimize for performance
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA cache_size=10000")
            self._connection.execute("PRAGMA temp_store=MEMORY")
        return self._connection
    
    def _init_database(self) -> None:
        """Initialize database schema."""
        if not self.state_enabled:
            return
        
        try:
            conn = self._get_connection()
            
            # Create torrents table with indexes
            conn.execute("""
                CREATE TABLE IF NOT EXISTS torrents (
                    hash TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    current_state TEXT NOT NULL,
                    state_since TEXT NOT NULL,
                    stalled_since TEXT,
                    last_updated TEXT NOT NULL
                )
            """)
            
            # Create indexes for faster queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_current_state 
                ON torrents(current_state)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_stalled_since 
                ON torrents(stalled_since) 
                WHERE stalled_since IS NOT NULL
            """)
            
            # Create metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Create blacklist table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    hash TEXT PRIMARY KEY,
                    name TEXT,
                    added_at TEXT NOT NULL,
                    reason TEXT
                )
            """)

            # Create unregistered torrents table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS unregistered_torrents (
                    hash TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL
                )
            """)

            conn.commit()
            logger.debug("SQLite database initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            self.state_enabled = False
    
    def _migrate_from_json(self) -> None:
        """Migrate from old JSON format if it exists."""
        if not self.state_enabled:
            return
            
        json_file = os.path.splitext(self.state_file)[0] + ".json"
        msgpack_file = os.path.splitext(self.state_file)[0] + ".msgpack"
        
        # Try JSON first
        if os.path.exists(json_file):
            try:
                import json
                with open(json_file, 'r') as f:
                    old_state = json.load(f)
                
                if self._import_old_state(old_state):
                    os.remove(json_file)
                    logger.info("Removed old JSON state file after successful migration")
            except Exception as e:
                logger.warning(f"Could not migrate from JSON: {e}")
        
        # Try MessagePack if it exists
        elif os.path.exists(msgpack_file):
            try:
                import msgpack
                with open(msgpack_file, 'rb') as f:
                    old_state = msgpack.unpack(f, raw=False, strict_map_key=False)
                
                if self._import_old_state(old_state):
                    os.remove(msgpack_file)
                    logger.info("Removed old MessagePack state file after successful migration")
            except ImportError:
                logger.warning("MessagePack file found but msgpack library not installed")
            except Exception as e:
                logger.warning(f"Could not migrate from MessagePack: {e}")
    
    def _import_old_state(self, old_state: Dict[str, Any]) -> bool:
        """
        Import state from old format.
        
        Args:
            old_state: Old state dictionary
            
        Returns:
            True if successful
        """
        torrents = old_state.get("torrents", {})
        if not torrents:
            return False
        
        try:
            conn = self._get_connection()
            for hash_val, data in torrents.items():
                conn.execute("""
                    INSERT OR REPLACE INTO torrents 
                    (hash, first_seen, current_state, state_since, stalled_since, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    hash_val,
                    data.get("first_seen", datetime.now(timezone.utc).isoformat()),
                    data.get("current_state", "unknown"),
                    data.get("state_since", datetime.now(timezone.utc).isoformat()),
                    data.get("stalled_since"),
                    datetime.now(timezone.utc).isoformat()
                ))
            
            conn.commit()
            logger.info(f"Migrated {len(torrents)} torrents to SQLite")
            return True
        except Exception as e:
            logger.error(f"Failed to import old state: {e}")
            return False
    
    def save(self) -> bool:
        """
        Save is automatic with SQLite (each operation commits).
        
        Returns:
            True if enabled
        """
        if self._connection:
            try:
                self._connection.commit()
            except Exception:
                pass
        return self.state_enabled
    
    def update_torrent_state(self, torrent_hash: str, current_state: str) -> None:
        """
        Update the state of a torrent and track stall time.
        
        Args:
            torrent_hash: Torrent hash
            current_state: Current torrent state
        """
        if not self.state_enabled:
            return
        
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            conn = self._get_connection()
            
            # Check if torrent exists
            cursor = conn.execute(
                "SELECT current_state, stalled_since FROM torrents WHERE hash = ?",
                (torrent_hash,)
            )
            result = cursor.fetchone()
            
            if result is None:
                # New torrent
                stalled_since = now if current_state == TorrentState.STALLED_DL.value else None
                conn.execute("""
                    INSERT INTO torrents 
                    (hash, first_seen, current_state, state_since, stalled_since, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (torrent_hash, now, current_state, now, stalled_since, now))
                logger.debug(f"Tracking new torrent {torrent_hash[:8]}")
            else:
                previous_state = result["current_state"]
                
                if previous_state != current_state:
                    # State changed
                    if current_state == TorrentState.STALLED_DL.value and not result["stalled_since"]:
                        # Entering stalled state
                        conn.execute("""
                            UPDATE torrents 
                            SET current_state = ?, state_since = ?, stalled_since = ?, last_updated = ?
                            WHERE hash = ?
                        """, (current_state, now, now, now, torrent_hash))
                        logger.debug(f"Torrent {torrent_hash[:8]} entered stalled state")
                    elif current_state != TorrentState.STALLED_DL.value and result["stalled_since"]:
                        # Exiting stalled state
                        conn.execute("""
                            UPDATE torrents 
                            SET current_state = ?, state_since = ?, stalled_since = NULL, last_updated = ?
                            WHERE hash = ?
                        """, (current_state, now, now, torrent_hash))
                        logger.debug(f"Torrent {torrent_hash[:8]} exited stalled state")
                    else:
                        # Normal state change
                        conn.execute("""
                            UPDATE torrents 
                            SET current_state = ?, state_since = ?, last_updated = ?
                            WHERE hash = ?
                        """, (current_state, now, now, torrent_hash))
                else:
                    # Just update last seen
                    conn.execute(
                        "UPDATE torrents SET last_updated = ? WHERE hash = ?",
                        (now, torrent_hash)
                    )

            # Only commit if not in batch mode
            if not self._in_batch:
                conn.commit()
        except sqlite3.IntegrityError as e:
            logger.error(f"Database integrity error updating torrent state: {e}")
        except sqlite3.OperationalError as e:
            logger.error(f"Database operational error updating torrent state: {e}")
        except Exception as e:
            logger.error(f"Failed to update torrent state: {e}")
    
    def get_stalled_duration_days(self, torrent_hash: str) -> float:
        """
        Get how many days a torrent has been continuously stalled.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            Days stalled (0 if not stalled or state disabled)
        """
        if not self.state_enabled:
            return 0.0
        
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT stalled_since FROM torrents WHERE hash = ?",
                (torrent_hash,)
            )
            result = cursor.fetchone()
            
            if not result or not result["stalled_since"]:
                return 0.0
            
            stalled_start = datetime.fromisoformat(result["stalled_since"])
            if stalled_start.tzinfo is None:
                stalled_start = stalled_start.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            duration = (now - stalled_start).total_seconds() / SECONDS_PER_DAY
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
        if not self.state_enabled or not current_hashes:
            return 0
        
        try:
            conn = self._get_connection()
            
            # Get count of torrents to be deleted
            cursor = conn.execute("""
                SELECT COUNT(*) as count 
                FROM torrents 
                WHERE hash NOT IN ({})
            """.format(','.join('?' * len(current_hashes))), current_hashes)
            
            result = cursor.fetchone()
            count = result["count"] if result else 0
            
            if count > 0:
                # Delete torrents no longer in qBittorrent
                conn.execute("""
                    DELETE FROM torrents
                    WHERE hash NOT IN ({})
                """.format(','.join('?' * len(current_hashes))), current_hashes)

                logger.debug(f"Cleaned up state for {count} removed torrents")

            conn.commit()
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup old torrents: {e}")
            return 0
    
    def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get stored information for a torrent.
        
        Args:
            torrent_hash: Torrent hash
            
        Returns:
            Torrent state info or None
        """
        if not self.state_enabled:
            return None
        
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT * FROM torrents WHERE hash = ?",
                (torrent_hash,)
            )
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error(f"Failed to get torrent info: {e}")
            return None
    
    def is_blacklisted(self, torrent_hash: str) -> bool:
        """
        Check if a torrent is blacklisted.

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if blacklisted
        """
        if not self.state_enabled:
            return False

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT 1 FROM blacklist WHERE hash = ?",
                (torrent_hash,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to check blacklist: {e}")
            return False

    def add_to_blacklist(self, torrent_hash: str, name: str = "", reason: str = "") -> bool:
        """
        Add a torrent to the blacklist.

        Args:
            torrent_hash: Torrent hash
            name: Torrent name (optional)
            reason: Reason for blacklisting (optional)

        Returns:
            True if successful
        """
        if not self.state_enabled:
            logger.warning("State persistence disabled - cannot add to blacklist")
            return False

        try:
            conn = self._get_connection()
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                INSERT OR REPLACE INTO blacklist (hash, name, added_at, reason)
                VALUES (?, ?, ?, ?)
            """, (torrent_hash, name, now, reason))
            conn.commit()
            logger.info(f"Added {torrent_hash[:8]} to blacklist")
            return True
        except Exception as e:
            logger.error(f"Failed to add to blacklist: {e}")
            return False

    def remove_from_blacklist(self, torrent_hash: str) -> bool:
        """
        Remove a torrent from the blacklist.

        Args:
            torrent_hash: Torrent hash

        Returns:
            True if successful
        """
        if not self.state_enabled:
            logger.warning("State persistence disabled - cannot remove from blacklist")
            return False

        try:
            conn = self._get_connection()
            cursor = conn.execute("DELETE FROM blacklist WHERE hash = ?", (torrent_hash,))
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Removed {torrent_hash[:8]} from blacklist")
                return True
            else:
                logger.warning(f"Torrent {torrent_hash[:8]} not found in blacklist")
                return False
        except Exception as e:
            logger.error(f"Failed to remove from blacklist: {e}")
            return False

    def get_blacklist(self) -> List[Dict[str, Any]]:
        """
        Get all blacklisted torrents.

        Returns:
            List of blacklist entries
        """
        if not self.state_enabled:
            return []

        try:
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT hash, name, added_at, reason
                FROM blacklist
                ORDER BY added_at DESC
            """)
            results = cursor.fetchall()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to get blacklist: {e}")
            return []

    def clear_blacklist(self) -> bool:
        """
        Clear all entries from the blacklist.

        Returns:
            True if successful
        """
        if not self.state_enabled:
            logger.warning("State persistence disabled - cannot clear blacklist")
            return False

        try:
            conn = self._get_connection()
            cursor = conn.execute("DELETE FROM blacklist")
            conn.commit()
            logger.info(f"Cleared {cursor.rowcount} entries from blacklist")
            return True
        except Exception as e:
            logger.error(f"Failed to clear blacklist: {e}")
            return False

    def set_metadata(self, key: str, value: str) -> bool:
        """
        Set a metadata value.

        Args:
            key: Metadata key
            value: Metadata value

        Returns:
            True if successful
        """
        if not self.state_enabled:
            return False

        try:
            conn = self._get_connection()
            conn.execute("""
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES (?, ?)
            """, (key, value))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to set metadata {key}: {e}")
            return False

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a metadata value.

        Args:
            key: Metadata key
            default: Default value if key not found

        Returns:
            Metadata value or default
        """
        if not self.state_enabled:
            return default

        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT value FROM metadata WHERE key = ?",
                (key,)
            )
            result = cursor.fetchone()
            return result['value'] if result else default
        except Exception as e:
            logger.error(f"Failed to get metadata {key}: {e}")
            return default

    def mark_unregistered(self, torrent_hash: str) -> None:
        """Record when a torrent was first seen as unregistered.

        Args:
            torrent_hash: The torrent hash
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO unregistered_torrents (hash, first_seen) VALUES (?, ?)",
            (torrent_hash, now),
        )
        if not self._in_batch:
            conn.commit()

    def get_unregistered_hours(self, torrent_hash: str) -> float | None:
        """Get how many hours a torrent has been seen as unregistered.

        Args:
            torrent_hash: The torrent hash

        Returns:
            Hours since first seen as unregistered, or None if not tracked
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT first_seen FROM unregistered_torrents WHERE hash = ?",
            (torrent_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        first_seen = datetime.fromisoformat(row[0])
        now = datetime.now(timezone.utc)
        return (now - first_seen).total_seconds() / 3600

    def clear_unregistered(self, torrent_hash: str) -> None:
        """Remove a torrent from unregistered tracking (it recovered).

        Args:
            torrent_hash: The torrent hash
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM unregistered_torrents WHERE hash = ?",
            (torrent_hash,),
        )
        if not self._in_batch:
            conn.commit()

    def cleanup_unregistered(self, active_hashes: List[str]) -> None:
        """Remove unregistered entries for torrents that no longer exist.

        Args:
            active_hashes: List of currently active torrent hashes
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        if not active_hashes:
            cursor.execute("DELETE FROM unregistered_torrents")
        else:
            placeholders = ",".join("?" for _ in active_hashes)
            cursor.execute(
                f"DELETE FROM unregistered_torrents WHERE hash NOT IN ({placeholders})",
                active_hashes,
            )
        if not self._in_batch:
            conn.commit()

    def count_unregistered(self) -> int:
        """Count the number of torrents currently tracked as unregistered.

        Returns:
            Number of unregistered torrents in the state database
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM unregistered_torrents")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to count unregistered torrents: {e}")
            return 0

    def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            finally:
                self._connection = None

    def __del__(self):
        """Clean up database connection on deletion."""
        self.close()