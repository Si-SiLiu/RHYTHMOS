import argparse
import json
from datetime import datetime
from time import perf_counter
from uuid import uuid4

try:
    from .pipeline import STEP_NAMES
    from .pipeline import baseline as baseline_step
    from .pipeline import fetch as fetch_step
    from .pipeline import governance as governance_step
    from .pipeline import confidence as confidence_step
    from .pipeline import ai_feedback as ai_feedback_step
    from .pipeline import importer as import_step
    from .pipeline import local_coach as local_coach_step
    from .pipeline import manual_summary as manual_summary_step
    from .pipeline import kubios_screenshot as kubios_screenshot_step
    from .pipeline import metrics as metrics_step
    from .pipeline import recovery as recovery_step
    from .pipeline import resolution as resolution_step
    from .pipeline import report as report_step
    from .pipeline import token as token_step
    from .pipeline.history import SyncHistory
    from .pipeline.logger import PipelineLogger
    from .pipeline.errors import PipelineStepError
    from .scheduler.lock import PipelineLock, PipelineLockBusy
except ImportError:
    from pipeline import STEP_NAMES
    from pipeline import baseline as baseline_step
    from pipeline import fetch as fetch_step
    from pipeline import governance as governance_step
    from pipeline import confidence as confidence_step
    from pipeline import ai_feedback as ai_feedback_step
    from pipeline import importer as import_step
    from pipeline import local_coach as local_coach_step
    from pipeline import manual_summary as manual_summary_step
    from pipeline import kubios_screenshot as kubios_screenshot_step
    from pipeline import metrics as metrics_step
    from pipeline import recovery as recovery_step
    from pipeline import resolution as resolution_step
    from pipeline import report as report_step
    from pipeline import token as token_step
    from pipeline.history import SyncHistory
    from pipeline.logger import PipelineLogger
    from pipeline.errors import PipelineStepError
    from scheduler.lock import PipelineLock, PipelineLockBusy


DEFAULT_STEPS = {
    "token": token_step.run,
    "fetch": fetch_step.run,
    "import": import_step.run,
    "kubios-screenshot": kubios_screenshot_step.run,
    "manual-summary": manual_summary_step.run,
    "metrics": metrics_step.run,
    "resolution": resolution_step.run,
    "baseline": baseline_step.run,
    "recovery": recovery_step.run,
    "confidence": confidence_step.run,
    "local-coach": local_coach_step.run,
    "ai-feedback": ai_feedback_step.run,
    "report": report_step.run,
    "governance": governance_step.run,
}

NO_NEW_DATA_SKIPPABLE_STEPS = {
    "metrics", "baseline", "recovery", "confidence", "local-coach"
}


class PipelineError(RuntimeError):
    def __init__(self, step, error_code, safe_message, summary):
        super().__init__(f"Pipeline stopped at {step} [{error_code}]: {safe_message}")
        self.step = step
        self.error_code = error_code
        self.safe_message = safe_message
        self.summary = summary


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _result_counts(result):
    return {
        "records_imported": int(result.get("records_imported", 0) or 0),
        "metrics_updated": int(result.get("metrics_updated", 0) or 0),
        "baseline_updated": int(result.get("baseline_updated", 0) or 0),
        "recovery_updated": int(result.get("recovery_updated", 0) or 0),
        "reports_generated": int(result.get("reports_generated", 0) or 0),
        "warning_count": int(result.get("warning_count", 0) or 0),
        "confidence_updated": int(result.get("confidence_updated", 0) or 0),
        "local_coach_records_updated": int(result.get("local_coach_records_updated", 0) or 0),
        "prospective_eligible_days": int(result.get("prospective_eligible_days", 0) or 0),
    }


def _safe_failure(step, exc):
    if isinstance(exc, PipelineStepError):
        return exc.code, exc.safe_message
    code = (
        "PIPELINE_FINALIZATION_FAILED"
        if step == "finalization"
        else f"{step.upper()}_STEP_FAILED"
    )
    return code, f"The {step} step failed safely. Review the step log and resume after correction."


class PipelineRunner:
    def __init__(self, steps=None, history=None, logger=None, lock_factory=None):
        self.steps = steps or DEFAULT_STEPS
        self.history = history or SyncHistory()
        self.logger = logger or PipelineLogger()
        self.lock_factory = lock_factory or (
            lambda trigger_type: PipelineLock(trigger_type=trigger_type)
        )

    def run(self, dry_run=False, only=None, resume=False, if_new_data=False,
            trigger_type="manual", acquire_lock=True):
        if trigger_type not in {"manual", "scheduled", "catch_up"}:
            raise ValueError("INVALID_SYNC_TRIGGER_TYPE")
        if acquire_lock:
            with self.lock_factory(trigger_type):
                return self.run(
                    dry_run=dry_run,
                    only=only,
                    resume=resume,
                    if_new_data=if_new_data,
                    trigger_type=trigger_type,
                    acquire_lock=False,
                )
        if only is not None and only not in self.steps:
            raise ValueError(f"Unknown pipeline step: {only}")
        if only and resume:
            raise ValueError("--only and --resume cannot be used together")
        if if_new_data and (only or resume):
            raise ValueError("--if-new-data requires a full non-resume pipeline")

        selected_steps = [only] if only else list(STEP_NAMES)
        run_id = self.history.latest_failed_run_id() if resume and not dry_run else None
        if resume and not dry_run and not run_id:
            raise ValueError("No interrupted pipeline is available to resume")
        run_id = run_id or uuid4().hex
        completed = self.history.completed_steps(run_id) if resume and not dry_run else set()
        pipeline_started_at = _now()
        pipeline_clock = perf_counter()
        context = {
            "run_id": run_id,
            "dry_run": dry_run,
            "trigger_type": trigger_type,
            "results": {},
            "resume_aggregates": (
                self.history.aggregate_run(run_id) if resume and not dry_run else {}
            ),
        }
        self.logger.pipeline_started(run_id, dry_run=dry_run, only=only, resume=resume)

        for step_name in selected_steps:
            if step_name in completed:
                context["results"][step_name] = {"resumed_skip": True}
                continue

            if context.get("no_new_data") and step_name in NO_NEW_DATA_SKIPPABLE_STEPS:
                step_started_at = _now()
                self.logger.step_started(run_id, step_name)
                result = {"no_new_data_skip": True}
                context["results"][step_name] = result
                self.logger.step_finished(run_id, step_name, 0.0)
                if not dry_run:
                    self.history.record(
                        run_id, step_started_at, _now(), 0.0, True, step_name,
                        "skipped:no_new_data", **_result_counts(result),
                        trigger_type=trigger_type,
                    )
                continue

            step_started_at = _now()
            step_clock = perf_counter()
            self.logger.step_started(run_id, step_name)
            try:
                result = self.steps[step_name](context, dry_run=dry_run) or {}
            except Exception as exc:
                step_duration = perf_counter() - step_clock
                error_code, safe_message = _safe_failure(step_name, exc)
                self.logger.step_failed(run_id, step_name, step_duration, error_code)
                finish_time = _now()
                if not dry_run:
                    self.history.record(
                        run_id,
                        step_started_at,
                        finish_time,
                        step_duration,
                        False,
                        step_name,
                        f"failed:{error_code}",
                        trigger_type=trigger_type,
                    )
                    total_duration = perf_counter() - pipeline_clock
                    aggregates = self.history.aggregate_run(run_id)
                    self.history.record(
                        run_id,
                        pipeline_started_at,
                        finish_time,
                        total_duration,
                        False,
                        "pipeline",
                        f"stopped:{step_name}:{error_code}",
                        **aggregates,
                        trigger_type=trigger_type,
                    )
                else:
                    aggregates = _result_counts({})
                    total_duration = perf_counter() - pipeline_clock
                self.logger.pipeline_finished(run_id, total_duration, False)
                summary = {
                    "run_id": run_id,
                    "success": False,
                    "dry_run": dry_run,
                    "trigger_type": trigger_type,
                    "failed_step": step_name,
                    "error_code": error_code,
                    "error_message": safe_message,
                    "duration": round(total_duration, 3),
                    **aggregates,
                }
                raise PipelineError(
                    step_name,
                    error_code,
                    safe_message,
                    summary,
                ) from exc

            step_duration = perf_counter() - step_clock
            context["results"][step_name] = result
            if if_new_data and not dry_run and step_name == "import":
                fetch_changed = context["results"].get("fetch", {}).get("source_changed", True)
                context["no_new_data"] = (
                    fetch_changed is False
                    and int(result.get("records_imported", 0) or 0) == 0
                    and int(result.get("kubios_files", 0) or 0) == 0
                )
            self.logger.step_finished(run_id, step_name, step_duration)
            if not dry_run:
                self.history.record(
                    run_id,
                    step_started_at,
                    _now(),
                    step_duration,
                    True,
                    step_name,
                    "completed",
                    **_result_counts(result),
                    trigger_type=trigger_type,
                )

        duration = perf_counter() - pipeline_clock
        try:
            if dry_run:
                aggregates = {
                    key: sum(
                        _result_counts(result)[key]
                        for result in context["results"].values()
                    )
                    for key in _result_counts({})
                }
            else:
                aggregates = self.history.aggregate_run(run_id)
                final_message = (
                    f"completed_selective:{only}"
                    if only
                    else "completed_no_new_data_with_warnings"
                    if context.get("no_new_data") and aggregates.get("warning_count", 0)
                    else "completed_no_new_data"
                    if context.get("no_new_data")
                    else "completed_with_warnings"
                    if aggregates.get("warning_count", 0)
                    else "completed"
                )
                self.history.record(
                    run_id,
                    pipeline_started_at,
                    _now(),
                    duration,
                    True,
                    "pipeline",
                    final_message,
                    **aggregates,
                    trigger_type=trigger_type,
                )
            self.logger.pipeline_finished(run_id, duration, True)
        except Exception as exc:
            error_code, safe_message = _safe_failure("finalization", exc)
            try:
                self.logger.step_failed(
                    run_id,
                    "finalization",
                    perf_counter() - pipeline_clock,
                    error_code,
                )
                self.logger.pipeline_finished(run_id, duration, False)
            except Exception:
                pass
            if "aggregates" not in locals():
                aggregates = _result_counts({})
            if not dry_run:
                try:
                    self.history.record(
                        run_id,
                        pipeline_started_at,
                        _now(),
                        duration,
                        False,
                        "pipeline",
                        f"stopped:finalization:{error_code}",
                        **aggregates,
                        trigger_type=trigger_type,
                    )
                except Exception:
                    pass
            summary = {
                "run_id": run_id,
                "success": False,
                "dry_run": dry_run,
                "trigger_type": trigger_type,
                "failed_step": "finalization",
                "error_code": error_code,
                "error_message": safe_message,
                "duration": round(duration, 3),
                **aggregates,
            }
            raise PipelineError(
                "finalization",
                error_code,
                safe_message,
                summary,
            ) from exc

        warnings = [
            warning
            for result in context["results"].values()
            for warning in result.get("warnings", [])
        ]
        return {
            "run_id": run_id,
            "success": True,
            "dry_run": dry_run,
            "trigger_type": trigger_type,
            "only": only,
            "resumed": resume,
            "duration": round(duration, 3),
            "steps": context["results"],
            "state_updated": bool(
                context["results"].get("governance", {}).get("state_updated", False)
            ),
            "dashboard_ready": True,
            "warnings": warnings,
            "no_new_data_short_circuit": bool(context.get("no_new_data")),
            **aggregates,
        }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the RHYTHMOS｜律衡 sync pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Validate steps without database writes.")
    parser.add_argument("--only", choices=tuple(DEFAULT_STEPS), help="Run one pipeline step.")
    parser.add_argument("--resume", action="store_true", help="Resume the latest interrupted run.")
    parser.add_argument("--if-new-data", action="store_true", help="Skip deterministic rebuilds only when fetched source files are unchanged.")
    parser.add_argument("--trigger-type", choices=("manual", "scheduled", "catch_up"), default="manual", help="Record why this pipeline run was started.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    runner = PipelineRunner()
    try:
        summary = runner.run(dry_run=args.dry_run, only=args.only, resume=args.resume, if_new_data=args.if_new_data, trigger_type=args.trigger_type)
    except (PipelineError, PipelineLockBusy, ValueError) as exc:
        if isinstance(exc, PipelineError):
            print(json.dumps(exc.summary, ensure_ascii=False, indent=2))
        raise SystemExit(str(exc))
    finally:
        runner.logger.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
