#!/usr/bin/env python3
import logging
import os
import sys
import time

from qbittorrentapi import Client, LoginFailed, APIConnectionError

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("qbt-cleanup")


def detect_private_flag(t):
    """
    Torrents sometimes carry their private flag under
      - t.is_private
      - t.isPrivate
      - t.private
    This helper will pick whichever one exists.
    """
    for attr in ("is_private", "isPrivate", "private"):
        if hasattr(t, attr):
            return bool(getattr(t, attr))
    return False


def run_cleanup():
    # ─── load env ───────────────────────────────────────────────────────────────
    host = os.environ.get("QB_HOST", "localhost")
    port = os.environ.get("QB_PORT", "8080")
    username = os.environ.get("QB_USERNAME", "admin")
    password = os.environ.get("QB_PASSWORD", "adminadmin")

    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))

    private_ratio = float(os.environ.get("PRIVATE_RATIO", str(fallback_ratio)))
    private_days = float(os.environ.get("PRIVATE_DAYS", str(fallback_days)))
    nonpriv_ratio = float(os.environ.get("NONPRIVATE_RATIO", str(fallback_ratio)))
    nonpriv_days = float(os.environ.get("NONPRIVATE_DAYS", str(fallback_days)))

    ignore_ratio_priv = os.environ.get("IGNORE_QBT_RATIO_PRIVATE", "False").lower() == "true"
    ignore_ratio_non = os.environ.get("IGNORE_QBT_RATIO_NONPRIVATE", "False").lower() == "true"
    ignore_time_priv = os.environ.get("IGNORE_QBT_TIME_PRIVATE", "False").lower() == "true"
    ignore_time_non = os.environ.get("IGNORE_QBT_TIME_NONPRIVATE", "False").lower() == "true"

    delete_files = os.environ.get("DELETE_FILES", "True").lower() == "true"
    dry_run = os.environ.get("DRY_RUN", "False").lower() == "true"

    check_paused_only = os.environ.get("CHECK_PAUSED_ONLY", "False").lower() == "true"
    check_priv_paused = os.environ.get("CHECK_PRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"
    check_nonpriv_paused = os.environ.get("CHECK_NONPRIVATE_PAUSED_ONLY", str(check_paused_only)).lower() == "true"

    # ─── connect ────────────────────────────────────────────────────────────────
    try:
        qbt = Client(
            host=f"{host}:{port}",
            username=username,
            password=password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=30),
        )
        qbt.auth_log_in()
        version = qbt.app.version
        api_v = qbt.app.web_api_version
        logger.info(f"Connected to qBittorrent {version} (API: {api_v})")
    except LoginFailed:
        logger.error("Login failed, check your credentials")
        return
    except APIConnectionError:
        logger.error("Cannot reach qBittorrent Web UI")
        return
    except Exception:
        logger.exception("Unexpected error during login/connect")
        return

    # ─── pull in qB limits ──────────────────────────────────────────────────────
    try:
        prefs = qbt.app.preferences
        if prefs.get("max_ratio_enabled", False) and not ignore_ratio_priv:
            global_r = prefs.get("max_ratio", fallback_ratio)
            private_ratio = private_ratio if os.environ.get("PRIVATE_RATIO") else global_r
            nonpriv_ratio = nonpriv_ratio if os.environ.get("NONPRIVATE_RATIO") else global_r
            logger.info(f"Using qB ratio limits: private={private_ratio}, nonpriv={nonpriv_ratio}")

        if prefs.get("max_seeding_time_enabled", False) and not ignore_time_priv:
            gl_min = prefs.get("max_seeding_time", fallback_days * 24 * 60)
            gl_days = gl_min / 60 / 24
            private_days = private_days if os.environ.get("PRIVATE_DAYS") else gl_days
            nonpriv_days = nonpriv_days if os.environ.get("NONPRIVATE_DAYS") else gl_days
            logger.info(f"Using qB time limits: private={private_days}d, nonpriv={nonpriv_days}d")
    except Exception:
        logger.exception("Failed to read qBittorrent preferences, using ENV values")

    logger.info(f"Private  → ratio={private_ratio}, days={private_days}, paused_only={check_priv_paused}")
    logger.info(f"Non‑priv→ ratio={nonpriv_ratio}, days={nonpriv_days}, paused_only={check_nonpriv_paused}")

    sec_priv = private_days * 86400
    sec_nonpriv = nonpriv_days * 86400

    # ─── fetch torrents ─────────────────────────────────────────────────────────
    try:
        torrents = qbt.torrents.info()
        logger.info(f"Fetched {len(torrents)} torrents")
    except Exception:
        logger.exception("Could not list torrents")
        qbt.auth_log_out()
        return

    # ─── debug first torrent ────────────────────────────────────────────────────
    if torrents:
        # safe repr to show the JSON-like contents
        logger.debug("raw first torrent → %r", torrents[0])

    # ─── classify ────────────────────────────────────────────────────────────────
    priv_count = sum(1 for t in torrents if detect_private_flag(t))
    logger.info(f"Detected {priv_count} private, {len(torrents) - priv_count} non‑private")

    to_delete = []
    not_ready = []

    for t in torrents:
        try:
            is_priv = detect_private_flag(t)
            state = t.state
            paused = state in ("pausedUP", "pausedDL")

            # skip if we only care about paused:
            if (is_priv and check_priv_paused and not paused) or (
               not is_priv and check_nonpriv_paused and not paused):
                continue

            ratio_lim = private_ratio if is_priv else nonpriv_ratio
            time_lim = sec_priv if is_priv else sec_nonpriv

            if t.ratio >= ratio_lim or t.seeding_time >= time_lim:
                to_delete.append(t)
                logger.info(
                    f"→ delete: {t.name[:60]!r} "
                    f"(priv={is_priv}, state={state}, "
                    f"ratio={t.ratio:.2f}/{ratio_lim:.2f}, "
                    f"time={t.seeding_time/86400:.1f}/{time_lim/86400:.1f}d)"
                )
            elif paused:
                not_ready.append(t)
        except Exception:
            logger.exception(f"Error evaluating {t.name}")

    if not_ready:
        logger.info(f"{len(not_ready)} paused torrents not yet at their limits")

    # ─── do delete ──────────────────────────────────────────────────────────────
    if to_delete:
        priv_d = sum(detect_private_flag(t) for t in to_delete)
        np_d = len(to_delete) - priv_d

        if dry_run:
            logger.info(f"DRY RUN: would delete {len(to_delete)} ({priv_d} priv, {np_d} non‑priv)")
        else:
            hashes = [t.hash for t in to_delete]
            try:
                qbt.torrents.delete(hashes=hashes, delete_files=delete_files)
                logger.info(
                    f"Deleted {len(to_delete)} torrents ({priv_d} priv, {np_d} non‑priv)"
                    + (" +files" if delete_files else "")
                )
            except Exception:
                logger.exception("Failed to delete torrents")
    else:
        logger.info("No torrents matched deletion criteria")

    # ─── logout ────────────────────────────────────────────────────────────────
    try:
        qbt.auth_log_out()
    except Exception:
        pass


def main():
    interval_h = int(os.environ.get("SCHEDULE_HOURS", "24"))
    run_once = os.environ.get("RUN_ONCE", "False").lower() == "true"

    logger.info("### qBittorrent cleanup starting")
    if run_once:
        run_cleanup()
    else:
        logger.info(f"### looping every {interval_h}h")
        while True:
            try:
                run_cleanup()
                logger.info(f"Sleeping {interval_h}h …")
                time.sleep(interval_h * 3600)
            except KeyboardInterrupt:
                logger.info("Interrupted; exiting")
                sys.exit(0)
            except Exception:
                logger.exception("Uncaught error in main loop; retrying in 60s")
                time.sleep(60)


if __name__ == "__main__":
    main()
