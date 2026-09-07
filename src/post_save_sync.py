"""Start a canonical local sync after today's recovery data is saved."""

from __future__ import annotations

from pathlib import Path
import subprocess
from datetime import date


BASE_DIR = Path(__file__).resolve().parents[1]


def refresh_local_coach_for_date(coach_date: str, connection=None) -> bool:
    """Rebuild one recommendation after a local sleep/training/nutrition/neural write."""
    try:
        from .db import connect
        from .local_coach.engine import generate_recommendation
        from .local_coach.config import load_rules
        from .local_coach.storage import load_input, upsert_recommendation
        from .personal_logging.summaries import (
            rebuild_daily_nutrition_summary, rebuild_daily_training_summary,
        )
        owns_connection = connection is None
        connection = connection or connect()
        try:
            # The modern meal editor is read directly by Local Coach; these
            # summaries keep legacy logging and manual training in sync too.
            rebuild_daily_nutrition_summary(connection, coach_date)
            rebuild_daily_training_summary(connection, coach_date)
            if not connection.execute(
                    "SELECT 1 FROM recovery_scores WHERE date=?", (coach_date,)
            ).fetchone():
                return False
            rules = load_rules()
            output = generate_recommendation(
                load_input(connection, coach_date, freshness_days=rules["freshness_days"]),
                rules,
            )
            upsert_recommendation(connection, output)
            connection.commit()
            return True
        finally:
            if owns_connection:
                connection.close()
    except Exception:
        # A user save must remain successful even if a recommendation cannot be
        # rebuilt (for example, before the first recovery score exists).
        return False


def start_priority_data_sync() -> int:
    """Start the highest-priority full sync after recovery, sleep, or training changes."""
    python = BASE_DIR / ".venv" / "bin" / "python"
    runner = BASE_DIR / "scripts" / "run_scheduled_sync.py"
    if not python.is_file() or not runner.is_file():
        raise RuntimeError("同步运行环境不完整")
    process = subprocess.Popen(
        [str(python), str(runner), "--trigger-type", "manual"],
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return process.pid


def start_codex_feedback_refresh(analysis_date: str) -> int:
    """Queue a focused morning-feedback refresh after recovery is confirmed.

    It runs independently from the longer Polar fetch so a 06:30 recovery save
    can update the training recommendation without waiting for historical data.
    """
    try:
        normalized_date = date.fromisoformat(str(analysis_date)[:10]).isoformat()
    except ValueError as exc:
        raise RuntimeError("反馈日期无效") from exc
    python = BASE_DIR / ".venv" / "bin" / "python"
    runner = BASE_DIR / "scripts" / "generate_codex_feedback.py"
    if not python.is_file() or not runner.is_file():
        raise RuntimeError("Codex 反馈运行环境不完整")
    process = subprocess.Popen(
        [str(python), str(runner), "--date", normalized_date],
        cwd=BASE_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return process.pid


def start_recovery_post_save_sync() -> int:
    """Backward-compatible name for the priority data-change trigger."""
    return start_priority_data_sync()
