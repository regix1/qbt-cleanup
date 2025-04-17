#!/usr/bin/env python3
import os
from qbittorrentapi import Client, LoginFailed, APIConnectionError

# ─── config via ENV ────────────────────────────────────────────────────────────
HOST     = os.environ.get("QB_HOST",     "localhost")
PORT     = os.environ.get("QB_PORT",     "8080")
USERNAME = os.environ.get("QB_USERNAME", "admin")
PASSWORD = os.environ.get("QB_PASSWORD", "adminadmin")

# ─── connect ──────────────────────────────────────────────────────────────────
try:
    qbt = Client(
        host=f"{HOST}:{PORT}",
        username=USERNAME,
        password=PASSWORD,
        VERIFY_WEBUI_CERTIFICATE=False,
    )
    qbt.auth_log_in()
except (LoginFailed, APIConnectionError) as e:
    print(f"❌ {e}")
    exit(1)

# ─── helper to detect private flag via trackers msg ──────────────────────────
def is_private(t):
    try:
        # one HTTP call per torrent, so this is slower!
        trackers = qbt.torrents.trackers(hash=t.hash)
        return any(
            (tr.status == 0 and tr.msg and "private" in tr.msg.lower())
            for tr in trackers
        )
    except Exception:
        return False

# ─── fetch & classify ────────────────────────────────────────────────────────
all_torrents = qbt.torrents.info()
public, private = [], []

for t in all_torrents:
    if is_private(t):
        private.append(t)
    else:
        public.append(t)

# ─── print first 3 of each ───────────────────────────────────────────────────
print(f"\nFirst 3 public  torrents  ({len(public)} total):")
for t in public[:3]:
    print(f" • {t.name}  [{t.hash}]")

print(f"\nFirst 3 private torrents  ({len(private)} total):")
for t in private[:3]:
    print(f" • {t.name}  [{t.hash}]")

qbt.auth_log_out()
