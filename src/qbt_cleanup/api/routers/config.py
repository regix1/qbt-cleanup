"""Configuration router for the qbt-cleanup web API."""

import dataclasses
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request

from ...config_overrides import ConfigOverrideManager
from ..app_state import AppState
from ..models import ActionResponse, ConfigResponse, ConfigUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter()


def get_app_state(request: Request) -> AppState:
    """Retrieve the shared AppState from the application."""
    return request.app.state.app_state


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge overlay into base.

    For keys present in both dicts where both values are dicts, merge
    recursively.  Otherwise the overlay value wins.

    Args:
        base: The base dictionary to merge into (not mutated).
        overlay: The overlay dictionary whose values take priority.

    Returns:
        A new merged dictionary.
    """
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@router.get("/config", response_model=ConfigResponse)
def get_config(request: Request) -> ConfigResponse:
    """Return the current effective configuration."""
    config = ConfigOverrideManager.get_effective_config()

    connection_dict = dataclasses.asdict(config.connection)

    return ConfigResponse(
        connection=connection_dict,
        limits=dataclasses.asdict(config.limits),
        behavior=dataclasses.asdict(config.behavior),
        schedule=dataclasses.asdict(config.schedule),
        fileflows=dataclasses.asdict(config.fileflows),
        orphaned=dataclasses.asdict(config.orphaned),
        web=dataclasses.asdict(config.web),
    )


@router.put("/config", response_model=ActionResponse)
def update_config(request: Request, body: ConfigUpdateRequest) -> ActionResponse:
    """Update configuration overrides.

    Merges the provided overrides into the existing override file using
    a deep merge so that nested sections (e.g. ``limits``, ``behavior``)
    are updated field-by-field rather than replaced wholesale.
    Reloads the effective configuration and updates the shared AppState.
    """
    app_state = get_app_state(request)

    current_overrides = ConfigOverrideManager.load_overrides()
    merged_overrides = _deep_merge(current_overrides, body.overrides)
    ConfigOverrideManager.save_overrides(merged_overrides)

    effective_config = ConfigOverrideManager.get_effective_config()
    app_state.update_config(effective_config)

    logger.info("Configuration overrides updated via API")

    return ActionResponse(
        success=True,
        message="Configuration updated successfully",
    )
