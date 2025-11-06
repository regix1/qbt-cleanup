#!/usr/bin/env python3
"""Orphaned files scanner and cleanup functionality."""

import logging
import os
import shutil
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
            return active_paths

        except Exception as e:
            logger.error(f"Failed to get active torrent paths: {e}")
            return set()

    def scan_for_orphaned_files(self, scan_dirs: List[str],
                                active_paths: Set[Path]) -> List[Path]:
        """
        Scan directories for orphaned files and folders.

        Args:
            scan_dirs: List of directory paths to scan
            active_paths: Set of paths that are actively tracked

        Returns:
            List of orphaned paths (files or directories)
        """
        orphaned = []

        for scan_dir_str in scan_dirs:
            scan_dir = Path(scan_dir_str).resolve()

            if not scan_dir.exists():
                logger.warning(f"Scan directory does not exist: {scan_dir}")
                continue

            if not scan_dir.is_dir():
                logger.warning(f"Scan path is not a directory: {scan_dir}")
                continue

            logger.info(f"Scanning directory for orphaned files: {scan_dir}")

            try:
                # Get all immediate children (files and directories)
                for item in scan_dir.iterdir():
                    item_resolved = item.resolve()

                    # Check if this item or any of its parents are in active paths
                    if not self._is_path_active(item_resolved, active_paths):
                        orphaned.append(item_resolved)
                        logger.debug(f"Found orphaned item: {item_resolved}")

            except Exception as e:
                logger.error(f"Error scanning directory {scan_dir}: {e}")
                continue

        return orphaned

    def _is_path_active(self, path: Path, active_paths: Set[Path]) -> bool:
        """
        Check if a path or any of its children are in the active paths set.

        Args:
            path: Path to check
            active_paths: Set of active paths

        Returns:
            True if path is active, False if orphaned
        """
        # Direct match
        if path in active_paths:
            return True

        # Check if any active path is a child of this path
        # This handles the case where we're checking a parent directory
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
            logger.debug(f"Error checking path ancestry for {path}: {e}")

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
                               dry_run: bool = False) -> Tuple[int, int]:
        """
        Main orchestration method for orphaned file cleanup.

        Args:
            scan_dirs: List of directories to scan
            dry_run: If True, don't actually delete anything

        Returns:
            Tuple of (files_removed, dirs_removed)
        """
        if not scan_dirs:
            logger.info("No scan directories configured for orphaned file cleanup")
            return 0, 0

        logger.info("Starting orphaned file cleanup")
        logger.info(f"Scan directories: {scan_dirs}")
        logger.info(f"Dry run: {dry_run}")

        # Get all active torrent paths
        active_paths = self.get_active_torrent_paths()

        if not active_paths:
            logger.warning("No active torrent paths found, skipping orphaned file scan")
            return 0, 0

        # Scan for orphaned files
        orphaned_paths = self.scan_for_orphaned_files(scan_dirs, active_paths)

        logger.info(f"Found {len(orphaned_paths)} orphaned items")

        if not orphaned_paths:
            return 0, 0

        # Remove orphaned files
        return self.remove_orphaned_files(orphaned_paths, dry_run)
