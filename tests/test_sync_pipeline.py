import tempfile
import unittest
import subprocess
import sys
import sqlite3
from contextlib import nullcontext
from pathlib import Path

from src.pipeline.history import SyncHistory
from src.pipeline import STEP_NAMES
from src.pipeline.logger import PipelineLogger
from src.pipeline.governance import sync_runtime_documents
from src.pipeline.importer import run as run_import_step
from src.pipeline.errors import PipelineStepError
from src.sync_pipeline import PipelineError, PipelineRunner


class SyncPipelineTests(unittest.TestCase):
    def make_runner(self, steps):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        runner = PipelineRunner(
            steps=steps,
            history=SyncHistory(root / "history.db"),
            logger=PipelineLogger(root / "sync.log"),
            lock_factory=lambda trigger_type: nullcontext(),
        )
        return directory, runner

    def test_pipeline_runs_steps_in_order_and_records_summary(self):
        calls = []
        names = STEP_NAMES

        def make_step(name):
            def step(context, dry_run=False):
                calls.append(name)
                values = {
                    "import": {"records_imported": 3},
                    "metrics": {"metrics_updated": 4},
                    "baseline": {"baseline_updated": 5},
                    "recovery": {"recovery_updated": 6},
                    "local-coach": {"local_coach_records_updated": 7},
                    "report": {"reports_generated": 1},
                    "governance": {"state_updated": True},
                }
                return values.get(name, {})

            return step

        directory, runner = self.make_runner({name: make_step(name) for name in names})
        try:
            summary = runner.run()
            self.assertEqual(calls, list(names))
            self.assertTrue(summary["success"])
            self.assertEqual(summary["records_imported"], 3)
            self.assertEqual(summary["baseline_updated"], 5)
            self.assertEqual(summary["recovery_updated"], 6)
            self.assertEqual(summary["reports_generated"], 1)
            self.assertEqual(summary["metrics_updated"], 4)
            self.assertEqual(summary["local_coach_records_updated"], 7)
            self.assertTrue(summary["state_updated"])
            self.assertTrue(summary["dashboard_ready"])
            self.assertEqual(runner.history.last_sync()["success"], 1)
        finally:
            runner.logger.close()
            directory.cleanup()

    def test_selective_sync_runs_only_requested_step(self):
        calls = []
        steps = {
            name: (lambda context, dry_run=False, name=name: calls.append(name) or {})
            for name in STEP_NAMES
        }
        directory, runner = self.make_runner(steps)
        try:
            summary = runner.run(only="report")
            self.assertEqual(calls, ["report"])
            self.assertEqual(summary["only"], "report")
        finally:
            runner.logger.close()
            directory.cleanup()

    def test_selective_sync_rejects_unknown_step(self):
        directory, runner = self.make_runner({"token": lambda context, dry_run=False: {}})
        try:
            with self.assertRaises(ValueError):
                runner.run(only="unknown")
        finally:
            runner.logger.close()
            directory.cleanup()

    def test_trigger_type_is_recorded_in_canonical_history(self):
        directory, runner = self.make_runner({
            "token": lambda context, dry_run=False: {}
        })
        try:
            summary = runner.run(only="token", trigger_type="scheduled")
            self.assertEqual(summary["trigger_type"], "scheduled")
            self.assertEqual(runner.history.last_sync()["trigger_type"], "scheduled")
            self.assertEqual(
                runner.history.last_sync_by_trigger("scheduled")["success"], 1
            )
            with self.assertRaises(ValueError):
                runner.run(only="token", trigger_type="invalid")
        finally:
            runner.logger.close()
            directory.cleanup()

    def test_if_new_data_short_circuits_downstream_when_snapshot_unchanged(self):
        names = STEP_NAMES
        calls = []
        def make_step(name):
            def step(context, dry_run=False):
                calls.append(name)
                if name == "fetch":
                    return {"source_changed": False}
                if name == "import":
                    return {"records_imported": 0, "kubios_files": 0}
                return {"state_updated": True} if name == "governance" else {}
            return step
        directory, runner = self.make_runner({name: make_step(name) for name in names})
        try:
            result = runner.run(if_new_data=True)
            self.assertEqual(
                calls,
                [
                    "token", "fetch", "import", "manual-summary", "resolution",
                    "ai-feedback", "report", "governance",
                ],
            )
            self.assertTrue(result["no_new_data_short_circuit"])
            self.assertTrue(result["steps"]["recovery"]["no_new_data_skip"])
            self.assertEqual(runner.history.last_sync()["message"], "completed_no_new_data")
        finally:
            runner.logger.close(); directory.cleanup()

    def test_if_new_data_never_skips_when_source_changed(self):
        names = STEP_NAMES
        calls = []
        def make_step(name):
            def step(context, dry_run=False):
                calls.append(name)
                return {"source_changed": True} if name == "fetch" else {}
            return step
        directory, runner = self.make_runner({name: make_step(name) for name in names})
        try:
            result = runner.run(if_new_data=True)
            self.assertEqual(calls, list(names))
            self.assertFalse(result["no_new_data_short_circuit"])
        finally:
            runner.logger.close(); directory.cleanup()

    def test_if_new_data_rejects_selective_or_resume_mode(self):
        directory, runner = self.make_runner({"token": lambda context, dry_run=False: {}})
        try:
            with self.assertRaises(ValueError):
                runner.run(only="token", if_new_data=True)
            with self.assertRaises(ValueError):
                runner.run(resume=True, if_new_data=True)
        finally:
            runner.logger.close(); directory.cleanup()

    def test_governance_syncs_only_marked_document_regions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changelog = root / "CHANGELOG.md"
            handoff = root / "HANDOFF.md"
            source = "manual before\n<!-- PIPELINE_SYNC_START -->\nold\n<!-- PIPELINE_SYNC_END -->\nmanual after\n"
            changelog.write_text(source, encoding="utf-8")
            handoff.write_text(source, encoding="utf-8")
            context = {
                "results": {
                    "import": {"records_imported": 2},
                    "metrics": {"metrics_updated": 3},
                    "baseline": {"baseline_updated": 4},
                    "recovery": {"recovery_updated": 5},
                    "report": {"reports_generated": 1},
                },
                "resume_aggregates": {},
            }
            sync_runtime_documents(context, changelog, handoff)
            for path in (changelog, handoff):
                document = path.read_text(encoding="utf-8")
                self.assertIn("manual before", document)
                self.assertIn("manual after", document)
                self.assertIn("Records Imported: 2", document)
                self.assertNotIn("\nold\n", document)

            resume_context = {
                "results": {"baseline": {"resumed_skip": True}},
                "resume_aggregates": {
                    "records_imported": 2,
                    "metrics_updated": 3,
                    "baseline_updated": 4,
                    "recovery_updated": 5,
                    "reports_generated": 1,
                },
            }
            sync_runtime_documents(resume_context, changelog, handoff)
            self.assertIn("Baselines Updated: 4", handoff.read_text(encoding="utf-8"))

    def test_import_step_dry_run_detects_optional_kubios_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            imports_dir = Path(directory) / "imports"
            result = run_import_step({}, dry_run=True, imports_dir=imports_dir)
            self.assertEqual(result["kubios_files"], 0)

            imports_dir.mkdir()
            (imports_dir / "morning.csv").write_text("date\n", encoding="utf-8")
            result = run_import_step({}, dry_run=True, imports_dir=imports_dir)
            self.assertEqual(result["kubios_files"], 1)

    def test_script_mode_can_import_governance_generator(self):
        root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; "
            f"root={str(root)!r}; "
            "sys.path=[root + '/src'] + [p for p in sys.path if p not in ('', root)]; "
            "from pipeline.governance import update_project_state; "
            "assert callable(update_project_state)"
        )
        process = subprocess.run(
            [sys.executable, "-c", script],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_safe_step_error_is_exposed_without_raw_exception(self):
        steps = {
            name: (lambda context, dry_run=False: {})
            for name in STEP_NAMES
        }
        steps["fetch"] = lambda context, dry_run=False: (_ for _ in ()).throw(
            PipelineStepError("FETCH_SAFE_FAILURE", "Required endpoint unavailable.")
        )
        directory, runner = self.make_runner(steps)
        try:
            with self.assertRaises(PipelineError) as raised:
                runner.run()
            self.assertEqual(raised.exception.error_code, "FETCH_SAFE_FAILURE")
            self.assertEqual(
                raised.exception.summary["error_message"],
                "Required endpoint unavailable.",
            )
        finally:
            runner.logger.close()
            directory.cleanup()

    def test_final_history_failure_becomes_controlled_pipeline_error(self):
        class FailingFinalHistory(SyncHistory):
            def record(self, *args, **kwargs):
                if args[5] == "pipeline":
                    raise sqlite3.OperationalError("synthetic final write failure")
                return super().record(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steps = {
                name: (lambda context, dry_run=False: {})
                for name in STEP_NAMES
            }
            logger = PipelineLogger(root / "sync.log")
            runner = PipelineRunner(
                steps=steps,
                history=FailingFinalHistory(root / "history.db"),
                logger=logger,
                lock_factory=lambda trigger_type: nullcontext(),
            )
            with self.assertRaises(PipelineError) as raised:
                runner.run()
            logger.close()
            self.assertEqual(
                raised.exception.error_code,
                "PIPELINE_FINALIZATION_FAILED",
            )
            self.assertEqual(
                raised.exception.summary["failed_step"],
                "finalization",
            )


if __name__ == "__main__":
    unittest.main()
