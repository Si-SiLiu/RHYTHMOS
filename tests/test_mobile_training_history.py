import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import db
from src.mobile_training_history import (
    CONTRACT_KIND,
    MobileTrainingHistoryError,
    build_mobile_training_history,
)


class MobileTrainingHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "recovery.db"
        self.connection = db.connect(self.path)
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(
                   source,external_id,date,raw_json,sport,duration,calories
               ) VALUES('polar','polar-1','2026-09-05','{"private":"never export"}',
                        'running','PT45M',460)"""
        )
        self.connection.execute(
            """INSERT INTO manual_activity_sessions(
                   date,duration_minutes,calories_kcal,activity_type,activity_name,session_rpe
               ) VALUES('2026-09-06',55,320,'strength_training','Upper body',7)"""
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_history_uses_resolved_local_training_without_private_payloads(self):
        history = build_mobile_training_history(
            self.path, days=14, generated_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(history["kind"], CONTRACT_KIND)
        self.assertEqual(history["generated_at"], "2026-09-07T00:00:00Z")
        self.assertEqual([item["date"] for item in history["days"]], ["2026-09-05", "2026-09-06"])
        self.assertEqual(history["days"][0]["duration_minutes"], 45.0)
        self.assertEqual(history["days"][0]["polar_sports"], ["running"])
        self.assertEqual(history["days"][1]["sessions"], [{
            "source": "manual", "sport": "strength_training", "polar_sport": None, "start_time": None, "duration_minutes": 55.0,
            "calories_kcal": 320.0, "average_hr_bpm": None, "maximum_hr_bpm": None,
            "distance_meters": None, "fat_burn_percentage": None, "session_rpe": 7.0,
        }])
        self.assertNotIn("private", str(history))
        self.assertNotIn("polar-1", str(history))

    def test_history_rejects_unsafe_ranges(self):
        with self.assertRaises(MobileTrainingHistoryError):
            build_mobile_training_history(self.path, days=0)
        with self.assertRaises(MobileTrainingHistoryError):
            build_mobile_training_history(self.path, days=31)
