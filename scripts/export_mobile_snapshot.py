"""Export the read-only RHYTHMOS iOS Today projection as JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.mobile_snapshot import write_mobile_daily_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Destination JSON file")
    parser.add_argument("--db", type=Path, default=None, help="Source recovery.db (read-only)")
    parser.add_argument("--date", default=None, help="ISO date to export; defaults to latest factual date")
    args = parser.parse_args()

    exported = write_mobile_daily_snapshot(args.output, args.db, args.date)
    if not exported:
        print("No factual RHYTHMOS date is available; no file was written.")
        return 2
    print(f"Wrote mobile daily snapshot to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
