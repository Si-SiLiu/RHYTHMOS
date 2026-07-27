"""Idempotently remove the RHYTHMOS｜律衡 user LaunchAgent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.scheduler.launch_agent import DEFAULT_PLIST_PATH, uninstall_launch_agent


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Uninstall the RHYTHMOS｜律衡 sync LaunchAgent."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plist", type=Path, default=DEFAULT_PLIST_PATH)
    parser.add_argument("--no-unload", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    target = args.plist.expanduser()
    if args.dry_run:
        result = {
            "status": "dry_run",
            "target": str(target),
            "installed": target.exists(),
            "changed": False,
            "called_launchctl": False,
        }
    else:
        removed = uninstall_launch_agent(
            plist_path=target,
            unload=not args.no_unload,
        )
        result = {
            "status": "uninstalled",
            "target": str(target),
            "changed": removed,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
