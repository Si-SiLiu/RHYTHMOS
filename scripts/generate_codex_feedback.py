"""Generate one approved Codex feedback record outside the long Polar sync."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import os
import sys


BASE_DIR = Path(__file__).resolve().parents[1]
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.ai_feedback import AIFeedbackError, generate_feedback_for_date


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh one RHYTHMOS Codex feedback record.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args(argv)
    try:
        analysis_date = date.fromisoformat(str(args.date)[:10]).isoformat()
        generate_feedback_for_date(analysis_date, language="zh-CN")
    except (AIFeedbackError, OSError, ValueError):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
