import sqlite3
import unittest
from datetime import date
from pathlib import Path

from src import db
from src.personal_profile import (
    PersonalProfileValidationError,
    calculate_age,
    get_personal_goals,
    get_personal_profile,
    latest_body_measurement,
    save_personal_goals,
    save_personal_profile,
)


class PersonalProfileTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        db.init_db(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_age_is_calculated_against_birthday(self):
        self.assertEqual(calculate_age("1990-07-17", date(2026, 7, 17)), 36)
        self.assertEqual(calculate_age("1990-07-18", date(2026, 7, 17)), 35)
        with self.assertRaises(PersonalProfileValidationError):
            calculate_age("2027-01-01", date(2026, 7, 17))

    def test_profile_is_singleton_and_updates_locally(self):
        save_personal_profile(self.connection, {
            "name": "Test User", "gender": "prefer_not_to_say",
            "birth_date": "1990-01-01", "height_cm": 170,
        })
        save_personal_profile(self.connection, {
            "name": "Updated User", "gender": "female",
            "birth_date": "1991-02-03", "height_cm": 171.5,
        })
        profile = get_personal_profile(self.connection)
        self.assertEqual(profile["name"], "Updated User")
        self.assertEqual(profile["height_cm"], 171.5)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM personal_profile").fetchone()[0], 1,
        )

    def test_goals_are_optional_validated_and_upserted(self):
        save_personal_goals(self.connection, {
            "training_goal": "fat_loss", "target_weight_kg": 65, "target_body_fat_percent": 18,
            "target_waist_cm": 75,
        })
        self.assertEqual(get_personal_goals(self.connection)["target_weight_kg"], 65)
        self.assertEqual(get_personal_goals(self.connection)["training_goal"], "fat_loss")
        with self.assertRaises(PersonalProfileValidationError):
            save_personal_goals(self.connection, {"training_goal": "maintenance", "target_body_fat_percent": 101})
        with self.assertRaises(PersonalProfileValidationError):
            save_personal_goals(self.connection, {"training_goal": "invalid"})

    def test_latest_body_measurement_prefers_latest_date(self):
        self.connection.execute(
            "INSERT INTO body_measurements(date,height_cm,weight_kg,is_primary) VALUES('2026-07-16',170,60,1)"
        )
        self.connection.execute(
            "INSERT INTO body_measurements(date,height_cm,weight_kg,is_primary) VALUES('2026-07-17',170,61,1)"
        )
        self.connection.commit()
        self.assertEqual(latest_body_measurement(self.connection)["weight_kg"], 61)

    def test_personal_summary_metrics_are_left_aligned(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "src" / "pages" / "5_Personal.py").read_text(encoding="utf-8")
        self.assertIn("justify-content: flex-start !important", source)
        self.assertIn("text-align: left !important", source)
        self.assertIn('div[data-baseweb="select"] div[value]', source)


if __name__ == "__main__":
    unittest.main()
