"""Notifications router for the qbt-cleanup web API."""

import logging

from fastapi import APIRouter

from ...config_overrides import ConfigOverrideManager
from ...notifier import Notifier
from ..models import NotificationTestResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/actions/test-notification", response_model=NotificationTestResponse)
def test_notification() -> NotificationTestResponse:
    """Send a test notification to verify notification configuration.

    Creates a temporary Notifier instance from the current effective config
    and sends a test notification.
    """
    config = ConfigOverrideManager.get_effective_config()
    notify_config = config.notifications

    if not notify_config.enabled:
        return NotificationTestResponse(
            success=False,
            message="Notifications are not enabled",
        )

    if not notify_config.urls:
        return NotificationTestResponse(
            success=False,
            message="No notification URLs configured",
        )

    notifier = Notifier(
        enabled=notify_config.enabled,
        urls=notify_config.urls,
        on_delete=notify_config.on_delete,
        on_error=notify_config.on_error,
        on_orphaned=notify_config.on_orphaned,
    )

    success, count = notifier.test()

    if success:
        return NotificationTestResponse(
            success=True,
            message=f"Test notification sent to {count} service(s)",
            services_notified=count,
        )
    else:
        return NotificationTestResponse(
            success=False,
            message="Failed to send test notification. Check your NOTIFY_URLS configuration.",
        )
