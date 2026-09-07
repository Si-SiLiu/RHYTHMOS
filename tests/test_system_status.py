import json
import tempfile
import unittest
from unittest import mock
from datetime import date
from pathlib import Path

from src import system_status


class SystemStatusTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.state_path = self.root / "project_state.json"
        self.versions_path = self.root / "versions.json"
        self.versions = {
            "app_version": "0.10.0",
            "recovery_engine_version": "1.0.0",
            "baseline_engine_version": "1.0.0",
            "confidence_engine_version": "1.0.0",
            "database_schema_version": "0.1.0",
            "dashboard_version": "0.2.0",
            "model_version": "unreleased",
        }
        self.state = {
            **self.versions,
            "test_total": 10,
            "test_passed": 10,
            "test_failed": 0,
            "test_success": True,
            "latest_data_date": "2026-07-08",
            "updated_at": "2026-07-10T12:00:00+08:00",
            "current_phase": "Release Readiness",
            "next_goal": "One-Click Sync Pipeline",
            "prioritized_issues": [],
        }
        self.write_files()

    def tearDown(self):
        self.directory.cleanup()

    def write_files(self):
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")
        self.versions_path.write_text(json.dumps(self.versions), encoding="utf-8")

    def load(self):
        return system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: True,
            sync_reader=lambda _: None,
            today=date(2026, 7, 10),
        )

    def test_normal_status_is_healthy(self):
        status = self.load()
        self.assertEqual(status["system_health"], "Healthy")
        self.assertEqual(status["test_status"], "PASS")
        self.assertEqual(status["test_passed"], 10)

    def test_missing_state_is_friendly_and_unhealthy(self):
        self.state_path.unlink()
        status = self.load()
        self.assertEqual(status["system_health"], "Unhealthy")
        self.assertIsNotNone(status["state_error"])
        self.assertEqual(status["app_version"], self.versions["app_version"])

    def test_failed_tests_are_unhealthy(self):
        self.state.update(test_passed=9, test_failed=1, test_success=False)
        self.write_files()
        status = self.load()
        self.assertEqual(status["system_health"], "Unhealthy")
        self.assertEqual(status["test_status"], "FAIL")

    def test_missing_latest_date_is_warning(self):
        self.state["latest_data_date"] = None
        self.write_files()
        status = self.load()
        self.assertEqual(status["system_health"], "Warning")

    def test_active_p1_issue_is_warning(self):
        self.state["prioritized_issues"] = [
            {"priority": "P1", "status": "planned", "description": "Migration ledger"}
        ]
        self.write_files()
        status = self.load()
        self.assertEqual(status["system_health"], "Warning")
        self.assertEqual(status["active_p1_count"], 1)

    def test_blocked_external_p1_issue_does_not_degrade_local_health(self):
        self.state["prioritized_issues"] = [
            {"priority": "P1", "status": "blocked", "description": "Future provider review"}
        ]
        self.write_files()
        status = self.load()
        self.assertEqual(status["system_health"], "Healthy")
        self.assertEqual(status["active_p1_count"], 0)

    def test_unreadable_database_is_unhealthy(self):
        status = system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: False,
            today=date(2026, 7, 10),
        )
        self.assertEqual(status["system_health"], "Unhealthy")

    def test_last_sync_summary_is_exposed(self):
        status = system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: True,
            sync_reader=lambda _: {
                "finish_time": "2026-07-10T18:30:00+08:00",
                "duration": 12.5,
                "success": 1,
                "records_imported": 7,
                "warning_count": 2,
            },
            today=date(2026, 7, 10),
        )
        self.assertEqual(status["last_sync"], "2026-07-10T18:30:00+08:00")
        self.assertEqual(status["last_sync_duration"], 12.5)
        self.assertTrue(status["last_sync_success"])
        self.assertEqual(status["last_sync_records_imported"], 7)
        self.assertEqual(status["last_sync_warning_count"], 2)
        self.assertEqual(status["system_health"], "Warning")

    def test_failed_sync_warnings_do_not_degrade_system_health(self):
        status = system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: True,
            sync_reader=lambda _: {
                "finish_time": "2026-07-10T18:30:00+08:00",
                "success": 0,
                "warning_count": 2,
            },
            today=date(2026, 7, 10),
        )
        self.assertEqual(status["system_health"], "Healthy")
        self.assertEqual(status["last_sync_warning_count"], 2)

    def test_auxiliary_sync_warnings_do_not_degrade_core_data_health(self):
        status = system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: True,
            sync_reader=lambda _: {
                "finish_time": "2026-07-10T18:30:00+08:00",
                "success": 1,
                "warning_count": 2,
                "source_warning_count": 0,
            },
            today=date(2026, 7, 10),
        )
        self.assertEqual(status["system_health"], "Healthy")
        self.assertEqual(status["last_sync_source_warning_count"], 0)
        self.assertEqual(status["last_sync_auxiliary_warning_count"], 2)

    def test_optional_polar_source_warnings_remain_visible_to_health(self):
        status = system_status.load_system_status(
            self.state_path,
            self.versions_path,
            database_check=lambda _: True,
            sync_reader=lambda _: {
                "finish_time": "2026-07-10T18:30:00+08:00",
                "success": 1,
                "warning_count": 2,
                "source_warning_count": 1,
            },
            today=date(2026, 7, 10),
        )
        self.assertEqual(status["system_health"], "Warning")
        self.assertEqual(status["last_sync_auxiliary_warning_count"], 1)

    def test_canonical_status_uses_live_data_freshness_over_stale_snapshot(self):
        with mock.patch.object(system_status, "STATE_PATH", self.state_path), \
             mock.patch.object(system_status, "get_data_freshness", return_value={
                 "latest_daily_metrics_date": "2026-07-10",
             }):
            status = system_status.load_system_status(
                self.state_path,
                self.versions_path,
                database_check=lambda _: True,
                sync_reader=lambda _: None,
                today=date(2026, 7, 10),
            )
        self.assertEqual(status["latest_data_date"], "2026-07-10")
        self.assertEqual(status["data_age_days"], 0)
        self.assertEqual(status["system_health"], "Healthy")


if __name__ == "__main__":
    unittest.main()
