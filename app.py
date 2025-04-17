#!/usr/bin/env python3
import logging
import os
import sys
import time
from datetime import datetime

import qbittorrentapi

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("qbt-cleanup")


def run_cleanup():
    # qBittorrent connection settings from environment variables
    qb_host = os.environ.get("QB_HOST", "localhost")
    qb_port = int(os.environ.get("QB_PORT", "8080"))
    qb_username = os.environ.get("QB_USERNAME", "admin")
    qb_password = os.environ.get("QB_PASSWORD", "adminadmin")

    # Fallback cleanup settings
    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))

    # Private torrent settings (default to fallback if not set)
    private_ratio = float(os.environ.get("PRIVATE_RATIO", str(fallback_ratio)))
    private_days = float(os.environ.get("PRIVATE_DAYS", str(fallback_days)))

    # Non‑private torrent settings
    nonprivate_ratio = float(os.environ.get("NONPRIVATE_RATIO", str(fallback_ratio)))
    nonprivate_days = float(os.environ.get("NONPRIVATE_DAYS", str(fallback_days)))

    # Ignore qBittorrent’s built‑in limits?
    ignore_qbt_ratio_private = os.environ.get("IGNORE_QBT_RATIO_PRIVATE", "False").lower() == "true"
    ignore_qbt_ratio_nonprivate = os.environ.get("IGNORE_QBT_RATIO_NONPRIVATE", "False").lower() == "true"
    ignore_qbt_time_private = os.environ.get("IGNORE_QBT_TIME_PRIVATE", "False").lower() == "true"
    ignore_qbt_time_nonprivate = os.environ.get("IGNORE_QBT_TIME_NONPRIVATE", "False").lower() == "true"

    # Other settings
    delete_files = os.environ.get("DELETE_FILES", "True").lower() == "true"
    dry_run = os.environ.get("DRY_RUN", "False").lower() == "true"

    # Legacy paused‑only handling
    check_paused_only = os.environ.get("CHECK_PAUSED_ONLY", "False").lower() == "true"
    check_private_paused_only = os.environ.get("CHECK_PRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"
    check_nonprivate_paused_only = os.environ.get("CHECK_NONPRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"

    # Connect to qBittorrent
    try:
        conn_info = dict(
            host=qb_host,
            port=qb_port,
            username=qb_username,
            password=qb_password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=30),
        )
        qbt_client = qbittorrentapi.Client(**conn_info)
        qbt_client.auth_log_in()

        version = qbt_client.app.version
        api_version = qbt_client.app.web_api_version
        logger.info(f"Connected to qBittorrent {version} (API: {api_version})")

        # Warn if qBittorrent version < 4.1
        try:
            clean_version = version.lstrip('v')
            major, minor = map(int, clean_version.split('.')[:2])
            if major < 4 or (major == 4 and minor < 1):
                logger.warning(f"This script is designed for qBittorrent 4.1.0+ (detected {version})")
        except Exception:
            logger.warning(f"Could not parse qBittorrent version: {version}")

    except qbittorrentapi.LoginFailed as e:
        logger.error(f"Login failed: {e}")
        return
    except qbittorrentapi.APIConnectionError as e:
        logger.error(f"Connection error: {e}")
        return
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    try:
        # Pull in qBittorrent’s own ratio/time limits if enabled
        prefs = qbt_client.app.preferences

        if prefs.get('max_ratio_enabled', False):
            global_ratio = prefs.get('max_ratio', fallback_ratio)
            if not ignore_qbt_ratio_private and os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio
                logger.info(f"Using qBittorrent ratio for private torrents: {private_ratio}")
            if not ignore_qbt_ratio_nonprivate and os.environ.get("NONPRIVATE_RATIO") is None:
                nonprivate_ratio = global_ratio
                logger.info(f"Using qBittorrent ratio for non‑private torrents: {nonprivate_ratio}")

        if prefs.get('max_seeding_time_enabled', False):
            # API reports minutes
            global_minutes = prefs.get('max_seeding_time', fallback_days * 24 * 60)
            global_days = global_minutes / (60 * 24)
            if not ignore_qbt_time_private and os.environ.get("PRIVATE_DAYS") is None:
                private_days = global_days
                logger.info(f"Using qBittorrent seeding time for private torrents: {private_days:.1f} days")
            if not ignore_qbt_time_nonprivate and os.environ.get("NONPRIVATE_DAYS") is None:
                nonprivate_days = global_days
                logger.info(f"Using qBittorrent seeding time for non‑private torrents: {nonprivate_days:.1f} days")

        logger.info(f"Private torrent settings: Ratio={private_ratio:.2f}, Days={private_days:.1f}, "
                    f"PausedOnly={check_private_paused_only}")
        logger.info(f"Non‑private torrent settings: Ratio={nonprivate_ratio:.2f}, Days={nonprivate_days:.1f}, "
                    f"PausedOnly={check_nonprivate_paused_only}")

        private_limit_secs = private_days * 86400
        nonprivate_limit_secs = nonprivate_days * 86400

        # Fetch all torrents
        torrents = qbt_client.torrents.info()
        logger.info(f"Found {len(torrents)} torrents total")

        # Count private vs non‑private
        private_count = sum(1 for t in torrents if getattr(t, 'private', False))
        nonprivate_count = len(torrents) - private_count
        logger.info(f"Torrent breakdown: {private_count} private, {nonprivate_count} non‑private")

        to_delete = []
        not_ready = []

        for t in torrents:
            is_private = getattr(t, 'private', False)
            state = t.state
            is_paused = state in ("pausedUP", "pausedDL")

            # Skip if we’re only checking paused and this torrent isn’t paused
            if is_private and check_private_paused_only and not is_paused:
                continue
            if not is_private and check_nonprivate_paused_only and not is_paused:
                continue

            ratio_limit = private_ratio if is_private else nonprivate_ratio
            time_limit = private_limit_secs if is_private else nonprivate_limit_secs

            if t.ratio >= ratio_limit or t.seeding_time >= time_limit:
                to_delete.append(t)
                days_seeded = t.seeding_time / 86400
                logger.info(f"Queuing for delete: {t.name[:60]} "
                            f"(private={is_private}, state={state}, "
                            f"ratio={t.ratio:.2f}/{ratio_limit:.2f}, "
                            f"seeded={days_seeded:.1f}/{time_limit/86400:.1f} days)")
            elif is_paused:
                not_ready.append((t.name, t.ratio, t.seeding_time / 86400, is_private))

        if not_ready:
            logger.info(f"{len(not_ready)} paused torrents not yet meeting criteria")

        if to_delete:
            private_del = sum(1 for t in to_delete if getattr(t, 'private', False))
            nonpriv_del = len(to_delete) - private_del

            if dry_run:
                logger.info(f"DRY RUN: Would delete {len(to_delete)} torrents "
                            f"({private_del} private, {nonpriv_del} non‑private)")
            else:
                hashes = [t.hash for t in to_delete]
                try:
                    qbt_client.torrents.delete(hashes=hashes, delete_files=delete_files)
                    logger.info(f"Deleted {len(to_delete)} torrents "
                                f"({private_del} private, {nonpriv_del} non‑private)"
                                + (" and their files" if delete_files else ""))
                except Exception as de:
                    logger.error(f"Failed to delete torrents: {de}")
        else:
            logger.info("No torrents met deletion criteria")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

    finally:
        try:
            qbt_client.auth_log_out()
            logger.info("Logged out from qBittorrent")
        except Exception:
            pass


def main():
    interval_h = int(os.environ.get("SCHEDULE_HOURS", "24"))
    run_once = os.environ.get("RUN_ONCE", "False").lower() == "true"

    logger.info("qBittorrent Cleanup Container started")
    logger.info(f"Schedule: {'Run once' if run_once else f'Every {interval_h} hours'}")

    if run_once:
        run_cleanup()
    else:
        interval_s = interval_h * 3600
        while True:
            try:
                run_cleanup()
                logger.info(f"Next run in {interval_h} hours. Sleeping...")
                time.sleep(interval_s)
            except KeyboardInterrupt:
                logger.info("Shutdown signal received, exiting")
                sys.exit(0)
            except Exception as ex:
                logger.error(f"Unexpected error: {ex}, retrying in 60s")
                time.sleep(60)


if __name__ == "__main__":
    main()
