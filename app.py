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
        # Create connection with configurable timeout for better reliability
        conn_info = dict(
            host=qb_host,
            port=qb_port,
            username=qb_username,
            password=qb_password,
            VERIFY_WEBUI_CERTIFICATE=False,  # Set to True in production with proper cert
            REQUESTS_ARGS=dict(timeout=30)   # Configurable timeout
        )
        
        qbt_client = qbittorrentapi.Client(**conn_info)
        qbt_client.auth_log_in()
        
        # Check and log version information
        version = qbt_client.app.version
        api_version = qbt_client.app.web_api_version
        logger.info(f"Connected to qBittorrent {version} (API: {api_version})")
        
        # Check minimum supported version (adjust as needed)
        # Parse version string manually since version_tuple might not exist
        try:
            # Remove 'v' prefix if it exists
            clean_version = version.lstrip('v')
            version_parts = clean_version.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1])
            if major < 4 or (major == 4 and minor < 1):
                logger.warning(f"This script is designed for qBittorrent 4.1.0+ (detected {version})")
        except (ValueError, IndexError):
            # If we can't parse the version, just log and continue
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
        # Get qBittorrent preferences
        prefs = qbt_client.app.preferences
        
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
        torrents = qbt_client.torrents.info()
        logger.info(f"Found {len(torrents)} torrents")
        
        # Count paused torrents
        paused_torrents = [t for t in torrents if t.state in ["pausedUP", "pausedDL"]]
        if check_paused_only:
            logger.info(f"Found {len(paused_torrents)} paused torrents to check")
        
        # Identify torrents meeting deletion criteria
        torrents_to_delete = []
        paused_but_not_ready = []
        
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
            elif is_paused:
                days_seeded = torrent.seeding_time / 86400  # Convert seconds to days
                paused_but_not_ready.append({
                    "name": torrent.name,
                    "ratio": torrent.ratio,
                    "days_seeded": days_seeded
                })
        
        # Log paused torrents that don't meet criteria yet
        if paused_but_not_ready:
            logger.info(f"Found {len(paused_but_not_ready)} paused torrents that don't meet deletion criteria yet:")
            for idx, t in enumerate(paused_but_not_ready[:5], 1):  # Show up to 5 examples
                logger.info(
                    f"  {idx}. {t['name'][:50]}... "
                    f"(Ratio: {t['ratio']:.2f}/{ratio_limit:.2f}, "
                    f"Seeded: {t['days_seeded']:.1f}/{days_limit:.1f} days)"
                )
            if len(paused_but_not_ready) > 5:
                logger.info(f"  ... and {len(paused_but_not_ready) - 5} more")
                
        # Delete torrents if not in dry-run mode
        if torrents_to_delete:
            if dry_run:
                logger.info(f"DRY RUN: Would delete {len(torrents_to_delete)} torrents")
            else:
                hashes = [t.hash for t in torrents_to_delete]
                qbt_client.torrents.delete(delete_files=delete_files, hashes=hashes)
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
            try:
                run_cleanup()
                logger.info(f"Next run in {interval_hours} hours. Sleeping...")
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal, exiting...")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                # Sleep a shorter time before retrying after an error
                time.sleep(60)

if __name__ == "__main__":
    main()