#!/usr/bin/env python3
"""invctl - inventory management CLI.

Stores items in $INVCTL_DB (default: ./inventory.json). Talks to a (pretend)
pricing service that requires --token.
"""

import argparse
import csv
import json
import os
import sys
import time

DB = os.environ.get("INVCTL_DB", "inventory.json")
CONFIG = os.path.expanduser("~/.invctl.toml")


def load():
    if not os.path.exists(DB):
        items = [
            {
                "sku": f"SKU-{i:04d}",
                "name": f"Widget {i}",
                "qty": i % 7,
                "created": 1767225600 + i * 3600,
            }
            for i in range(1, 401)
        ]
        save(items)
        return items
    with open(DB) as f:
        return json.load(f)


def save(items):
    with open(DB, "w") as f:
        json.dump(items, f, indent=2)


def warn_config():
    if not os.path.exists(CONFIG):
        print(f"warning: {CONFIG} not found, using defaults")


def find(items, sku):
    for it in items:
        if it["sku"] == sku:
            return it
    print(f"Error: {sku} not found", file=sys.stderr)
    sys.exit(1)


def cmd_list(args):
    warn_config()
    items = load()
    if args.json:
        print(
            json.dumps([{**it, "created": time.ctime(it["created"])} for it in items])
        )
    else:
        for it in items:
            print(f"{it['sku']}  {it['name']:<20} qty={it['qty']}")


def cmd_get(args):
    it = find(load(), args.sku)
    print(json.dumps(it) if args.json else f"{it['sku']} {it['name']} qty={it['qty']}")


def cmd_import(args):
    items = load()
    known = {it["sku"] for it in items}
    added = 0
    with open(args.file) as f:
        for row in csv.DictReader(f):
            try:
                qty = int(row["qty"])
            except (KeyError, ValueError):
                print(f"skipping bad row: {row}", file=sys.stderr)
                continue
            if row["sku"] in known:
                print(f"skipping duplicate {row['sku']}", file=sys.stderr)
                continue
            items.append(
                {
                    "sku": row["sku"],
                    "name": row["name"],
                    "qty": qty,
                    "created": int(time.time()),
                }
            )
            added += 1
    save(items)
    print(f"imported {added} items")


def cmd_export(args):
    items = load()
    if args.format == "json":
        print(json.dumps(items))
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=["sku", "name", "qty", "created"])
        w.writeheader()
        w.writerows(items)


def cmd_delete(args):
    items = load()
    it = find(items, args.sku)
    if not args.force:
        if not sys.stdin.isatty():
            print("Error: refusing to delete without --force", file=sys.stderr)
            sys.exit(1)
        if input(f"Delete {args.sku}? [y/N] ").lower() != "y":
            return
    if it["qty"] > 0 and not args.force:
        print("Error: item still has stock", file=sys.stderr)
        sys.exit(1)
    save([x for x in items if x["sku"] != args.sku])
    print(f"deleted {args.sku}")


def cmd_price(args):
    if not args.token:
        print("Error: --token required", file=sys.stderr)
        sys.exit(1)
    it = find(load(), args.sku)
    print(json.dumps({"sku": it["sku"], "price_cents": 1999}))


def main():
    p = argparse.ArgumentParser(prog="invctl", description="Manage inventory.")
    p.add_argument("--version", action="version", version="invctl 1.4.2")
    sub = p.add_subparsers(dest="noun", required=True)
    item = sub.add_parser("item", help="manage items").add_subparsers(
        dest="verb", required=True
    )

    s = item.add_parser("list", help="list items")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = item.add_parser("get", help="show one item")
    s.add_argument("sku")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_get)

    s = item.add_parser("import", help="import items from CSV")
    s.add_argument("file")
    s.set_defaults(fn=cmd_import)

    s = item.add_parser("export", help="export all items")
    s.add_argument("--format", choices=["csv", "json"], default="csv")
    s.set_defaults(fn=cmd_export)

    s = item.add_parser("delete", help="delete an item")
    s.add_argument("sku")
    s.add_argument("--force", action="store_true", help="skip confirmation")
    s.set_defaults(fn=cmd_delete)

    s = item.add_parser("price", help="look up current price")
    s.add_argument("sku")
    s.add_argument("--token", help="pricing API token")
    s.set_defaults(fn=cmd_price)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
