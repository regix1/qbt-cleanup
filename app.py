#!/usr/bin/env python3
import os
from qbittorrentapi import Client

def main():
    # use the same env vars your container already has
    host = os.getenv("QB_HOST", "localhost")
    port = os.getenv("QB_PORT", "8080")
    user = os.getenv("QB_USERNAME", "admin")
    pw   = os.getenv("QB_PASSWORD", "adminadmin")

    qbt = Client(
        host=f"{host}:{port}",
        username=user,
        password=pw,
        VERIFY_WEBUI_CERTIFICATE=False,
    )
    qbt.auth_log_in()

    torrents = qbt.torrents.info()
    public = []
    private = []
    for t in torrents:
        # most builds expose .private, fallback to False if missing
        is_priv = getattr(t, "private", False)
        (private if is_priv else public).append(t)

    print(f"Found {len(public)} public, {len(private)} private torrents\n")

    print("→ PUBLIC torrents:")
    for t in public:
        print(f"  • {t.name}  [{t.hash}]  tags={t.tags}")

    print("\n→ PRIVATE torrents:")
    for t in private:
        print(f"  • {t.name}  [{t.hash}]  tags={t.tags}")

    qbt.auth_log_out()

if __name__ == "__main__":
    main()
