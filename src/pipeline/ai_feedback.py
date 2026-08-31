"""Optional Codex-feedback step after deterministic data processing."""

try:
    from src.ai_feedback import AIFeedbackError, generate_latest_feedback
except ImportError:
    from ai_feedback import AIFeedbackError, generate_latest_feedback


def run(context, dry_run=False):
    """Never make optional AI feedback prevent source data from synchronizing."""

    if dry_run:
        return {"ai_feedback_records_updated": 0, "dry_run": True}
    try:
        output = generate_latest_feedback(language="zh-CN")
    except AIFeedbackError:
        return {
            "ai_feedback_records_updated": 0,
            "warning_count": 1,
            "warnings": ["Codex 综合反馈未更新；本地规则反馈保持可用。"],
        }
    return {
        "ai_feedback_records_updated": 1,
        "ai_feedback_date": output.get("audit", {}).get("generated_at"),
    }
