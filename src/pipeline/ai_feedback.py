"""Optional Codex-feedback step after deterministic data processing."""

import sqlite3

try:
    from src.ai_feedback import AIFeedbackError, generate_latest_feedback
    from src.dashboard_data import get_latest_ai_feedback
    from src.db import connect
except ImportError:
    from ai_feedback import AIFeedbackError, generate_latest_feedback
    from dashboard_data import get_latest_ai_feedback
    from db import connect


def run(context, dry_run=False):
    """Never make optional AI feedback prevent source data from synchronizing."""

    if dry_run:
        return {"ai_feedback_records_updated": 0, "dry_run": True}
    try:
        connection = connect()
        try:
            row = connection.execute("SELECT MAX(date) FROM recovery_scores").fetchone()
            analysis_date = str(row[0]) if row and row[0] else None
        finally:
            connection.close()
        existing = get_latest_ai_feedback(analysis_date=analysis_date) if analysis_date else None
        if (
            existing
            and not existing.get("is_stale")
            and context.get("trigger_type") != "manual"
        ):
            return {
                "ai_feedback_records_updated": 0,
                "ai_feedback_skipped_unchanged": True,
            }
        output = generate_latest_feedback(language="zh-CN")
    except (AIFeedbackError, OSError, ValueError, sqlite3.Error):
        return {
            "ai_feedback_records_updated": 0,
            "warning_count": 1,
            "warnings": ["Codex 综合反馈未更新；本地规则反馈保持可用。"],
        }
    return {
        "ai_feedback_records_updated": 1,
        "ai_feedback_date": output.get("audit", {}).get("generated_at"),
    }
