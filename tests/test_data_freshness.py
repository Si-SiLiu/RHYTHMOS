import json
import tempfile
import unittest
from unittest import mock
from datetime import date
from pathlib import Path

from src import db
from src.data_freshness import collect_freshness, latest_raw_date


class DataFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.db_path = root / "recovery.db"
        self.raw_dir = root / "raw"
        self.raw_dir.mkdir()
        self.connection = db.connect(self.db_path)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def write_source(self, day="2026-07-12"):
        (self.raw_dir / "polar_daily_activity.json").write_text(
            json.dumps([{"date": day}]), encoding="utf-8"
        )

    def insert_raw(self, day="2026-07-12"):
        self.connection.execute(
            "INSERT INTO polar_daily_activity_raw (source,external_id,date,raw_json) VALUES ('polar',?,?, '{}')",
            (day, day),
        )
        self.connection.commit()

    def insert_metrics(self, day="2026-07-12"):
        self.connection.execute(
            "INSERT INTO daily_recovery_metrics (date,training_count,training_calories) VALUES (?,0,0)", (day,)
        )
        self.connection.commit()

    def insert_downstream(self, day="2026-07-12"):
        self.connection.execute(
            "INSERT INTO recovery_scores (date,recovery_score,activity_load_score,training_load_score,score_version,recommendation) VALUES (?,80,1,1,'v1.0','ok')", (day,)
        )
        self.connection.execute(
            """INSERT INTO recovery_confidence
            (date,data_completeness_score,baseline_maturity_score,confidence_score,confidence_level,
             group_scores_json,available_groups_json,missing_groups_json,confidence_version)
             VALUES (?,90,90,90,'high','{}','[]','[]','1.0.0')""", (day,)
        )
        values = (day,) + tuple("{}" for _ in range(7)) + ("[]", "[]", "1.0.0", "1.0.0", 1)
        self.connection.execute("""INSERT INTO local_coach_recommendations
            (date,morning_training_json,evening_training_json,sleep_advice_json,hydration_advice_json,
             nutrition_advice_json,recovery_advice_json,rationale_json,data_limitations_json,safety_notices_json,
             engine_version,rule_config_version,generated_without_cloud_ai) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
        self.connection.commit()

    def collect(self, day="2026-07-12"):
        return collect_freshness(self.db_path, self.raw_dir, today=date.fromisoformat(day))

    def test_fully_aligned_pipeline_has_no_blocker(self):
        self.write_source(); self.insert_raw(); self.insert_metrics(); self.insert_downstream()
        result = self.collect()
        self.assertTrue(result["database_aligned_with_source"])
        self.assertIsNone(result["prospective_collection_blocker"])

    def test_source_missing_today_is_distinct_from_import_failure(self):
        self.write_source("2026-07-08")
        result = self.collect("2026-07-12")
        self.assertEqual(result["source_data_lag_days"], 4)
        self.assertEqual(result["prospective_collection_blocker"], "source_data_not_available_for_today")

    def test_raw_import_lag_is_detected(self):
        self.write_source()
        self.assertEqual(self.collect()["prospective_collection_blocker"], "raw_import_lag")

    def test_daily_metrics_lag_is_detected(self):
        self.write_source(); self.insert_raw()
        self.assertEqual(self.collect()["prospective_collection_blocker"], "daily_metrics_lag")

    def test_recovery_lag_is_detected(self):
        self.write_source(); self.insert_raw(); self.insert_metrics()
        self.assertEqual(self.collect()["prospective_collection_blocker"], "recovery_lag")

    def test_missing_or_malformed_raw_is_safe(self):
        path = self.raw_dir / "polar_daily_activity.json"
        path.write_text("not-json", encoding="utf-8")
        self.assertIsNone(latest_raw_date(path))
        self.assertEqual(self.collect()["prospective_collection_blocker"], "source_data_unavailable")

    def test_unchanged_raw_file_is_parsed_once_per_revision(self):
        path = self.raw_dir / "cached.json"
        path.write_text('{"rows":[{"date":"2026-08-26"}]}', encoding="utf-8")
        with mock.patch("src.data_freshness.json.loads", wraps=json.loads) as loads:
            self.assertEqual(latest_raw_date(path), "2026-08-26")
            self.assertEqual(latest_raw_date(path), "2026-08-26")
        self.assertEqual(loads.call_count, 1)

    def test_output_declares_no_health_values(self):
        self.write_source("2026-07-08")
        result = self.collect()
        self.assertFalse(result["contains_health_values"])
        serialized = json.dumps(result).lower()
        for forbidden in ("raw_json", "access_token", "refresh_token", "current_value"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
