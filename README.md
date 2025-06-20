# qbt-cleanup

Automatically clean up qBittorrent torrents based on ratio and seeding time without affecting Sonarr and Radarr file management.

![GitHub last commit](https://img.shields.io/github/last-commit/regix1/qbt-cleanup)
![Docker Image Size](https://img.shields.io/github/repo-size/regix1/qbt-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Description

This tool solves a specific issue with qBittorrent, Sonarr, and Radarr integration. In certain media server configurations, Sonarr and Radarr removal tasks may not run as expected, leading to torrents remaining in qBittorrent. Additionally, using qBittorrent's built-in removal option can interfere with Sonarr and Radarr's file management, causing health check errors.

This tool bridges this gap by:
* Safely removing torrents that meet your criteria without disrupting Sonarr/Radarr file management
* Working with either qBittorrent's built-in settings or custom thresholds you specify
* Supporting different cleanup criteria for private and non-private torrents
* Allowing separate pause monitoring for private and non-private torrents
* **NEW:** FileFlows integration to protect files currently being processed
* **NEW:** Force deletion of non-paused torrents that meet criteria but fail to auto-pause
* **NEW:** Stale download cleanup for torrents stuck downloading too long
* Giving you control over whether associated files are deleted
* Providing scheduled cleanup to prevent torrent buildup
* Manual scan triggering via Docker signals

## Quick Start

```bash
docker run -d \
  --name qbt-cleanup \
  --restart unless-stopped \
  -v /path/to/config:/config \
  -e QB_HOST=192.168.1.100 \
  -e QB_PORT=8080 \
  -e QB_USERNAME=admin \
  -e QB_PASSWORD=adminadmin \
  -e FALLBACK_RATIO=1.0 \
  -e FALLBACK_DAYS=7 \
  -e PRIVATE_RATIO=2.0 \
  -e PRIVATE_DAYS=14 \
  -e NONPRIVATE_RATIO=1.0 \
  -e NONPRIVATE_DAYS=3 \
  -e DELETE_FILES=true \
  -e CHECK_PRIVATE_PAUSED_ONLY=true \
  -e CHECK_NONPRIVATE_PAUSED_ONLY=false \
  -e SCHEDULE_HOURS=24 \
  ghcr.io/regix1/qbittorrent-cleanup:latest
```

## Configuration Options

| Environment Variable | Description | Default |
|----------------------|-------------|---------|
| `QB_HOST` | qBittorrent WebUI host | `localhost` |
| `QB_PORT` | qBittorrent WebUI port | `8080` |
| `QB_USERNAME` | qBittorrent WebUI username | `admin` |
| `QB_PASSWORD` | qBittorrent WebUI password | `adminadmin` |
| `QB_VERIFY_SSL` | Verify SSL certificate for qBittorrent WebUI | `false` |
| `FALLBACK_RATIO` | Ratio threshold if not set in qBittorrent | `1.0` |
| `FALLBACK_DAYS` | Days seeding threshold if not set in qBittorrent | `7` |
| `PRIVATE_RATIO` | Ratio threshold for private torrents | Same as FALLBACK_RATIO |
| `PRIVATE_DAYS` | Days seeding threshold for private torrents | Same as FALLBACK_DAYS |
| `NONPRIVATE_RATIO` | Ratio threshold for non-private torrents | Same as FALLBACK_RATIO |
| `NONPRIVATE_DAYS` | Days seeding threshold for non-private torrents | Same as FALLBACK_DAYS |
| `IGNORE_QBT_RATIO_PRIVATE` | Ignore qBittorrent's ratio settings for private torrents | `false` |
| `IGNORE_QBT_RATIO_NONPRIVATE` | Ignore qBittorrent's ratio settings for non-private torrents | `false` |
| `IGNORE_QBT_TIME_PRIVATE` | Ignore qBittorrent's seeding time settings for private torrents | `false` |
| `IGNORE_QBT_TIME_NONPRIVATE` | Ignore qBittorrent's seeding time settings for non-private torrents | `false` |
| `DELETE_FILES` | Whether to delete files on disk | `true` |
| `DRY_RUN` | Test run without deleting anything | `false` |
| `SCHEDULE_HOURS` | Hours between cleanup runs | `24` |
| `RUN_ONCE` | Run once and exit instead of scheduling | `false` |
| `CHECK_PAUSED_ONLY` | Legacy setting (use specific settings below instead) | `false` |
| `CHECK_PRIVATE_PAUSED_ONLY` | Only check paused private torrents | Same as CHECK_PAUSED_ONLY |
| `CHECK_NONPRIVATE_PAUSED_ONLY` | Only check paused non-private torrents | Same as CHECK_PAUSED_ONLY |
| `FORCE_DELETE_AFTER_HOURS` | Force delete non-paused torrents after X hours of meeting criteria (0=disabled) | `0` |
| `FORCE_DELETE_PRIVATE_AFTER_HOURS` | Force delete non-paused private torrents after X hours (0=disabled) | Same as FORCE_DELETE_AFTER_HOURS |
| `FORCE_DELETE_NONPRIVATE_AFTER_HOURS` | Force delete non-paused non-private torrents after X hours (0=disabled) | Same as FORCE_DELETE_AFTER_HOURS |
| `CLEANUP_STALE_DOWNLOADS` | Enable cleanup of stalled downloading torrents | `false` |
| `MAX_STALLED_DAYS` | Maximum days a torrent can be stalled before deletion (0=disabled) | `3` |
| `MAX_STALLED_PRIVATE_DAYS` | Maximum stalled days for private torrents (0=disabled) | Same as MAX_STALLED_DAYS |
| `MAX_STALLED_NONPRIVATE_DAYS` | Maximum stalled days for non-private torrents (0=disabled) | Same as MAX_STALLED_DAYS |
| `FILEFLOWS_ENABLED` | Enable FileFlows integration to protect processing files | `false` |
| `FILEFLOWS_HOST` | FileFlows server host | `localhost` |
| `FILEFLOWS_PORT` | FileFlows server port | `19200` |
| `FILEFLOWS_TIMEOUT` | FileFlows API timeout in seconds | `10` |

## Force Delete Feature

Sometimes qBittorrent fails to automatically pause torrents when they meet seeding criteria. The force delete feature addresses this by allowing deletion of torrents that meet your ratio/time criteria but remain unpaused.

### How it works:
- When `CHECK_*_PAUSED_ONLY=true` is set, normally only paused torrents are considered for deletion
- If force delete is enabled, torrents that meet criteria but aren't paused will be deleted after the specified time
- The tool estimates how long a torrent has exceeded the deletion criteria
- Once this "excess time" exceeds your force delete threshold, the torrent is removed

### Configuration:
```bash
# Force delete non-paused torrents after 24 hours of meeting criteria
-e FORCE_DELETE_AFTER_HOURS=24 \
# Or set different values for private vs non-private
-e FORCE_DELETE_PRIVATE_AFTER_HOURS=48 \
-e FORCE_DELETE_NONPRIVATE_AFTER_HOURS=12 \
```

### Benefits:
- Prevents torrents from getting "stuck" when qBittorrent fails to pause them
- Maintains your paused-only workflow while providing a safety net
- Different timeouts for private vs non-private torrents allow for careful ratio management

## Stale Download Cleanup

Torrents that get stuck in a stalled state can accumulate over time. The stale download cleanup feature automatically removes torrents that have been continuously stalled for too long.

### How it works:
- Tracks torrents specifically in the `stalledDL` state (no progress being made)
- Uses persistent state storage to monitor how long each torrent has been continuously stalled
- Only counts consecutive stall time - if a torrent resumes downloading, the stall timer resets
- Removes torrents that exceed your maximum allowed stall time
- Respects FileFlows protection (won't delete if files are being processed)
- Actively downloading torrents are never affected, only stalled ones

### Configuration:
```bash
# Enable stalled download cleanup with 3-day stall limit
-e CLEANUP_STALE_DOWNLOADS=true \
-e MAX_STALLED_DAYS=3 \
# Or set different limits for private vs non-private
-e MAX_STALLED_PRIVATE_DAYS=7 \
-e MAX_STALLED_NONPRIVATE_DAYS=1 \
```

**Important:** For persistence across container restarts, mount a volume to `/config`:
```bash
-v /path/to/config:/config
```
The script stores state tracking data in `/config/qbt_cleanup_state.json`.

### Benefits:
- Only removes truly problematic torrents (stalled, not just slow)
- Preserves legitimate slow downloads that are still making progress
- Different limits for private vs non-private torrents
- Persistent tracking across script restarts
- Reduces manual intervention for genuinely stuck downloads

## FileFlows Integration

FileFlows is a file processing automation tool that can handle video encoding, audio processing, and file organization. This tool now includes optional FileFlows integration to prevent deletion of torrents whose files are currently being processed.

### How it works:
- When enabled, the tool checks FileFlows for any files currently being processed
- Torrents containing files that match FileFlows processing files are automatically protected from deletion
- Files are protected during active processing and for 10 minutes after completion
- Protection uses filename matching between torrent files and FileFlows processing queue

### Configuration:
```bash
# Enable FileFlows integration
-e FILEFLOWS_ENABLED=true \
-e FILEFLOWS_HOST=192.168.1.200 \
-e FILEFLOWS_PORT=19200 \
-e FILEFLOWS_TIMEOUT=10 \
```

### Benefits:
- Prevents deletion of torrents while their files are being processed by FileFlows
- Maintains seeding while ensuring post-processing completion
- Automatic protection without manual intervention
- Seamless integration with your existing media workflow

## Private vs Non-Private Torrents

The tool now supports different cleanup criteria for private and non-private torrents:

- **Private torrents** are from private trackers that typically require maintaining good ratios
- **Non-private torrents** are from public trackers where ratio maintenance may be less important

This feature allows you to:
- Keep private torrents seeding longer to maintain your tracker ratio
- Remove non-private torrents more aggressively to free up resources
- Maintain different ratios for each type based on your needs
- Independently control which torrents are monitored based on pause state
- Set different force delete and stale download timeouts

For example, you might set:
- Private torrents: higher ratio requirement (2.0), longer seed time (14 days), and only process paused torrents
- Non-private torrents: lower ratio (1.0), shorter seed time (3 days), and process all torrents regardless of state

## Override qBittorrent Settings

New override options allow you to selectively ignore qBittorrent's built-in ratio and seeding time settings:

- Use `IGNORE_QBT_RATIO_PRIVATE=true` to use your custom ratio for private torrents even if qBittorrent has its own ratio settings
- Use `IGNORE_QBT_RATIO_NONPRIVATE=true` to use your custom ratio for non-private torrents
- Use `IGNORE_QBT_TIME_PRIVATE=true` to use your custom seeding time for private torrents
- Use `IGNORE_QBT_TIME_NONPRIVATE=true` to use your custom seeding time for non-private torrents

This is particularly useful when you want qBittorrent to handle one type of torrent but use custom settings for the other.

## Manual Scan Trigger

You can trigger a manual scan without waiting for the scheduled run:

```bash
# Trigger manual scan
docker kill --signal=SIGUSR1 qbt-cleanup
```

This is useful for testing or when you want an immediate cleanup after making configuration changes.

## Docker Compose Example

```yaml
version: '3'

services:
  qbt-cleanup:
    image: ghcr.io/regix1/qbittorrent-cleanup:latest
    container_name: qbt-cleanup
    restart: unless-stopped
    depends_on:
      - qbittorrent
    volumes:
      - ./qbt-cleanup-config:/config
    environment:
      - QB_HOST=192.168.1.100
      - QB_PORT=8080
      - QB_USERNAME=admin
      - QB_PASSWORD=adminadmin
      - FALLBACK_RATIO=1.0
      - FALLBACK_DAYS=7
      - PRIVATE_RATIO=2.0
      - PRIVATE_DAYS=14
      - NONPRIVATE_RATIO=1.0
      - NONPRIVATE_DAYS=3
      - IGNORE_QBT_RATIO_NONPRIVATE=true
      - IGNORE_QBT_TIME_NONPRIVATE=true
      - DELETE_FILES=true
      - DRY_RUN=false
      - CHECK_PRIVATE_PAUSED_ONLY=true
      - CHECK_NONPRIVATE_PAUSED_ONLY=false
      - SCHEDULE_HOURS=24
      - RUN_ONCE=false
      # Force delete settings
      - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
      - FORCE_DELETE_NONPRIVATE_AFTER_HOURS=12
      # Stalled download cleanup
      - CLEANUP_STALE_DOWNLOADS=true
      - MAX_STALLED_PRIVATE_DAYS=7
      - MAX_STALLED_NONPRIVATE_DAYS=1
      # FileFlows integration (optional)
      - FILEFLOWS_ENABLED=true
      - FILEFLOWS_HOST=192.168.1.200
      - FILEFLOWS_PORT=19200
      - FILEFLOWS_TIMEOUT=10
```

## Why Use This Tool?

### The Problem

When using qBittorrent with Sonarr and Radarr, several issues can occur in specific setups:

1. In certain configurations, Sonarr and Radarr removal tasks may not run as expected, leading to torrents remaining in qBittorrent
2. This can occur in unique media server setups or when scheduled tasks are interrupted
3. Using qBittorrent's built-in removal feature interferes with Sonarr/Radarr file management and triggers health check errors
4. Without proper cleanup, your torrent client becomes cluttered with completed torrents
5. File processing tools like FileFlows may be working on files from torrents that get deleted prematurely
6. qBittorrent may fail to pause torrents when they meet seeding criteria, leaving them running indefinitely
7. Downloads can get stuck in a stalled state with no progress, cluttering the download queue

### The Solution

This tool provides a safe way to clean up your torrents:
- It removes torrents from qBittorrent based on ratio/time criteria without disrupting Sonarr/Radarr
- It applies different criteria to private and non-private torrents based on your preferences
- It allows for independent monitoring of pause state for private vs. non-private torrents
- It protects files currently being processed by FileFlows from premature deletion
- It provides force deletion for torrents that meet criteria but fail to auto-pause
- It automatically cleans up downloads that are stuck in stalled states
- It gives you control over file deletion to match your media management setup
- It runs on a schedule to keep your torrent client tidy
- It supports manual triggering for immediate cleanup when needed

## How It Works

1. The tool connects to your qBittorrent WebUI
2. If FileFlows integration is enabled, it checks for currently processing files
3. It checks torrents against the specified criteria:
   - For stalled downloads: Checks against MAX_STALLED_*_DAYS if stall cleanup is enabled
   - For seeding torrents: Checks against PRIVATE_RATIO/DAYS and NONPRIVATE_RATIO/DAYS (or qBittorrent's settings)
   - It applies CHECK_PRIVATE_PAUSED_ONLY to private torrents and CHECK_NONPRIVATE_PAUSED_ONLY to non-private torrents
   - If force delete is enabled, it also checks non-paused torrents that have exceeded criteria for the specified time
4. Torrents are protected from deletion if their files are being processed by FileFlows
5. When torrents meet or exceed deletion criteria and are not protected, they are deleted from qBittorrent (with or without their files, as configured)
6. The process repeats on the schedule you define

## Pause Monitoring

You can now set different pause monitoring options for private and non-private torrents:

- `CHECK_PRIVATE_PAUSED_ONLY=true`: Only check private torrents that are in a paused state
- `CHECK_NONPRIVATE_PAUSED_ONLY=true`: Only check non-private torrents that are in a paused state

Setting these differently allows for more nuanced control. For example:
- Set `CHECK_PRIVATE_PAUSED_ONLY=true` to only remove private torrents after they've been paused by qBittorrent's built-in ratio management
- Set `CHECK_NONPRIVATE_PAUSED_ONLY=false` to aggressively clean up public torrents regardless of their state

This creates an effective workflow where your private torrents are handled more carefully than public ones.

## Using With Media Management Tools

This tool is designed to work harmoniously with:
- **Radarr** - Movie management
- **Sonarr** - TV show management  
- **Lidarr** - Music management
- **Readarr** - Book management
- **FileFlows** - File processing automation

By providing a reliable cleanup mechanism that doesn't interfere with these applications' file management, you avoid the health check errors that can occur when using qBittorrent's built-in removal feature.

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/regix1/qbt-cleanup).

## License