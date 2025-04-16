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
  -e DELETE_FILES=true \
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
| `DELETE_FILES` | Whether to delete files on disk | `true` |
| `DRY_RUN` | Test run without deleting anything | `false` |
| `SCHEDULE_HOURS` | Hours between cleanup runs | `24` |
| `RUN_ONCE` | Run once and exit instead of scheduling | `false` |
| `CHECK_PAUSED_ONLY` | Only check paused torrents | `false` |

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
      - DELETE_FILES=true
      - DRY_RUN=false
      - SCHEDULE_HOURS=24
      - RUN_ONCE=false
      - CHECK_PAUSED_ONLY=true
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
- It can target only paused torrents (recommended) to ensure you're only removing completed downloads
- It gives you control over file deletion to match your media management setup
- It runs on a schedule to keep your torrent client tidy

## How It Works

1. The tool connects to your qBittorrent WebUI
2. It checks torrents against the specified criteria (either qBittorrent's configured limits or your fallback values)
   - When CHECK_PAUSED_ONLY=true, only paused torrents are evaluated (recommended)
   - When CHECK_PAUSED_ONLY=false, all torrents are evaluated
3. When torrents meet or exceed these criteria, they are deleted from qBittorrent (with or without their files, as configured)
4. The process repeats on the schedule you define

## Paused-Only Mode

The recommended way to use this tool is with `CHECK_PAUSED_ONLY=true`. This creates an effective workflow:

1. Use qBittorrent's built-in ratio management to pause torrents that reach your thresholds
2. Have this tool automatically remove those paused torrents that Sonarr/Radarr haven't cleaned up

This approach ensures only torrents that are already paused (and thus likely completed and processed by your *arr applications) are removed.

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
