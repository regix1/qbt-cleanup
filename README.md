# qBittorrent Cleanup Tool

Automated torrent management for qBittorrent with Sonarr/Radarr compatibility

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fregix1%2Fqbittorrent--cleanup-blue)](https://github.com/regix1/qbt-cleanup/pkgs/container/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-2.1-green)

## Features

- **Smart Cleanup** - Removes torrents based on ratio and seeding time without breaking Sonarr/Radarr imports
- **Private/Public Differentiation** - Apply different rules for private vs public trackers
- **FileFlows Protection** - Prevents deletion of torrents while files are being processed
- **Force Delete** - Removes stuck torrents that won't auto-pause after meeting criteria
- **Stalled Detection** - Cleans up downloads that are stuck with no progress
- **Persistent State** - Tracks torrent history across container restarts
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

## Sample Log Output

```
Starting cleanup cycle...
Connected to qBittorrent v4.5.2 (API: 2.8.3, SSL: disabled)
FileFlows: Connected
Found 47 torrents
Private: 45 | Public: 2
Using qBittorrent ratio limits: Private=2.0, Public=1.0
Features: Force delete after 48h/12h | Stalled cleanup after 7d/3d | Paused-only: Private
-> delete: Ubuntu.22.04.iso (priv=False, state=pausedUP, ratio=1.05/1.00, time=3.2/3.0d)
-> delete stalled: Some.Movie.mkv (priv=True, stalled=8.1/7.0d)
-> skipping (FileFlows): Processing.File.mp4
Deleted 2 torrents
   Completed: 1 | Stalled: 1
Cleanup cycle completed successfully
Next run: 18:00:02 (6h)
```

## Frequently Asked Questions

### Can this tool rename files while keeping torrents seeding?

No, this is not possible. The BitTorrent protocol requires exact file names and structures to match the torrent's metadata hash. If you rename files:
- The torrent client cannot verify pieces against the metadata
- The torrent will show as incomplete and stop seeding
- You would need to create a new torrent with the renamed files

This is a fundamental limitation of how BitTorrent works, not a limitation of this tool.

### Why separate rules for Private and Public torrents?

Private trackers typically have strict ratio requirements and track your account's performance. Public trackers generally don't have these requirements. This tool allows you to:
- Maintain higher ratios on private trackers to keep good standing
- Clean up public torrents more aggressively to save space
- Use different strategies based on tracker type

### How does FileFlows protection work?

When FileFlows integration is enabled, the tool:
1. Queries the FileFlows API for actively processing files
2. Checks if any torrent files match those being processed
3. Skips deletion of protected torrents
4. Includes a 10-minute grace period after processing completes

### What happens if the container restarts?

The tool maintains state in `/config/qbt_cleanup_state.json`. This file tracks:
- When torrents were first seen
- How long torrents have been stalled
- Previous torrent states

Mount a volume to `/config` to persist this data across restarts.

## How It Works

### Architecture

The tool uses a modular Python package structure:

- **config.py** - Environment variable parsing and validation
- **client.py** - qBittorrent API wrapper with retry logic
- **state.py** - Persistent state management
- **classifier.py** - Torrent categorization logic
- **fileflows.py** - FileFlows API integration
- **cleanup.py** - Main orchestration
- **main.py** - Entry point and scheduler

### Process Flow

1. Connect to qBittorrent and FileFlows (if enabled)
2. Fetch all torrents and their metadata
3. Classify torrents based on configured rules
4. Check FileFlows protection status
5. Delete torrents that meet criteria
6. Save state for persistence
7. Sleep until next scheduled run

## Compatibility

- **qBittorrent** 4.3.0+ (5.0.0+ for enhanced private tracker detection)
- **Sonarr/Radarr** - Doesn't interfere with their import process
- **FileFlows** - Optional integration for processing protection
- **Docker/Docker Compose** - Primary deployment method
- **Kubernetes** - Configure via environment variables

## Safety Features

- **Dry Run Mode** - Test configuration without deleting anything
- **FileFlows Protection** - Never delete torrents with files being processed
- **State Persistence** - Maintains history across restarts
- **Graceful Degradation** - Continues working if state can't be saved
- **Connection Retry** - Handles temporary network issues
- **SSL Support** - Works with self-signed certificates

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

### State Not Persisting

Ensure you've mounted a volume to `/config`:

```yaml
volumes:
  - ./qbt-cleanup/config:/config
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

Built for the self-hosting community to provide better torrent management that works seamlessly with the *arr ecosystem.