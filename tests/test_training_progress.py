import unittest

from src.training_progress import (
    filter_strength_progress_records,
    strength_progress_records,
)


class StrengthProgressTests(unittest.TestCase):
    def test_records_keep_actions_separate_and_merge_same_day_work(self):
        sessions = [
            {
                "date": "2026-09-01",
                "status": "completed",
                "exercises": [{
                    "custom_exercise_name": "杠铃卧推",
                    "sets": [
                        {"set_type": "warmup", "load_value": 40, "load_unit": "kg", "reps": 10, "completed": True},
                        {"set_type": "working", "load_value": 80, "load_unit": "kg", "reps": 5, "completed": True},
                        {"set_type": "working", "load_value": 82.5, "load_unit": "kg", "reps": 3, "completed": True},
                    ],
                }],
            },
            {
                "date": "2026-09-01",
                "status": "completed",
                "exercises": [{
                    "custom_exercise_name": "杠铃卧推",
                    "sets": [{"set_type": "working", "load_value": 100, "load_unit": "lb", "reps": 5, "completed": True}],
                }, {
                    "custom_exercise_name": "杠铃划船",
                    "sets": [{"set_type": "working", "load_value": 60, "load_unit": "kg", "reps": 8, "completed": True}],
                }],
            },
        ]

        records = strength_progress_records(sessions)

        bench = next(record for record in records if record["exercise"] == "杠铃卧推")
        row = next(record for record in records if record["exercise"] == "杠铃划船")
        self.assertEqual(bench["working_set_count"], 3)
        self.assertEqual(bench["max_load_kg"], 82.5)
        self.assertAlmostEqual(bench["volume_kg"], 874.3, places=2)
        self.assertAlmostEqual(bench["estimated_1rm_kg"], 93.33, places=2)
        self.assertEqual(row["volume_kg"], 480)

    def test_records_exclude_incomplete_bodyweight_and_high_rep_1rm_estimates(self):
        records = strength_progress_records([{
            "date": "2026-09-02",
            "status": "completed",
            "exercises": [{
                "custom_exercise_name": "深蹲",
                "sets": [
                    {"set_type": "working", "load_value": 100, "load_unit": "kg", "reps": 15, "completed": True},
                    {"set_type": "working", "load_value": 110, "load_unit": "kg", "reps": 3, "completed": False},
                    {"set_type": "working", "load_value": 20, "load_unit": "bodyweight", "reps": 10, "completed": True},
                ],
            }],
        }])

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["max_load_kg"], 100)
        self.assertEqual(records[0]["volume_kg"], 1500)
        self.assertIsNone(records[0]["estimated_1rm_kg"])

    def test_filter_returns_only_one_action_inside_the_chosen_window(self):
        records = [
            {"exercise": "杠铃卧推", "date": "2026-08-01"},
            {"exercise": "杠铃卧推", "date": "2026-09-01"},
            {"exercise": "杠铃划船", "date": "2026-09-01"},
        ]

        self.assertEqual(
            filter_strength_progress_records(
                records, "杠铃卧推", start_date="2026-08-15"
            ),
            [{"exercise": "杠铃卧推", "date": "2026-09-01"}],
        )

    def test_actions_without_a_comparable_completed_loaded_set_are_excluded(self):
        records = strength_progress_records([{
            "date": "2026-09-03",
            "status": "completed",
            "exercises": [{
                "custom_exercise_name": "自重深蹲",
                "sets": [{
                    "set_type": "working",
                    "load_unit": "bodyweight",
                    "reps": 10,
                    "completed": True,
                }],
            }],
        }])

        self.assertEqual(records, [])
