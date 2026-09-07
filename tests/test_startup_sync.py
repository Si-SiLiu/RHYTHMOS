import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.pipeline import governance
from src.scheduler.startup import start_catch_up_if_due


class StartupCatchUpTests(unittest.TestCase):
    def test_eligible_startup_queues_canonical_catch_up_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / ".venv" / "bin" / "python"
            runner = root / "scripts" / "run_scheduled_sync.py"
            python.parent.mkdir(parents=True)
            runner.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")
            runner.write_text("", encoding="utf-8")
            received = {}

            def process_factory(arguments, **kwargs):
                received["arguments"] = arguments
                received["kwargs"] = kwargs
                return SimpleNamespace(pid=1234)

            outcome = start_catch_up_if_due(
                config_loader=lambda: SimpleNamespace(config=object()),
                history_factory=lambda: "history",
                state_evaluator=lambda config, scheduler_history: SimpleNamespace(
                    eligible=True, state="eligible"
                ),
                process_factory=process_factory,
                project_root=root,
            )

            self.assertTrue(outcome.dispatched)
            self.assertEqual(outcome.pid, 1234)
            self.assertEqual(
                received["arguments"],
                [
                    str(python.resolve()),
                    str(runner.resolve()),
                    "--trigger-type",
                    "catch_up",
                ],
            )
            self.assertEqual(received["kwargs"]["cwd"], root.resolve())
            self.assertTrue(received["kwargs"]["start_new_session"])

    def test_ineligible_startup_does_not_spawn_a_process(self):
        outcome = start_catch_up_if_due(
            config_loader=lambda: SimpleNamespace(config=object()),
            history_factory=lambda: "history",
            state_evaluator=lambda config, scheduler_history: SimpleNamespace(
                eligible=False, state="already_synced"
            ),
            process_factory=lambda *args, **kwargs: self.fail("must not spawn"),
        )
        self.assertFalse(outcome.dispatched)
        self.assertEqual(outcome.state, "already_synced")


class PipelineGovernanceTests(unittest.TestCase):
    def test_routine_governance_does_not_run_the_full_project_test_suite(self):
        with patch.object(
            governance,
            "sync_runtime_documents",
            return_value="2026-09-02T10:30:00+08:00",
        ) as sync_documents:
            result = governance.run({"results": {}, "resume_aggregates": {}})

        sync_documents.assert_called_once()
        self.assertTrue(result["state_updated"])
        self.assertEqual(result["state_check"], "deferred")
        self.assertNotIn("test_total", result)

    def test_documentation_failure_becomes_a_warning_not_a_pipeline_failure(self):
        with patch.object(
            governance,
            "sync_runtime_documents",
            side_effect=RuntimeError("synthetic failure"),
        ):
            result = governance.run({"results": {}, "resume_aggregates": {}})

        self.assertFalse(result["state_updated"])
        self.assertEqual(result["warning_count"], 1)
        self.assertEqual(result["warnings"], ["GOVERNANCE_DOCUMENTS_NOT_UPDATED"])


if __name__ == "__main__":
    unittest.main()
