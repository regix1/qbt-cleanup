# qBittorrent Cleanup Tool

Automated torrent management for qBittorrent with Sonarr/Radarr compatibility.

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fregix1%2Fqbittorrent--cleanup-blue)](https://github.com/regix1/qbt-cleanup/pkgs/container/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-2.2.0-green)

## Overview

Automates torrent cleanup in qBittorrent based on ratio and seeding time. Works alongside Sonarr/Radarr without breaking their imports. Supports separate rules for private and public trackers so you can maintain good standing on private trackers while cleaning up public torrents more aggressively.

Runs in Docker, persists state in SQLite, and supports optional FileFlows integration and orphaned file cleanup.

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

For orphaned file cleanup, mount your download directories at the **same path** as qBittorrent:

```bash
-v /path/to/downloads:/downloads \
-e CLEANUP_ORPHANED_FILES=true \
-e ORPHANED_SCAN_DIRS=/downloads
```

## Configuration

All settings are configured via environment variables.

### Connection

| Variable | Description | Default |
|----------|-------------|---------|
| `QB_HOST` | qBittorrent WebUI host | `localhost` |
| `QB_PORT` | qBittorrent WebUI port | `8080` |
| `QB_USERNAME` | qBittorrent username | `admin` |
| `QB_PASSWORD` | qBittorrent password | `adminadmin` |
| `QB_VERIFY_SSL` | Verify SSL certificate | `false` |

### Cleanup Limits

| Variable | Description | Default |
|----------|-------------|---------|
| `FALLBACK_RATIO` | Default ratio if not set per-type | `1.0` |
| `FALLBACK_DAYS` | Default seeding days if not set per-type | `7` |
| `PRIVATE_RATIO` | Ratio limit for private torrents | `FALLBACK_RATIO` |
| `PRIVATE_DAYS` | Seeding days for private torrents | `FALLBACK_DAYS` |
| `PUBLIC_RATIO` | Ratio limit for public torrents | `FALLBACK_RATIO` |
| `PUBLIC_DAYS` | Seeding days for public torrents | `FALLBACK_DAYS` |

### Behavior

| Variable | Description | Default |
|----------|-------------|---------|
| `DELETE_FILES` | Delete files when removing torrents | `true` |
| `DRY_RUN` | Log what would be deleted without actually deleting | `false` |
| `SCHEDULE_HOURS` | Hours between cleanup runs | `24` |
| `RUN_ONCE` | Run a single cleanup and exit | `false` |

### Paused-Only and Force Delete

| Variable | Description | Default |
|----------|-------------|---------|
| `CHECK_PAUSED_ONLY` | Only delete torrents qBittorrent has paused (applies to both types) | `false` |
| `CHECK_PRIVATE_PAUSED_ONLY` | Only delete paused private torrents | `CHECK_PAUSED_ONLY` |
| `CHECK_PUBLIC_PAUSED_ONLY` | Only delete paused public torrents | `CHECK_PAUSED_ONLY` |
| `FORCE_DELETE_AFTER_HOURS` | Force delete if criteria met for this many hours (applies to both types) | `0` (disabled) |
| `FORCE_DELETE_PRIVATE_AFTER_HOURS` | Force delete threshold for private torrents | `FORCE_DELETE_AFTER_HOURS` |
| `FORCE_DELETE_PUBLIC_AFTER_HOURS` | Force delete threshold for public torrents | `FORCE_DELETE_AFTER_HOURS` |

Force delete handles torrents that meet your ratio/time criteria but qBittorrent won't auto-pause (e.g., share limits are disabled or set differently). After the configured hours, the torrent is deleted regardless of pause state.

```
Torrent reaches 2.0 ratio
 |- CHECK_PRIVATE_PAUSED_ONLY=false  -> Delete immediately
 |- CHECK_PRIVATE_PAUSED_ONLY=true
    |- qBittorrent pauses it         -> Delete immediately
    |- qBittorrent doesn't pause it
       |- FORCE_DELETE=0             -> Never force delete
       |- FORCE_DELETE=48            -> Delete after 48 hours
```

### Stalled Download Cleanup

| Variable | Description | Default |
|----------|-------------|---------|
| `CLEANUP_STALE_DOWNLOADS` | Enable stalled download cleanup | `false` |
| `MAX_STALLED_DAYS` | Max days a download can be stalled (applies to both types) | `3` |
| `MAX_STALLED_PRIVATE_DAYS` | Max stalled days for private torrents | `MAX_STALLED_DAYS` |
| `MAX_STALLED_PUBLIC_DAYS` | Max stalled days for public torrents | `MAX_STALLED_DAYS` |

### qBittorrent Limit Overrides

By default, the tool reads ratio/time limits from qBittorrent's preferences and uses those if no environment variable is explicitly set. These flags let you ignore the qBittorrent values entirely:

| Variable | Description | Default |
|----------|-------------|---------|
| `IGNORE_QBT_RATIO_PRIVATE` | Ignore qBittorrent's ratio for private torrents | `false` |
| `IGNORE_QBT_RATIO_PUBLIC` | Ignore qBittorrent's ratio for public torrents | `false` |
| `IGNORE_QBT_TIME_PRIVATE` | Ignore qBittorrent's seeding time for private torrents | `false` |
| `IGNORE_QBT_TIME_PUBLIC` | Ignore qBittorrent's seeding time for public torrents | `false` |

### FileFlows Integration

Prevents deletion of torrents whose files are currently being processed by [FileFlows](https://fileflows.com). Uses the lightweight `/api/status` endpoint (~500 bytes) to detect actively processing files in real-time.

| Variable | Description | Default |
|----------|-------------|---------|
| `FILEFLOWS_ENABLED` | Enable FileFlows protection | `false` |
| `FILEFLOWS_HOST` | FileFlows server host | `localhost` |
| `FILEFLOWS_PORT` | FileFlows server port | `19200` |
| `FILEFLOWS_TIMEOUT` | API timeout in seconds | `10` |

When enabled, the tool queries FileFlows once per cycle to get actively processing files. If a torrent's files match any processing file by name, the torrent is protected from deletion. On API failure, the last known processing state is used as a fallback to avoid accidental deletions.

### Orphaned File Cleanup

Identifies and removes files on disk that aren't tracked by any active torrent in qBittorrent.

| Variable | Description | Default |
|----------|-------------|---------|
| `CLEANUP_ORPHANED_FILES` | Enable orphaned file cleanup | `false` |
| `ORPHANED_SCAN_DIRS` | Comma-separated directories to scan (container paths) | (empty) |
| `ORPHANED_MIN_AGE_HOURS` | Minimum file age before removal | `1.0` |
| `ORPHANED_SCHEDULE_DAYS` | Days between orphaned cleanup runs | `7` |

A file is only removed if it meets **both** criteria:
1. Not tracked by any active torrent in qBittorrent
2. Not modified for at least `ORPHANED_MIN_AGE_HOURS`

The orphaned scan runs on its own schedule (default weekly), independent of the main torrent cleanup. The schedule persists across restarts via the database.

**Path matching requirement:** Download directories must be mounted at the **same path** in both the qBittorrent and qbt-cleanup containers. Mismatched paths will cause all files to appear orphaned. The tool aborts the scan if it detects a path mismatch.

```yaml
# Correct - same /downloads path in both containers
qbittorrent:
  volumes:
    - /host/downloads:/downloads

qbt-cleanup:
  volumes:
    - /host/downloads:/downloads    # same path
  environment:
    - ORPHANED_SCAN_DIRS=/downloads
```

Multiple directories:
```yaml
environment:
  - ORPHANED_SCAN_DIRS=/data/complete,/data/movies,/data/tv
```

Always test with `DRY_RUN=true` first.

**Orphaned scan logs** are written to `/config/` with timestamps:
- `orphaned_dryrun_YYYY-MM-DD_HH-MM-SS.log` - what would be deleted
- `orphaned_cleanup_YYYY-MM-DD_HH-MM-SS.log` - what was actually deleted

## Common Use Cases

### Private Tracker Optimization

```yaml
environment:
  - PRIVATE_RATIO=2.0
  - PRIVATE_DAYS=30
  - PUBLIC_RATIO=1.0
  - PUBLIC_DAYS=3
  - CHECK_PRIVATE_PAUSED_ONLY=true
  - CHECK_PUBLIC_PAUSED_ONLY=false
```

### Media Server with FileFlows

```yaml
environment:
  - FILEFLOWS_ENABLED=true
  - FILEFLOWS_HOST=192.168.1.200
  - FILEFLOWS_PORT=19200
  - CHECK_PRIVATE_PAUSED_ONLY=true
  - PRIVATE_RATIO=2.0
  - PRIVATE_DAYS=14
  - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
  - FORCE_DELETE_PUBLIC_AFTER_HOURS=24
```

FileFlows protection prevents deletion during active processing. Force delete handles torrents that qBittorrent won't auto-pause.

### Aggressive Space Management

```yaml
environment:
  - PRIVATE_RATIO=1.0
  - PRIVATE_DAYS=7
  - PUBLIC_RATIO=0.5
  - PUBLIC_DAYS=1
  - CLEANUP_STALE_DOWNLOADS=true
  - MAX_STALLED_PUBLIC_DAYS=2
```

### Orphaned File Cleanup

```yaml
volumes:
  - /path/to/downloads:/downloads

environment:
  - CLEANUP_ORPHANED_FILES=true
  - ORPHANED_SCAN_DIRS=/downloads
  - ORPHANED_MIN_AGE_HOURS=1.0
  - ORPHANED_SCHEDULE_DAYS=7
  - DRY_RUN=true  # test first!
```

## Docker Compose

```yaml
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
      # Must match qBittorrent's mount path for orphaned file cleanup
      - ./downloads:/downloads
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

      # Advanced (optional)
      - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
      - FORCE_DELETE_PUBLIC_AFTER_HOURS=12
      - CLEANUP_STALE_DOWNLOADS=true
      - MAX_STALLED_DAYS=3

      # Orphaned file cleanup (optional)
      # - CLEANUP_ORPHANED_FILES=true
      # - ORPHANED_SCAN_DIRS=/downloads
      # - ORPHANED_SCHEDULE_DAYS=7
```

## Manual Control

### Trigger Immediate Cleanup

```bash
docker kill --signal=SIGUSR1 qbt-cleanup
```

### View Logs

```bash
docker logs -f qbt-cleanup
```

### Orphaned Scan Logs

```bash
# List all orphaned scan logs
ls -lth ./qbt-cleanup/config/orphaned_*.log

# View the most recent dry run
cat $(ls -t ./qbt-cleanup/config/orphaned_dryrun_*.log | head -n1)

# View the most recent cleanup
cat $(ls -t ./qbt-cleanup/config/orphaned_cleanup_*.log | head -n1)
```

### Blacklist Management

Protect specific torrents from automatic deletion.

**Interactive selection (recommended):**

```bash
docker exec -it qbt-cleanup qbt-cleanup-ctl select
```

Displays a numbered list of all torrents. Enter numbers to toggle blacklist status.

**Manual commands:**

```bash
# Add to blacklist
docker exec qbt-cleanup qbt-cleanup-ctl blacklist add <HASH>
docker exec qbt-cleanup qbt-cleanup-ctl blacklist add <HASH> --name "Movie" --reason "Keep forever"

# List blacklisted torrents
docker exec qbt-cleanup qbt-cleanup-ctl blacklist list

# Remove from blacklist
docker exec qbt-cleanup qbt-cleanup-ctl blacklist remove <HASH>

# Clear entire blacklist
docker exec qbt-cleanup qbt-cleanup-ctl blacklist clear -y

# Show status and stats
docker exec qbt-cleanup qbt-cleanup-ctl status

# List tracked torrents
docker exec qbt-cleanup qbt-cleanup-ctl list --limit 10
```

## How It Works

### Process Flow

1. Connect to qBittorrent (and FileFlows if enabled)
2. Fetch all torrents and metadata
3. Build torrent file lists (only when FileFlows is active)
4. Update SQLite database with current torrent states
5. Remove stale database entries for torrents no longer in qBittorrent
6. Check blacklist, classify torrents against configured rules
7. Check FileFlows protection for candidates marked for deletion
8. Delete torrents that meet all criteria
9. Run orphaned file cleanup on its own schedule (if enabled)

### Deletion Logic

A torrent is deleted when it meets ANY of:

1. **Standard deletion** - Ratio OR seeding time exceeded, and either paused-only is off or the torrent is paused
2. **Force delete** - Meets criteria but won't pause, and has exceeded the force delete threshold
3. **Stalled cleanup** - Download stalled with no progress for the configured number of days

**Protected from deletion:**
- Blacklisted torrents
- Files actively being processed by FileFlows
- Active downloads (except stalled)
- Torrents that haven't met any deletion criteria

### Architecture

```
src/qbt_cleanup/
  main.py              Entry point and scheduler
  cleanup.py           Orchestration
  client.py            qBittorrent API wrapper with retry logic
  classifier.py        Torrent classification and deletion decisions
  fileflows.py         FileFlows /api/status integration
  orphaned_scanner.py  Orphaned file detection and cleanup
  state.py             SQLite state management
  config.py            Environment variable parsing
  models.py            Data models
  constants.py         Enums and constants
  utils.py             Parsing and formatting helpers
  ctl.py               CLI control utility (blacklist, status)
```

### State Storage

- **Engine:** SQLite with WAL mode and indexed queries
- **Location:** `/config/qbt_cleanup_state.db`
- **Migration:** Automatic from JSON/MessagePack formats on first run
- **Cleanup:** Automatically removes entries for torrents no longer in qBittorrent
- **Blacklist:** Stored in database, persists across restarts

## Compatibility

- **qBittorrent** 4.3.0+ (5.0.0+ for native private tracker detection)
- **Sonarr/Radarr** - Does not interfere with imports
- **FileFlows** - Optional processing protection via `/api/status`
- **Docker/Docker Compose** - Primary deployment method

## Troubleshooting

### Permission Issues

```bash
sudo chown -R 1000:1000 ./qbt-cleanup/config
sudo chmod 755 ./qbt-cleanup/config
```

### SSL Certificate Warnings

```yaml
environment:
  - QB_VERIFY_SSL=false
```

### Database Issues

```bash
ls -lh ./qbt-cleanup/config/qbt_cleanup_state.db
docker exec qbt-cleanup qbt-cleanup-ctl status
```

### Private Tracker Detection

The tool detects private torrents via:
1. qBittorrent 5.0.0+ `isPrivate` field (preferred, no extra API calls)
2. Tracker message analysis (fallback for older versions)

Check your qBittorrent version and tracker configuration if detection isn't working.

## FAQ

**Can this tool rename files while keeping torrents seeding?**
No. BitTorrent requires exact file names matching the torrent metadata hash. Renaming files breaks piece verification and stops seeding.

**Why separate rules for private and public?**
Private trackers track your ratio and may ban accounts with poor standing. Public trackers don't. This lets you seed longer on private trackers while cleaning up public torrents quickly.

**What happens on container restart?**
All state is preserved in SQLite. Stalled durations, torrent history, blacklist entries, and orphaned cleanup schedule all persist.

## License

MIT License - See [LICENSE](LICENSE) for details.
