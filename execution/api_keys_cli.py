"""
CLI tool for managing EDGAR Intelligence API keys.

Usage:
    python api_keys_cli.py create --name "John Doe" --email john@example.com
    python api_keys_cli.py create --name "Pro User" --email pro@example.com --tier pro
    python api_keys_cli.py list
    python api_keys_cli.py revoke --id 3
    python api_keys_cli.py usage --id 1
"""

import argparse
import sys

from api_db import create_key, list_keys, revoke_key, get_daily_usage, get_key_limit, TIER_LIMITS


def cmd_create(args):
    """Create a new API key."""
    try:
        plaintext_key = create_key(name=args.name, email=args.email, tier=args.tier)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    limit = TIER_LIMITS[args.tier]
    print()
    print("  API Key created successfully!")
    print()
    print(f"    Key:    {plaintext_key}")
    print(f"    Name:   {args.name}")
    print(f"    Email:  {args.email}")
    print(f"    Tier:   {args.tier} ({limit} queries/day)")
    print()
    print("    SAVE THIS KEY - it cannot be retrieved again.")
    print()


def cmd_list(args):
    """List all API keys."""
    keys = list_keys()

    if not keys:
        print("No API keys found.")
        return

    print()
    print(f"  {'ID':<4} {'Prefix':<20} {'Name':<16} {'Email':<24} {'Tier':<6} {'Active':<8} {'Last Used'}")
    print(f"  {'--':<4} {'--':<20} {'--':<16} {'--':<24} {'--':<6} {'--':<8} {'--'}")

    for key in keys:
        active = "yes" if key["is_active"] else "no"
        last_used = key["last_used"][:10] if key["last_used"] else "never"
        print(f"  {key['id']:<4} {key['key_prefix']:<20} {key['name']:<16} {key['email']:<24} {key['tier']:<6} {active:<8} {last_used}")

    print()


def cmd_revoke(args):
    """Revoke an API key."""
    success = revoke_key(args.id)
    if success:
        print(f"  API key {args.id} revoked successfully.")
    else:
        print(f"  Error: API key {args.id} not found.")


def cmd_usage(args):
    """Show usage for an API key."""
    keys = list_keys()
    key = next((k for k in keys if k["id"] == args.id), None)

    if not key:
        print(f"  Error: API key {args.id} not found.")
        return

    count = get_daily_usage(args.id)
    limit = get_key_limit(key["tier"])

    print()
    print(f"  Key:       {key['key_prefix']}")
    print(f"  Name:      {key['name']}")
    print(f"  Tier:      {key['tier']}")
    print(f"  Today:     {count}/{limit} queries used")
    print(f"  Remaining: {limit - count}")
    print()


def main():
    parser = argparse.ArgumentParser(description="EDGAR Intelligence API Key Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # create
    create_parser = subparsers.add_parser("create", help="Create a new API key")
    create_parser.add_argument("--name", required=True, help="User/app name")
    create_parser.add_argument("--email", required=True, help="Contact email")
    create_parser.add_argument("--tier", default="free", choices=list(TIER_LIMITS.keys()), help="Pricing tier")

    # list
    subparsers.add_parser("list", help="List all API keys")

    # revoke
    revoke_parser = subparsers.add_parser("revoke", help="Revoke an API key")
    revoke_parser.add_argument("--id", required=True, type=int, help="Key ID to revoke")

    # usage
    usage_parser = subparsers.add_parser("usage", help="Show usage for a key")
    usage_parser.add_argument("--id", required=True, type=int, help="Key ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "revoke": cmd_revoke,
        "usage": cmd_usage,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
