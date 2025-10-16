#!/usr/bin/env python3
"""Control utility for qBittorrent cleanup tool."""

import sys
import argparse
from datetime import datetime
from typing import Optional

from .state import StateManager
from .config import Config
from .client import QBittorrentClient


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        return iso_timestamp


def cmd_blacklist_add(args) -> int:
    """Add torrent to blacklist."""
    state = StateManager()

    # Get torrent name from qBittorrent if not provided
    name = args.name
    if not name and not args.no_lookup:
        try:
            config = Config.from_environment()
            client = QBittorrentClient(config.connection)
            if client.connect():
                torrents = client.get_torrents()
                for t in torrents:
                    if t.hash == args.hash:
                        name = t.name
                        break
                client.disconnect()
        except Exception as e:
            print(f"Warning: Could not fetch torrent name: {e}")

    success = state.add_to_blacklist(args.hash, name or "", args.reason or "")

    if success:
        print(f"Added torrent to blacklist: {args.hash[:16]}...")
        if name:
            print(f"  Name: {name}")
        if args.reason:
            print(f"  Reason: {args.reason}")
        return 0
    else:
        print(f"Failed to add torrent to blacklist", file=sys.stderr)
        return 1


def cmd_blacklist_remove(args) -> int:
    """Remove torrent from blacklist."""
    state = StateManager()
    success = state.remove_from_blacklist(args.hash)

    if success:
        print(f"Removed torrent from blacklist: {args.hash[:16]}...")
        return 0
    else:
        print(f"Torrent not found in blacklist", file=sys.stderr)
        return 1


def cmd_blacklist_list(args) -> int:
    """List all blacklisted torrents."""
    state = StateManager()
    entries = state.get_blacklist()

    if not entries:
        print("No torrents in blacklist")
        return 0

    print(f"Blacklisted torrents ({len(entries)}):")
    print()

    for entry in entries:
        print(f"Hash: {entry['hash']}")
        if entry['name']:
            print(f"  Name: {entry['name']}")
        print(f"  Added: {format_timestamp(entry['added_at'])}")
        if entry['reason']:
            print(f"  Reason: {entry['reason']}")
        print()

    return 0


def cmd_blacklist_clear(args) -> int:
    """Clear all blacklisted torrents."""
    state = StateManager()

    if not args.yes:
        response = input("Are you sure you want to clear the entire blacklist? (y/N): ")
        if response.lower() not in ('y', 'yes'):
            print("Cancelled")
            return 0

    success = state.clear_blacklist()

    if success:
        print("Blacklist cleared")
        return 0
    else:
        print("Failed to clear blacklist", file=sys.stderr)
        return 1


def cmd_status(args) -> int:
    """Show status information."""
    state = StateManager()

    if not state.state_enabled:
        print("State: DISABLED (database not accessible)")
        return 1

    print("State: ENABLED")
    print(f"Database: {state.state_file}")
    print()

    # Get counts
    try:
        conn = state._get_connection()

        # Torrent count
        cursor = conn.execute("SELECT COUNT(*) FROM torrents")
        torrent_count = cursor.fetchone()[0]

        # Blacklist count
        cursor = conn.execute("SELECT COUNT(*) FROM blacklist")
        blacklist_count = cursor.fetchone()[0]

        print(f"Tracked torrents: {torrent_count}")
        print(f"Blacklisted torrents: {blacklist_count}")

        # Stalled count
        cursor = conn.execute("SELECT COUNT(*) FROM torrents WHERE stalled_since IS NOT NULL")
        stalled_count = cursor.fetchone()[0]

        if stalled_count > 0:
            print(f"Currently stalled: {stalled_count}")

        return 0
    except Exception as e:
        print(f"Error getting status: {e}", file=sys.stderr)
        return 1


def cmd_list_torrents(args) -> int:
    """List tracked torrents with names from qBittorrent."""
    try:
        # Get torrent info from qBittorrent
        config = Config.from_environment()
        client = QBittorrentClient(config.connection)

        if not client.connect():
            print("Failed to connect to qBittorrent", file=sys.stderr)
            return 1

        torrents = client.get_torrents()
        client.disconnect()

        if not torrents:
            print("No torrents found")
            return 0

        # Create hash to name mapping
        hash_to_name = {t.hash: t.name for t in torrents}

        # Get state info
        state = StateManager()
        blacklisted = {entry['hash'] for entry in state.get_blacklist()}

        # Sort by name
        torrents_sorted = sorted(torrents, key=lambda t: t.name.lower())

        # Apply limit if specified
        if args.limit:
            torrents_sorted = torrents_sorted[:args.limit]

        print(f"\nAll torrents ({len(torrents_sorted)}):\n")
        print(f"{'#':<4} {'Status':<3} {'State':<12} {'Name':<60}")
        print("=" * 90)

        for i, torrent in enumerate(torrents_sorted, 1):
            status = "[B]" if torrent.hash in blacklisted else "[ ]"
            truncated_name = torrent.name[:60] if len(torrent.name) > 60 else torrent.name
            print(f"{i:<4} {status:<3} {torrent.state:<12} {truncated_name}")

        print(f"\n[B] = Blacklisted")
        print(f"\nTotal: {len(torrents_sorted)} torrents")
        if blacklisted:
            print(f"Blacklisted: {len(blacklisted)} torrents")

        return 0
    except Exception as e:
        print(f"Error listing torrents: {e}", file=sys.stderr)
        return 1


def cmd_select_torrents(args) -> int:
    """Interactive torrent selection for blacklisting."""
    try:
        config = Config.from_environment()
        client = QBittorrentClient(config.connection)

        if not client.connect():
            print("Failed to connect to qBittorrent", file=sys.stderr)
            return 1

        torrents = client.get_torrents()
        client.disconnect()

        if not torrents:
            print("No torrents found")
            return 0

        # Sort by name
        torrents = sorted(torrents, key=lambda t: t.name.lower())

        # Check blacklist status
        state = StateManager()
        blacklisted_hashes = {entry['hash'] for entry in state.get_blacklist()}

        print(f"\n{'#':<4} {'Status':<3} {'Name':<60} {'Hash':<16}")
        print("=" * 90)

        for i, torrent in enumerate(torrents, 1):
            status = "[B]" if torrent.hash in blacklisted_hashes else "[ ]"
            truncated_name = torrent.name[:60] if len(torrent.name) > 60 else torrent.name
            truncated_hash = torrent.hash[:16]
            print(f"{i:<4} {status:<3} {truncated_name:<60} {truncated_hash}...")

        print("\n[B] = Already blacklisted")
        print("\nEnter torrent numbers to toggle blacklist (space-separated, e.g., '1 3 5')")
        print("Or enter 'q' to quit without changes")

        try:
            selection = input("\nSelect torrents: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled")
            return 0

        if selection.lower() == 'q':
            print("Cancelled")
            return 0

        # Parse selection
        try:
            selected_indices = [int(x) for x in selection.split()]
        except ValueError:
            print("Invalid input. Please enter numbers separated by spaces.", file=sys.stderr)
            return 1

        # Process selections
        changes = []
        for idx in selected_indices:
            if idx < 1 or idx > len(torrents):
                print(f"Skipping invalid number: {idx}")
                continue

            torrent = torrents[idx - 1]
            is_blacklisted = torrent.hash in blacklisted_hashes

            if is_blacklisted:
                # Remove from blacklist
                if state.remove_from_blacklist(torrent.hash):
                    changes.append(f"Removed: {torrent.name}")
            else:
                # Add to blacklist
                reason = "Manually protected" if not args.reason else args.reason
                if state.add_to_blacklist(torrent.hash, torrent.name, reason):
                    changes.append(f"Added: {torrent.name}")

        if changes:
            print("\nChanges applied:")
            for change in changes:
                print(f"  {change}")
            return 0
        else:
            print("\nNo changes made")
            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog='qbt-cleanup-ctl',
        description='Control utility for qBittorrent cleanup tool'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Blacklist commands
    blacklist_parser = subparsers.add_parser('blacklist', help='Manage blacklist')
    blacklist_subparsers = blacklist_parser.add_subparsers(dest='blacklist_command')

    # blacklist add
    add_parser = blacklist_subparsers.add_parser('add', help='Add torrent to blacklist')
    add_parser.add_argument('hash', help='Torrent hash')
    add_parser.add_argument('--name', help='Torrent name (optional)')
    add_parser.add_argument('--reason', help='Reason for blacklisting (optional)')
    add_parser.add_argument('--no-lookup', action='store_true',
                           help='Do not lookup torrent name from qBittorrent')

    # blacklist remove
    remove_parser = blacklist_subparsers.add_parser('remove', help='Remove torrent from blacklist')
    remove_parser.add_argument('hash', help='Torrent hash')

    # blacklist list
    blacklist_subparsers.add_parser('list', help='List blacklisted torrents')

    # blacklist clear
    clear_parser = blacklist_subparsers.add_parser('clear', help='Clear all blacklisted torrents')
    clear_parser.add_argument('-y', '--yes', action='store_true', help='Skip confirmation')

    # Status command
    subparsers.add_parser('status', help='Show status information')

    # List torrents command
    list_parser = subparsers.add_parser('list', help='List tracked torrents')
    list_parser.add_argument('--limit', type=int, help='Limit number of results')

    # Select torrents command (interactive)
    select_parser = subparsers.add_parser('select', help='Interactively select torrents to blacklist/unblacklist')
    select_parser.add_argument('--reason', help='Reason for blacklisting (optional)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Route to appropriate command
    if args.command == 'blacklist':
        if not args.blacklist_command:
            blacklist_parser.print_help()
            return 1

        if args.blacklist_command == 'add':
            return cmd_blacklist_add(args)
        elif args.blacklist_command == 'remove':
            return cmd_blacklist_remove(args)
        elif args.blacklist_command == 'list':
            return cmd_blacklist_list(args)
        elif args.blacklist_command == 'clear':
            return cmd_blacklist_clear(args)
    elif args.command == 'status':
        return cmd_status(args)
    elif args.command == 'list':
        return cmd_list_torrents(args)
    elif args.command == 'select':
        return cmd_select_torrents(args)

    parser.print_help()
    return 1


if __name__ == '__main__':
    sys.exit(main())
