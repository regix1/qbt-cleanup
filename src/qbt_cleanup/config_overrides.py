#!/usr/bin/env python3
"""Configuration override management for qBittorrent cleanup.

Allows runtime configuration changes to be persisted to a JSON file
and overlaid on top of environment-based defaults.
"""

import json
import os
from dataclasses import fields
from pathlib import Path
from typing import Any

from .config import Config


class ConfigOverrideManager:
    """Manages configuration overrides stored in a JSON file."""

    OVERRIDE_FILE = "/config/config_overrides.json"

    @staticmethod
    def load_overrides() -> dict:
        """Read overrides from the JSON file.

        Returns:
            Dictionary of override values, or empty dict if file not found
            or contains invalid JSON.
        """
        try:
            with open(ConfigOverrideManager.OVERRIDE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def save_overrides(overrides: dict) -> None:
        """Write overrides atomically to the JSON file.

        Writes to a temporary file first, then renames to avoid
        partial writes on crash.

        Args:
            overrides: Dictionary of override values to persist.
        """
        override_path = Path(ConfigOverrideManager.OVERRIDE_FILE)
        override_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = override_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, indent=2)

        # Atomic rename (on POSIX; on Windows this replaces if target exists on Python 3.3+)
        tmp_path.replace(override_path)

    @staticmethod
    def _apply_overrides(instance: Any, overrides: dict) -> None:
        """Recursively apply override values to a dataclass instance.

        Args:
            instance: A dataclass instance to modify in place.
            overrides: Dictionary of field names to values. For nested
                       dataclass fields, the value should be a dict.
        """
        field_map = {f.name: f for f in fields(instance)}

        for key, value in overrides.items():
            if key not in field_map:
                continue

            current_value = getattr(instance, key)

            # If the current value is a dataclass, recurse into it
            if hasattr(current_value, "__dataclass_fields__") and isinstance(value, dict):
                ConfigOverrideManager._apply_overrides(current_value, value)
            else:
                setattr(instance, key, value)

    @staticmethod
    def get_effective_config() -> Config:
        """Build a Config from environment variables, then overlay JSON overrides.

        Returns:
            A Config instance with environment defaults overridden by any
            values found in the override JSON file.
        """
        config = Config.from_environment()
        overrides = ConfigOverrideManager.load_overrides()

        if overrides:
            ConfigOverrideManager._apply_overrides(config, overrides)

        return config
