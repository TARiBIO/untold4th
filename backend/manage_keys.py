#!/usr/bin/env python3
"""
Simple key manager for the Untold 4th AI sizing API.

Usage examples:
  python manage_keys.py list
  python manage_keys.py add "Brand X"
  python manage_keys.py deactivate "Brand X"
  python manage_keys.py activate "Brand X"
  python manage_keys.py show "Brand X"
"""

import argparse
import json
import secrets
import string
from pathlib import Path
import sys

API_KEYS_FILE = Path(__file__).with_name("api_keys.json")


def load_keys():
    if API_KEYS_FILE.exists():
        with API_KEYS_FILE.open() as f:
            return json.load(f)
    return {}


def save_keys(data):
    with API_KEYS_FILE.open("w") as f:
        json.dump(data, f, indent=2)
        print(f"[OK] Saved keys to {API_KEYS_FILE}")


def generate_key(length=20):
    alphabet = string.ascii_uppercase + string.digits
    return "UN4TH-" + "".join(secrets.choice(alphabet) for _ in range(length))


def cmd_list(args):
    data = load_keys()
    if not data:
        print("No keys yet.")
        return
    print("Existing brands & status:\n")
    for brand, info in data.items():
        status = "ACTIVE" if info.get("active", True) else "INACTIVE"
        print(f"- {brand}: {status}")


def cmd_add(args):
    data = load_keys()
    brand = args.brand.strip()
    if brand in data:
        print(f"[ERR] Brand '{brand}' already exists.")
        sys.exit(1)
    key = generate_key()
    data[brand] = {"key": key, "active": True}
    save_keys(data)
    print(f"[OK] Created key for {brand}: {key}")


def cmd_deactivate(args):
    data = load_keys()
    brand = args.brand.strip()
    if brand not in data:
        print(f"[ERR] Brand '{brand}' not found.")
        sys.exit(1)
    data[brand]["active"] = False
    save_keys(data)
    print(f"[OK] Deactivated key for {brand}.")


def cmd_activate(args):
    data = load_keys()
    brand = args.brand.strip()
    if brand not in data:
        print(f"[ERR] Brand '{brand}' not found.")
        sys.exit(1)
    data[brand]["active"] = True
    save_keys(data)
    print(f"[OK] Activated key for {brand}.")


def cmd_show(args):
    data = load_keys()
    brand = args.brand.strip()
    info = data.get(brand)
    if not info:
        print(f"[ERR] Brand '{brand}' not found.")
        sys.exit(1)
    status = "ACTIVE" if info.get("active", True) else "INACTIVE"
    print(f"Brand: {brand}")
    print(f"Key:   {info['key']}")
    print(f"Status:{status}")


def main():
    parser = argparse.ArgumentParser(description="Manage API keys for Untold 4th backend")
    sub = parser.add_subparsers(dest="command", required=True)

    sub_list = sub.add_parser("list", help="List all brands & status")
    sub_list.set_defaults(func=cmd_list)

    sub_add = sub.add_parser("add", help="Add a new brand and generate a key")
    sub_add.add_argument("brand", help="Brand name (e.g. 'Antracea')")
    sub_add.set_defaults(func=cmd_add)

    sub_deact = sub.add_parser("deactivate", help="Deactivate a brand key")
    sub_deact.add_argument("brand")
    sub_deact.set_defaults(func=cmd_deactivate)

    sub_act = sub.add_parser("activate", help="Activate a brand key")
    sub_act.add_argument("brand")
    sub_act.set_defaults(func=cmd_activate)

    sub_show = sub.add_parser("show", help="Show key for a single brand")
    sub_show.add_argument("brand")
    sub_show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
