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
    
    # Cleanup settings
    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))
    delete_files = os.environ.get("DELETE_FILES", "True").lower() == "true"
    dry_run = os.environ.get("DRY_RUN", "False").lower() == "true"
    check_paused_only = os.environ.get("CHECK_PAUSED_ONLY", "False").lower() == "true"
    
    # Schedule settings
    interval_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
    
    # Connect to qBittorrent
    try:
        qbt_client = qbittorrentapi.Client(
            host=qb_host,
            port=qb_port,
            username=qb_username,
            password=qb_password,
        )
        qbt_client.auth_log_in()
        logger.info(f"Connected to qBittorrent {qbt_client.app.version} (API: {qbt_client.app.web_api_version})")
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return
    
    try:
        # Get qBittorrent preferences
        prefs = qbt_client.app_preferences()
        
        # Get ratio limit from qBittorrent preferences (if enabled)
        if prefs.get('max_ratio_enabled', False):
            ratio_limit = prefs.get('max_ratio', fallback_ratio)
            logger.info(f"Using qBittorrent's configured ratio limit: {ratio_limit}")
        else:
            ratio_limit = fallback_ratio
            logger.info(f"Ratio limit not enabled in qBittorrent, using fallback: {ratio_limit}")
        
        # Get seeding time limit from qBittorrent preferences (if enabled)
        if prefs.get('max_seeding_time_enabled', False):
            # Convert minutes to days
            days_limit = prefs.get('max_seeding_time', fallback_days * 60 * 24) / (60 * 24)
            logger.info(f"Using qBittorrent's configured seeding time limit: {days_limit:.1f} days")
        else:
            days_limit = fallback_days
            logger.info(f"Seeding time limit not enabled in qBittorrent, using fallback: {days_limit} days")
        
        # Log paused-only mode
        if check_paused_only:
            logger.info("Running in paused-only mode: only checking paused torrents")
        
        # Convert days to seconds for comparison
        seeding_time_limit = days_limit * 24 * 60 * 60
        
        # Get all torrents
        torrents = qbt_client.torrents_info()
        logger.info(f"Found {len(torrents)} torrents")
        
        # Identify torrents meeting deletion criteria
        torrents_to_delete = []
        for torrent in torrents:
            # Check if we should only process paused torrents
            is_paused = torrent.state in ["pausedUP", "pausedDL"]
            
            if check_paused_only and not is_paused:
                continue  # Skip non-paused torrents in paused-only mode
                
            # Check if ratio or seeding time exceeds limits
            if torrent.ratio >= ratio_limit or torrent.seeding_time >= seeding_time_limit:
                days_seeded = torrent.seeding_time / 86400  # Convert seconds to days
                
                torrents_to_delete.append(torrent)
                logger.info(
                    f"Found: {torrent.name[:50]}... "
                    f"(State: {torrent.state}, Ratio: {torrent.ratio:.2f}, "
                    f"Seeded: {days_seeded:.1f} days)"
                )
        
        # Delete torrents if not in dry-run mode
        if torrents_to_delete:
            if dry_run:
                logger.info(f"DRY RUN: Would delete {len(torrents_to_delete)} torrents")
            else:
                hashes = [t.hash for t in torrents_to_delete]
                qbt_client.torrents_delete(delete_files=delete_files, hashes=hashes)
                logger.info(f"Deleted {len(torrents_to_delete)} torrents" + 
                          (" and their files" if delete_files else ""))
        else:
            logger.info("No torrents met the criteria for deletion")
            
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        qbt_client.auth_log_out()
        logger.info("Logged out from qBittorrent")

def main():
    # Get schedule interval from environment
    interval_hours = int(os.environ.get("SCHEDULE_HOURS", "24"))
    interval_seconds = interval_hours * 60 * 60
    run_once = os.environ.get("RUN_ONCE", "False").lower() == "true"
    
    logger.info(f"qBittorrent Cleanup Container started")
    logger.info(f"Schedule: {'Run once' if run_once else f'Every {interval_hours} hours'}")
    
    if run_once:
        # Run once and exit
        run_cleanup()
    else:
        # Run on a schedule
        while True:
            run_cleanup()
            logger.info(f"Next run in {interval_hours} hours. Sleeping...")
            time.sleep(interval_seconds)

if __name__ == "__main__":
    main()