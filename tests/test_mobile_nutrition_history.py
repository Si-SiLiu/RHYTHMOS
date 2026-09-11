import tempfile
import unittest
from pathlib import Path

from src import db
from src.mobile_nutrition_history import (
    MobileNutritionHistoryError,
    build_mobile_nutrition_history,
)
from src.nutrition_logging import create_meal_record, food_catalog_by_name


class MobileNutritionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rhythmos.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_projects_completed_desktop_meals_in_chronological_history(self):
        catalog = food_catalog_by_name(self.connection)
        create_meal_record(self.connection, {
            "date": "2026-09-07", "meal_type": "breakfast", "eaten_at": "08:00",
        }, [{"food_catalog_id": catalog["egg"]["id"], "quantity": 2, "unit": "piece"}])

        history = build_mobile_nutrition_history(self.path, days=28)

        self.assertEqual((history["kind"], history["version"]), ("rhythmos.mobile_nutrition_history", 1))
        self.assertEqual(len(history["days"]), 1)
        day = history["days"][0]
        self.assertEqual((day["date"], day["recorded_meals"], day["food_count"]), ("2026-09-07", 1, 1))
        self.assertEqual(day["meals"][0]["items"][0]["food_name"], "鸡蛋")
        self.assertEqual(day["energy"]["intake_calories"], 143.0)

    def test_rejects_history_ranges_outside_the_recovery_style_window(self):
        with self.assertRaises(MobileNutritionHistoryError):
            build_mobile_nutrition_history(self.path, days=29)

