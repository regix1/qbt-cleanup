#!/usr/bin/env python3
import os
import sys
from qbittorrentapi import Client, LoginFailed, APIConnectionError

def main():
    # use your existing env vars
    host     = os.environ.get("QB_HOST", "localhost")
    port     = os.environ.get("QB_PORT", "8080")
    username = os.environ.get("QB_USERNAME", "admin")
    password = os.environ.get("QB_PASSWORD", "adminadmin")

    # connect
    try:
        client = Client(
            host=f"{host}:{port}",
            username=username,
            password=password,
            VERIFY_WEBUI_CERTIFICATE=False,
            REQUESTS_ARGS=dict(timeout=10),
        )
        client.auth_log_in()
    except LoginFailed:
        print("❌ Login failed — check QB_USERNAME/QB_PASSWORD")
        sys.exit(1)
    except APIConnectionError:
        print("❌ Cannot reach qBittorrent Web UI — check QB_HOST/QB_PORT")
        sys.exit(1)

    # fetch all torrents
    all_torrents = client.torrents_info()

    public = []
    private = []

    # determine private flag by fetching each torrent's properties
    for t in all_torrents:
        props = client.torrents_properties(t.hash)
        if props.get("private", False):
            private.append(t.name)
        else:
            public.append(t.name)

    # report
    print("\n=== PUBLIC TORRENTS ===")
    for name in public:
        print(f"  • {name}")
    print(f"\nTotal public:  {len(public)}")

    print("\n=== PRIVATE TORRENTS ===")
    for name in private:
        print(f"  • {name}")
    print(f"\nTotal private: {len(private)}\n")

    client.auth_log_out()

if __name__ == "__main__":
    main()
