#!/usr/bin/env python3
"""Utility functions for qBittorrent cleanup."""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


_BOOL_TRUE = frozenset(('true', '1', 'yes', 'on'))
_BOOL_FALSE = frozenset(('false', '0', 'no', 'off'))


def parse_bool(env_var: str, default: bool = False) -> bool:
    """
    Parse boolean environment variable.

    Args:
        env_var: Environment variable name
        default: Default value if not set

    Returns:
        Parsed boolean value
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    lower = raw.strip().lower()
    if lower not in _BOOL_TRUE and lower not in _BOOL_FALSE:
        logger.warning(f"{env_var}='{raw}' is not a recognized boolean, treating as False")
    return lower in _BOOL_TRUE


def parse_float(env_var: str, default: float, min_val: Optional[float] = None) -> float:
    """
    Parse float environment variable with optional minimum value.
    
    Args:
        env_var: Environment variable name
        default: Default value if not set
        min_val: Minimum allowed value
        
    Returns:
        Parsed float value
    """
    try:
        value = float(os.environ.get(env_var, str(default)))
        if min_val is not None and value < min_val:
            logger.warning(f"{env_var}={value} is below minimum {min_val}, using minimum")
            return min_val
        return value
    except (ValueError, TypeError):
        logger.warning(f"Invalid float value for {env_var}, using default {default}")
        return default


def parse_int(env_var: str, default: int, min_val: Optional[int] = None) -> int:
    """
    Parse integer environment variable with optional minimum value.
    
    Args:
        env_var: Environment variable name
        default: Default value if not set
        min_val: Minimum allowed value
        
    Returns:
        Parsed integer value
    """
    try:
        value = int(os.environ.get(env_var, str(default)))
        if min_val is not None and value < min_val:
            logger.warning(f"{env_var}={value} is below minimum {min_val}, using minimum")
            return min_val
        return value
    except (ValueError, TypeError):
        logger.warning(f"Invalid integer value for {env_var}, using default {default}")
        return default


def truncate_name(name: str, max_length: int = 60) -> str:
    """
    Truncate a torrent name for display.
    
    Args:
        name: Torrent name to truncate
        max_length: Maximum length
        
    Returns:
        Truncated name with ellipsis if needed
    """
    if len(name) <= max_length:
        return name
    return name[:max_length - 3] + "..."
