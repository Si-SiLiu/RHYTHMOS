import inspect
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from src import neural_fatigue_service


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


class NeuralFatigueServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.connection = sqlite3.connect(f"{self.temp.name}/service.db")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """CREATE TABLE daily_recovery_metrics(date TEXT, sleep_score REAL);
               CREATE TABLE recovery_scores(date TEXT, recovery_score REAL);
               CREATE TABLE baseline_metrics(date TEXT, window_days INTEGER, metric_name TEXT, valid_days INTEGER, percent_change REAL);
               CREATE TABLE cognitive_training_sessions(id INTEGER, started_at TEXT, completed INTEGER);
               CREATE TABLE cognitive_training_task_results(session_id INTEGER, task_type TEXT, median_rt_ms REAL, accuracy REAL);"""
        )

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def insert_daily(self, day="2026-07-30", sleep=80, recovery=70):
        self.connection.execute("INSERT INTO daily_recovery_metrics VALUES (?,?)", (day, sleep))
        self.connection.execute("INSERT INTO recovery_scores VALUES (?,?)", (day, recovery))
        self.connection.execute("INSERT INTO baseline_metrics VALUES (?,?,?,?,?)", (day, 28, "sleep_score", 28, None))
        self.connection.execute("INSERT INTO baseline_metrics VALUES (?,?,?,?,?)", (day, 28, "nightly_hrv_rmssd", 28, None))

    def view(self, **kwargs):
        return neural_fatigue_service.build_neural_fatigue_view(connection=self.connection, now=NOW, **kwargs)

    def test_complete_recovery_and_sleep_data_are_available(self):
        self.insert_daily()
        view = self.view()
        self.assertEqual(view["result"].status, "available")
        self.assertEqual(view["result"].burden_score, 25)
        self.assertEqual(view["target_date"], date(2026, 7, 30))
        self.assertEqual({row["name"] for row in view["component_rows"]}, {"cognitive", "recovery", "sleep", "training", "subjective"})

    def test_insufficient_data_and_only_training_are_not_scored(self):
        self.connection.execute("INSERT INTO daily_recovery_metrics VALUES (?,?)", ("2026-07-30", None))
        self.connection.execute("INSERT INTO baseline_metrics VALUES (?,?,?,?,?)", ("2026-07-30", 28, "training_duration", 20, 40))
        view = self.view()
        self.assertEqual(view["result"].status, "insufficient_data")
        self.assertIsNone(view["result"].burden_score)
        self.assertEqual(view["unavailable_reason"], "minimum_data_condition_not_met")

    def test_cognitive_missing_does_not_block_recovery_sleep(self):
        self.insert_daily()
        view = self.view()
        cognitive = next(row for row in view["component_rows"] if row["name"] == "cognitive")
        self.assertFalse(cognitive["included"])
        self.assertEqual(view["result"].available_components, ("recovery", "sleep"))

    def test_stale_cognitive_is_excluded(self):
        self.insert_daily("2026-07-10")
        self.connection.execute("INSERT INTO cognitive_training_sessions VALUES (1,?,1)", ("2026-07-10T08:00:00+00:00",))
        self.connection.execute("INSERT INTO cognitive_training_task_results VALUES (1,'stroop_control',550,.9)")
        self.connection.execute("INSERT INTO cognitive_training_sessions VALUES (2,?,1)", ("2026-07-09T08:00:00+00:00",))
        self.connection.execute("INSERT INTO cognitive_training_task_results VALUES (2,'stroop_control',500,.95)")
        view = self.view(target_date=date(2026, 7, 10))
        self.assertIn("component_cognitive_stale_excluded", view["result"].reasons)

    def test_baseline_sample_count_source_and_observed_at_are_exposed(self):
        self.insert_daily()
        view = self.view()
        sleep = next(row for row in view["component_rows"] if row["name"] == "sleep")
        self.assertEqual(sleep["source"], "daily_recovery_metrics.sleep_score")
        self.assertEqual(sleep["baseline_sample_count"], 28)
        self.assertEqual(sleep["observed_at"], datetime(2026, 7, 30, tzinfo=timezone.utc))
        self.assertEqual(sleep["freshness_hours"], 12)

    def test_service_is_read_only_network_free_and_deterministic(self):
        self.insert_daily()
        before = self.connection.total_changes
        first, second = self.view(), self.view()
        self.assertEqual(before, self.connection.total_changes)
        self.assertEqual(first, second)
        source = inspect.getsource(neural_fatigue_service.build_neural_fatigue_view)
        for forbidden in ("requests", "urllib", "INSERT", "UPDATE", "DELETE", "streamlit"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
