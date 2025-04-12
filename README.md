# qbt-cleanup

Automatically clean up qBittorrent torrents based on ratio and seeding time without affecting Sonarr and Radarr health checks.

## Description

This tool helps manage your qBittorrent instance by automatically cleaning up torrents based on their ratio and seeding time. Unlike qBittorrent's built-in auto-management, this tool will not pause torrents (which can trigger health check alerts in Sonarr and Radarr), but instead directly deletes them when they meet your specified criteria.

The tool can:
- Check torrents against ratio and seeding time thresholds
- Either use qBittorrent's built-in settings or custom thresholds you specify
- Optionally delete the actual files from disk
- Run once or on a schedule
- Display detailed logs of its operations

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
|---------------------|-------------|---------|
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
