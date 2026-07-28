import unittest

from src.dashboard import (
    _add_development_action,
    _clone_development_action_rows,
    _development_action_rows,
    _is_strength_training_session,
    _historical_action_summary,
    _historical_action_rows,
    _polar_training_data_row,
    _recommended_action_name,
    _remove_development_action,
    _today_action_summary,
)


class DevelopmentActionControlsTests(unittest.TestCase):
    def test_add_and_remove_affect_only_the_current_development_type(self):
        rows_by_development = {}
        upper_pull_rows = _development_action_rows(rows_by_development, "上肢拉力")
        lower_push_rows = _development_action_rows(rows_by_development, "下肢推力")

        _add_development_action(upper_pull_rows, {"id": "upper-1"})
        _add_development_action(upper_pull_rows, {"id": "upper-2"})
        _add_development_action(lower_push_rows, {"id": "lower-1"})

        self.assertTrue(_remove_development_action(upper_pull_rows))
        self.assertEqual(upper_pull_rows, [{"id": "upper-1"}])
        self.assertEqual(lower_push_rows, [{"id": "lower-1"}])

        self.assertTrue(_remove_development_action(upper_pull_rows))
        self.assertFalse(_remove_development_action(upper_pull_rows))
        self.assertEqual(upper_pull_rows, [])
        self.assertEqual(lower_push_rows, [{"id": "lower-1"}])

    def test_remove_on_an_empty_current_type_is_a_no_op(self):
        rows_by_development = {}
        recovery_rows = _development_action_rows(rows_by_development, "主动恢复")

        self.assertFalse(_remove_development_action(recovery_rows))
        self.assertEqual(recovery_rows, [])

    def test_recommended_action_names_follow_the_existing_order(self):
        names = ["动作一", "动作二", "动作三"]

        self.assertEqual(_recommended_action_name([], names), "动作一")
        self.assertEqual(
            _recommended_action_name([{"name": "动作一"}], names), "动作二"
        )
        self.assertEqual(
            _recommended_action_name([{"name": "动作三"}], names), "动作一"
        )

    def test_clone_preserves_all_development_types_but_uses_fresh_row_ids(self):
        source = {
            "上肢拉力": [{"id": "upper-1", "name": "正手引体向上", "sets": 3, "reps": 8, "load": 5.0}],
            "下肢推力": [{"id": "lower-1", "name": "杠铃前蹲", "sets": 4, "reps": 6, "load": 40.0}],
        }

        copied = _clone_development_action_rows(source)

        self.assertEqual(
            {key: [{field: row[field] for field in ("name", "sets", "reps", "load")} for row in rows] for key, rows in copied.items()},
            {key: [{field: row[field] for field in ("name", "sets", "reps", "load")} for row in rows] for key, rows in source.items()},
        )
        self.assertNotEqual(copied["上肢拉力"][0]["id"], source["上肢拉力"][0]["id"])
        self.assertNotEqual(copied["下肢推力"][0]["id"], source["下肢推力"][0]["id"])
        self.assertEqual(source["上肢拉力"][0]["id"], "upper-1")

    def test_today_summary_uses_sets_times_reps_and_load(self):
        summary = _today_action_summary({
            "上肢拉力": [{"sets": 3, "reps": 8, "load": 5.0}],
            "下肢推力": [{"sets": 2, "reps": 10, "load": 20.0}],
        })

        self.assertEqual(summary["exercise_count"], 2)
        self.assertEqual(summary["total_sets"], 5)
        self.assertEqual(summary["total_reps"], 44)
        self.assertEqual(summary["volume_load"], 520.0)
        self.assertEqual(summary["development_types"], "上肢拉力、下肢推力")

    def test_only_strength_polar_sessions_enable_action_details(self):
        self.assertTrue(_is_strength_training_session({"polar_sport_type": "15"}))
        self.assertTrue(_is_strength_training_session({"polar_sport_display": "力量训练"}))
        self.assertFalse(_is_strength_training_session({"polar_sport_display": "表演舞"}))

    def test_history_uses_the_same_polar_data_shape(self):
        row = _polar_training_data_row([{
            "date": "2026-07-27", "start_time": "08:30:00",
            "duration_seconds": 3600, "average_hr": 120, "max_hr": 160,
            "calories": 500, "distance_meters": 1000,
        }])

        self.assertEqual(row["训练次数"], 1)
        self.assertEqual(row["开始时间"], "08:30:00")
        self.assertEqual(row["训练时长"], "01:00:00")
        self.assertEqual(row["训练热量（卡路里）"], 500)
        self.assertEqual(row["距离（米）"], 1000)

    def test_history_action_summary_matches_daily_summary_fields(self):
        summary = _historical_action_summary({
            "exercises": [{
                "custom_exercise_name": "自定义动作",
                "sets": [
                    {"reps": 8, "load_value": 20},
                    {"reps": 6, "load_value": 20},
                ],
            }],
        })

        self.assertEqual(summary["exercise_count"], 1)
        self.assertEqual(summary["total_sets"], 2)
        self.assertEqual(summary["total_reps"], 14)
        self.assertEqual(summary["volume_load"], 280)

    def test_history_action_rows_use_the_daily_compact_fields(self):
        rows = _historical_action_rows({
            "exercises": [{
                "development_strength_type": "上肢拉力",
                "custom_exercise_name": "自定义动作",
                "sets": [
                    {"reps": 8, "load_value": 20},
                    {"reps": 6, "load_value": 25},
                ],
            }],
        }, {})

        self.assertEqual(rows["上肢拉力"], [{
            "name": "自定义动作", "sets": 2, "reps": 14, "load": 25.0,
        }])


if __name__ == "__main__":
    unittest.main()
