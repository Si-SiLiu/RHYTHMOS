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

    def test_desktop_style_meal_slot_keeps_multiple_food_rows_together(self):
        save_mobile_manual_nutrition_entry({
            "date": "2026-09-07", "meal_slot": "meal_2", "meal_type": "lunch",
            "eaten_at": "12:30", "items": [
                {"food_name": "鸡胸肉", "amount": 180, "unit": "g", "calories_kcal": 297.5, "protein_g": 55.8},
                {"food_name": "米饭", "amount": 200, "unit": "g", "calories_kcal": 232.0, "carbohydrate_g": 51.6},
            ],
        }, db_path=str(self.path))

        records = list_meal_records(self.connection)
        self.assertEqual(len(records), 1)
        self.assertEqual((records[0]["meal_slot"], records[0]["meal_type"]), ("meal_2", "lunch"))
        self.assertEqual([item["custom_food_name"] for item in records[0]["items"]], ["鸡胸肉", "米饭"])
        self.assertEqual(records[0]["items"][0]["protein_g"], 55.8)
        self.assertEqual(records[0]["items"][1]["calories_kcal"], 232.0)
