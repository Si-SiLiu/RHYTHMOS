import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import db
from src.mobile_snapshot import (
    CONTRACT_KIND,
    CONTRACT_VERSION,
    MobileSnapshotContractError,
    build_mobile_daily_snapshot,
    validate_mobile_daily_snapshot,
    write_mobile_daily_snapshot,
)


class MobileDailySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovery.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        if self.connection is not None:
            self.connection.close()
        self.temp.cleanup()

    def test_snapshot_exports_only_mobile_safe_today_projection(self):
        self.connection.execute(
            """INSERT INTO daily_recovery_metrics(
                   date,sleep_duration,sleep_score,nightly_hrv_rmssd,
                   nightly_resting_hr,respiration_rate,morning_rmssd,morning_mean_hr
               ) VALUES('2026-09-07','PT7H30M',82,52,49,14,44,56)"""
        )
        self.connection.execute(
            """INSERT INTO recovery_scores(
                   date,recovery_score,activity_load_score,training_load_score,
                   score_version,recommendation
               ) VALUES('2026-09-07',84,20,16,'1.0.0','正常训练')"""
        )
        self.connection.execute(
            """INSERT INTO recovery_confidence(
                   date,data_completeness_score,baseline_maturity_score,
                   confidence_score,confidence_level,group_scores_json,
                   available_groups_json,missing_groups_json,confidence_version
               ) VALUES('2026-09-07',90,80,86,'high','{}','[]','[\"respiration\"]','1.0.0')"""
        )
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(
                   source,external_id,date,raw_json,sport,duration,calories
               ) VALUES('polar','session-1','2026-09-07','{}','running','PT45M',460)"""
        )
        self.connection.commit()

        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at=datetime(2026, 9, 7, 5, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(snapshot["kind"], CONTRACT_KIND)
        self.assertEqual(snapshot["version"], CONTRACT_VERSION)
        self.assertEqual(snapshot["generated_at"], "2026-09-07T05:30:00Z")
        self.assertEqual(snapshot["date"], "2026-09-07")
        self.assertEqual(snapshot["recovery"]["status"], "ready")
        self.assertEqual(snapshot["recovery"]["recommendation_code"], "normal_training")
        self.assertEqual(snapshot["recovery"]["morning_hrv_rmssd_ms"]["value"], 44)
        self.assertEqual(snapshot["sleep"]["duration_minutes"]["value"], 450)
        self.assertEqual(snapshot["training"], {
            "session_count": 1,
            "duration_minutes": 45.0,
            "calories_kcal": 460,
            "sports": ["running"],
        })
        self.assertNotIn("raw_json", json.dumps(snapshot))
        self.assertNotIn("session-1", json.dumps(snapshot))

    def test_explicit_empty_date_remains_explicitly_unavailable(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertEqual(snapshot["recovery"]["status"], "insufficient_data")
        self.assertIsNone(snapshot["recovery"]["score"])
        self.assertIsNone(snapshot["sleep"]["duration_minutes"]["value"])
        self.assertEqual(snapshot["training"]["session_count"], 0)

    def test_missing_database_has_no_implicit_snapshot(self):
        self.connection.close()
        self.path.unlink()
        self.connection = None

        self.assertIsNone(build_mobile_daily_snapshot(self.path))

    def test_writer_creates_json_only_for_a_factual_or_selected_day(self):
        output = Path(self.temp.name) / "exports" / "today.json"

        exported = write_mobile_daily_snapshot(
            output,
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertTrue(exported)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["date"], "2026-09-07")

    def test_contract_validator_accepts_exported_snapshot(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )

        self.assertIs(validate_mobile_daily_snapshot(snapshot), snapshot)

    def test_contract_validator_rejects_unknown_members(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )
        snapshot["training"]["debug_session_ids"] = []

        with self.assertRaisesRegex(MobileSnapshotContractError, "unexpected keys: debug_session_ids"):
            validate_mobile_daily_snapshot(snapshot)

    def test_contract_validator_rejects_inconsistent_or_unsafe_values(self):
        snapshot = build_mobile_daily_snapshot(
            self.path,
            "2026-09-07",
            generated_at="2026-09-07T00:00:00Z",
        )
        inconsistent = copy.deepcopy(snapshot)
        inconsistent["recovery"]["status"] = "ready"
        with self.assertRaisesRegex(MobileSnapshotContractError, "inconsistent"):
            validate_mobile_daily_snapshot(inconsistent)

        unsafe = copy.deepcopy(snapshot)
        unsafe["sleep"]["score"]["value"] = float("nan")
        with self.assertRaisesRegex(MobileSnapshotContractError, "JSON-safe"):
            validate_mobile_daily_snapshot(unsafe)


if __name__ == "__main__":
    unittest.main()
