#!/usr/bin/env python3
import os
import sys
from qbittorrentapi import Client, LoginFailed, APIConnectionError

def main():
    # ─── load your env ─────────────────────────────────────────────────────────
    host = os.environ.get("QB_HOST", "localhost")
    port = os.environ.get("QB_PORT", "8080")
    user = os.environ.get("QB_USERNAME", "admin")
    pwd  = os.environ.get("QB_PASSWORD", "adminadmin")

    tag = os.environ.get("TARGET_TAG")
    if not tag:
        print("❌ set TARGET_TAG to the tag you want to filter on")
        sys.exit(1)

    # ─── connect ───────────────────────────────────────────────────────────────
    try:
        client = Client(
            host=f"{host}:{port}",
            username=user,
            password=pwd,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=10),
        )
        client.auth_log_in()
    except LoginFailed:
        print("❌ Login failed – check your QB_USERNAME/QB_PASSWORD")
        sys.exit(1)
    except APIConnectionError:
        print("❌ Cannot reach qBittorrent – check your QB_HOST/QB_PORT")
        sys.exit(1)

    # ─── fetch only public torrents with that tag ───────────────────────────────
    public_torrents = client.torrents_info(private=False, tag=tag)

    if not public_torrents:
        print(f"⚠️  No public torrents found with tag '{tag}'")
    else:
        print(f"\nFound {len(public_torrents)} public torrents tagged '{tag}':\n")
        for t in public_torrents:
            print(f" • {t.name}   (hash={t.hash})")
        print()

    # ─── optionally delete them (uncomment to enable) ───────────────────────────
    # hashes = [t.hash for t in public_torrents]
    # if hashes:
    #     client.torrents_delete(delete_files=True, torrent_hashes=hashes)
    #     print(f"🗑  Deleted {len(hashes)} torrents + their files")

    client.auth_log_out()


if __name__ == "__main__":
    main()
