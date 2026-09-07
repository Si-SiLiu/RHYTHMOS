import io
import json
import plistlib
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.install_daily_sync_launch_agent import main as install_main
from scripts.uninstall_daily_sync_launch_agent import main as uninstall_main
from src.pipeline.history import SyncHistory
from src.scheduler.config import (
    DEFAULT_CONFIG,
    SCHEDULED_SYNC_TIMES,
    SchedulerConfig,
    SchedulerConfigError,
    load_scheduler_config,
    save_scheduler_config,
    validate_scheduler_config,
)
from src.scheduler.history import CatchUpLimitReached, SchedulerHistory
from src.scheduler.launch_agent import (
    LABEL,
    get_launch_agent_status,
    install_launch_agent,
    render_launch_agent,
    uninstall_launch_agent,
)
from src.scheduler.lock import PipelineLock, PipelineLockBusy, pipeline_is_running
from src.scheduler.runner import run_triggered_pipeline
from src.scheduler.status import (
    evaluate_catch_up,
    get_daily_scheduler_status,
    has_successful_sync_today,
    next_scheduled_datetime,
)


UTC = timezone.utc


def make_runtime(root: Path):
    python = root / ".venv" / "bin" / "python"
    runner = root / "scripts" / "run_scheduled_sync.py"
    python.parent.mkdir(parents=True)
    runner.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    runner.write_text("", encoding="utf-8")


class SchedulerConfigTests(unittest.TestCase):
    def test_default_time_is_the_final_fixed_slot(self):
        self.assertEqual(DEFAULT_CONFIG.sync_time, "23:00")
        self.assertEqual((DEFAULT_CONFIG.hour, DEFAULT_CONFIG.minute), (23, 0))
        self.assertEqual(
            DEFAULT_CONFIG.scheduled_times,
            ("12:00", "18:00", "23:00"),
        )

    def test_time_and_fields_are_strictly_validated(self):
        valid = {
            "enabled": True,
            "sync_time": "23:59",
            "timezone_mode": "system",
            "catch_up_on_app_start": True,
            "prompt_before_catch_up": True,
            "max_catch_up_runs_per_day": 1,
        }
        self.assertEqual(validate_scheduler_config(valid).sync_time, "23:59")
        for invalid in ("6:00", "24:00", "12:60", "06:00 ", 600):
            values = {**valid, "sync_time": invalid}
            with self.assertRaises(SchedulerConfigError):
                validate_scheduler_config(values)
        with self.assertRaises(SchedulerConfigError):
            validate_scheduler_config({**valid, "unexpected": True})
        with self.assertRaises(SchedulerConfigError):
            validate_scheduler_config({**valid, "enabled": 1})
        with self.assertRaises(SchedulerConfigError):
            validate_scheduler_config({**valid, "max_catch_up_runs_per_day": 2})

    def test_damaged_config_falls_back_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.toml"
            damaged = 'enabled = true\nsync_time = "not-time"\n'
            path.write_text(damaged, encoding="utf-8")
            loaded = load_scheduler_config(path)
            self.assertTrue(loaded.used_fallback)
            self.assertEqual(loaded.config, DEFAULT_CONFIG)
            self.assertEqual(path.read_text(encoding="utf-8"), damaged)

    def test_save_updates_time_atomically_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scheduler.toml"
            expected = SchedulerConfig(sync_time="07:45")
            save_scheduler_config(expected, path)
            loaded = load_scheduler_config(path)
            self.assertFalse(loaded.used_fallback)
            self.assertEqual(loaded.config, expected)


class LaunchAgentTests(unittest.TestCase):
    def test_plist_uses_virtualenv_middle_dot_path_and_local_calendar(self):
        with tempfile.TemporaryDirectory(prefix="Daily·Recovery·Coach-") as directory:
            root = Path(directory)
            make_runtime(root)
            value = plistlib.loads(render_launch_agent(root, DEFAULT_CONFIG))
            self.assertEqual(value["Label"], LABEL)
            self.assertEqual(
                value["ProgramArguments"],
                [
                    "/usr/bin/env",
                    str(root.resolve() / ".venv" / "bin" / "python"),
                    str(root.resolve() / "scripts" / "run_scheduled_sync.py"),
                    "--trigger-type",
                    "scheduled",
                ],
            )
            self.assertIn("·", value["ProgramArguments"][1])
            self.assertNotIn("WorkingDirectory", value)
            self.assertTrue(
                value["StandardOutPath"].endswith(
                    "/Library/Logs/Daily Recovery Coach/scheduler.stdout.log"
                )
            )
            self.assertEqual(
                value["StartCalendarInterval"],
                [{"Hour": int(value[:2]), "Minute": int(value[3:])} for value in SCHEDULED_SYNC_TIMES],
            )
            self.assertFalse(value["RunAtLoad"])
            self.assertNotIn("EnvironmentVariables", value)

    def test_plist_contains_no_secret_or_environment_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_runtime(root)
            content = render_launch_agent(root, DEFAULT_CONFIG).decode("utf-8")
            lowered = content.lower()
            self.assertNotIn("polar_access_token", lowered)
            self.assertNotIn("client_secret", lowered)
            self.assertNotIn(".env", lowered)

    def test_changed_time_keeps_refresh_calendar(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_runtime(root)
            config = SchedulerConfig(sync_time="18:27")
            value = plistlib.loads(render_launch_agent(root, config))
            self.assertEqual(
                value["StartCalendarInterval"],
                [{"Hour": int(value[:2]), "Minute": int(value[3:])} for value in SCHEDULED_SYNC_TIMES],
            )

    def test_install_without_loading_and_uninstall_are_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Daily·Recovery·Coach"
            root.mkdir()
            make_runtime(root)
            plist_path = Path(directory) / "LaunchAgents" / f"{LABEL}.plist"
            first = install_launch_agent(root, DEFAULT_CONFIG, plist_path=plist_path, load=False)
            second = install_launch_agent(root, DEFAULT_CONFIG, plist_path=plist_path, load=False)
            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertTrue(uninstall_launch_agent(plist_path=plist_path, unload=False))
            self.assertFalse(uninstall_launch_agent(plist_path=plist_path, unload=False))

    def test_launch_agent_status_distinguishes_loaded_and_abnormal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            make_runtime(root)
            plist_path = Path(directory) / "agent.plist"
            plist_path.write_bytes(render_launch_agent(root, DEFAULT_CONFIG))

            def loaded(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 0, "", "")

            def missing(*args, **kwargs):
                return subprocess.CompletedProcess(args[0], 113, "", "")

            self.assertEqual(
                get_launch_agent_status(plist_path, command_runner=loaded).state,
                "installed",
            )
            self.assertEqual(
                get_launch_agent_status(plist_path, command_runner=missing).state,
                "abnormal",
            )
            plist_path.unlink()
            self.assertEqual(get_launch_agent_status(plist_path).state, "not_installed")

    def test_install_and_uninstall_dry_runs_do_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "agent.plist"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    install_main(["--dry-run", "--plist", str(target)]),
                    0,
                )
            self.assertFalse(target.exists())
            self.assertFalse(json.loads(output.getvalue())["wrote_files"])
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    uninstall_main(["--dry-run", "--plist", str(target)]),
                    0,
                )
            self.assertFalse(target.exists())


class PipelineLockTests(unittest.TestCase):
    def test_lock_blocks_concurrent_process_boundary_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pipeline.lock"
            first = PipelineLock(path, trigger_type="manual")
            first.acquire()
            self.assertTrue(pipeline_is_running(path))
            with self.assertRaises(PipelineLockBusy):
                PipelineLock(
                    path,
                    acquire_timeout_seconds=0.01,
                    trigger_type="scheduled",
                ).acquire()
            first.release()
            self.assertFalse(pipeline_is_running(path))
            with PipelineLock(path, trigger_type="scheduled") as recovered:
                self.assertTrue(recovered.acquired)

    def test_exception_and_abandoned_metadata_do_not_permanently_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pipeline.lock"
            old = datetime.now(UTC) - timedelta(days=1)
            path.write_text(
                json.dumps(
                    {
                        "pid": 999999,
                        "acquired_at": old.isoformat(),
                        "trigger_type": "scheduled",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                with PipelineLock(
                    path,
                    stale_metadata_seconds=60,
                    trigger_type="manual",
                ) as lock:
                    self.assertTrue(lock.recovered_abandoned_metadata)
                    raise RuntimeError("synthetic")
            with PipelineLock(path, trigger_type="manual"):
                pass


class SchedulerHistoryAndCatchUpTests(unittest.TestCase):
    def test_trigger_types_and_one_catch_up_attempt_per_day(self):
        with tempfile.TemporaryDirectory() as directory:
            history = SchedulerHistory(Path(directory) / "scheduler.db")
            now = datetime(2026, 7, 15, 7, 0, tzinfo=UTC)
            invocation = history.begin("catch_up", now)
            history.finish(
                invocation,
                now + timedelta(minutes=1),
                success=True,
                pipeline_run_id="pipeline-1",
                warning_count=2,
                result_code="COMPLETED_WITH_WARNINGS",
            )
            self.assertEqual(history.catch_up_attempts_on(now.date()), 1)
            with self.assertRaises(CatchUpLimitReached):
                history.begin("catch_up", now + timedelta(hours=1))
            latest = history.latest("catch_up")
            self.assertEqual(latest["trigger_type"], "catch_up")
            self.assertEqual(latest["warning_count"], 2)

    def test_catch_up_is_eligible_after_the_most_recent_missed_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scheduler_history = SchedulerHistory(root / "scheduler.db")
            sync_path = root / "sync.db"
            lock_path = root / "pipeline.lock"
            before = datetime(2026, 7, 15, 22, 59, tzinfo=UTC)
            after = datetime(2026, 7, 15, 23, 1, tzinfo=UTC)
            self.assertEqual(
                evaluate_catch_up(
                    DEFAULT_CONFIG,
                    scheduler_history=scheduler_history,
                    sync_history_path=sync_path,
                    lock_path=lock_path,
                    now=before,
                ).state,
                "eligible",
            )
            due = evaluate_catch_up(
                DEFAULT_CONFIG,
                scheduler_history=scheduler_history,
                sync_history_path=sync_path,
                lock_path=lock_path,
                now=after,
            )
            self.assertEqual(due.state, "eligible")
            self.assertTrue(due.eligible)
            self.assertFalse(sync_path.exists())
            self.assertFalse((root / "scheduler.db").exists())

    def test_successful_pipeline_today_suppresses_catch_up(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)
            sync_path = root / "sync.db"
            SyncHistory(sync_path).record(
                "pipeline-1",
                (now - timedelta(minutes=1)).isoformat(),
                now.isoformat(),
                60,
                True,
                "pipeline",
                "completed",
            )
            self.assertTrue(has_successful_sync_today(sync_path, now=now))
            state = evaluate_catch_up(
                DEFAULT_CONFIG,
                scheduler_history=SchedulerHistory(root / "scheduler.db"),
                sync_history_path=sync_path,
                lock_path=root / "pipeline.lock",
                now=now,
            )
            self.assertEqual(state.state, "already_synced")

    def test_defer_and_running_lock_states_do_not_trigger_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 7, 15, 23, 30, tzinfo=UTC)
            history = SchedulerHistory(root / "scheduler.db")
            history.defer_catch_up(now)
            deferred = evaluate_catch_up(
                DEFAULT_CONFIG,
                scheduler_history=history,
                sync_history_path=root / "sync.db",
                lock_path=root / "pipeline.lock",
                now=now,
            )
            self.assertEqual(deferred.state, "deferred")

            other_history = SchedulerHistory(root / "other.db")
            with PipelineLock(root / "pipeline.lock", trigger_type="manual"):
                running = evaluate_catch_up(
                    DEFAULT_CONFIG,
                    scheduler_history=other_history,
                    sync_history_path=root / "sync.db",
                    lock_path=root / "pipeline.lock",
                    now=now,
                )
                self.assertEqual(running.state, "sync_running")

    def test_next_schedule_and_status_use_local_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 7, 15, 23, 1, tzinfo=UTC)
            next_run = next_scheduled_datetime(DEFAULT_CONFIG, now=now)
            self.assertEqual(next_run, datetime(2026, 7, 16, 12, 0, tzinfo=UTC))
            status = get_daily_scheduler_status(
                DEFAULT_CONFIG,
                scheduler_history=SchedulerHistory(root / "scheduler.db"),
                sync_history_path=root / "sync.db",
                lock_path=root / "pipeline.lock",
                now=now,
            )
            self.assertTrue(status.enabled)
            self.assertFalse(status.today_synced)
            self.assertEqual(status.sync_time, "23:00")


class TriggeredRunnerTests(unittest.TestCase):
    class FakeLogger:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakeRunner:
        def __init__(self, calls):
            self.calls = calls
            self.logger = TriggeredRunnerTests.FakeLogger()

        def run(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "success": True,
                "dry_run": kwargs["dry_run"],
                "run_id": "pipeline-1",
                "warning_count": 0,
            }

    def test_scheduler_calls_pipeline_once_and_passes_trigger_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            runner = self.FakeRunner(calls)
            now = datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
            summary = run_triggered_pipeline(
                "scheduled",
                dry_run=True,
                scheduler_history=SchedulerHistory(root / "scheduler.db"),
                pipeline_history_path=root / "sync.db",
                pipeline_factory=lambda: runner,
                now_provider=lambda: now,
            )
            self.assertEqual(
                calls,
                [{
                    "dry_run": True,
                    "trigger_type": "scheduled",
                    "if_new_data": True,
                    "acquire_lock": True,
                }],
            )
            self.assertEqual(summary["trigger_type"], "scheduled")
            self.assertTrue(summary["pipeline_invoked"])
            self.assertTrue(runner.logger.closed)

    def test_scheduled_trigger_runs_after_a_successful_sync_today(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
            sync_path = root / "sync.db"
            SyncHistory(sync_path).record(
                "pipeline-1",
                now.isoformat(),
                now.isoformat(),
                1,
                True,
                "pipeline",
                "completed",
            )
            calls = []
            summary = run_triggered_pipeline(
                "scheduled",
                scheduler_history=SchedulerHistory(root / "scheduler.db"),
                pipeline_history_path=sync_path,
                pipeline_factory=lambda: self.FakeRunner(calls),
                now_provider=lambda: now,
            )
            self.assertEqual(calls, [{
                "dry_run": False,
                "trigger_type": "scheduled",
                "if_new_data": True,
                "acquire_lock": True,
            }])
            self.assertTrue(summary["pipeline_invoked"])
            self.assertEqual(summary["status"], "success")

    def test_manual_scheduled_and_catch_up_are_all_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
            for trigger_type in ("manual", "scheduled", "catch_up"):
                calls = []
                summary = run_triggered_pipeline(
                    trigger_type,
                    dry_run=True,
                    scheduler_history=SchedulerHistory(root / f"{trigger_type}.db"),
                    pipeline_history_path=root / "sync.db",
                    pipeline_factory=lambda calls=calls: self.FakeRunner(calls),
                    now_provider=lambda: now,
                )
                self.assertEqual(summary["trigger_type"], trigger_type)
                self.assertEqual(calls[0]["trigger_type"], trigger_type)
                self.assertEqual(
                    calls[0]["if_new_data"],
                    trigger_type in {"scheduled", "catch_up"},
                )


if __name__ == "__main__":
    unittest.main()
