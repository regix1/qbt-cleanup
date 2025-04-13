# qbt-cleanup

Automatically clean up qBittorrent torrents based on ratio and seeding time without affecting Sonarr and Radarr health checks.

![GitHub last commit](https://img.shields.io/github/last-commit/regix1/qbittorrent-cleanup)
![Docker Pulls](https://img.shields.io/docker/pulls/regix1/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Description

This tool helps manage your qBittorrent instance by automatically cleaning up torrents based on their ratio and seeding time. Unlike qBittorrent's built-in auto-management, this tool will not pause torrents (which can trigger health check alerts in Sonarr and Radarr), but instead directly deletes them when they meet your specified criteria.

The tool can:
* Check torrents against ratio and seeding time thresholds
* Either use qBittorrent's built-in settings or custom thresholds you specify
* Optionally delete the actual files from disk
* Run once or on a schedule
* Display detailed logs of its operations
* Optionally only check paused torrents

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

### Problem with qBittorrent's Built-in Automation

qBittorrent offers built-in ratio and seeding time limits, but it pauses torrents rather than removing them. This can cause problems with Sonarr and Radarr, which monitor torrent client status and may report health check errors when torrents are paused.

### Solution

This tool directly deletes torrents when they meet criteria, preventing Sonarr/Radarr health check alerts while still maintaining your desired ratio and seeding time rules.

## How It Works

1. The tool connects to your qBittorrent WebUI
2. It checks all torrents against the specified criteria (either qBittorrent's configured limits or your fallback values)
3. When torrents meet or exceed these criteria, they are deleted (with or without their files, as configured)
4. The process repeats on the schedule you define

## Paused-Only Mode

If you enable `CHECK_PAUSED_ONLY=true`, the tool will only consider torrents that are already paused. This allows you to:

1. Use qBittorrent's built-in ratio management to pause torrents
2. Then have this tool clean up only those paused torrents

This creates a two-stage deletion process that some users prefer.

## Using With Radarr and Sonarr

Since this tool deletes torrents directly instead of pausing them, it works well with:

- Radarr
- Sonarr
- Lidarr
- Readarr

And other *arr applications that expect torrents to remain active until they're completely removed.

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/regix1/qbittorrent-cleanup).

## License

This project is licensed under the MIT License - see the LICENSE file for details.