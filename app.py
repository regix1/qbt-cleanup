#!/usr/bin/env python3
import os
import sys
from qbittorrentapi import Client, LoginFailed, APIConnectionError

# ─── pick up your existing env vars ─────────────────────────────────────────────
host     = os.environ.get("QB_HOST",     "localhost")
port     = os.environ.get("QB_PORT",     "8080")
username = os.environ.get("QB_USERNAME", "")
password = os.environ.get("QB_PASSWORD", "")

if not username or not password:
    print("❌ Please set QB_USERNAME and QB_PASSWORD")
    sys.exit(1)

# ─── connect ────────────────────────────────────────────────────────────────────
client = Client(
    host=f"{host}:{port}",
    username=username,
    password=password,
    VERIFY_WEBUI_CERTIFICATE=False,
)
try:
    client.auth_log_in()
except (LoginFailed, APIConnectionError) as e:
    print("❌ Failed to log in:", e)
    sys.exit(1)

# ─── fetch public vs private ────────────────────────────────────────────────────
public_torrents  = client.torrents.info(private=False)[:3]
private_torrents = client.torrents.info(private=True)[:3]

# ─── print them ─────────────────────────────────────────────────────────────────
print(f"First 3 public torrents  ({len(public_torrents)} shown):")
for t in public_torrents:
    print(f" • {t.name}  [{t.hash}]")

print(f"\nFirst 3 private torrents ({len(private_torrents)} shown):")
for t in private_torrents:
    print(f" • {t.name}  [{t.hash}]")

# ─── clean up ───────────────────────────────────────────────────────────────────
client.auth_log_out()
