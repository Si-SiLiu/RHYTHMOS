"""Deterministic post-import rebuild followed by a queued morning feedback refresh."""

from src.pipeline import baseline, confidence, local_coach, metrics, recovery, report
from scripts.update_project_state import update_project_state


def run_downstream(date_value=None):
    context = {"results": {}, "kubios_screenshot_date": date_value}
    steps = (
        ("metrics", metrics.run), ("baseline", baseline.run),
        ("recovery", recovery.run), ("confidence", confidence.run),
        ("local-coach", local_coach.run), ("report", report.run),
    )
    try:
        for name, runner in steps:
            context["results"][name] = runner(context, dry_run=False)
        state = update_project_state()
        context["results"]["governance"] = {
            "state_updated": True, "test_total": state["test_total"]
        }
        if date_value:
            try:
                from src.post_save_sync import start_codex_feedback_refresh

                context["results"]["ai-feedback"] = {
                    "queued": True,
                    "pid": start_codex_feedback_refresh(str(date_value)),
                }
            except RuntimeError:
                # Confirmed recovery data remains available even when the
                # optional cloud explanation runner cannot be started.
                context["results"]["ai-feedback"] = {"queued": False}
    except Exception:
        return {"success": False, "error_code": "downstream_rebuild_failed"}
    return {"success": True, "steps": context["results"]}
