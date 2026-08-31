import sqlite3
import unittest
from pathlib import Path

from src import db
from src.dashboard import _create_week_plan
from src.training_plan import (
    analyze_plan_actual,
    build_hprs_snapshot,
    create_training_block,
    create_training_day_template,
    create_training_prescription,
    delete_training_prescription,
    create_training_program,
    get_or_create_training_block,
    get_weekly_training_plan,
    plan_day_for_date,
    prescription_snapshot,
    update_training_day_planned_date,
    update_training_day_sport_type,
)


class TrainingPlanTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        db.init_db(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_plan_tables_are_created_and_old_training_tables_remain(self):
        tables = {row[0] for row in self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertTrue({
            "training_programs", "training_day_templates", "training_blocks",
            "training_prescriptions", "training_sessions", "training_exercises",
            "training_sets",
        } <= tables)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(training_sessions)")}
        self.assertTrue({
            "training_program_id", "training_day_template_id",
            "prescription_snapshot_json", "hprs_adjustment_json",
        } <= columns)
        day_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(training_day_templates)")}
        self.assertIn("sport_type", day_columns)

    def test_weekly_plan_is_rendered_before_personal_training_baseline(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "dashboard.py").read_text(encoding="utf-8")
        main_source = source.split("def main():", 1)[1]
        self.assertLess(
            main_source.index("_render_weekly_training_plan(connection)"),
            main_source.index("_render_training_baseline()"),
        )

    def test_daily_plan_does_not_repeat_the_section_sport_type_selector(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "dashboard.py").read_text(encoding="utf-8")
        plan_inputs = source.split("def _render_daily_plan_inputs", 1)[1].split(
            "def _render_day_action_editor", 1
        )[0]
        self.assertNotIn("training_plan_day_type_", plan_inputs)
        self.assertNotIn("update_training_day_sport_type", plan_inputs)
        self.assertIn("training_plan_day_date_{sport_type}_{day['id']}", plan_inputs)

    def test_new_week_plan_has_only_empty_manual_days(self):
        _create_week_plan(self.connection)
        plan = get_weekly_training_plan(self.connection)
        self.assertEqual(len(plan["days"]), 7)
        self.assertTrue(all(day["prescription_count"] == 0 for day in plan["days"]))
        self.assertTrue(all(day["planned_date"] for day in plan["days"]))

    def test_manual_planned_date_selects_the_matching_plan_day(self):
        program = create_training_program(self.connection, "手动日期计划")
        first = create_training_day_template(
            self.connection, program, "mon", "周一", planned_date="2026-08-10",
        )
        create_training_day_template(
            self.connection, program, "tue", "周二", planned_date="2026-08-11",
        )
        update_training_day_planned_date(self.connection, first, "2026-08-12")
        plan = get_weekly_training_plan(self.connection)
        self.assertEqual(plan_day_for_date(plan, __import__("datetime").date(2026, 8, 12))["id"], first)
        self.assertIsNone(plan_day_for_date(plan, __import__("datetime").date(2026, 8, 10)))

    def test_plan_hierarchy_and_weekday_lookup(self):
        program = create_training_program(self.connection, "基础周计划")
        day = create_training_day_template(self.connection, program, "mon", "周一")
        block = create_training_block(self.connection, day, "main_strength", "主力量")
        prescription = create_training_prescription(
            self.connection, block, custom_exercise_name="深蹲",
            planned_sets=[{"reps": 5, "load_value": 60}],
        )
        plan = get_weekly_training_plan(self.connection)
        self.assertEqual(plan["program"]["name"], "基础周计划")
        self.assertEqual(plan["days"][0]["prescription_count"], 1)
        self.assertEqual(plan_day_for_date(plan, __import__("datetime").date(2026, 7, 20))["day_key"], "mon")
        self.assertEqual(prescription_snapshot(plan["days"][0])[0]["prescriptions"][0]["id"], prescription)

    def test_daily_sport_type_and_action_lifecycle(self):
        program = create_training_program(self.connection, "按日计划")
        day = create_training_day_template(self.connection, program, "mon", "周一")
        update_training_day_sport_type(self.connection, day, "performance_dance")
        block = get_or_create_training_block(self.connection, day, "daily_plan", "表演舞")
        self.assertEqual(get_or_create_training_block(self.connection, day, "daily_plan", "表演舞"), block)
        prescription = create_training_prescription(
            self.connection, block, custom_exercise_name="舞蹈组合",
            planned_sets=[{"reps": 8, "load_value": 0}], target_notes="热身",
        )
        day_data = get_weekly_training_plan(self.connection)["days"][0]
        self.assertEqual(day_data["sport_type"], "performance_dance")
        self.assertEqual(day_data["prescription_count"], 1)
        delete_training_prescription(self.connection, prescription)
        self.assertEqual(get_weekly_training_plan(self.connection)["days"][0]["prescription_count"], 0)

    def test_plan_actual_analysis_does_not_require_old_records_to_have_plan_links(self):
        result = analyze_plan_actual(None, [{"training_prescription_id": None, "sets": [{"completed": True}]}])
        self.assertEqual(result["actual_sets"], 1)
        self.assertIsNone(result["exercise_completion_rate"])

    def test_hprs_snapshot_preserves_original_and_adjusts_regulated_sets(self):
        snapshot = build_hprs_snapshot(
            [{"load_value": 100, "reps": 10}],
            status="moderate_reduction", volume_adjustment_percent=-20,
            intensity_adjustment_percent=-10, reason="recovery signal",
        )
        self.assertEqual(snapshot["original_sets"][0]["reps"], 10)
        self.assertEqual(snapshot["regulated_sets"][0]["reps"], 8)
        self.assertEqual(snapshot["regulated_sets"][0]["load_value"], 90)


if __name__ == "__main__":
    unittest.main()
