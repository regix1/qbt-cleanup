#!/usr/bin/env python3
"""FileFlows integration for protecting files during processing."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Set, Optional, Tuple
import requests

from .config import FileFlowsConfig

logger = logging.getLogger(__name__)


class FileFlowsClient:
    """Client for FileFlows API integration using /api/status endpoint."""

    def __init__(self, config: FileFlowsConfig):
        self.config = config
        self.base_url = f"http://{config.host}:{config.port}/api"
        self._proc_names: Set[str] = set()
        self._proc_stems: Set[str] = set()
        self._cache_built: bool = False
        self._last_successful_names: Optional[Set[str]] = None
        self._last_successful_stems: Optional[Set[str]] = None
        self._api_failures: int = 0

    @property
    def is_enabled(self) -> bool:
        """Check if FileFlows integration is enabled."""
        return self.config.enabled

    def _fetch_status(self) -> Optional[Dict[str, Any]]:
        """
        Fetch /api/status from FileFlows.

        Returns:
            Parsed status dict, or None on failure.
        """
        try:
            response = requests.get(
                f"{self.base_url}/status",
                timeout=self.config.timeout,
            )

            if response.status_code != 200:
                logger.warning(f"FileFlows API returned status {response.status_code}")
                self._api_failures += 1
                return None

            self._api_failures = 0
            return response.json()

        except requests.Timeout:
            logger.warning("FileFlows API request timed out")
            self._api_failures += 1
            return None
        except requests.ConnectionError as conn_err:
            logger.warning(f"FileFlows connection failed: {conn_err}")
            self._api_failures += 1
            return None
        except requests.RequestException as req_err:
            logger.warning(f"FileFlows API error: {req_err}")
            self._api_failures += 1
            return None
        except ValueError as json_err:
            logger.error(f"FileFlows returned invalid JSON: {json_err}")
            self._api_failures += 1
            return None

    def test_connection(self) -> bool:
        """
        Test connection to FileFlows and pre-populate the processing cache.

        Returns:
            True if connection successful.
        """
        if not self.is_enabled:
            return False

        status = self._fetch_status()
        if status is None:
            return False

        processing_files: List[Dict[str, Any]] = status.get("processingFiles", [])
        processing_count: int = status.get("processing", 0)
        queue_count: int = status.get("queue", 0)

        self._build_sets(processing_files)
        self._cache_built = True

        logger.info(
            f"[FileFlows] Connected | processing: {processing_count} | queue: {queue_count}"
        )
        return True

    def get_processing_files(self) -> Optional[List[Dict[str, Any]]]:
        """
        Get files currently being processed by FileFlows via /api/status.

        Returns:
            List of processing file dicts, or None on failure.
        """
        if not self.is_enabled:
            return []

        status = self._fetch_status()
        if status is None:
            return None

        processing_files: List[Dict[str, Any]] = status.get("processingFiles", [])
        logger.debug(f"Found {len(processing_files)} actively processing files")
        return processing_files

    def build_processing_cache(self) -> Tuple[Set[str], Set[str]]:
        """
        Build cache of processing file names/stems for efficient lookup.

        On API failure, falls back to the last successful cache.

        Returns:
            Tuple of (proc_names, proc_stems) sets.
        """
        processing_files = self.get_processing_files()

        if processing_files is None:
            if self._last_successful_names is not None:
                logger.warning(
                    f"Using cached FileFlows data ({len(self._last_successful_names)} names) "
                    f"due to API failure (attempt {self._api_failures})"
                )
                self._proc_names = self._last_successful_names
                self._proc_stems = self._last_successful_stems or set()
                return self._proc_names, self._proc_stems

            logger.warning("FileFlows API failed and no cache available - protection disabled")
            self._proc_names = set()
            self._proc_stems = set()
            return self._proc_names, self._proc_stems

        self._build_sets(processing_files)
        self._cache_built = True
        return self._proc_names, self._proc_stems

    def _build_sets(self, processing_files: List[Dict[str, Any]]) -> None:
        """
        Build proc_names and proc_stems sets from a list of processingFiles entries.

        Each entry has 'name' (full path) and 'relativePath'.
        """
        names: Set[str] = set()
        stems: Set[str] = set()

        for entry in processing_files:
            full_path: str = entry.get("name", "")
            relative_path: str = entry.get("relativePath", "")

            for path_str in (full_path, relative_path):
                if path_str:
                    p = Path(path_str)
                    names.add(p.name)
                    stems.add(p.stem)

        self._proc_names = names
        self._proc_stems = stems
        self._last_successful_names = names
        self._last_successful_stems = stems

        if names:
            logger.info(f"FileFlows cache: {len(processing_files)} files, {len(names)} names")

    def is_torrent_protected(self, torrent_files: List[str]) -> bool:
        """
        Check if any torrent files are being processed by FileFlows.

        Args:
            torrent_files: List of file paths in the torrent.

        Returns:
            True if any files are being processed.
        """
        if not self.is_enabled or not torrent_files:
            return False

        if not self._cache_built:
            self.build_processing_cache()

        if not self._proc_names:
            return False

        for file_path in torrent_files:
            p = Path(file_path)
            if p.name in self._proc_names or p.stem in self._proc_stems:
                logger.info(f"FileFlows protection active: {p.name}")
                return True

        return False

    def clear_cache(self) -> None:
        """Clear the processing cache."""
        self._proc_names = set()
        self._proc_stems = set()
        self._cache_built = False
        self._last_successful_names = None
        self._last_successful_stems = None
