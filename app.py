#!/usr/bin/env python3
import logging
import os
import sys
import time
from datetime import datetime

import qbittorrentapi

# ─── Set up logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("qbt-cleanup")


def run_cleanup():
    # ─── qBittorrent connection settings from environment ────────────────────────
    qb_host     = os.environ.get("QB_HOST", "localhost")
    qb_port     = os.environ.get("QB_PORT", "8080")
    qb_username = os.environ.get("QB_USERNAME", "admin")
    qb_password = os.environ.get("QB_PASSWORD", "adminadmin")

    # ─── Cleanup settings (fallback) ────────────────────────────────────────────
    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days  = float(os.environ.get("FALLBACK_DAYS", "7"))

    # ─── Private torrents settings ──────────────────────────────────────────────
    private_ratio = float(os.environ.get("PRIVATE_RATIO", str(fallback_ratio)))
    private_days  = float(os.environ.get("PRIVATE_DAYS", str(fallback_days)))

    # ─── Non‑private torrents settings ──────────────────────────────────────────
    nonprivate_ratio = float(os.environ.get("NONPRIVATE_RATIO", str(fallback_ratio)))
    nonprivate_days  = float(os.environ.get("NONPRIVATE_DAYS", str(fallback_days)))

    # ─── Overrides ──────────────────────────────────────────────────────────────
    ignore_qbt_ratio_private    = os.environ.get("IGNORE_QBT_RATIO_PRIVATE", "False").lower() == "true"
    ignore_qbt_ratio_nonprivate = os.environ.get("IGNORE_QBT_RATIO_NONPRIVATE", "False").lower() == "true"
    ignore_qbt_time_private     = os.environ.get("IGNORE_QBT_TIME_PRIVATE", "False").lower() == "true"
    ignore_qbt_time_nonprivate  = os.environ.get("IGNORE_QBT_TIME_NONPRIVATE", "False").lower() == "true"

    # ─── Other settings ─────────────────────────────────────────────────────────
    delete_files = os.environ.get("DELETE_FILES", "True").lower() == "true"
    dry_run      = os.environ.get("DRY_RUN", "False").lower() == "true"

    # ─── Paused‑only settings ───────────────────────────────────────────────────
    check_paused_only               = os.environ.get("CHECK_PAUSED_ONLY", "False").lower() == "true"
    check_private_paused_only       = os.environ.get("CHECK_PRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"
    check_nonprivate_paused_only    = os.environ.get("CHECK_NONPRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"

    # ─── Connect to qBittorrent ─────────────────────────────────────────────────
    try:
        conn_args = dict(
            host=f"{qb_host}:{qb_port}",
            username=qb_username,
            password=qb_password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=30),
        )
        qbt = qbittorrentapi.Client(**conn_args)
        qbt.auth_log_in()
        version = qbt.app.version
        api_v   = qbt.app.web_api_version
        logger.info(f"Connected to qBittorrent {version} (API: {api_v})")

        # Warn if version < 4.1.0
        try:
            v = version.lstrip("v").split(".")
            if int(v[0]) < 4 or (int(v[0]) == 4 and int(v[1]) < 1):
                logger.warning("This script is designed for qBittorrent 4.1.0+")
        except Exception:
            logger.warning(f"Could not parse qBittorrent version: {version}")
    except qbittorrentapi.LoginFailed as e:
        logger.error(f"Login failed: {e}")
        return
    except qbittorrentapi.APIConnectionError as e:
        logger.error(f"Connection error: {e}")
        return
    except Exception as e:
        logger.error(f"Unexpected error connecting: {e}")
        return

    # ─── Helper: detect private flag by parsing tracker messages ────────────────
    def is_private(t):
        try:
            trackers = qbt.torrents.trackers(hash=t.hash)
            for tr in trackers:
                if tr.status == 0 and tr.msg and "private" in tr.msg.lower():
                    return True
        except Exception as e:
            logger.warning(f"Could not detect privacy for {t.name}: {e}")
        return False

    # ─── Pull in qBittorrent preferences for ratio/time limits ─────────────────
    try:
        prefs = qbt.app.preferences

        # Ratio limits
        if prefs.get("max_ratio_enabled", False):
            global_ratio = prefs.get("max_ratio", fallback_ratio)
            if not ignore_qbt_ratio_private and os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio
            if not ignore_qbt_ratio_nonprivate and os.environ.get("NONPRIVATE_RATIO") is None:
                nonprivate_ratio = global_ratio
            logger.info(f"Using ratio limits → private={private_ratio}, nonpriv={nonprivate_ratio}")
        else:
            logger.info("Ratio limit not enabled; using fallbacks")

        # Seeding time limits
        if prefs.get("max_seeding_time_enabled", False):
            # qB gives minutes
            gl_min = prefs.get("max_seeding_time", fallback_days * 24 * 60)
            gl_days = gl_min / 60 / 24
            if not ignore_qbt_time_private and os.environ.get("PRIVATE_DAYS") is None:
                private_days = gl_days
            if not ignore_qbt_time_nonprivate and os.environ.get("NONPRIVATE_DAYS") is None:
                nonprivate_days = gl_days
            logger.info(f"Using time limits → private={private_days:.1f}d, nonpriv={nonprivate_days:.1f}d")
        else:
            logger.info("Seeding time limit not enabled; using fallbacks")
    except Exception as e:
        logger.warning(f"Failed to read preferences: {e}")

    # ─── Log effective settings ─────────────────────────────────────────────────
    logger.info(f"Private torrents → ratio={private_ratio:.2f}, days={private_days:.1f}, paused_only={check_private_paused_only}")
    logger.info(f"Non‑private torrents → ratio={nonprivate_ratio:.2f}, days={nonprivate_days:.1f}, paused_only={check_nonprivate_paused_only}")

    sec_priv    = private_days  * 86400
    sec_nonpriv = nonprivate_days * 86400

    # ─── Fetch all torrents ──────────────────────────────────────────────────────
    try:
        torrents = qbt.torrents.info()
        logger.info(f"Fetched {len(torrents)} torrents")
    except Exception as e:
        logger.error(f"Could not list torrents: {e}")
        qbt.auth_log_out()
        return

    # ─── Count by privacy ────────────────────────────────────────────────────────
    private_count    = sum(1 for t in torrents if is_private(t))
    nonprivate_count = len(torrents) - private_count
    logger.info(f"Torrent breakdown: {private_count} private, {nonprivate_count} non‑private")

    # ─── Identify which to delete ────────────────────────────────────────────────
    to_delete    = []
    not_ready    = []

    for t in torrents:
        priv   = is_private(t)
        state  = t.state
        paused = state in ("pausedUP", "pausedDL")

        # Skip based on paused-only flags
        if (priv   and check_private_paused_only   and not paused) or \
           (not priv and check_nonprivate_paused_only and not paused):
            continue

        ratio_lim = private_ratio    if priv else nonprivate_ratio
        time_lim  = sec_priv         if priv else sec_nonpriv

        if t.ratio >= ratio_lim or t.seeding_time >= time_lim:
            to_delete.append((t, priv, ratio_lim, time_lim))
            logger.info(f"→ delete: {t.name[:60]!r} (priv={priv}, state={state}, ratio={t.ratio:.2f}/{ratio_lim:.2f}, time={t.seeding_time/86400:.1f}/{time_lim/86400:.1f}d)")
        elif paused:
            not_ready.append((t, priv, ratio_lim, time_lim))

    if not_ready:
        logger.info(f"{len(not_ready)} paused torrents not yet at their limits")

    # ─── Perform deletion ───────────────────────────────────────────────────────
    if to_delete:
        priv_d = sum(1 for t, p, _, _ in to_delete if p)
        np_d   = len(to_delete) - priv_d
        hashes = [t.hash for t, _, _, _ in to_delete]

        if dry_run:
            logger.info(f"DRY RUN: would delete {len(hashes)} ({priv_d} priv, {np_d} non‑priv)")
        else:
            try:
                qbt.torrents.delete(delete_files=delete_files, hashes=hashes)
                logger.info(f"Deleted {len(hashes)} torrents ({priv_d} priv, {np_d} non‑priv)" + (" +files" if delete_files else ""))
            except Exception as e:
                logger.error(f"Failed to delete torrents: {e}")
    else:
        logger.info("No torrents matched deletion criteria")

    # ─── Logout ─────────────────────────────────────────────────────────────────
    try:
        qbt.auth_log_out()
        logger.info("Logged out from qBittorrent")
    except Exception:
        pass


def main():
    interval_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
    interval_secs  = interval_hours * 3600
    run_once       = os.environ.get("RUN_ONCE", "False").lower() == "true"

    logger.info("### qBittorrent cleanup starting")
    if run_once:
        run_cleanup()
    else:
        logger.info(f"### looping every {interval_hours}h")
        while True:
            try:
                run_cleanup()
                logger.info(f"Sleeping {interval_hours}h …")
                time.sleep(interval_secs)
            except KeyboardInterrupt:
                logger.info("Interrupted; exiting")
                sys.exit(0)
            except Exception as e:
                logger.error(f"Uncaught error in main loop: {e}")
                time.sleep(60)


if __name__ == "__main__":
    main()
