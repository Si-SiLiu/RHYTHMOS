import tempfile
import unittest
from pathlib import Path

from src.db import connect
from src.nutrition_logging import (
    create_meal_record,
    find_meal_id_for_slot,
    get_meal_record,
    meal_type_for_slot,
)


class MealSlotTests(unittest.TestCase):
    def test_numbered_meals_are_classified_from_their_time(self):
        self.assertEqual(meal_type_for_slot("meal_1", "08:59"), "breakfast")
        self.assertEqual(meal_type_for_slot("meal_2", "12:00"), "lunch")
        self.assertEqual(meal_type_for_slot("meal_3", "13:59"), "lunch")
        self.assertEqual(meal_type_for_slot("meal_1", "17:00"), "dinner")
        self.assertEqual(meal_type_for_slot("meal_3", "19:59"), "dinner")
        self.assertEqual(meal_type_for_slot("meal_100", "12:30"), "lunch")

    def test_numbered_slot_is_saved_independently_of_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory) / "meal_slots.db") as connection:
                record_id = create_meal_record(connection, {
                    "date": "2026-09-04", "meal_type": "breakfast",
                    "meal_slot": "meal_1", "eaten_at": "08:00",
                    "actual_meal_time": "08:00", "planned_meal_time": "08:00",
                }, [])
                record = get_meal_record(connection, record_id)
                self.assertEqual(record["meal_slot"], "meal_1")
                self.assertEqual(record["meal_type"], "breakfast")
                self.assertEqual(
                    find_meal_id_for_slot(connection, "meal_1", "2026-09-04"), record_id,
                )

                extra_id = create_meal_record(connection, {
                    "date": "2026-09-04", "meal_type": "free_snack",
                    "meal_slot": "meal_100", "eaten_at": "10:00",
                    "actual_meal_time": "10:00", "planned_meal_time": "10:00",
                }, [])
                self.assertEqual(
                    find_meal_id_for_slot(connection, "meal_100", "2026-09-04"), extra_id,
                )


if __name__ == "__main__":
    unittest.main()
