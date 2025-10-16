# qBittorrent Cleanup Tool

Automated torrent management for qBittorrent with Sonarr/Radarr compatibility.

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fregix1%2Fqbittorrent--cleanup-blue)](https://github.com/regix1/qbt-cleanup/pkgs/container/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-2.1-green)

## Overview

This tool automates torrent cleanup in qBittorrent based on ratio and seeding time. It's designed to work alongside Sonarr/Radarr without breaking their imports, and it can handle private and public trackers with different rules.

The main benefit is that you can maintain good ratios on private trackers while automatically cleaning up public torrents more aggressively. Everything runs in Docker and persists state using SQLite, so tracking continues even after restarts.

## Key Features

- **Smart Cleanup** - Removes torrents when they hit ratio or time limits without interfering with Sonarr/Radarr imports
- **Private/Public Differentiation** - Different rules for private vs public trackers to maintain good standing
- **High Performance** - Uses SQLite with indexed queries for instant operations even with thousands of torrents
- **FileFlows Protection** - Won't delete torrents while files are being post-processed
- **Force Delete** - Can remove stuck torrents that meet criteria but won't auto-pause
- **Stalled Detection** - Cleans up downloads that are stuck without progress
- **Persistent State** - Tracks torrent history across restarts using SQLite database
- **Manual Trigger** - Run cleanup on-demand via Docker signals

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
  -e PRIVATE_RATIO=2.0 \
  -e PRIVATE_DAYS=14 \
  -e PUBLIC_RATIO=1.0 \
  -e PUBLIC_DAYS=3 \
  ghcr.io/regix1/qbittorrent-cleanup:latest
```

## Configuration

### Connection Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `QB_HOST` | qBittorrent WebUI host | `localhost` |
| `QB_PORT` | qBittorrent WebUI port | `8080` |
| `QB_USERNAME` | qBittorrent username | `admin` |
| `QB_PASSWORD` | qBittorrent password | `adminadmin` |
| `QB_VERIFY_SSL` | Verify SSL certificate | `false` |

### Cleanup Criteria

| Variable | Description | Default |
|----------|-------------|---------|
| `FALLBACK_RATIO` | Default ratio if not set in qBittorrent | `1.0` |
| `FALLBACK_DAYS` | Default days if not set in qBittorrent | `7` |
| `PRIVATE_RATIO` | Ratio requirement for private torrents | `FALLBACK_RATIO` |
| `PRIVATE_DAYS` | Seeding days for private torrents | `FALLBACK_DAYS` |
| `PUBLIC_RATIO` | Ratio requirement for public torrents | `FALLBACK_RATIO` |
| `PUBLIC_DAYS` | Seeding days for public torrents | `FALLBACK_DAYS` |

### Behavior Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DELETE_FILES` | Delete files when removing torrents | `true` |
| `DRY_RUN` | Test mode without actual deletions | `false` |
| `SCHEDULE_HOURS` | Hours between cleanup runs | `24` |
| `RUN_ONCE` | Run once and exit | `false` |

### Advanced Features

| Variable | Description | Default |
|----------|-------------|---------|
| `CHECK_PRIVATE_PAUSED_ONLY` | Only check paused private torrents | `false` |
| `CHECK_PUBLIC_PAUSED_ONLY` | Only check paused public torrents | `false` |
| `FORCE_DELETE_PRIVATE_AFTER_HOURS` | Force delete stuck private torrents after X hours | `0` (disabled) |
| `FORCE_DELETE_PUBLIC_AFTER_HOURS` | Force delete stuck public torrents after X hours | `0` (disabled) |
| `CLEANUP_STALE_DOWNLOADS` | Enable stalled download cleanup | `false` |
| `MAX_STALLED_PRIVATE_DAYS` | Maximum days private torrents can be stalled | `3` |
| `MAX_STALLED_PUBLIC_DAYS` | Maximum days public torrents can be stalled | `3` |

### qBittorrent Settings Override

| Variable | Description | Default |
|----------|-------------|---------|
| `IGNORE_QBT_RATIO_PRIVATE` | Ignore qBittorrent's ratio for private | `false` |
| `IGNORE_QBT_RATIO_PUBLIC` | Ignore qBittorrent's ratio for public | `false` |
| `IGNORE_QBT_TIME_PRIVATE` | Ignore qBittorrent's time for private | `false` |
| `IGNORE_QBT_TIME_PUBLIC` | Ignore qBittorrent's time for public | `false` |

### FileFlows Integration

| Variable | Description | Default |
|----------|-------------|---------|
| `FILEFLOWS_ENABLED` | Enable FileFlows protection | `false` |
| `FILEFLOWS_HOST` | FileFlows server host | `localhost` |
| `FILEFLOWS_PORT` | FileFlows server port | `19200` |
| `FILEFLOWS_TIMEOUT` | API timeout in seconds | `10` |

## Common Use Cases

### Private Tracker Optimization

Maintain good ratios on private trackers while cleaning up public torrents more aggressively:

```yaml
environment:
  - PRIVATE_RATIO=2.0
  - PRIVATE_DAYS=30
  - PUBLIC_RATIO=1.0
  - PUBLIC_DAYS=3
  - CHECK_PRIVATE_PAUSED_ONLY=true  # Wait for qBittorrent to pause
  - CHECK_PUBLIC_PAUSED_ONLY=false   # Clean immediately
```

### Media Server with FileFlows

Protect files during post-processing:

```yaml
environment:
  - FILEFLOWS_ENABLED=true
  - FILEFLOWS_HOST=192.168.1.200
  - FILEFLOWS_PORT=19200
  - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
  - FORCE_DELETE_PUBLIC_AFTER_HOURS=24
```

### Aggressive Space Management

Remove completed torrents quickly to save disk space:

```yaml
environment:
  - PRIVATE_RATIO=1.0
  - PRIVATE_DAYS=7
  - PUBLIC_RATIO=0.5
  - PUBLIC_DAYS=1
  - CLEANUP_STALE_DOWNLOADS=true
  - MAX_STALLED_PUBLIC_DAYS=2
```

## Docker Compose Example

```yaml
version: '3'

services:
  qbittorrent:
    image: hotio/qbittorrent:latest
    container_name: qbittorrent
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/New_York
    volumes:
      - ./config:/config
      - ./downloads:/downloads
    ports:
      - 8080:8080

  qbt-cleanup:
    image: ghcr.io/regix1/qbittorrent-cleanup:latest
    container_name: qbt-cleanup
    restart: unless-stopped
    depends_on:
      - qbittorrent
    volumes:
      - ./qbt-cleanup/config:/config
    environment:
      # Connection
      - QB_HOST=qbittorrent
      - QB_PORT=8080
      - QB_USERNAME=admin
      - QB_PASSWORD=adminadmin

      # Cleanup rules
      - PRIVATE_RATIO=2.0
      - PRIVATE_DAYS=14
      - PUBLIC_RATIO=1.0
      - PUBLIC_DAYS=3

      # Behavior
      - DELETE_FILES=true
      - CHECK_PRIVATE_PAUSED_ONLY=true
      - CHECK_PUBLIC_PAUSED_ONLY=false
      - SCHEDULE_HOURS=6

      # Advanced features (optional)
      - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
      - FORCE_DELETE_PUBLIC_AFTER_HOURS=12
      - CLEANUP_STALE_DOWNLOADS=true
      - MAX_STALLED_DAYS=3
```

## Manual Control

Trigger an immediate cleanup without waiting for the schedule:

```bash
docker kill --signal=SIGUSR1 qbt-cleanup
```

View real-time logs:

```bash
docker logs -f qbt-cleanup
```

## Performance

The tool uses SQLite for state management, which provides excellent performance even with large numbers of torrents:

| Torrents | Load Time | Save Time | Memory Usage |
|----------|-----------|-----------|--------------|
| 500 | ~5ms | ~2ms per update | Minimal |
| 5,000 | ~10ms | ~2ms per update | Minimal |
| 50,000 | ~50ms | ~2ms per update | Minimal |

### State Storage

- **Database:** SQLite with indexed queries
- **Location:** `/config/qbt_cleanup_state.db`
- **Migration:** Automatic from JSON/MessagePack formats
- **Cleanup:** Automatically removes torrents that no longer exist

## How It Works

### Architecture

The tool uses a modular Python package structure:

- **src/qbt_cleanup/** - Main package directory
  - **state.py** - SQLite database for persistent state management
  - **client.py** - qBittorrent API wrapper with retry logic
  - **classifier.py** - Torrent categorization logic
  - **fileflows.py** - FileFlows API integration
  - **cleanup.py** - Main orchestration
  - **config.py** - Environment variable parsing
  - **main.py** - Entry point and scheduler

### Process Flow

1. Connect to qBittorrent and FileFlows (if enabled)
2. Fetch all torrents and their metadata
3. Update SQLite database with current torrent states
4. Remove database entries for non-existent torrents
5. Classify torrents based on configured rules
6. Check FileFlows protection status
7. Delete torrents that meet criteria
8. Commit database changes

### Deletion Logic

A torrent is deleted when it meets ANY of these conditions:

1. **Standard Deletion:** Ratio OR seeding time exceeded
2. **Force Delete:** Exceeded limits but won't pause (after timeout)
3. **Stalled Cleanup:** Download stalled for too long

Torrents are protected from deletion when:
- Files are being processed by FileFlows
- They don't meet any deletion criteria
- They're actively downloading (except stalled)

## Frequently Asked Questions

### Can this tool rename files while keeping torrents seeding?

No, this is not possible. The BitTorrent protocol requires exact file names and structures to match the torrent's metadata hash. If you rename files:
- The torrent client cannot verify pieces against the metadata
- The torrent will show as incomplete and stop seeding
- You would need to create a new torrent with the renamed files

This is a fundamental limitation of how BitTorrent works.

### Why separate rules for Private and Public torrents?

Private trackers typically have strict ratio requirements and track your account's performance. Public trackers generally don't have these requirements. This tool allows you to:
- Maintain higher ratios on private trackers to keep good standing
- Clean up public torrents more aggressively to save space
- Use different strategies based on tracker type

### How does the SQLite database improve performance?

SQLite provides:
- Indexed queries for instant lookups
- Atomic updates without rewriting the entire file
- Automatic cleanup of non-existent torrents
- Crash recovery and data integrity
- Efficient storage even with thousands of torrents

### What happens if the container restarts?

All state is preserved in the SQLite database at `/config/qbt_cleanup_state.db`. The tool will:
- Continue tracking stalled durations
- Remember previous torrent states
- Automatically migrate from JSON if upgrading

## Compatibility

- **qBittorrent** 4.3.0+ (5.0.0+ for enhanced private tracker detection)
- **Sonarr/Radarr** - Doesn't interfere with their import process
- **FileFlows** - Optional integration for processing protection
- **Docker/Docker Compose** - Primary deployment method
- **Kubernetes** - Configure via environment variables

## Troubleshooting

### Permission Issues

If you see permission errors, ensure the config directory is writable:

```bash
# Fix permissions (adjust UID:GID to match your setup)
sudo chown -R 1000:1000 ./qbt-cleanup/config
sudo chmod 755 ./qbt-cleanup/config
```

### SSL Certificate Warnings

For self-signed certificates:

```yaml
environment:
  - QB_VERIFY_SSL=false
```

### Database Issues

Check database status:

```bash
# View database size
ls -lh ./qbt-cleanup/config/qbt_cleanup_state.db

# Check if database is accessible
docker exec qbt-cleanup ls -la /config/
```

### Torrents Not Being Detected as Private

The tool uses two methods to detect private torrents:
1. qBittorrent 5.0.0+ `isPrivate` field (preferred)
2. Tracker message analysis (fallback)

If detection isn't working correctly, check your qBittorrent version and tracker configuration.

## Contributing

Contributions are welcome. The modular architecture makes it straightforward to:
- Add new features or integrations
- Improve classification logic
- Enhance error handling
- Add support for other torrent clients

## License

MIT License - See [LICENSE](LICENSE) file for details

## Acknowledgments

Built for the self-hosting community to provide better torrent management that works seamlessly with the arr ecosystem.
