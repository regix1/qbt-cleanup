#!/usr/bin/env python3
"""Notification support via Apprise for qBittorrent cleanup events."""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CleanupSummary:
    """Summary of a cleanup run for notification purposes."""
    total_checked: int = 0
    total_deleted: int = 0
    private_deleted: int = 0
    public_deleted: int = 0
    stalled_deleted: int = 0
    unregistered_deleted: int = 0
    orphaned_files_removed: int = 0
    orphaned_dirs_removed: int = 0
    rechecked_torrents: int = 0
    resumed_torrents: int = 0


class Notifier:
    """Apprise-based notification sender for cleanup events.

    Wraps the Apprise library to send notifications to any of 90+
    supported services (Discord, Slack, Telegram, Pushover, email,
    webhooks, etc.) using simple URL-based configuration.

    If Apprise is not installed or no URLs are configured, all
    notification calls become no-ops.
    """

    def __init__(self, enabled: bool, urls: list[str],
                 on_delete: bool = True, on_error: bool = True,
                 on_orphaned: bool = True) -> None:
        """Initialize the notifier.

        Args:
            enabled: Whether notifications are enabled
            urls: List of Apprise notification URLs
            on_delete: Notify on torrent deletions
            on_error: Notify on scan errors
            on_orphaned: Notify on orphaned file cleanup
        """
        self._enabled = enabled
        self._on_delete = on_delete
        self._on_error = on_error
        self._on_orphaned = on_orphaned
        self._apprise = None

        if not enabled or not urls:
            if enabled and not urls:
                logger.warning("[Notifications] Enabled but no NOTIFY_URLS configured")
            return

        try:
            import apprise
            self._apprise = apprise.Apprise()
            for url in urls:
                self._apprise.add(url)
            loaded = len(self._apprise)
            logger.info(f"[Notifications] Initialized with {loaded} service(s)")
        except ImportError:
            logger.warning(
                "[Notifications] Apprise library not installed. "
                "Install with: pip install apprise"
            )
            self._enabled = False

    @property
    def is_active(self) -> bool:
        """Check if notifications are active and configured."""
        return self._enabled and self._apprise is not None

    def notify_scan_complete(self, summary: CleanupSummary) -> int:
        """Send notification for a completed scan.

        Args:
            summary: Cleanup run summary

        Returns:
            Number of services successfully notified
        """
        if not self.is_active:
            return 0

        if not self._on_delete and summary.total_deleted == 0:
            return 0

        parts: list[str] = []

        if summary.total_deleted > 0:
            parts.append(f"Deleted {summary.total_deleted} torrent(s)")
            details: list[str] = []
            if summary.private_deleted > 0:
                details.append(f"{summary.private_deleted} private")
            if summary.public_deleted > 0:
                details.append(f"{summary.public_deleted} public")
            if summary.stalled_deleted > 0:
                details.append(f"{summary.stalled_deleted} stalled")
            if summary.unregistered_deleted > 0:
                details.append(f"{summary.unregistered_deleted} unregistered")
            if details:
                parts.append(f"  ({', '.join(details)})")
        else:
            parts.append("No torrents needed cleanup")

        if summary.rechecked_torrents > 0:
            parts.append(f"Rechecked {summary.rechecked_torrents} torrent(s)")
        if summary.resumed_torrents > 0:
            parts.append(f"Resumed {summary.resumed_torrents} torrent(s)")

        if summary.orphaned_files_removed > 0 and self._on_orphaned:
            parts.append(
                f"Removed {summary.orphaned_files_removed} orphaned file(s), "
                f"{summary.orphaned_dirs_removed} empty dir(s)"
            )

        title = "qbt-cleanup: Scan Complete"
        body = "\n".join(parts)
        body += f"\n\nTotal checked: {summary.total_checked}"

        return self._send(title=title, body=body, notify_type="info")

    def notify_error(self, error_message: str, context: str = "Cleanup") -> int:
        """Send notification for an error.

        Args:
            error_message: The error message
            context: Context where the error occurred

        Returns:
            Number of services successfully notified
        """
        if not self.is_active or not self._on_error:
            return 0

        title = f"qbt-cleanup: {context} Failed"
        body = f"Error: {error_message}"

        return self._send(title=title, body=body, notify_type="failure")

    def notify_orphaned_complete(self, files_removed: int, dirs_removed: int,
                                  dry_run: bool = False) -> int:
        """Send notification for orphaned file cleanup completion.

        Args:
            files_removed: Number of files removed
            dirs_removed: Number of directories removed
            dry_run: Whether this was a dry run

        Returns:
            Number of services successfully notified
        """
        if not self.is_active or not self._on_orphaned:
            return 0

        if files_removed == 0 and dirs_removed == 0:
            return 0

        prefix = "[DRY RUN] Would remove" if dry_run else "Removed"
        title = "qbt-cleanup: Orphaned Cleanup"
        body = f"{prefix} {files_removed} file(s) and {dirs_removed} directory(ies)"

        return self._send(title=title, body=body, notify_type="info")

    def test(self) -> tuple[bool, int]:
        """Send a test notification to verify configuration.

        Returns:
            Tuple of (success, services_notified)
        """
        if not self.is_active:
            return False, 0

        count = self._send(
            title="qbt-cleanup: Test Notification",
            body="This is a test notification from qbt-cleanup. "
                 "If you see this, notifications are working correctly!",
            notify_type="info",
        )
        return count > 0, count

    def _send(self, title: str, body: str, notify_type: str = "info") -> int:
        """Send a notification via Apprise.

        Args:
            title: Notification title
            body: Notification body text
            notify_type: Apprise notify type (info, success, warning, failure)

        Returns:
            Number of services successfully notified
        """
        if not self._apprise:
            return 0

        try:
            import apprise
            type_map = {
                "info": apprise.NotifyType.INFO,
                "success": apprise.NotifyType.SUCCESS,
                "warning": apprise.NotifyType.WARNING,
                "failure": apprise.NotifyType.FAILURE,
            }
            apprise_type = type_map.get(notify_type, apprise.NotifyType.INFO)

            result = self._apprise.notify(
                title=title,
                body=body,
                notify_type=apprise_type,
            )
            count = len(self._apprise)
            if result:
                logger.debug(f"[Notifications] Sent to {count} service(s): {title}")
            else:
                logger.warning(f"[Notifications] Failed to send: {title}")
            return count if result else 0
        except Exception as e:
            logger.error(f"[Notifications] Error sending notification: {e}")
            return 0
