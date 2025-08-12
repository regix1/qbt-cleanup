# 🧹 qBittorrent Cleanup Tool

> Intelligent torrent management for qBittorrent with Sonarr/Radarr compatibility

[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Fregix1%2Fqbittorrent--cleanup-blue)](https://github.com/regix1/qbt-cleanup/pkgs/container/qbittorrent-cleanup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/badge/version-2.0-green)

## ✨ Features

- 🎯 **Smart Cleanup** - Remove torrents based on ratio and seeding time without breaking Sonarr/Radarr
- 🔐 **Private/Public Differentiation** - Different rules for private vs public trackers
- 📁 **FileFlows Protection** - Never delete torrents while files are being processed
- ⏰ **Force Delete** - Remove stuck torrents that fail to auto-pause
- 🐌 **Stalled Detection** - Clean up downloads stuck with no progress
- 🎨 **Beautiful Logs** - Color-coded output with emojis for easy monitoring
- 🔄 **Persistent State** - Track torrent history across container restarts
- 🎮 **Manual Control** - Trigger scans on-demand via Docker signals

## 🚀 Quick Start

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
  -e NONPRIVATE_RATIO=1.0 \
  -e NONPRIVATE_DAYS=3 \
  ghcr.io/regix1/qbittorrent-cleanup:latest
```

## 📋 Configuration

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
| `PRIVATE_RATIO` | Ratio for private torrents | `FALLBACK_RATIO` |
| `PRIVATE_DAYS` | Days for private torrents | `FALLBACK_DAYS` |
| `NONPRIVATE_RATIO` | Ratio for public torrents | `FALLBACK_RATIO` |
| `NONPRIVATE_DAYS` | Days for public torrents | `FALLBACK_DAYS` |

### Behavior Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DELETE_FILES` | Delete files when removing torrents | `true` |
| `DRY_RUN` | Test mode (no actual deletions) | `false` |
| `SCHEDULE_HOURS` | Hours between cleanup runs | `24` |
| `RUN_ONCE` | Run once and exit | `false` |

### Advanced Features

| Variable | Description | Default |
|----------|-------------|---------|
| `CHECK_PRIVATE_PAUSED_ONLY` | Only check paused private torrents | `false` |
| `CHECK_NONPRIVATE_PAUSED_ONLY` | Only check paused public torrents | `false` |
| `FORCE_DELETE_PRIVATE_AFTER_HOURS` | Force delete stuck private torrents after X hours | `0` |
| `FORCE_DELETE_NONPRIVATE_AFTER_HOURS` | Force delete stuck public torrents after X hours | `0` |
| `CLEANUP_STALE_DOWNLOADS` | Enable stalled download cleanup | `false` |
| `MAX_STALLED_PRIVATE_DAYS` | Max days private torrents can be stalled | `3` |
| `MAX_STALLED_NONPRIVATE_DAYS` | Max days public torrents can be stalled | `3` |

### FileFlows Integration

| Variable | Description | Default |
|----------|-------------|---------|
| `FILEFLOWS_ENABLED` | Enable FileFlows protection | `false` |
| `FILEFLOWS_HOST` | FileFlows server host | `localhost` |
| `FILEFLOWS_PORT` | FileFlows server port | `19200` |
| `FILEFLOWS_TIMEOUT` | API timeout in seconds | `10` |

## 🎯 Use Cases

### Private Tracker Optimization
Maintain good ratios on private trackers while cleaning up public torrents aggressively:

```yaml
environment:
  - PRIVATE_RATIO=2.0
  - PRIVATE_DAYS=30
  - NONPRIVATE_RATIO=1.0
  - NONPRIVATE_DAYS=3
  - CHECK_PRIVATE_PAUSED_ONLY=true  # Wait for qBittorrent to pause
  - CHECK_NONPRIVATE_PAUSED_ONLY=false  # Clean immediately
```

### Media Server with FileFlows
Protect files during post-processing:

```yaml
environment:
  - FILEFLOWS_ENABLED=true
  - FILEFLOWS_HOST=192.168.1.200
  - FILEFLOWS_PORT=19200
  - FORCE_DELETE_AFTER_HOURS=24  # Clean stuck torrents after 24h
```

### Aggressive Cleanup
Remove completed torrents quickly to save space:

```yaml
environment:
  - PRIVATE_RATIO=1.0
  - PRIVATE_DAYS=7
  - NONPRIVATE_RATIO=0.5
  - NONPRIVATE_DAYS=1
  - CLEANUP_STALE_DOWNLOADS=true
  - MAX_STALLED_DAYS=2
```

## 📦 Docker Compose

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
      - NONPRIVATE_RATIO=1.0
      - NONPRIVATE_DAYS=3
      
      # Behavior
      - DELETE_FILES=true
      - CHECK_PRIVATE_PAUSED_ONLY=true
      - CHECK_NONPRIVATE_PAUSED_ONLY=false
      - SCHEDULE_HOURS=6
      
      # Advanced features
      - FORCE_DELETE_PRIVATE_AFTER_HOURS=48
      - FORCE_DELETE_NONPRIVATE_AFTER_HOURS=12
      - CLEANUP_STALE_DOWNLOADS=true
      - MAX_STALLED_DAYS=3
      
      # FileFlows (optional)
      - FILEFLOWS_ENABLED=false
```

## 🎮 Manual Control

Trigger an immediate cleanup without waiting for the schedule:

```bash
docker kill --signal=SIGUSR1 qbt-cleanup
```

View real-time logs with pretty colors:

```bash
docker logs -f qbt-cleanup
```

## 📊 What You'll See

The tool provides beautiful, informative logs:

```
╔══════════════════════════════════════════════════════════╗
║          🧹 qBittorrent Cleanup Tool v2.0 🧹            ║
╚══════════════════════════════════════════════════════════╝
12:00:00 ✓ Mode: Scheduled (every 6h)
12:00:00 ✓ Starting cleanup cycle...
12:00:01 ✓ Connected to qBittorrent v4.5.2
12:00:01 ✓ 📁 FileFlows: Connected
12:00:01 ✓ 📊 Found 47 torrents
12:00:01 ✓ 🔐 Private: 45 | 🌐 Public: 2
12:00:01 ✓ ⚙️  Features: ⏰ Force delete | 🐌 Stalled cleanup | ⏸️ Paused-only
12:00:02 ✓ 🗑️ Deleted 3 torrents
12:00:02 ✓    📈 Completed: 2 | Stalled: 1
12:00:02 ✓ Cleanup cycle completed successfully 🎉
12:00:02 ✓ Next run: 18:00:02 (6h)
────────────────────────────────────────────────────────────
```

## 🔧 How It Works

### Architecture
The tool uses a modular architecture for maintainability:
- **Config Management** - Environment variable parsing and validation
- **Client Wrapper** - qBittorrent API interactions with retry logic
- **State Manager** - Persistent tracking of torrent history
- **Classifier** - Intelligent torrent categorization
- **FileFlows Integration** - Protection for files being processed
- **Cleanup Orchestrator** - Coordinates all components

### Process Flow
1. **Connect** to qBittorrent and FileFlows (if enabled)
2. **Fetch** all torrents and their metadata
3. **Classify** torrents based on your rules:
   - Check if stalled too long
   - Check ratio/time limits
   - Apply pause-only filters
   - Check force delete timeouts
4. **Protect** torrents with files in FileFlows
5. **Delete** torrents that meet criteria
6. **Save** state for persistence
7. **Sleep** until next scheduled run

## 🤝 Compatibility

Works seamlessly with:
- **Sonarr** / **Radarr** - Doesn't interfere with their file management
- **FileFlows** - Protects files during processing
- **qBittorrent** 4.3.0+ (5.0.0+ for enhanced private detection)
- **Docker** / **Docker Compose**
- **Kubernetes** (via environment variables)

## 🛡️ Safety Features

- **Dry Run Mode** - Test your configuration without deleting anything
- **FileFlows Protection** - Never delete torrents with files being processed
- **State Persistence** - Tracks history across restarts
- **Graceful Degradation** - Continues working even if state can't be saved
- **Smart Retries** - Handles temporary connection issues
- **SSL Flexibility** - Works with self-signed certificates

## 📝 Troubleshooting

### Permission Issues
If you see permission errors, ensure the config directory is writable:

```bash
# Fix permissions (adjust UID:GID to match your setup)
sudo chown -R 1000:1000 ./qbt-cleanup/config
sudo chmod 755 ./qbt-cleanup/config
```

### SSL Warnings
For self-signed certificates, set:
```yaml
environment:
  - QB_VERIFY_SSL=false
```

### State Not Persisting
Mount a volume to `/config`:
```yaml
volumes:
  - ./qbt-cleanup/config:/config
```

## 🚦 Feature Details

### Force Delete
Handles torrents that meet criteria but won't pause:
- Monitors how long torrents exceed limits
- Deletes after specified timeout
- Different timeouts for private/public

### Stalled Detection
Removes stuck downloads automatically:
- Tracks consecutive stall time
- Resets timer if download resumes
- Configurable per torrent type

### FileFlows Integration
Protects files during processing:
- Real-time processing detection
- 10-minute grace period after completion
- Filename-based matching

## 📈 Monitoring

Monitor the tool's performance:

```bash
# View logs
docker logs qbt-cleanup

# Follow logs in real-time
docker logs -f qbt-cleanup

# Check container health
docker ps | grep qbt-cleanup

# View state file (if mounted)
cat ./qbt-cleanup/config/qbt_cleanup_state.json
```

## 🤝 Contributing

Contributions are welcome! The modular architecture makes it easy to:
- Add new features
- Integrate with other tools
- Improve classification logic
- Enhance logging

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details

## 🙏 Acknowledgments

- Built for the self-hosting community
- Inspired by the need for better torrent management
- Designed to work with the *arr ecosystem

---

<p align="center">
  Made with ❤️ for the self-hosting community
</p>