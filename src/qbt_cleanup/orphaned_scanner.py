#!/usr/bin/env python3
"""Orphaned files scanner and cleanup functionality."""

import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Set, List, Tuple

from .client import QBittorrentClient

logger = logging.getLogger(__name__)


class OrphanedFilesScanner:
    """Scanner for identifying and removing orphaned torrent files."""

    def __init__(self, client: QBittorrentClient):
        """
        Initialize orphaned files scanner.

        Args:
            client: qBittorrent client instance
        """
        self.client = client

    def _add_parent_paths(self, path: Path, stop_at: Path, paths_set: Set[Path]) -> None:
        """
        Add all parent directories up to stop_at directory.

        Args:
            path: Starting path
            stop_at: Stop adding parents when reaching this path
            paths_set: Set to add parent paths to
        """
        current = path.parent
        while current != stop_at and current.parent != current:
            paths_set.add(current)
            current = current.parent

    def get_active_torrent_paths(self) -> Set[Path]:
        """
        Get all file and directory paths from active torrents.

        Returns:
            Set of resolved absolute paths that are tracked by qBittorrent
        """
        active_paths = set()

        try:
            torrents = self.client.get_torrents()
            logger.info(f"Found {len(torrents)} active torrents in qBittorrent")

            for torrent in torrents:
                try:
                    # Get the save path for this torrent
                    save_path = Path(torrent.save_path).resolve()

                    # Get the content path (the actual torrent folder/file)
                    content_path = Path(torrent.content_path).resolve()

                    # Add the main content path
                    active_paths.add(content_path)

                    # If it's a directory, add all parent directories up to save_path
                    if content_path.is_dir():
                        self._add_parent_paths(content_path, save_path, active_paths)

                    # Also get individual files for multi-file torrents
                    files = self.client.get_torrent_files(torrent.hash)
                    for file_path in files:
                        full_path = (save_path / file_path).resolve()
                        active_paths.add(full_path)
                        # Add all parent directories of this file
                        self._add_parent_paths(full_path, save_path, active_paths)

                except Exception as e:
                    logger.warning(f"Error processing torrent {torrent.name}: {e}")
                    continue

            logger.info(f"Collected {len(active_paths)} active paths from torrents")

            # Log all active paths for debugging
            logger.info("Active paths from qBittorrent:")
            for path in sorted(active_paths):
                logger.info(f"  ACTIVE: {path}")

            return active_paths

        except Exception as e:
            logger.error(f"Failed to get active torrent paths: {e}")
            return set()

    def scan_for_orphaned_files(self, scan_dirs: List[str],
                                active_paths: Set[Path],
                                min_age_hours: float = 1.0) -> List[Path]:
        """
        Scan directories recursively for orphaned files and folders.

        Args:
            scan_dirs: List of directory paths to scan
            active_paths: Set of paths that are actively tracked
            min_age_hours: Minimum age in hours for a file to be considered orphaned

        Returns:
            List of orphaned paths (files or directories)
        """
        orphaned = []
        current_time = time.time()
        min_age_seconds = min_age_hours * 3600  # Convert hours to seconds

        for scan_dir_str in scan_dirs:
            scan_dir = Path(scan_dir_str).resolve()

            if not scan_dir.exists():
                logger.warning(f"Scan directory does not exist: {scan_dir}")
                continue

            if not scan_dir.is_dir():
                logger.warning(f"Scan path is not a directory: {scan_dir}")
                continue

            logger.info(f"Scanning directory recursively for orphaned files: {scan_dir}")
            logger.info(f"Minimum file age: {min_age_hours} hours")

            try:
                # Recursively walk through all subdirectories
                for root, dirs, files in os.walk(scan_dir):
                    root_path = Path(root).resolve()

                    # Check each directory in this level
                    for dir_name in dirs:
                        dir_path = (root_path / dir_name).resolve()
                        self._check_and_add_orphaned(
                            dir_path, active_paths, current_time,
                            min_age_seconds, min_age_hours, orphaned
                        )

                    # Check each file in this level
                    for file_name in files:
                        file_path = (root_path / file_name).resolve()
                        self._check_and_add_orphaned(
                            file_path, active_paths, current_time,
                            min_age_seconds, min_age_hours, orphaned
                        )

            except Exception as e:
                logger.error(f"Error scanning directory {scan_dir}: {e}")
                continue

        return orphaned

    def _check_and_add_orphaned(self, item_path: Path, active_paths: Set[Path],
                                current_time: float, min_age_seconds: float,
                                min_age_hours: float, orphaned: List[Path]) -> None:
        """
        Check if an item is orphaned and add to list if it is.

        Args:
            item_path: Path to check
            active_paths: Set of active paths
            current_time: Current timestamp
            min_age_seconds: Minimum age in seconds
            min_age_hours: Minimum age in hours (for logging)
            orphaned: List to add orphaned items to
        """
        # Check if this item or any of its parents are in active paths
        is_active = self._is_path_active(item_path, active_paths)

        logger.info(f"SCANNED: {item_path} -> {'ACTIVE (keeping)' if is_active else 'NOT ACTIVE (checking age)'}")

        if not is_active:
            # Check file modification time
            try:
                mtime = item_path.stat().st_mtime
                age_seconds = current_time - mtime
                age_hours = age_seconds / 3600

                if age_seconds >= min_age_seconds:
                    orphaned.append(item_path)
                    logger.info(f"  -> ORPHANED: Age {age_hours:.1f}h >= {min_age_hours}h - WILL DELETE")
                else:
                    logger.info(f"  -> TOO RECENT: Age {age_hours:.1f}h < {min_age_hours}h - KEEPING")
            except Exception as e:
                logger.warning(f"Error checking modification time for {item_path}: {e}")
                return

    def _is_path_active(self, path: Path, active_paths: Set[Path]) -> bool:
        """
        Check if a path is tracked by qBittorrent.

        A path is considered active if:
        1. It's directly in the active paths set, OR
        2. Any active path is a child of this path (this path is a parent), OR
        3. This path is a child of any active path (this path is inside an active torrent)

        Args:
            path: Path to check
            active_paths: Set of active paths from qBittorrent

        Returns:
            True if path is active, False if orphaned
        """
        # Direct match
        if path in active_paths:
            return True

        # Check if any active path is a child of this path
        # This handles the case where we're checking a parent directory
        # Example: checking /data/incomplete when /data/incomplete/movies/Torrent is active
        try:
            for active_path in active_paths:
                try:
                    # Check if active_path is relative to path (i.e., path is a parent)
                    active_path.relative_to(path)
                    return True
                except ValueError:
                    # active_path is not relative to path
                    continue
        except Exception as e:
            logger.debug(f"Error checking if active path is child of {path}: {e}")

        # Check if this path is a child of any active path
        # This handles files/folders inside an active torrent folder
        # Example: checking /data/incomplete/movies/Torrent/file.mkv when /data/incomplete/movies/Torrent is active
        try:
            for active_path in active_paths:
                try:
                    # Check if path is relative to active_path (i.e., path is a child)
                    path.relative_to(active_path)
                    return True
                except ValueError:
                    # path is not relative to active_path
                    continue
        except Exception as e:
            logger.debug(f"Error checking if {path} is child of active path: {e}")

        return False

    def remove_orphaned_files(self, orphaned_paths: List[Path],
                             dry_run: bool = False) -> Tuple[int, int]:
        """
        Remove orphaned files and directories.

        Args:
            orphaned_paths: List of orphaned paths to remove
            dry_run: If True, don't actually delete anything

        Returns:
            Tuple of (files_removed, dirs_removed)
        """
        files_removed = 0
        dirs_removed = 0

        for path in orphaned_paths:
            try:
                if not path.exists():
                    logger.debug(f"Path no longer exists, skipping: {path}")
                    continue

                if path.is_file():
                    if dry_run:
                        logger.info(f"[DRY RUN] Would remove orphaned file: {path}")
                    else:
                        logger.info(f"Removing orphaned file: {path}")
                        path.unlink()
                    files_removed += 1

                elif path.is_dir():
                    if dry_run:
                        logger.info(f"[DRY RUN] Would remove orphaned directory: {path}")
                    else:
                        logger.info(f"Removing orphaned directory: {path}")
                        shutil.rmtree(path)
                    dirs_removed += 1

            except Exception as e:
                logger.error(f"Error removing orphaned path {path}: {e}")
                continue

        return files_removed, dirs_removed

    def cleanup_orphaned_files(self, scan_dirs: List[str],
                               min_age_hours: float = 1.0,
                               dry_run: bool = False,
                               log_dir: str = "/config") -> Tuple[int, int]:
        """
        Main orchestration method for orphaned file cleanup.

        Args:
            scan_dirs: List of directories to scan (recursively)
            min_age_hours: Minimum age in hours for a file to be considered orphaned
            dry_run: If True, don't actually delete anything
            log_dir: Directory to write orphaned cleanup logs

        Returns:
            Tuple of (files_removed, dirs_removed)
        """
        if not scan_dirs:
            logger.info("No scan directories configured for orphaned file cleanup")
            return 0, 0

        logger.info("Starting orphaned file cleanup")
        logger.info(f"Scan directories: {scan_dirs}")
        logger.info(f"Minimum file age: {min_age_hours} hours")
        logger.info(f"Dry run: {dry_run}")

        # Get all active torrent paths
        active_paths = self.get_active_torrent_paths()

        if not active_paths:
            logger.warning("No active torrent paths found, skipping orphaned file scan")
            return 0, 0

        # Scan for orphaned files (always recursive)
        orphaned_paths = self.scan_for_orphaned_files(scan_dirs, active_paths, min_age_hours)

        logger.info(f"Found {len(orphaned_paths)} orphaned items")

        # Write orphaned files to log
        if orphaned_paths:
            self._write_orphaned_log(orphaned_paths, dry_run, log_dir)

        if not orphaned_paths:
            return 0, 0

        # Remove orphaned files
        return self.remove_orphaned_files(orphaned_paths, dry_run)

    def _write_orphaned_log(self, orphaned_paths: List[Path], dry_run: bool, log_dir: str) -> None:
        """
        Write orphaned files to a dedicated log file.

        Args:
            orphaned_paths: List of orphaned paths
            dry_run: Whether this is a dry run
            log_dir: Directory to write logs to
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_dir_path = Path(log_dir)
            log_dir_path.mkdir(parents=True, exist_ok=True)

            # Main orphaned cleanup log (append mode)
            main_log = log_dir_path / "orphaned_cleanup.log"

            # Dry run review file (overwrite mode)
            if dry_run:
                review_file = log_dir_path / f"orphaned_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

            # Categorize files and directories
            files = [p for p in orphaned_paths if p.is_file()]
            dirs = [p for p in orphaned_paths if p.is_dir()]

            # Write to main log
            with open(main_log, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"Orphaned File Cleanup - {timestamp}\n")
                f.write(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")
                f.write(f"Total orphaned items: {len(orphaned_paths)} ({len(files)} files, {len(dirs)} directories)\n")
                f.write(f"{'='*80}\n\n")

                if files:
                    f.write(f"Orphaned Files ({len(files)}):\n")
                    for file_path in sorted(files):
                        f.write(f"  - {file_path}\n")
                    f.write("\n")

                if dirs:
                    f.write(f"Orphaned Directories ({len(dirs)}):\n")
                    for dir_path in sorted(dirs):
                        f.write(f"  - {dir_path}\n")
                    f.write("\n")

            logger.info(f"Orphaned file list written to: {main_log}")

            # Write dry run review file
            if dry_run:
                with open(review_file, "w", encoding="utf-8") as f:
                    f.write(f"DRY RUN REVIEW - {timestamp}\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(f"The following {len(orphaned_paths)} items would be deleted:\n\n")

                    if files:
                        f.write(f"FILES ({len(files)}):\n")
                        f.write("-" * 80 + "\n")
                        for file_path in sorted(files):
                            try:
                                size = file_path.stat().st_size / (1024**3)  # GB
                                f.write(f"{file_path}\n  Size: {size:.2f} GB\n\n")
                            except Exception:
                                f.write(f"{file_path}\n  Size: Unknown\n\n")

                    if dirs:
                        f.write(f"\nDIRECTORIES ({len(dirs)}):\n")
                        f.write("-" * 80 + "\n")
                        for dir_path in sorted(dirs):
                            try:
                                # Calculate directory size
                                total_size = sum(
                                    f.stat().st_size
                                    for f in dir_path.rglob('*')
                                    if f.is_file()
                                ) / (1024**3)  # GB
                                f.write(f"{dir_path}\n  Size: {total_size:.2f} GB\n\n")
                            except Exception:
                                f.write(f"{dir_path}\n  Size: Unknown\n\n")

                    f.write(f"\n{'='*80}\n")
                    f.write(f"To proceed with deletion, set DRY_RUN=false\n")

                logger.info(f"Dry run review file created: {review_file}")
                logger.info(f"Review this file before running with DRY_RUN=false")

        except Exception as e:
            logger.error(f"Error writing orphaned log: {e}")
