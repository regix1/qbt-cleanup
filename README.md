# qbt-cleanup

Automatically clean up qBittorrent torrents based on ratio and seeding time without affecting Sonarr and Radarr health checks.

![GitHub last commit](https://img.shields.io/github/last-commit/regix1/qbt-cleanup)
![Docker Image Size](https://img.shields.io/github/repo-size/regix1/qbt-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Description

This tool solves a critical issue for users of qBittorrent with Sonarr, Radarr, and other *arr applications. While qBittorrent offers built-in options to manage torrents based on ratio and seeding time, these options can cause problems with media management tools:

- qBittorrent's **pause option** stops seeding but keeps torrents in the client, triggering health check alerts in Sonarr/Radarr
- qBittorrent's **remove option** can delete torrents but if configured to remove files, it can interfere with Sonarr/Radarr's file management when these applications aren't set to handle file deletion themselves

This tool bridges this gap by:
* Directly removing torrents from qBittorrent when they meet criteria (not just pausing them)
* Providing control over whether the underlying files are deleted
* Working harmoniously with Sonarr/Radarr's expected workflow
* Preventing health check alerts while maintaining your desired ratio and seeding policies

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

### The Problem with qBittorrent's Built-in Options

qBittorrent provides two built-in methods for handling torrents that reach ratio/time limits:

1. **Pause Torrents**: This leaves torrents in the client, but Sonarr/Radarr expect torrents to remain active until properly removed, triggering health check alerts for paused torrents.

2. **Remove Torrents**: qBittorrent can remove torrents when limits are reached, but when configured to also delete files, this can cause issues if Sonarr/Radarr aren't configured to handle file removal themselves.

### The Solution

This tool provides an intelligent middle layer:

- It completely removes torrents from qBittorrent (not just pausing them), preventing Sonarr/Radarr health alerts
- It gives you control over file deletion with the `DELETE_FILES` option, allowing you to match your *arr applications' file management settings
- It can work with qBittorrent's native limits or use custom thresholds you specify

## How It Works

1. The tool connects to your qBittorrent WebUI
2. It checks torrents against the specified criteria (either qBittorrent's configured limits or your fallback values)
   - When CHECK_PAUSED_ONLY=true, only paused torrents are evaluated
   - When CHECK_PAUSED_ONLY=false (default), all torrents are evaluated
3. When torrents meet or exceed these criteria, they are deleted from qBittorrent (with or without their files, as configured)
4. The process repeats on the schedule you define

## Paused-Only Mode

If you enable `CHECK_PAUSED_ONLY=true`, the tool will only delete torrents that are already paused. This creates a powerful two-stage workflow:

1. Use qBittorrent's built-in ratio management to pause torrents that reach your thresholds
2. Have this tool automatically remove those paused torrents from qBittorrent

This approach gives you more granular control over your torrents and ensures only content that qBittorrent has already determined should be paused gets removed.

## Using With Radarr and Sonarr

This tool is specifically designed to work seamlessly with:

- Radarr
- Sonarr
- Lidarr
- Readarr

By removing torrents completely (rather than pausing them) and giving you control over file deletion, it ensures these applications continue to function correctly without health check alerts.

## Support

For issues, questions, or contributions, please visit the [GitHub repository](https://github.com/regix1/qbt-cleanup).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
