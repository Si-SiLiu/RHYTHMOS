import sqlite3
import unittest

from src.db import init_db
from src.input_habits import (
    clear_input_habits,
    get_input_habits,
    get_input_habit_defaults,
    record_input_habit,
    set_input_habits_enabled,
)


class InputHabitTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        init_db(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_learns_repeated_choices_and_numeric_defaults(self):
        for _ in range(2):
            record_input_habit(
                self.connection,
                "daily_log.training",
                fields=("duration_minutes", "session_rpe"),
                choices={"training.session_type": "strength"},
                numeric={"training.duration_minutes": 45, "training.session_rpe": 6},
            )

        defaults = get_input_habit_defaults(self.connection)
        self.assertEqual(defaults["training_type"], "strength")
        self.assertEqual(defaults["training_duration_minutes"], 45)
        self.assertEqual(defaults["training_session_rpe"], 6)
        self.assertEqual(get_input_habits(self.connection)["event_count"], 2)

    def test_disabled_learning_does_not_record_and_clear_preserves_other_data(self):
        set_input_habits_enabled(self.connection, False)
        record_input_habit(self.connection, "daily_log.nutrition", choices={"nutrition.meal_type": "dinner"})
        self.assertEqual(get_input_habits(self.connection)["event_count"], 0)

        set_input_habits_enabled(self.connection, True)
        record_input_habit(self.connection, "daily_log.nutrition", choices={"nutrition.meal_type": "dinner"})
        clear_input_habits(self.connection)
        profile = get_input_habits(self.connection)
        self.assertEqual(profile["event_count"], 0)
        self.assertTrue(profile["enabled"])


if __name__ == "__main__":
    unittest.main()
