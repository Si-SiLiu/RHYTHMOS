"""Install or regenerate the user LaunchAgent for daily local sync."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.scheduler.config import CONFIG_PATH, load_scheduler_config
from src.scheduler.launch_agent import (
    DEFAULT_PLIST_PATH,
    install_launch_agent,
    render_launch_agent,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the RHYTHMOS｜律衡 fixed-time sync LaunchAgent."
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--plist", type=Path, default=DEFAULT_PLIST_PATH)
    parser.add_argument("--project-root", type=Path, default=BASE_DIR)
    parser.add_argument(
        "--no-load",
        action="store_true",
        help="Generate the plist without calling launchctl (primarily for tests).",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    loaded = load_scheduler_config(args.config)
    config = loaded.config
    if not config.enabled:
        print(json.dumps({"status": "disabled", "installed": False}))
        return 0
    if args.dry_run:
        render_launch_agent(args.project_root, config)
        result = {
            "status": "dry_run",
            "target": str(args.plist.expanduser()),
            "sync_times": list(config.scheduled_times),
            "timezone_mode": config.timezone_mode,
            "config_fallback": loaded.used_fallback,
            "wrote_files": False,
            "called_launchctl": False,
        }
    else:
        installed = install_launch_agent(
            args.project_root,
            config,
            plist_path=args.plist,
            load=not args.no_load,
        )
        result = {
            "status": "installed",
            "target": str(installed.path),
            "sync_times": list(config.scheduled_times),
            "timezone_mode": config.timezone_mode,
            "config_fallback": loaded.used_fallback,
            "changed": installed.changed,
            "loaded": installed.loaded,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
