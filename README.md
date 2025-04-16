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
* Giving you control over whether associated files are deleted
* Providing scheduled cleanup to prevent torrent buildup

## Quick Start

```bash
docker run -d \
  --name qbt-cleanup \
  --restart unless-stopped \
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
  -e CHECK_PAUSED_ONLY=false \
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

## Private vs Non-Private Torrents

The tool now supports different cleanup criteria for private and non-private torrents:

- **Private torrents** are from private trackers that typically require maintaining good ratios
- **Non-private torrents** are from public trackers where ratio maintenance may be less important

This feature allows you to:
- Keep private torrents seeding longer to maintain your tracker ratio
- Remove non-private torrents more aggressively to free up resources
- Maintain different ratios for each type based on your needs
- Independently control which torrents are monitored based on pause state

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
```

## Why Use This Tool?

### The Problem

When using qBittorrent with Sonarr and Radarr, several issues can occur in specific setups:

1. In certain configurations, Sonarr and Radarr removal tasks may not run as expected, leading to torrents remaining in qBittorrent
2. This can occur in unique media server setups or when scheduled tasks are interrupted
3. Using qBittorrent's built-in removal feature interferes with Sonarr/Radarr file management and triggers health check errors
4. Without proper cleanup, your torrent client becomes cluttered with completed torrents

### The Solution

This tool provides a safe way to clean up your torrents:
- It removes torrents from qBittorrent based on ratio/time criteria without disrupting Sonarr/Radarr
- It applies different criteria to private and non-private torrents based on your preferences
- It allows for independent monitoring of pause state for private vs. non-private torrents
- It gives you control over file deletion to match your media management setup
- It runs on a schedule to keep your torrent client tidy

## How It Works

1. The tool connects to your qBittorrent WebUI
2. It checks torrents against the specified criteria:
   - For private torrents: PRIVATE_RATIO and PRIVATE_DAYS (or qBittorrent's settings)
   - For non-private torrents: NONPRIVATE_RATIO and NONPRIVATE_DAYS (or fallback values)
   - It applies CHECK_PRIVATE_PAUSED_ONLY to private torrents and CHECK_NONPRIVATE_PAUSED_ONLY to non-private torrents
3. When torrents meet or exceed these criteria, they are deleted from qBittorrent (with or without their files, as configured)
4. The process repeats on the schedule you define

## Pause Monitoring

You can now set different pause monitoring options for private and non-private torrents:

- `CHECK_PRIVATE_PAUSED_ONLY=true`: Only check private torrents that are in a paused state
- `CHECK_NONPRIVATE_PAUSED_ONLY=true`: Only check non-private torrents that are in a paused state

Setting these differently allows for more nuanced control. For example:
- Set `CHECK_PRIVATE_PAUSED_ONLY=true` to only remove private torrents after they've been paused by qBittorrent's built-in ratio management
- Set `CHECK_NONPRIVATE_PAUSED_ONLY=false` to aggressively clean up public torrents regardless of their state

This creates an effective workflow where your private torrents are handled more carefully than public ones.

## Using With Radarr and Sonarr

This tool is designed to work harmoniously with:
- Radarr
- Sonarr
- Lidarr
- Readarr

By providing a reliable cleanup mechanism that doesn't interfere with these applications' file management, you avoid the health check errors that can occur when using qBittorrent's built-in removal feature.

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/regix1/qbt-cleanup).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
