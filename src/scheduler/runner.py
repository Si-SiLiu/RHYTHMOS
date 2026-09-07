"""Single trigger-aware adapter around the existing One-Click Sync Pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

from src.pipeline.history import HISTORY_PATH
from src.sync_pipeline import PipelineError, PipelineRunner

from . import TRIGGER_TYPES
from .history import CatchUpLimitReached, SchedulerHistory
from .lock import PipelineLockBusy
from .config import load_scheduler_config
from .status import evaluate_catch_up


TriggerType = Literal["manual", "scheduled", "catch_up"]


class SchedulerRunError(RuntimeError):
    def __init__(self, error_code: str, summary: dict):
        super().__init__(error_code)
        self.error_code = error_code
        self.summary = summary


def _now() -> datetime:
    return datetime.now().astimezone()


def _close_pipeline_logger(runner) -> None:
    logger = getattr(runner, "logger", None)
    close = getattr(logger, "close", None)
    if callable(close):
        close()


def run_triggered_pipeline(
    trigger_type: TriggerType,
    *,
    dry_run: bool = False,
    scheduler_history: SchedulerHistory | None = None,
    pipeline_history_path: Path | str = HISTORY_PATH,
    pipeline_factory: Callable[[], PipelineRunner] = PipelineRunner,
    now_provider: Callable[[], datetime] = _now,
    acquire_lock: bool = True,
) -> dict:
    """Run the shared pipeline with lock and trigger provenance.

    Scheduled requests run at every LaunchAgent interval so the local dataset
    stays current throughout the day. Catch-up requests are still limited to
    one successful canonical pipeline run per local day; manual requests
    remain explicitly user-driven and may always run when the lock is
    available.
    """
    if trigger_type not in TRIGGER_TYPES:
        raise ValueError("SCHEDULER_TRIGGER_TYPE_INVALID")
    history = scheduler_history or SchedulerHistory()
    invocation_id = None
    pipeline_runner = None
    try:
        started_at = now_provider()
        if started_at.tzinfo is None:
            raise ValueError("SCHEDULER_TIMESTAMP_MUST_BE_AWARE")
        if trigger_type == "catch_up" and not dry_run:
            state = evaluate_catch_up(
                load_scheduler_config().config,
                scheduler_history=history,
                sync_history_path=pipeline_history_path,
                now=started_at,
            )
            if not state.eligible:
                return {
                    "success": True,
                    "status": state.state,
                    "trigger_type": trigger_type,
                    "pipeline_invoked": False,
                    "today_synced": state.today_synced,
                }
        try:
            invocation_id = history.begin(trigger_type, started_at, dry_run=dry_run)
        except CatchUpLimitReached as exc:
            raise SchedulerRunError(
                "CATCH_UP_LIMIT_REACHED",
                {
                    "success": False,
                    "status": "limit_reached",
                    "trigger_type": trigger_type,
                    "error_code": "CATCH_UP_LIMIT_REACHED",
                },
            ) from exc

        try:
            pipeline_runner = pipeline_factory()
            pipeline_summary = pipeline_runner.run(
                dry_run=dry_run,
                trigger_type=trigger_type,
                # Scheduled and app-open refreshes only need to regenerate
                # deterministic and Codex feedback when their source snapshot
                # changed. Manual saves remain full runs because the change can
                # be local (for example, a reviewed recovery record).
                if_new_data=trigger_type in {"scheduled", "catch_up"},
                acquire_lock=acquire_lock,
            )
        except Exception as exc:
            if isinstance(exc, PipelineError):
                pipeline_run_id = exc.summary.get("run_id")
                error_code = exc.summary.get("error_code", "PIPELINE_FAILED")
                warning_count = int(exc.summary.get("warning_count", 0) or 0)
            elif isinstance(exc, PipelineLockBusy):
                pipeline_run_id = None
                error_code = "SYNC_ALREADY_RUNNING"
                warning_count = 0
            else:
                pipeline_run_id = None
                error_code = "PIPELINE_INVOCATION_FAILED"
                warning_count = 0
            history.finish(
                invocation_id,
                now_provider(),
                success=False,
                pipeline_run_id=pipeline_run_id,
                warning_count=warning_count,
                result_code=error_code,
            )
            safe_summary = {
                "success": False,
                "status": "failed",
                "trigger_type": trigger_type,
                "scheduler_invocation_id": invocation_id,
                "pipeline_run_id": pipeline_run_id,
                "error_code": error_code,
            }
            raise SchedulerRunError(error_code, safe_summary) from exc

        warning_count = int(pipeline_summary.get("warning_count", 0) or 0)
        result_code = "COMPLETED_WITH_WARNINGS" if warning_count else "COMPLETED"
        history.finish(
            invocation_id,
            now_provider(),
            success=True,
            pipeline_run_id=pipeline_summary.get("run_id"),
            warning_count=warning_count,
            result_code=result_code,
        )
        return {
            **pipeline_summary,
            "status": "success",
            "trigger_type": trigger_type,
            "scheduler_invocation_id": invocation_id,
            "pipeline_invoked": True,
        }
    finally:
        if pipeline_runner is not None:
            _close_pipeline_logger(pipeline_runner)


def run_manual_sync(**kwargs) -> dict:
    return run_triggered_pipeline("manual", **kwargs)


def run_scheduled_sync(**kwargs) -> dict:
    return run_triggered_pipeline("scheduled", **kwargs)


def run_catch_up_sync(**kwargs) -> dict:
    return run_triggered_pipeline("catch_up", **kwargs)
