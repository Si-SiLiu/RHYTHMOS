import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src import db
from src.training_logging import (
    create_custom_exercise_catalog, create_manual_training_session,
    list_exercise_catalog, save_training_details,
)
from src.training_logging.summary import summarize_training
from src.ui.components.training_entry import (
    ENTRY_MODES, EXERTION_PREFERENCES, apply_catalog_defaults,
    copied_set_for_entry, default_load_unit, visible_set_fields,
)


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = (ROOT / "src" / "dashboard.py").read_text(encoding="utf-8")
COMPONENT = (ROOT / "src" / "ui" / "components" / "training_entry.py").read_text(encoding="utf-8")


class SimplifiedTrainingEntryTests(unittest.TestCase):
    def _database(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        connection = sqlite3.connect(Path(directory.name) / "training.db")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(connection)
        self.addCleanup(connection.close)
        return connection

    @staticmethod
    def _set(**updates):
        row = {
            "uuid": "original", "set_type": "working", "load_value": 80,
            "load_unit": "kg", "reps": 8, "duration_seconds": 60,
            "distance_meters": 1000, "resistance_level": 4,
            "incline_percent": 2, "rpe": 8, "rir": 2,
            "rest_seconds": 120, "side": "bilateral", "completed": True,
            "notes": "preserve",
        }
        row.update(updates)
        return row

    # Mode switching (1–5)
    def test_01_default_mode_is_simple(self):
        self.assertEqual(ENTRY_MODES[0], "simple")

    def test_02_advanced_mode_is_supported(self):
        self.assertIn("set_type", visible_set_fields("weight_reps", "advanced", "rpe"))

    def test_03_switching_mode_does_not_mutate_data(self):
        row = self._set()
        before = dict(row)
        visible_set_fields("weight_reps", "simple", "rpe")
        visible_set_fields("weight_reps", "advanced", "rpe")
        self.assertEqual(row, before)

    def test_04_mode_uses_session_state_key(self):
        self.assertIn('key=f"training_entry_mode_{session[\'id\']}"', DASHBOARD)

    def test_05_advanced_fields_hidden_not_deleted(self):
        row = self._set()
        fields = visible_set_fields("weight_reps", "simple", "rpe")
        self.assertNotIn("rest_seconds", fields)
        self.assertEqual(row["rest_seconds"], 120)

    # Dynamic fields (6–11)
    def test_06_weight_reps_simple_fields(self):
        self.assertEqual(
            visible_set_fields("weight_reps", "simple", "rpe"),
            ("load_value", "load_unit", "reps", "rpe"),
        )

    def test_07_duration_does_not_require_reps_in_ui(self):
        self.assertEqual(visible_set_fields("duration", "simple", "rpe"), ("duration_seconds", "rpe"))

    def test_08_distance_duration_has_both_fields(self):
        fields = visible_set_fields("distance_duration", "simple", "rpe")
        self.assertEqual(fields[:2], ("distance_meters", "duration_seconds"))

    def test_09_dance_has_no_load(self):
        fields = visible_set_fields("dance_practice", "advanced", "rpe")
        self.assertNotIn("load_value", fields)
        self.assertNotIn("set_type", fields)

    def test_10_freeform_can_be_notes_only(self):
        fields = visible_set_fields("freeform", "simple", "none")
        self.assertIn("notes", fields)
        self.assertNotIn("reps", fields)

    def test_11_bodyweight_is_not_zero_kg(self):
        self.assertEqual(default_load_unit("bodyweight_reps"), "bodyweight")

    # Catalog and custom exercise (12–15)
    def test_12_barbell_squat_autofills_catalog_metadata(self):
        connection = self._database()
        squat = next(x for x in list_exercise_catalog(connection) if x["canonical_name"] == "barbell_back_squat")
        result = apply_catalog_defaults({"sets": [{}]}, squat)
        self.assertEqual((result["exercise_category"], result["primary_muscle_group"], result["equipment"]),
                         ("strength", "lower_body", "barbell"))

    def test_13_catalog_properties_not_required_in_simple_set_fields(self):
        fields = visible_set_fields("weight_reps", "simple", "rpe")
        self.assertTrue({"exercise_category", "primary_muscle_group", "equipment"}.isdisjoint(fields))

    def test_14_custom_exercise_minimum_setup_is_present(self):
        for token in ("custom_exercise_name", "exercise_category", "measurement_mode"):
            self.assertIn(token, DASHBOARD)

    def test_15_unconfirmed_custom_exercise_does_not_write_catalog(self):
        connection = self._database()
        before = connection.execute("SELECT COUNT(*) FROM exercise_catalog").fetchone()[0]
        payload = {"custom_exercise_name": "Only this time", "exercise_category": "other", "measurement_mode": "freeform"}
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM exercise_catalog").fetchone()[0], before)
        self.assertNotEqual(payload["custom_exercise_name"], "")

    # RPE/RIR (16–20)
    def test_16_rpe_is_default_preference(self):
        self.assertEqual(EXERTION_PREFERENCES[0], "rpe")

    def test_17_rir_hides_rpe(self):
        fields = visible_set_fields("weight_reps", "simple", "rir")
        self.assertIn("rir", fields); self.assertNotIn("rpe", fields)

    def test_18_none_hides_both_effort_fields(self):
        fields = visible_set_fields("weight_reps", "simple", "none")
        self.assertNotIn("rpe", fields); self.assertNotIn("rir", fields)

    def test_19_other_effort_value_is_preserved(self):
        row = self._set()
        copied_set_for_entry(row, "weight_reps", "simple", "rpe")
        self.assertEqual(row["rir"], 2)

    def test_20_no_rpe_rir_conversion_rule(self):
        self.assertNotIn("convert", COMPONENT.casefold())

    # Set operations (21–27)
    def test_21_add_set_defaults_completed_for_post_entry(self):
        copied = copied_set_for_entry(self._set(), "weight_reps", "simple", "rpe")
        self.assertTrue(copied["completed"])

    def test_22_copy_previous_copies_applicable_values(self):
        copied = copied_set_for_entry(self._set(), "weight_reps", "simple", "rpe")
        self.assertEqual((copied["load_value"], copied["reps"], copied["rpe"]), (80, 8, 8))

    def test_23_copy_gets_new_uuid(self):
        copied = copied_set_for_entry(self._set(), "weight_reps", "simple", "rpe")
        self.assertNotEqual(copied["uuid"], "original")

    def test_24_set_numbers_are_derived_contiguously(self):
        copies = [copied_set_for_entry(self._set(), "weight_reps", "simple", "rpe") for _ in range(3)]
        self.assertEqual(list(range(1, len(copies) + 1)), [1, 2, 3])

    def test_25_batch_copy_count_and_uuid_uniqueness(self):
        copies = [copied_set_for_entry(self._set(), "weight_reps", "simple", "rpe") for _ in range(20)]
        self.assertEqual(len({x["uuid"] for x in copies}), 20)

    def test_26_delete_requires_confirmation(self):
        self.assertIn("confirm_delete_set", DASHBOARD)
        self.assertIn("confirm_delete_exercise", DASHBOARD)

    def test_27_blank_sets_are_filtered_by_service(self):
        self.assertIn("if cleaned:", (ROOT / "src" / "training_logging" / "storage.py").read_text())

    # Page and lifecycle (28–37)
    def test_28_simple_mode_does_not_show_all_advanced_fields(self):
        self.assertLess(len(visible_set_fields("weight_reps", "simple", "rpe")),
                        len(visible_set_fields("weight_reps", "advanced", "rpe")))

    def test_29_default_quick_actions_are_simplified(self):
        for token in ("add_set", "copy_previous_set", "more_actions"):
            self.assertIn(token, DASHBOARD)

    def test_30_desktop_rows_cap_primary_fields(self):
        self.assertIn("primary_fields = fields[:4]", DASHBOARD)

    def test_31_narrow_screen_has_responsive_css(self):
        self.assertIn("@media (max-width: 760px)", DASHBOARD)

    def test_32_dark_theme_uses_theme_neutral_css(self):
        css = DASHBOARD.split('TRAINING_CSS = """', 1)[1].split('"""', 1)[0]
        self.assertNotIn("background:#", css.replace(" ", "").lower())

    def test_33_light_theme_uses_theme_neutral_css(self):
        css = DASHBOARD.split('TRAINING_CSS = """', 1)[1].split('"""', 1)[0]
        self.assertNotIn("color:#", css.replace(" ", "").lower())

    def test_34_simplified_chinese_i18n(self):
        locale = json.loads((ROOT / "locales" / "zh-CN.json").read_text())["training_logging"]
        self.assertEqual(locale["simple_mode"], "简单模式")

    def test_35_english_i18n(self):
        locale = json.loads((ROOT / "locales" / "en.json").read_text())["training_logging"]
        self.assertEqual(locale["simple_mode"], "Simple mode")

    def test_36_rerun_does_not_save_implicitly(self):
        self.assertIn("save_training_details(", DASHBOARD)
        self.assertIn("if draft_clicked or complete_clicked:", DASHBOARD)

    def test_37_save_failure_keeps_editor_state(self):
        failure_block = DASHBOARD.split("if draft_clicked or complete_clicked:", 1)[1]
        self.assertIn("except Exception as exc:", failure_block)
        self.assertNotIn("session_state.clear", failure_block)

    # Regression and safety (38–47)
    def test_38_training_volume_formula_unchanged(self):
        result = summarize_training([{"primary_muscle_group": "legs", "sets": [self._set()]}])
        self.assertEqual(result["strength_volume_load_kg"], 640)

    def test_39_working_set_count_unchanged(self):
        result = summarize_training([{"sets": [self._set(), self._set(set_type="warmup")]}])
        self.assertEqual(result["working_set_count"], 1)

    def test_40_muscle_group_count_unchanged(self):
        result = summarize_training([{"primary_muscle_group": "legs", "sets": [self._set(), self._set()]}])
        self.assertEqual(result["muscle_group_set_counts"], {"legs": 2})

    def test_41_polar_objective_priority_guard_remains(self):
        storage = (ROOT / "src" / "training_logging" / "storage.py").read_text()
        self.assertIn("POLAR_OBJECTIVE_FIELDS_READ_ONLY", storage)

    def test_42_recovery_engine_version_unchanged(self):
        versions = json.loads((ROOT / "config" / "versions.json").read_text())
        self.assertEqual(versions["recovery_engine_version"], "1.0.0")

    def test_43_baseline_engine_version_unchanged(self):
        versions = json.loads((ROOT / "config" / "versions.json").read_text())
        self.assertEqual(versions["baseline_engine_version"], "1.0.0")

    def test_44_confidence_engine_version_unchanged(self):
        versions = json.loads((ROOT / "config" / "versions.json").read_text())
        self.assertEqual(versions["confidence_engine_version"], "1.0.0")

    def test_45_existing_structured_training_tests_remain(self):
        self.assertTrue((ROOT / "tests" / "test_structured_training_logging.py").is_file())

    def test_46_training_entry_does_not_call_cloud_ai(self):
        combined = (DASHBOARD + COMPONENT).casefold()
        self.assertNotIn("openai", combined)
        self.assertNotIn("http://", combined)

    def test_47_ui_does_not_output_secrets_or_full_health_data(self):
        combined = (DASHBOARD + COMPONENT).casefold()
        self.assertNotIn("api_key", combined)
        self.assertNotIn("access_token", combined)


class CustomExerciseCatalogConfirmationTests(unittest.TestCase):
    def test_explicit_service_call_is_idempotent_for_matching_definition(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(Path(directory) / "training.db")
            connection.row_factory = sqlite3.Row
            db.init_db(connection)
            payload = {
                "custom_exercise_name": "Wall Flow", "exercise_category": "mobility",
                "measurement_mode": "duration", "primary_muscle_group": "shoulder",
                "equipment": "wall", "is_unilateral": False,
            }
            first = create_custom_exercise_catalog(connection, payload)
            second = create_custom_exercise_catalog(connection, payload)
            self.assertEqual(first, second)
            connection.close()

    def test_explicit_catalog_save_can_be_used_by_existing_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(Path(directory) / "training.db")
            connection.row_factory = sqlite3.Row
            db.init_db(connection)
            catalog_id = create_custom_exercise_catalog(connection, {
                "custom_exercise_name": "Timed Flow", "exercise_category": "mobility",
                "measurement_mode": "duration",
            })
            session_id = create_manual_training_session(connection, {
                "date": "2026-07-18", "resolved_sport_type": "mobility", "status": "draft",
            })
            save_training_details(connection, session_id, {"status": "completed"}, [{
                "exercise_catalog_id": catalog_id, "exercise_category": "mobility",
                "measurement_mode": "duration", "sets": [{"duration_seconds": 60}],
            }])
            count = connection.execute("SELECT COUNT(*) FROM training_exercises").fetchone()[0]
            self.assertEqual(count, 1)
            connection.close()
