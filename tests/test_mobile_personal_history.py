import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src import db
from src.mobile_personal_history import (
    MobilePersonalHistoryError,
    build_mobile_personal_history,
)


class MobilePersonalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "recovery.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def test_exports_one_latest_point_per_date_in_chronological_order(self):
        self.connection.executemany(
            """INSERT INTO body_measurements(date,height_cm,weight_kg,body_fat_percent,waist_cm,is_primary)
               VALUES(?,?,?,?,?,?)""",
            [
                ("2026-09-01", 175, 81.0, 26.0, 90.0, 1),
                ("2026-09-03", 175, 80.8, 25.5, 89.5, 0),
                ("2026-09-03", 175, 80.65, 25.0, 89.0, 1),
            ],
        )
        self.connection.commit()

        history = build_mobile_personal_history(
            self.path, generated_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        )

        self.assertEqual(history["generated_at"], "2026-09-04T00:00:00Z")
        self.assertEqual(history["days"], [
            {"date": "2026-09-01", "weight_kg": 81.0, "body_fat_percent": 26.0, "waist_cm": 90.0},
            {"date": "2026-09-03", "weight_kg": 80.65, "body_fat_percent": 25.0, "waist_cm": 89.0},
        ])

    def test_uses_a_28_day_calendar_baseline_and_rejects_unsafe_ranges(self):
        self.connection.executemany(
            "INSERT INTO body_measurements(date,height_cm,weight_kg,is_primary) VALUES(?,?,?,1)",
            [("2026-07-31", 175, 82), ("2026-08-28", 175, 81)],
        )
        self.connection.commit()
        history = build_mobile_personal_history(self.path)
        self.assertNotIn("2026-07-31", [point["date"] for point in history["days"]])
        with self.assertRaises(MobilePersonalHistoryError):
            build_mobile_personal_history(self.path, days=29)


if __name__ == "__main__":
    unittest.main()
