import sqlite3
import unittest

from src import db
from src.training_plan_actual import (
    create_training_cycle,
    current_cycle_week_segment,
    cycle_end_date_for_weeks,
    copy_previous_week_training_content,
    cycle_week_segments,
    delete_training_cycle,
    get_current_training_cycle,
    get_training_cycle_for_date,
    list_training_cycles,
    list_planned_sessions,
    update_training_cycle,
    create_planned_exercise,
    create_planned_session,
    recent_outdoor_action_defaults,
    recent_planned_action_defaults,
)


class TrainingPlanActualInputLearningTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        db.init_db(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_recent_saved_action_becomes_the_input_default_for_its_module(self):
        first = create_planned_session(
            self.connection, "2026-08-03", "first", "upper_pull"
        )
        create_planned_exercise(
            self.connection, first, canonical_name="单手哑铃划船", display_name="单手哑铃划船",
            target_sets=3, target_reps=8, target_weight=20, module_key="accessory_strength",
        )
        latest = create_planned_session(
            self.connection, "2026-08-04", "latest", "upper_pull"
        )
        create_planned_exercise(
            self.connection, latest, canonical_name="单手哑铃划船", display_name="单手哑铃划船",
            target_sets=4, target_reps=6, target_weight=25, module_key="accessory_strength",
        )
        create_planned_exercise(
            self.connection, latest, canonical_name="杠铃后蹲", display_name="杠铃后蹲",
            target_sets=5, target_reps=5, target_weight=80, module_key="main_strength",
        )

        defaults = recent_planned_action_defaults(self.connection, "accessory_strength")

        self.assertEqual(defaults["单手哑铃划船"], {
            "target_sets": 4, "target_reps": 6, "target_weight": 25.0,
        })
        self.assertNotIn("杠铃后蹲", defaults)

    def test_recent_outdoor_action_becomes_the_input_default_for_its_module(self):
        session = create_planned_session(
            self.connection, "2026-08-10", "sprint", "acceleration"
        )
        create_planned_exercise(
            self.connection, session, canonical_name="站姿起跑", display_name="站姿起跑",
            target_sets=4, target_distance=30,
            module_key="acceleration",
        )

        defaults = recent_outdoor_action_defaults(self.connection, "acceleration")

        self.assertEqual(defaults["站姿起跑"], {
            "target_sets": 4,
            "target_distance_meters": 30.0,
        })

    def test_copy_previous_week_keeps_action_targets_and_does_not_overwrite(self):
        source_cycle = create_training_cycle(
            self.connection, "source", "2026-08-03", "2026-08-09"
        )
        destination_cycle = create_training_cycle(
            self.connection, "destination", "2026-08-10", "2026-08-16"
        )
        source_session = create_planned_session(
            self.connection, "2026-08-03", "上肢拉力 · 力量训练-整体性力量训练·主项",
            "upper_pull", cycle_id=source_cycle, notes="复制测试",
        )
        create_planned_exercise(
            self.connection, source_session, canonical_name="杠铃挺举硬拉", display_name="杠铃挺举硬拉",
            target_sets=3, target_reps=8, target_weight=80, module_key="main_strength",
        )

        result = copy_previous_week_training_content(
            self.connection, "2026-08-10", cycle_id=destination_cycle
        )

        self.assertEqual(result, {
            "source_session_count": 1, "copied_session_count": 1, "skipped_date_count": 0,
        })
        copied = list_planned_sessions(self.connection, cycle_id=destination_cycle)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0]["planned_date"], "2026-08-10")
        self.assertEqual(copied[0]["notes"], "复制测试")
        self.assertEqual(copied[0]["exercises"][0]["target_weight"], 80.0)

        repeated = copy_previous_week_training_content(
            self.connection, "2026-08-10", cycle_id=destination_cycle
        )
        self.assertEqual(repeated, {
            "source_session_count": 1, "copied_session_count": 0, "skipped_date_count": 1,
        })

    def test_training_cycle_requires_at_least_one_week(self):
        with self.assertRaisesRegex(ValueError, "CYCLE_MIN_ONE_WEEK"):
            create_training_cycle(self.connection, "too short", "2026-08-09", "2026-08-14")

        cycle_id = create_training_cycle(
            self.connection, "one week", "2026-08-09", "2026-08-15"
        )
        self.assertIsNotNone(cycle_id)

    def test_cycle_end_date_is_calculated_from_whole_weeks(self):
        self.assertEqual(
            cycle_end_date_for_weeks("2026-08-09", 1).isoformat(), "2026-08-15"
        )
        self.assertEqual(
            cycle_end_date_for_weeks("2026-08-09", 4).isoformat(), "2026-09-05"
        )
        with self.assertRaisesRegex(ValueError, "INVALID_CYCLE_DURATION"):
            cycle_end_date_for_weeks("2026-08-09", 0)

    def test_training_cycle_dates_can_be_updated_manually(self):
        cycle_id = create_training_cycle(
            self.connection, "editable", "2026-08-09", "2026-08-15"
        )

        update_training_cycle(
            self.connection, cycle_id, name="renamed",
            start_date="2026-08-16", end_date="2026-08-29"
        )

        updated = self.connection.execute(
            "SELECT name,start_date,end_date FROM training_cycles WHERE id=?", (cycle_id,)
        ).fetchone()
        self.assertEqual(tuple(updated), ("renamed", "2026-08-16", "2026-08-29"))

    def test_deleting_cycle_removes_its_plan_but_not_actual_data(self):
        cycle_id = create_training_cycle(
            self.connection, "cycle to delete", "2026-08-09", "2026-08-15"
        )
        session_id = create_planned_session(
            self.connection, "2026-08-09", "planned", "upper_pull", cycle_id=cycle_id
        )
        create_planned_exercise(
            self.connection, session_id, canonical_name="单手哑铃划船", display_name="单手哑铃划船",
            target_sets=3, target_reps=8, target_weight=20, module_key="accessory_strength",
        )

        delete_training_cycle(self.connection, cycle_id)

        self.assertIsNone(self.connection.execute(
            "SELECT id FROM training_cycles WHERE id=?", (cycle_id,)
        ).fetchone())
        self.assertIsNone(self.connection.execute(
            "SELECT id FROM planned_training_sessions WHERE id=?", (session_id,)
        ).fetchone())
        self.assertEqual(self.connection.execute(
            "SELECT COUNT(*) FROM planned_training_exercises"
        ).fetchone()[0], 0)

    def test_current_cycle_prefers_active_cycle_that_covers_today(self):
        create_training_cycle(
            self.connection, "planned", "2026-08-01", "2026-08-31", status="planned"
        )
        active_id = create_training_cycle(
            self.connection, "active", "2026-08-05", "2026-08-20", status="active"
        )
        create_training_cycle(
            self.connection, "expired", "2026-07-01", "2026-07-31", status="active"
        )

        current = get_current_training_cycle(self.connection, on_date="2026-08-09")

        self.assertEqual(current["id"], active_id)

    def test_historical_cycle_lookup_includes_completed_cycles(self):
        completed_id = create_training_cycle(
            self.connection, "completed", "2026-07-01", "2026-07-31",
            status="completed",
        )

        historical = get_training_cycle_for_date(
            self.connection, on_date="2026-07-14"
        )

        self.assertEqual(historical["id"], completed_id)

    def test_training_domains_keep_outdoor_cycles_and_plans_separate(self):
        indoor_id = create_training_cycle(
            self.connection, "室内周期", "2026-08-03", "2026-08-09",
        )
        outdoor_id = create_training_cycle(
            self.connection, "室外周期", "2026-08-03", "2026-08-09",
            training_domain="outdoor_running_jumping",
        )

        indoor = create_planned_session(
            self.connection, "2026-08-03", "室内计划", "upper_pull", cycle_id=indoor_id,
        )
        outdoor = create_planned_session(
            self.connection, "2026-08-03", "室外计划", "running", cycle_id=outdoor_id,
        )

        self.assertEqual(
            [item["id"] for item in list_training_cycles(self.connection)], [indoor_id]
        )
        self.assertEqual(
            [item["id"] for item in list_training_cycles(
                self.connection, training_domain="outdoor_running_jumping"
            )], [outdoor_id]
        )
        self.assertEqual(
            [item["id"] for item in list_planned_sessions(
                self.connection, training_domain="indoor_strength"
            )], [indoor]
        )
        self.assertEqual(
            [item["id"] for item in list_planned_sessions(
                self.connection, training_domain="outdoor_running_jumping"
            )], [outdoor]
        )

    def test_cycle_week_segments_follow_cycle_dates_and_matrix_weeks(self):
        segments = cycle_week_segments({
            "start_date": "2026-08-09", "end_date": "2026-08-22",
        })

        self.assertEqual([(item["start_date"], item["end_date"]) for item in segments], [
            ("2026-08-09", "2026-08-15"),
            ("2026-08-16", "2026-08-22"),
        ])
        self.assertEqual(segments[0]["matrix_week_start"], "2026-08-03")
        self.assertEqual(segments[1]["matrix_week_start"], "2026-08-10")

    def test_current_cycle_week_segment_tracks_the_date_inside_a_cycle(self):
        cycle = {"start_date": "2026-08-09", "end_date": "2026-08-22"}

        current = current_cycle_week_segment(cycle, on_date="2026-08-16")

        self.assertEqual(current["index"], 2)
        self.assertEqual(current["matrix_week_start"], "2026-08-10")
        self.assertIsNone(current_cycle_week_segment(cycle, on_date="2026-08-23"))


if __name__ == "__main__":
    unittest.main()
