#!/usr/bin/env python3
import os
from qbittorrentapi import Client, LoginFailed, APIConnectionError

# ─── CONFIGURE via ENV ─────────────────────────────────────────────────────────
HOST     = os.environ.get("QB_HOST",     "localhost")
PORT     = os.environ.get("QB_PORT",     "8080")
USERNAME = os.environ.get("QB_USERNAME", "admin")
PASSWORD = os.environ.get("QB_PASSWORD", "adminadmin")

# ─── CONNECT ───────────────────────────────────────────────────────────────────
try:
    qbt = Client(
        host=f"{HOST}:{PORT}",
        username=USERNAME,
        password=PASSWORD,
        VERIFY_WEBUI_CERTIFICATE=False,
    )
    qbt.auth_log_in()
except LoginFailed:
    print("⚠️ Login failed – check your credentials")
    exit(1)
except APIConnectionError:
    print("⚠️ Cannot reach qBittorrent Web UI")
    exit(1)

# ─── FETCH & SPLIT ──────────────────────────────────────────────────────────────
all_torrents = qbt.torrents.info()
public  = []
private = []

for t in all_torrents:
    # call the “generic properties” endpoint to get isPrivate
    props = qbt.torrents.properties(t.hash)
    if props.get("isPrivate", False):
        private.append(t)
    else:
        public.append(t)

# ─── PRINT FIRST 3 OF EACH ─────────────────────────────────────────────────────
print("\nFirst 3 public torrents  ({} total):".format(len(public)))
for t in public[:3]:
    print(f" • {t.name}  [{t.hash}]")

print("\nFirst 3 private torrents ({} total):".format(len(private)))
for t in private[:3]:
    print(f" • {t.name}  [{t.hash}]")

# ─── CLEANUP ───────────────────────────────────────────────────────────────────
qbt.auth_log_out()
