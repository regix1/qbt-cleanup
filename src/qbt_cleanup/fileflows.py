#!/usr/bin/env python3
"""FileFlows integration for protecting files during processing."""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Set, Optional
import requests

from .config import FileFlowsConfig
from .constants import FILEFLOWS_RECENT_THRESHOLD_MINUTES

logger = logging.getLogger(__name__)


class FileFlowsClient:
    """Client for FileFlows API integration."""
    
    def __init__(self, config: FileFlowsConfig):
        """
        Initialize FileFlows client.
        
        Args:
            config: FileFlows configuration
        """
        self.config = config
        self.base_url = f"http://{config.host}:{config.port}/api"
        self._processing_cache: Optional[Set[str]] = None
    
    @property
    def is_enabled(self) -> bool:
        """Check if FileFlows integration is enabled."""
        return self.config.enabled
    
    def test_connection(self) -> bool:
        """
        Test connection to FileFlows API.
        
        Returns:
            True if connection successful
        """
        if not self.is_enabled:
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/status",
                timeout=self.config.timeout
            )
            success = response.status_code == 200
            
            if success:
                logger.debug(f"FileFlows connection test successful")
            else:
                logger.warning(f"FileFlows returned status {response.status_code}")
            
            return success
        except requests.RequestException as e:
            logger.warning(f"FileFlows connection test failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error testing FileFlows connection: {e}")
            return False
    
    def get_processing_files(self) -> List[Dict[str, Any]]:
        """
        Get list of files currently being processed by FileFlows.
        
        Returns:
            List of processing file information
        """
        if not self.is_enabled:
            return []
        
        try:
            response = requests.get(
                f"{self.base_url}/library-file",
                timeout=self.config.timeout
            )
            
            if response.status_code != 200:
                logger.warning(f"FileFlows API returned status {response.status_code}")
                return []
            
            all_files = response.json()
            processing_files = []
            
            for file_info in all_files:
                if self._is_file_processing(file_info):
                    processing_files.append(file_info)
            
            logger.debug(f"Found {len(processing_files)} actively/recently processing files")
            return processing_files
            
        except requests.RequestException as e:
            logger.warning(f"Failed to get FileFlows processing files: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting FileFlows files: {e}")
            return []
    
    def _is_file_processing(self, file_info: Dict[str, Any]) -> bool:
        """
        Check if a file is currently processing or recently processed.
        
        Args:
            file_info: File information from FileFlows
            
        Returns:
            True if file is processing or recently processed
        """
        status = file_info.get('Status', -1)
        
        # Status 2 = actively processing
        if status == 2:
            return True
        
        # Status 1 = completed, check if recent
        if status == 1:
            processing_ended = file_info.get('ProcessingEnded', '')
            if processing_ended and processing_ended != "1970-01-01T00:00:00Z":
                try:
                    end_time = datetime.fromisoformat(processing_ended.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    time_since_end = now - end_time
                    
                    # Protect recently processed files
                    return time_since_end < timedelta(minutes=FILEFLOWS_RECENT_THRESHOLD_MINUTES)
                except (ValueError, TypeError):
                    pass
        
        return False
    
    def build_processing_cache(self) -> Set[str]:
        """
        Build cache of processing file paths for efficient lookup.
        
        Returns:
            Set of file paths being processed
        """
        processing_files = self.get_processing_files()
        processing_paths = set()
        
        for file_info in processing_files:
            # Add relative path if available
            if 'RelativePath' in file_info and file_info['RelativePath']:
                processing_paths.add(file_info['RelativePath'])
            
            # Add filename if available
            if 'Name' in file_info and file_info['Name']:
                processing_paths.add(file_info['Name'])
        
        self._processing_cache = processing_paths
        
        if processing_paths:
            logger.info(f"FileFlows cache: {len(processing_files)} files, {len(processing_paths)} paths")
        
        return processing_paths
    
    def is_torrent_protected(self, torrent_files: List[str]) -> bool:
        """
        Check if any torrent files are being processed by FileFlows.

        Args:
            torrent_files: List of file paths in torrent

        Returns:
            True if any files are being processed
        """
        if not self.is_enabled or not torrent_files:
            return False

        # Use cache if available, otherwise build it
        if self._processing_cache is None:
            self.build_processing_cache()

        if not self._processing_cache:
            return False

        # Build sets of processing names and stems for O(1) lookup
        proc_names = set()
        proc_stems = set()
        for proc_path in self._processing_cache:
            proc_names.add(Path(proc_path).name)
            proc_stems.add(Path(proc_path).stem)

        # Check each torrent file against processing cache
        for file_path in torrent_files:
            file_name = Path(file_path).name
            file_stem = Path(file_path).stem

            # Match on filename or stem
            if file_name in proc_names or file_stem in proc_stems:
                logger.info(f"FileFlows protection active: {file_name}")
                return True

        return False
    
    def clear_cache(self) -> None:
        """Clear the processing cache."""
        self._processing_cache = None