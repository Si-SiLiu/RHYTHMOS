import tempfile
import unittest
from pathlib import Path

from src import db
from src.mobile_nutrition_input import (
    MobileNutritionInputError,
    save_mobile_manual_nutrition_entry,
)
from src.nutrition_logging import list_meal_records


class MobileNutritionInputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "recovery.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def test_entry_is_replaced_without_touching_desktop_meals(self):
        first = {
            "date": "2026-09-07", "meal_type": "lunch", "eaten_at": "12:30",
            "food_name": "午餐", "amount": 1, "unit": "serving", "calories_kcal": 620,
            "protein_g": 35, "carbohydrate_g": 70, "fat_g": 18, "fiber_g": 8, "water_ml": 250,
        }
        save_mobile_manual_nutrition_entry(first, db_path=str(self.path))
        second = {**first, "calories_kcal": 650.129}
        save_mobile_manual_nutrition_entry(second, db_path=str(self.path))

        records = list_meal_records(self.connection)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["items"][0]["calories_kcal"], 650.13)
        self.assertEqual(records[0]["items"][0]["protein_g"], 35)

    def test_entry_requires_a_recognisable_nutrient_value(self):
        with self.assertRaises(MobileNutritionInputError):
            save_mobile_manual_nutrition_entry({
                "date": "2026-09-07", "meal_type": "lunch", "eaten_at": "12:30",
                "food_name": "午餐", "amount": 1, "unit": "serving",
            }, db_path=str(self.path))
