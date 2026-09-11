import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import db
from src.mobile_recovery_history import (
    CONTRACT_KIND,
    MobileRecoveryHistoryError,
    build_mobile_recovery_history,
)


class MobileRecoveryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovery.db"
        self.connection = db.connect(self.path)
        for day, score, rmssd, heart_rate, sleep_score in (
            ("2026-09-05", 68, 31, 62, 78),
            ("2026-09-06", 74, 38, 59, 82),
        ):
            self.connection.execute(
                "INSERT INTO daily_recovery_metrics(date,morning_rmssd,morning_mean_hr,sleep_score) VALUES(?,?,?,?)",
                (day, rmssd, heart_rate, sleep_score),
            )
            self.connection.execute(
                """INSERT INTO recovery_scores(
                       date,recovery_score,activity_load_score,training_load_score,score_version,recommendation
                   ) VALUES(?,?,?,?,?,?)""",
                (day, score, 10, 10, "1.0", "适度训练"),
            )
            self.connection.execute(
                """INSERT INTO polar_sleep_raw(source,external_id,date,raw_json)
                   VALUES('polar',?,?,?)""",
                (f"sleep-{day}", day, '{"sleepEvaluation":{"sleepSpan":"25200s"}}'),
            )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_history_exposes_only_allowlisted_objective_values_in_date_order(self):
        history = build_mobile_recovery_history(
            self.path, days=14, generated_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )
        self.assertEqual(history["kind"], CONTRACT_KIND)
        self.assertEqual(history["generated_at"], "2026-09-07T00:00:00Z")
        self.assertEqual([item["date"] for item in history["days"]], ["2026-09-05", "2026-09-06"])
        self.assertEqual(history["days"][1]["score"], 74)
        self.assertEqual(history["days"][1]["morning_hrv_rmssd_ms"]["value"], 38)
        self.assertEqual(
            set(history["days"][1]["details"]),
            {
                "pns_index", "sns_index", "physiological_age_years", "mean_rr_ms",
                "sdnn_ms", "poincare_sd1_ms", "poincare_sd2_ms", "stress_index",
                "respiration_rate_bpm", "measurement_quality",
            },
        )
        self.assertEqual(history["days"][1]["sleep_duration_minutes"]["value"], 420)
        self.assertEqual(history["days"][1]["sleep_score"]["value"], 82)
        self.assertEqual(
            set(history["days"][1]["sleep_details"]),
            {
                "duration_minutes", "score", "sleep_start_time", "wake_time",
                "actual_duration_minutes", "deep_duration_minutes", "rem_duration_minutes",
                "average_hr_bpm", "nightly_hrv_rmssd_ms", "resting_hr_bpm",
                "respiration_rate_bpm", "regularity_score",
            },
        )
        self.assertNotIn("raw_json", str(history))

    def test_history_rejects_unsafe_ranges(self):
        with self.assertRaises(MobileRecoveryHistoryError):
            build_mobile_recovery_history(self.path, days=0)
        with self.assertRaises(MobileRecoveryHistoryError):
            build_mobile_recovery_history(self.path, days=29)
