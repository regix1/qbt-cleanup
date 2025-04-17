#!/usr/bin/env python3
import os
from qbittorrentapi import Client, LoginFailed, APIConnectionError

# ─── CONFIG via ENV ──────────────────────────────────────────────────────────
HOST     = os.environ.get("QB_HOST",     "localhost")
PORT     = os.environ.get("QB_PORT",     "8080")
USERNAME = os.environ.get("QB_USERNAME", "admin")
PASSWORD = os.environ.get("QB_PASSWORD", "adminadmin")

# ─── CONNECT ─────────────────────────────────────────────────────────────────
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

# ─── FETCH & CLASSIFY ─────────────────────────────────────────────────────────
all_torrents = qbt.torrents.info()

public  = [t for t in all_torrents if getattr(t, "availability", 0) >= 0]
private = [t for t in all_torrents if getattr(t, "availability", 0) <  0]

# ─── PRINT FIRST 3 OF EACH ───────────────────────────────────────────────────
print(f"\nFirst 3 public  torrents  ({len(public)} total):")
for t in public[:3]:
    print(f" • {t.name}  [{t.hash}]")

print(f"\nFirst 3 private torrents  ({len(private)} total):")
for t in private[:3]:
    print(f" • {t.name}  [{t.hash}]")

qbt.auth_log_out()
