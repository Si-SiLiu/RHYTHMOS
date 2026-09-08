"""Manually publish the local mobile-safe projection to the RHYTHMOS cloud."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.cloud_projection_sync import CloudProjectionSyncError, publish_local_projections


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publish RHYTHMOS projections through the configured HTTPS sync service.")
    parser.add_argument("--days", type=int, default=14, help="History span to publish (1-30).")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        result = publish_local_projections(history_days=args.days)
    except (CloudProjectionSyncError, ValueError) as error:
        print(json.dumps({"success": False, "error": str(error)}, ensure_ascii=False))
        return 2
    # Never print a payload, bearer token, server URL, database content, or identifier.
    print(json.dumps(result or {"success": True, "status": "not_configured"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
