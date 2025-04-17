#!/usr/bin/env python3
import logging
import os
import sys
import time
from datetime import datetime

import qbittorrentapi

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("qbt-cleanup")


def run_cleanup():
    # ─── load env ───────────────────────────────────────────────────────────────
    qb_host = os.environ.get("QB_HOST", "localhost")
    qb_port = int(os.environ.get("QB_PORT", "8080"))
    qb_username = os.environ.get("QB_USERNAME", "admin")
    qb_password = os.environ.get("QB_PASSWORD", "adminadmin")

    # Fallback cleanup settings
    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))

    # Private vs non‑private settings
    private_ratio   = float(os.environ.get("PRIVATE_RATIO", str(fallback_ratio)))
    private_days    = float(os.environ.get("PRIVATE_DAYS",  str(fallback_days)))
    nonprivate_ratio= float(os.environ.get("NONPRIVATE_RATIO", str(fallback_ratio)))
    nonprivate_days = float(os.environ.get("NONPRIVATE_DAYS", str(fallback_days)))

    # Overrides for using qB limits
    ignore_qbt_ratio_private    = os.environ.get("IGNORE_QBT_RATIO_PRIVATE", "False").lower() == "true"
    ignore_qbt_ratio_nonprivate = os.environ.get("IGNORE_QBT_RATIO_NONPRIVATE", "False").lower() == "true"
    ignore_qbt_time_private     = os.environ.get("IGNORE_QBT_TIME_PRIVATE", "False").lower() == "true"
    ignore_qbt_time_nonprivate  = os.environ.get("IGNORE_QBT_TIME_NONPRIVATE", "False").lower() == "true"

    delete_files = os.environ.get("DELETE_FILES", "True").lower() == "true"
    dry_run      = os.environ.get("DRY_RUN", "False").lower() == "true"

    # paused-only flags
    check_paused_only          = os.environ.get("CHECK_PAUSED_ONLY", "False").lower() == "true"
    check_private_paused_only  = os.environ.get("CHECK_PRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"
    check_nonprivate_paused_only = os.environ.get("CHECK_NONPRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"

    # ─── connect ────────────────────────────────────────────────────────────────
    try:
        qbt_client = qbittorrentapi.Client(
            host=qb_host,
            port=qb_port,
            username=qb_username,
            password=qb_password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=30),
        )
        qbt_client.auth_log_in()
        ver = qbt_client.app.version
        api_v = qbt_client.app.web_api_version
        logger.info(f"Connected to qBittorrent {ver} (API: {api_v})")
    except Exception as e:
        logger.error(f"Failed to connect/login: {e}")
        return

    # ─── Helper function to detect private torrents by tracker messages ────────────
    def is_private(t):
        try:
            trackers = qbt_client.torrents.trackers(hash=t.hash)
            for tr in trackers:
                if tr.status == 0 and tr.msg and "private" in tr.msg.lower():
                    return True
        except Exception as e:
            logger.warning(f"Could not detect privacy for {t.name}: {e}")
        return False

    try:
        # ─── pull in qB limits ──────────────────────────────────────────────────
        prefs = qbt_client.app.preferences

        if prefs.get("max_ratio_enabled", False):
            global_ratio = prefs.get("max_ratio", fallback_ratio)
            if not ignore_qbt_ratio_private and os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio
            if not ignore_qbt_ratio_nonprivate and os.environ.get("NONPRIVATE_RATIO") is None:
                nonprivate_ratio = global_ratio
            logger.info(f"Using qBittorrent ratios → private={private_ratio}, non-private={nonprivate_ratio}")
        else:
            logger.info(f"No qB ratio limit, using fallback={fallback_ratio}")

        if prefs.get("max_seeding_time_enabled", False):
            gl_min = prefs.get("max_seeding_time", fallback_days * 24 * 60)
            gl_days = gl_min / 60 / 24
            if not ignore_qbt_time_private and os.environ.get("PRIVATE_DAYS") is None:
                private_days = gl_days
            if not ignore_qbt_time_nonprivate and os.environ.get("NONPRIVATE_DAYS") is None:
                nonprivate_days = gl_days
            logger.info(f"Using qB time limits → private={private_days}d, non-private={nonprivate_days}d")
        else:
            logger.info(f"No qB time limit, using fallback={fallback_days}d")

        # Convert days to seconds
        sec_priv    = private_days * 86400
        sec_nonpriv = nonprivate_days * 86400

        # ─── fetch torrents ─────────────────────────────────────────────────────
        torrents = qbt_client.torrents.info()
        logger.info(f"Fetched {len(torrents)} torrents")

        # Count private/non-private for logging
        private_count = 0
        for t in torrents:
            if is_private(t):
                private_count += 1
        nonprivate_count = len(torrents) - private_count
        logger.info(f"Torrent breakdown: {private_count} private, {nonprivate_count} non‑private")

        # Classify and collect
        torrents_to_delete = []
        paused_not_ready   = []
        for t in torrents:
            is_priv = is_private(t)
            paused  = t.state in ("pausedUP", "pausedDL")

            # skip if requiring paused-only and not paused
            if (is_priv and check_private_paused_only and not paused) or \
               (not is_priv and check_nonprivate_paused_only and not paused):
                continue

            ratio_limit = private_ratio   if is_priv else nonprivate_ratio
            time_limit  = sec_priv        if is_priv else sec_nonpriv

            if t.ratio >= ratio_limit or t.seeding_time >= time_limit:
                torrents_to_delete.append((t, is_priv, ratio_limit, time_limit))
                logger.info(f"→ delete: {t.name[:60]!r} (priv={is_priv}, state={t.state}, ratio={t.ratio:.2f}/{ratio_limit:.2f}, time={t.seeding_time/86400:.1f}/{time_limit/86400:.1f}d)")
            elif paused:
                paused_not_ready.append((t, is_priv, ratio_limit, time_limit))

        # Log paused-but-not-ready
        if paused_not_ready:
            logger.info(f"{len(paused_not_ready)} paused torrents not yet at their limits")
        
        # ─── delete ────────────────────────────────────────────────────────────────
        if torrents_to_delete:
            priv_d = sum(1 for t, p, *_ in torrents_to_delete if p)
            np_d   = len(torrents_to_delete) - priv_d
            hashes = [t.hash for t, *_ in torrents_to_delete]

            if dry_run:
                logger.info(f"DRY RUN: would delete {len(hashes)} ({priv_d} priv, {np_d} non‑priv)")
            else:
                try:
                    # Parameter name differs between API versions
                    try:
                        qbt_client.torrents.delete(
                            delete_files=delete_files,
                            torrent_hashes=hashes
                        )
                    except Exception:
                        # Fall back to older API parameter name
                        qbt_client.torrents.delete(
                            delete_files=delete_files,
                            hashes=hashes
                        )
                    logger.info(
                        f"Deleted {len(hashes)} torrents ({priv_d} priv, {np_d} non‑priv)"
                        + (" +files" if delete_files else "")
                    )
                except Exception as e:
                    logger.error(f"Failed to delete torrents: {e}")
        else:
            logger.info("No torrents matched deletion criteria")

    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
    finally:
        try:
            qbt_client.auth_log_out()
            logger.info("Logged out from qBittorrent")
        except:
            pass


def main():
    interval_h = int(os.environ.get("SCHEDULE_HOURS", "24"))
    run_once  = os.environ.get("RUN_ONCE", "False").lower() == "true"

    logger.info("qBittorrent Cleanup Container started")
    logger.info(f"Schedule: {'Run once' if run_once else f'Every {interval_h}h'}")

    if run_once:
        run_cleanup()
    else:
        while True:
            try:
                run_cleanup()
                logger.info(f"Next run in {interval_h}h. Sleeping…")
                time.sleep(interval_h * 3600)
            except KeyboardInterrupt:
                logger.info("Interrupted; exiting")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Uncaught error in main loop: {e}")
                time.sleep(60)


if __name__ == "__main__":
    main()
