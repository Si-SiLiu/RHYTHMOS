from datetime import datetime
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
# Backward-compatible export for maintenance tooling.  Routine syncs below do
# not invoke it because it executes the repository-wide test suite.
try:
    from scripts.update_project_state import update_project_state
except ImportError:
    base_path = str(BASE_DIR)
    if base_path not in sys.path:
        sys.path.insert(0, base_path)
    from scripts.update_project_state import update_project_state


CHANGELOG_PATH = BASE_DIR / "docs" / "CHANGELOG.md"
HANDOFF_PATH = BASE_DIR / "docs" / "HANDOFF.md"
SYNC_START = "<!-- PIPELINE_SYNC_START -->"
SYNC_END = "<!-- PIPELINE_SYNC_END -->"


def _replace_generated_region(path, content):
    path = Path(path)
    document = path.read_text(encoding="utf-8")
    if document.count(SYNC_START) != 1 or document.count(SYNC_END) != 1:
        raise RuntimeError(f"Pipeline sync markers are invalid in {path.name}.")
    before = document.split(SYNC_START, 1)[0]
    after = document.split(SYNC_END, 1)[1]
    updated = before + SYNC_START + "\n" + content.rstrip() + "\n" + SYNC_END + after
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(path)


def sync_runtime_documents(context, changelog_path=CHANGELOG_PATH, handoff_path=HANDOFF_PATH):
    results = context.get("results", {})
    resume = context.get("resume_aggregates", {})
    imported = results.get("import", {}).get(
        "records_imported", resume.get("records_imported", 0)
    )
    metrics = results.get("metrics", {}).get(
        "metrics_updated", resume.get("metrics_updated", 0)
    )
    baselines = results.get("baseline", {}).get(
        "baseline_updated", resume.get("baseline_updated", 0)
    )
    recovery = results.get("recovery", {}).get(
        "recovery_updated", resume.get("recovery_updated", 0)
    )
    reports = results.get("report", {}).get(
        "reports_generated", resume.get("reports_generated", 0)
    )
    warnings = results.get("fetch", {}).get(
        "warning_count", resume.get("warning_count", 0)
    )
    confidence = results.get("confidence", {}).get(
        "confidence_updated", resume.get("confidence_updated", 0)
    )
    local_coach = results.get("local-coach", {}).get(
        "local_coach_records_updated", resume.get("local_coach_records_updated", 0)
    )
    prospective = results.get("local-coach", {}).get(
        "prospective_eligible_days", resume.get("prospective_eligible_days", 0)
    )
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    content = "\n".join(
        (
            f"- Last Pipeline Sync: {timestamp}",
            (
                "- Result: no new source content; deterministic rebuild and report skipped"
                if context.get("no_new_data")
                else "- Result: completed through report generation"
            ),
            f"- Records Imported: {imported}",
            f"- Metrics Updated: {metrics}",
            f"- Baselines Updated: {baselines}",
            f"- Recovery Scores Updated: {recovery}",
            f"- Reports Generated: {reports}",
            f"- Endpoint Warnings: {warnings}",
            f"- Confidence Updated: {confidence}",
            f"- Local Coach Records Updated: {local_coach}",
            f"- Prospective Eligible Days: {prospective} / 14",
        )
    )
    _replace_generated_region(changelog_path, content)
    _replace_generated_region(handoff_path, content)
    return timestamp


def run(context, dry_run=False):
    if dry_run:
        return {"state_updated": False, "state_check": "planned"}
    # A health-data sync must never be held hostage by the repository-wide
    # governance check.  That check discovers and runs the full test suite,
    # which is intentionally a separate maintenance operation and can take
    # minutes.  Keeping only the small generated sync regions here preserves
    # the operational handoff without delaying data, recovery, or Codex
    # feedback updates.
    try:
        synchronized_at = sync_runtime_documents(context)
    except (OSError, RuntimeError):
        # Documentation maintenance cannot invalidate a completed health-data
        # and Codex-feedback refresh. The next pipeline can retry it.
        return {
            "state_updated": False,
            "state_check": "deferred",
            "warning_count": 1,
            "warnings": ["GOVERNANCE_DOCUMENTS_NOT_UPDATED"],
        }
    return {
        "state_updated": True,
        "state_check": "deferred",
        "phase_documents_updated": True,
        "documents_updated_at": synchronized_at,
    }
