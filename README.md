# qBittorrent Cleanup Tool

Automated torrent management for qBittorrent with Sonarr/Radarr compatibility.

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fregix1%2Fqbittorrent--cleanup-blue)](https://github.com/regix1/qbt-cleanup/pkgs/container/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-2.2.0-green)

## Overview

Automates torrent cleanup in qBittorrent based on ratio and seeding time. Works alongside Sonarr/Radarr without breaking their imports. Supports separate rules for private and public trackers so you can maintain good standing on private trackers while cleaning up public torrents more aggressively.

Runs in Docker, persists state in SQLite, and includes a web UI for monitoring and management. Runtime configuration overrides can be applied through the web UI without restarting the container. Supports optional FileFlows integration and orphaned file cleanup. Scans can be triggered via the scheduler, SIGUSR1 signal, the Web UI, or the REST API.

## Quick Start

```bash
docker run -d \
  --name qbt-cleanup \
  --restart unless-stopped \
  -v /path/to/config:/config \
  -p 9999:9999 \
  -e QB_HOST=192.168.1.100 \
  -e QB_PORT=8080 \
  -e QB_USERNAME=admin \
  -e QB_PASSWORD=yourpassword \
  -e PRIVATE_RATIO=2.0 \
  -e PRIVATE_DAYS=14 \
  -e PUBLIC_RATIO=1.0 \
  -e PUBLIC_DAYS=3 \
  ghcr.io/regix1/qbittorrent-cleanup:latest
```

The web UI is available at `http://your-server-ip:9999` after starting.

For orphaned file cleanup, mount your download directories at the **same path** as qBittorrent:

```bash
-v /path/to/downloads:/downloads \
-e CLEANUP_ORPHANED_FILES=true \
-e ORPHANED_SCAN_DIRS=/downloads
```

To disable the web interface: `-e WEB_ENABLED=false`

## Web UI

Access the web interface at `http://your-server-ip:9999`. Requires port mapping (`-p 9999:9999` in Docker or `ports: - 9999:9999` in Compose). Interactive API documentation is available at `/api/docs` (Swagger UI).

### Dashboard

- **5 stat cards** showing Total, Private, Public, Stalled, and Blacklisted torrent counts
- **Last Run card** with timestamp, success/fail indicator, and mini-stats: checked, removed, private removed, public removed, skipped, errors
- **Scheduler card** showing running/stopped state and the configured interval
- **Behavior card** displaying dry run and delete files settings
- **Run Scan** and **Orphaned Scan** buttons for triggering manual scans
- Auto-refreshes every 30 seconds

### Torrents

- **6 independent filter dimensions:** name search, state dropdown, category dropdown, type (private/public), blacklist status, tracker hostname
- Active filter chips with individual dismiss and "Clear All"
- **8 sortable columns:** Name, State, Ratio, Seeding Time, Type, Size, Progress, Blacklisted
- Pagination (25 per page) with "Showing X-Y of Z" info
- Compact mode toggle for fitting the table to the viewport
- Per-torrent blacklist toggle with confirmation dialog

### Blacklist

- **Add form:** hash input with optional name and reason fields
- **Torrent picker:** searchable dropdown of available torrents that auto-fills hash and name
- **Table:** name, hash, reason, date added, and remove button per entry
- **Clear All** with confirmation dialog

### Configuration

- **7 accordion sections:** Connection, Limits, Behavior, Schedule, FileFlows, Orphaned, Web
- Smart field types: toggle switches for booleans, number inputs, password fields with visibility toggle
- Per-field descriptions and reset buttons to restore defaults
- **Save** button persists changes to `/config/config_overrides.json`
- Changes take effect on the next cleanup cycle without container restart

### FileFlows

- **4 stat cards:** Integration status, Connection, Processing count, Queue count
- List of currently processing files
- Auto-refreshes every 15 seconds

### Disabling the Web UI

| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_ENABLED` | Enable the web UI | `true` |
| `WEB_PORT` | Web UI port | `9999` |
| `WEB_HOST` | Bind address | `0.0.0.0` |
| `WEB_DISPLAY_HOST` | Override IP shown in startup log | (auto-detected) |

## Configuration

All settings are configured via environment variables. Settings can also be changed at runtime through the Web UI Configuration page, which persists overrides to `/config/config_overrides.json`.

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
    ports:
      - 9999:9999
    environment:
      # Connection
      - QB_HOST=qbittorrent
      - QB_PORT=8080
      - QB_USERNAME=admin
      - QB_PASSWORD=yourpassword

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

      # Web UI
      - WEB_ENABLED=true
      - WEB_PORT=9999

      # Orphaned file cleanup (optional)
      # - CLEANUP_ORPHANED_FILES=true
      # - ORPHANED_SCAN_DIRS=/downloads
      # - ORPHANED_SCHEDULE_DAYS=7
```

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

## Manual Control

### Trigger Cleanup

```bash
# Via signal
docker kill --signal=SIGUSR1 qbt-cleanup

# Via API
curl -X POST http://localhost:9999/api/actions/scan

# Via API (orphaned files, bypasses schedule)
curl -X POST http://localhost:9999/api/actions/orphaned-scan
```

Or click **Run Scan** / **Orphaned Scan** on the Web UI Dashboard.

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

Blacklist can be managed through the Web UI (Blacklist page) or via the CLI:

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

## API Reference

Interactive documentation is available at `/api/docs` (Swagger UI).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check with version and uptime |
| GET | `/api/status` | Dashboard status with torrent counts and last run stats |
| GET | `/api/torrents` | List all torrents with live qBittorrent data |
| GET | `/api/blacklist` | List all blacklisted torrents |
| POST | `/api/blacklist` | Add a torrent to the blacklist |
| DELETE | `/api/blacklist/{hash}` | Remove a torrent from the blacklist |
| DELETE | `/api/blacklist` | Clear the entire blacklist |
| GET | `/api/config` | Get effective configuration (env + runtime overrides) |
| PUT | `/api/config` | Update runtime configuration overrides |
| POST | `/api/actions/scan` | Trigger a manual cleanup scan |
| POST | `/api/actions/orphaned-scan` | Trigger an orphaned file scan (bypasses schedule) |
| GET | `/api/fileflows/status` | FileFlows integration status and processing files |

```bash
# Trigger scan
curl -X POST http://localhost:9999/api/actions/scan

# Check status
curl http://localhost:9999/api/status

# Update config at runtime
curl -X PUT http://localhost:9999/api/config \
  -H "Content-Type: application/json" \
  -d '{"overrides": {"limits": {"private_ratio": 3.0}}}'
```

## Architecture

For contributors and advanced users.

- **Backend**: Python 3.11 with FastAPI, SQLite (WAL mode) at `/config/qbt_cleanup_state.db`
- **Frontend**: Angular 20 SPA with standalone components, signals, lazy-loaded routes, dark theme. Built at Docker image time, served as static files.
- **Runtime Config**: Env vars provide defaults. Web UI saves overrides to `/config/config_overrides.json`. Config is reloaded each cycle.
- **Threading**: Main thread runs the scheduler loop. Web UI (uvicorn) runs in a daemon thread. `AppState` bridges the two via lock + `threading.Event` objects.
- **Docker**: Multi-stage build -- Node 20 (Angular) then Python 3.11-slim. PUID/PGID support.

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

### State Storage

- **Engine:** SQLite with WAL mode and indexed queries
- **Location:** `/config/qbt_cleanup_state.db`
- **Migration:** Automatic from JSON/MessagePack formats on first run
- **Cleanup:** Automatically removes entries for torrents no longer in qBittorrent
- **Blacklist:** Stored in database, persists across restarts
- **Runtime Overrides:** `/config/config_overrides.json`

## Compatibility

- **qBittorrent** 4.3.0+ (5.0.0+ for native private tracker detection)
- **Sonarr/Radarr** - Does not interfere with imports
- **FileFlows** - Optional processing protection via `/api/status`
- **Docker/Docker Compose** - Primary deployment method
- **Web UI** - Any modern browser (Angular 20 SPA served via FastAPI)

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

**Do runtime config changes survive container restarts?**
Yes. Changes made through the Web UI Configuration page are saved to `/config/config_overrides.json`, which persists as long as `/config` is mounted as a volume. They overlay environment variable defaults on each cleanup cycle.

## License

MIT License - See [LICENSE](LICENSE) for details.
