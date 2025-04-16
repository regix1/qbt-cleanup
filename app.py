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
    
    # Cleanup settings for all torrents (used as fallback)
    fallback_ratio = float(os.environ.get("FALLBACK_RATIO", "1.0"))
    fallback_days = float(os.environ.get("FALLBACK_DAYS", "7"))
    
    # New settings for private torrents
    private_ratio = float(os.environ.get("PRIVATE_RATIO", str(fallback_ratio)))
    private_days = float(os.environ.get("PRIVATE_DAYS", str(fallback_days)))
    
    # New settings for non-private torrents
    nonprivate_ratio = float(os.environ.get("NONPRIVATE_RATIO", str(fallback_ratio)))
    nonprivate_days = float(os.environ.get("NONPRIVATE_DAYS", str(fallback_days)))
    
    # Other settings
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
            global_ratio_limit = prefs.get('max_ratio', fallback_ratio)
            logger.info(f"Using qBittorrent's configured ratio limit: {global_ratio_limit}")
            # Use global settings as defaults if specific ones weren't provided
            if os.environ.get("PRIVATE_RATIO") is None:
                private_ratio = global_ratio_limit
            if os.environ.get("NONPRIVATE_RATIO") is None:
                nonprivate_ratio = global_ratio_limit
        else:
            global_ratio_limit = fallback_ratio
            logger.info(f"Ratio limit not enabled in qBittorrent, using fallback: {global_ratio_limit}")
        
        # Get seeding time limit from qBittorrent preferences (if enabled)
        if prefs.get('max_seeding_time_enabled', False):
            # Convert minutes to days
            global_days_limit = prefs.get('max_seeding_time', fallback_days * 60 * 24) / (60 * 24)
            logger.info(f"Using qBittorrent's configured seeding time limit: {global_days_limit:.1f} days")
            # Use global settings as defaults if specific ones weren't provided
            if os.environ.get("PRIVATE_DAYS") is None:
                private_days = global_days_limit
            if os.environ.get("NONPRIVATE_DAYS") is None:
                nonprivate_days = global_days_limit
        else:
            global_days_limit = fallback_days
            logger.info(f"Seeding time limit not enabled in qBittorrent, using fallback: {global_days_limit} days")
        
        # Log private/non-private settings
        logger.info(f"Private torrent limits: Ratio={private_ratio:.2f}, Days={private_days:.1f}")
        logger.info(f"Non-private torrent limits: Ratio={nonprivate_ratio:.2f}, Days={nonprivate_days:.1f}")
        
        # Log paused-only mode
        if check_paused_only:
            logger.info("Running in paused-only mode: only checking paused torrents")
        
        # Convert days to seconds for comparison
        private_seeding_time_limit = private_days * 24 * 60 * 60
        nonprivate_seeding_time_limit = nonprivate_days * 24 * 60 * 60
        
        # Get all torrents
        torrents = qbt_client.torrents.info()
        logger.info(f"Found {len(torrents)} torrents")
        
        # Count torrents by privacy status
        private_count = sum(1 for t in torrents if getattr(t, 'isPrivate', False))
        nonprivate_count = len(torrents) - private_count
        logger.info(f"Torrent breakdown: {private_count} private, {nonprivate_count} non-private")
        
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
            
            # Determine if torrent is private (with fallback if field is missing)
            is_private = getattr(torrent, 'isPrivate', False)
            
            # Apply appropriate limits based on torrent privacy
            if is_private:
                ratio_limit = private_ratio
                seeding_time_limit = private_seeding_time_limit
                torrent_type = "private"
            else:
                ratio_limit = nonprivate_ratio
                seeding_time_limit = nonprivate_seeding_time_limit
                torrent_type = "non-private"
            
            # Check if ratio or seeding time exceeds limits
            if torrent.ratio >= ratio_limit or torrent.seeding_time >= seeding_time_limit:
                days_seeded = torrent.seeding_time / 86400  # Convert seconds to days
                
                torrents_to_delete.append(torrent)
                logger.info(
                    f"Found: {torrent.name[:50]}... "
                    f"({torrent_type}, State: {torrent.state}, Ratio: {torrent.ratio:.2f}/{ratio_limit:.2f}, "
                    f"Seeded: {days_seeded:.1f}/{seeding_time_limit/86400:.1f} days)"
                )
            elif is_paused:
                days_seeded = torrent.seeding_time / 86400  # Convert seconds to days
                paused_but_not_ready.append({
                    "name": torrent.name,
                    "ratio": torrent.ratio,
                    "days_seeded": days_seeded,
                    "is_private": is_private,
                    "ratio_limit": ratio_limit,
                    "days_limit": seeding_time_limit / 86400
                })
        
        # Log paused torrents that don't meet criteria yet
        if paused_but_not_ready:
            logger.info(f"Found {len(paused_but_not_ready)} paused torrents that don't meet deletion criteria yet:")
            for idx, t in enumerate(paused_but_not_ready[:5], 1):  # Show up to 5 examples
                logger.info(
                    f"  {idx}. {t['name'][:50]}... "
                    f"({'private' if t['is_private'] else 'non-private'}, "
                    f"Ratio: {t['ratio']:.2f}/{t['ratio_limit']:.2f}, "
                    f"Seeded: {t['days_seeded']:.1f}/{t['days_limit']:.1f} days)"
                )
            if len(paused_but_not_ready) > 5:
                logger.info(f"  ... and {len(paused_but_not_ready) - 5} more")
        
        # Count torrents to delete by privacy status
        private_to_delete = sum(1 for t in torrents_to_delete if getattr(t, 'isPrivate', False))
        nonprivate_to_delete = len(torrents_to_delete) - private_to_delete
                
        # Delete torrents if not in dry-run mode
        if torrents_to_delete:
            if dry_run:
                logger.info(f"DRY RUN: Would delete {len(torrents_to_delete)} torrents "
                          f"({private_to_delete} private, {nonprivate_to_delete} non-private)")
            else:
                hashes = [t.hash for t in torrents_to_delete]
                qbt_client.torrents.delete(delete_files=delete_files, hashes=hashes)
                logger.info(f"Deleted {len(torrents_to_delete)} torrents "
                          f"({private_to_delete} private, {nonprivate_to_delete} non-private)"
                          + (" and their files" if delete_files else ""))
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