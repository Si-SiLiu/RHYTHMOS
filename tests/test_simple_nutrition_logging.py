import json
import math
from pathlib import Path
import sqlite3
import unittest
from datetime import time
from uuid import UUID

from src import db
from src.ai_context.builder import build_ai_context
from src.nutrition_logging import (
    FOOD_UNITS, ai_meal_summaries, calculate_food_values, copy_meal_record,
    create_meal_from_template, create_meal_record, find_meal_id, food_catalog_by_name,
    get_meal_record, list_food_catalog, list_meal_records, list_meal_templates,
    meal_time_warning, predict_meal_time, recent_foods, recent_meal_times, save_meal_record, save_meal_template,
    soft_delete_meal_record,
)


class SimpleNutritionLoggingTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(self.connection)
        self.catalog = food_catalog_by_name(self.connection)
        self.meal = {
            "date": "2026-07-18", "meal_type": "breakfast", "eaten_at": "08:15",
            "status": "completed", "source": "manual",
        }

    def tearDown(self):
        self.connection.close()

    def test_catalog_has_multitag_foods_and_stable_units(self):
        self.assertEqual(len(list_food_catalog(self.connection)), 19)
        self.assertEqual(self.catalog["sweet_pepper"]["display_name_zh"], "甜椒")
        self.assertIn("protein_source", self.catalog["egg"]["category_tags"])
        self.assertIn("fat_source", self.catalog["egg"]["category_tags"])
        self.assertIn("whole_grain", self.catalog["oats"]["category_tags"])
        self.assertIn("vegetable", self.catalog["broccoli"]["category_tags"])
        self.assertEqual(self.catalog["egg"]["default_unit"], "piece")
        self.assertEqual(self.catalog["water"]["default_unit"], "ml")
        self.assertIn("vegetable", self.catalog["lettuce"]["category_tags"])
        self.assertIn("beverage", self.catalog["tea"]["category_tags"])
        self.assertEqual(self.catalog["whole_wheat_toast"]["default_unit"], "slice")
        self.assertEqual(len(FOOD_UNITS), 12)

    def test_reliable_and_missing_unit_conversion(self):
        egg = calculate_food_values(self.catalog["egg"], 2, "piece")
        self.assertEqual(egg["normalized_weight_g"], 100)
        self.assertEqual(egg["protein_g"], 12.56)
        water = calculate_food_values(self.catalog["water"], 350, "ml")
        self.assertEqual(water["normalized_volume_ml"], 350)
        custom = calculate_food_values(None, 1, "bowl")
        self.assertIsNone(custom["normalized_weight_g"])
        self.assertIsNone(custom["calories_kcal"])

    def test_create_draft_complete_update_and_soft_delete(self):
        draft = {
            **self.meal, "status": "draft", "planned_meal_time": "08:00",
            "actual_meal_time": "08:15",
        }
        record_id = create_meal_record(self.connection, draft, [{
            "food_catalog_id": self.catalog["oats"]["id"], "quantity": 50, "unit": "g",
        }])
        record = get_meal_record(self.connection, record_id)
        UUID(record["uuid"])
        self.assertEqual(record["status"], "draft")
        self.assertEqual(record["planned_meal_time"], "08:00:00")
        self.assertEqual(record["actual_meal_time"], "08:15:00")
        save_meal_record(self.connection, {**self.meal, "eaten_at": "08:20"}, [{
            "food_catalog_id": self.catalog["egg"]["id"], "quantity": 2, "unit": "piece",
        }], record_id=record_id)
        updated = get_meal_record(self.connection, record_id)
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["eaten_at"], "08:20:00")
        self.assertEqual(updated["actual_meal_time"], "08:20:00")
        self.assertEqual(updated["items"][0]["normalized_weight_g"], 100)
        self.assertTrue(soft_delete_meal_record(self.connection, record_id))
        self.assertIsNone(get_meal_record(self.connection, record_id))

    def test_updating_meal_with_supplement_replaces_legacy_rows_without_fk_error(self):
        record_id = create_meal_record(self.connection, self.meal, [], [{
            "custom_brand_name": "Brand A", "custom_product_name": "Vitamin C",
            "quantity": 1, "unit": "tablet",
        }])

        save_meal_record(self.connection, {
            **self.meal, "eaten_at": "08:30",
        }, [], [{
            "custom_brand_name": "Brand B", "custom_product_name": "Magnesium",
            "quantity": 2, "unit": "capsule",
        }], record_id=record_id)
        record = get_meal_record(self.connection, record_id)
        self.assertEqual(record["supplements"][0]["custom_product_name"], "Magnesium")
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM supplement_intake_records "
                "WHERE meal_record_id=? AND deleted_at IS NOT NULL", (record_id,)
            ).fetchone()[0],
            1,
        )
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_repeated_save_round_trip_keeps_food_beverage_and_supplement(self):
        items = [
            {"food_catalog_id": self.catalog["oats"]["id"], "item_type": "food", "quantity": 50, "unit": "g"},
            {"food_catalog_id": self.catalog["water"]["id"], "item_type": "beverage", "quantity": 350, "unit": "ml"},
        ]
        supplements = [{"item_name": "magnesium", "quantity": 1, "unit": "capsule"}]
        record_id = create_meal_record(self.connection, self.meal, items, supplements)

        for minute in ("08:20", "08:25", "08:30"):
            saved = get_meal_record(self.connection, record_id)
            save_meal_record(
                self.connection,
                {**self.meal, "eaten_at": minute},
                saved["items"],
                saved["supplements"],
                record_id=record_id,
            )
            reloaded = get_meal_record(self.connection, record_id)
            self.assertEqual(len(reloaded["items"]), 2)
            self.assertEqual({item["item_type"] for item in reloaded["items"]}, {"food", "beverage"})
            self.assertEqual(reloaded["items"][0]["quantity"], 50)
            self.assertEqual(reloaded["items"][1]["quantity"], 350)
            self.assertEqual(len(reloaded["supplements"]), 1)
            self.assertEqual(reloaded["supplements"][0]["quantity"], 1)

    def test_meal_types_on_same_date_are_independent(self):
        breakfast_id = create_meal_record(self.connection, self.meal, [{
            "food_catalog_id": self.catalog["oats"]["id"], "quantity": 50, "unit": "g",
        }])
        snack = {**self.meal, "meal_type": "morning_snack", "eaten_at": "10:30"}
        snack_id = create_meal_record(self.connection, snack, [{
            "food_catalog_id": self.catalog["apple"]["id"], "quantity": 1, "unit": "piece",
        }])

        save_meal_record(self.connection, snack, [{
            "food_catalog_id": self.catalog["greek_yogurt"]["id"], "quantity": 150, "unit": "g",
        }], record_id=snack_id)

        breakfast = get_meal_record(self.connection, breakfast_id)
        updated_snack = get_meal_record(self.connection, snack_id)
        self.assertEqual(breakfast["meal_type"], "breakfast")
        self.assertEqual(breakfast["items"][0]["food_catalog_id"], self.catalog["oats"]["id"])
        self.assertEqual(breakfast["items"][0]["quantity"], 50)
        self.assertEqual(updated_snack["meal_type"], "morning_snack")
        self.assertEqual(updated_snack["items"][0]["food_catalog_id"], self.catalog["greek_yogurt"]["id"])
        self.assertEqual(updated_snack["items"][0]["quantity"], 150)
        self.assertEqual(find_meal_id(self.connection, "breakfast", self.meal["date"]), breakfast_id)
        self.assertEqual(find_meal_id(self.connection, "morning_snack", self.meal["date"]), snack_id)
        self.assertIsNone(find_meal_id(self.connection, "lunch", self.meal["date"]))

    def test_recent_meal_times_are_distinct_and_most_recent_first(self):
        for meal_date, meal_time in (
            ("2026-07-16", "08:00"), ("2026-07-17", "08:30"),
            ("2026-07-18", "08:00"),
        ):
            create_meal_record(self.connection, {
                **self.meal, "date": meal_date, "eaten_at": meal_time,
                "actual_meal_time": meal_time,
            }, [])
        self.assertEqual(recent_meal_times(self.connection, "breakfast"), [
            "08:00:00", "08:30:00",
        ])

    def test_predict_meal_time_learns_recent_completed_habit(self):
        for meal_date, meal_time in (
            ("2026-07-16", "08:00"), ("2026-07-17", "08:20"),
            ("2026-07-18", "08:10"),
        ):
            create_meal_record(self.connection, {
                **self.meal, "date": meal_date, "eaten_at": meal_time,
                "actual_meal_time": meal_time,
            }, [])
        self.assertEqual(
            predict_meal_time(self.connection, "breakfast", "2026-07-19"),
            time(8, 10),
        )

    def test_predict_meal_time_excludes_current_date_and_drafts(self):
        create_meal_record(self.connection, {
            **self.meal, "date": "2026-07-18", "eaten_at": "08:10",
            "actual_meal_time": "08:10", "status": "completed",
        }, [])
        create_meal_record(self.connection, {
            **self.meal, "date": "2026-07-19", "eaten_at": "14:00",
            "actual_meal_time": "14:00", "status": "draft",
        }, [])
        self.assertEqual(
            predict_meal_time(self.connection, "breakfast", "2026-07-19"),
            time(8, 10),
        )

    def test_unknown_custom_food_is_unclassified_without_fake_nutrients(self):
        record_id = create_meal_record(self.connection, self.meal, [{
            "custom_food_name": "Unknown homemade dish", "quantity": 1, "unit": "bowl",
        }])
        item = get_meal_record(self.connection, record_id)["items"][0]
        self.assertEqual(item["classification_source"], "unclassified")
        self.assertEqual(json.loads(item["category_tags_json"]), [])
        for field in ("normalized_weight_g", "calories_kcal", "protein_g", "fat_g"):
            self.assertIsNone(item[field])

    def test_empty_row_is_ignored_and_invalid_values_are_rejected(self):
        record_id = create_meal_record(self.connection, self.meal, [{
            "custom_food_name": "", "quantity": None, "unit": "g",
        }])
        self.assertEqual(get_meal_record(self.connection, record_id)["items"], [])
        invalid = (
            {"custom_food_name": "x", "quantity": 0, "unit": "g"},
            {"custom_food_name": "x", "quantity": math.nan, "unit": "g"},
            {"custom_food_name": "x", "quantity": math.inf, "unit": "g"},
            {"custom_food_name": "x", "quantity": 1, "unit": "handful"},
            {"food_catalog_id": self.catalog["egg"]["id"], "quantity": 1, "unit": "ml"},
        )
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                create_meal_record(self.connection, self.meal, [item])

    def test_blank_food_row_does_not_block_beverage_only_meal(self):
        record_id = create_meal_record(self.connection, self.meal, [
            {"custom_food_name": "", "quantity": None, "unit": "g", "item_type": "food"},
            {"food_catalog_id": self.catalog["tea"]["id"], "quantity": 1, "unit": "cup", "item_type": "beverage"},
        ])
        record = get_meal_record(self.connection, record_id)
        self.assertEqual(len(record["items"]), 1)
        self.assertEqual(record["items"][0]["item_type"], "beverage")

    def test_summary_preserves_missing_values_and_completeness(self):
        record_id = create_meal_record(self.connection, self.meal, [
            {"food_catalog_id": self.catalog["egg"]["id"], "quantity": 2, "unit": "piece"},
            {"custom_food_name": "Unknown", "quantity": 1, "unit": "serving"},
        ])
        summary = get_meal_record(self.connection, record_id)["summary"]
        self.assertEqual(summary["food_count"], 2)
        self.assertEqual(summary["identified_food_count"], 1)
        self.assertEqual(summary["calories_kcal"], 143)
        self.assertEqual(summary["data_completeness"], 0.5)
        unknown_id = create_meal_record(self.connection, self.meal, [
            {"custom_food_name": "Unknown only", "quantity": 1, "unit": "serving"},
        ])
        self.assertIsNone(get_meal_record(self.connection, unknown_id)["summary"]["calories_kcal"])

    def test_recent_copy_and_uuid_are_independent(self):
        source = create_meal_record(self.connection, self.meal, [{
            "food_catalog_id": self.catalog["oats"]["id"], "quantity": 50, "unit": "g",
        }])
        copied = copy_meal_record(self.connection, source, "2026-07-19", "08:30")
        original = get_meal_record(self.connection, source)
        clone = get_meal_record(self.connection, copied)
        self.assertNotEqual(original["uuid"], clone["uuid"])
        self.assertNotEqual(original["items"][0]["uuid"], clone["items"][0]["uuid"])
        self.assertEqual(clone["source"], "copied")
        self.assertEqual(recent_foods(self.connection)[0]["catalog"]["canonical_name"], "oats")

    def test_template_round_trip_includes_food_and_supplement(self):
        template_id = save_meal_template(self.connection, "Morning", "breakfast", [{
            "food_catalog_id": self.catalog["oats"]["id"], "quantity": 50, "unit": "g",
        }], [{
            "item_name": "creatine_monohydrate", "quantity": 5, "unit": "g",
        }])
        self.assertEqual(list_meal_templates(self.connection)[0]["id"], template_id)
        record_id = create_meal_from_template(self.connection, template_id, "2026-07-19", "08:00")
        record = get_meal_record(self.connection, record_id)
        self.assertEqual(record["source"], "template")
        self.assertEqual(record["items"][0]["quantity"], 50)
        self.assertEqual(record["supplements"][0]["unit"], "g")

    def test_template_requires_a_name(self):
        with self.assertRaisesRegex(ValueError, "INVALID_MEAL_TEMPLATE"):
            save_meal_template(self.connection, "  ", "breakfast", [], [])

    def test_daily_supplement_keeps_unit_but_moves_active_component_to_product_profile(self):
        record_id = create_meal_record(self.connection, self.meal, [], [{
            "item_name": "fish_oil", "quantity": 1, "unit": "capsule",
            "active_component_name": "EPA+DHA", "active_amount": 840,
            "active_unit": "mg", "item_notes": "with breakfast",
        }])
        supplement = get_meal_record(self.connection, record_id)["supplements"][0]
        self.assertEqual(supplement["unit"], "capsule")
        self.assertIsNone(supplement["active_component_name"])
        self.assertIsNone(supplement["active_amount"])
        self.assertEqual(supplement["custom_product_name"], "fish_oil")

    def test_ai_context_contains_only_structured_meal_summary(self):
        create_meal_record(self.connection, {**self.meal, "notes": "private meal note"}, [{
            "food_catalog_id": self.catalog["egg"]["id"], "quantity": 2,
            "unit": "piece", "notes": "private item note",
        }])
        payload = build_ai_context(self.connection, "2026-07-18", range_days=1)
        meal = payload["nutrition_summary"]["meals"][0]
        self.assertEqual(meal["food_count"], 1)
        self.assertEqual(meal["protein_g"], 12.56)
        self.assertNotIn("private", str(payload))
        self.assertNotIn("food_catalog_id", str(payload))

    def test_time_warning_is_non_blocking_policy(self):
        self.assertTrue(meal_time_warning("breakfast", "17:06:00"))
        self.assertFalse(meal_time_warning("breakfast", "08:00:00"))

    def test_database_constraints_foreign_keys_and_uuid_uniqueness(self):
        record_id = create_meal_record(self.connection, self.meal, [{
            "custom_food_name": "x", "quantity": 1, "unit": "piece",
        }])
        item = get_meal_record(self.connection, record_id)["items"][0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO meal_records(uuid,date,meal_type,eaten_at,status,source) VALUES(?,?,?,?,?,?)",
                (get_meal_record(self.connection, record_id)["uuid"], "2026-07-18", "breakfast", "08:00", "draft", "manual"),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO meal_items(uuid,meal_record_id,custom_food_name,item_type,quantity,unit,classification_source)
                   VALUES(?,?,?,?,?,?,?)""",
                (item["uuid"], 999999, "x", "food", 1, "g", "unclassified"),
            )
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_legacy_category_migration_preserves_food_and_supplement(self):
        legacy = sqlite3.connect(":memory:")
        legacy.row_factory = sqlite3.Row
        legacy.execute("PRAGMA foreign_keys=ON")
        db.init_db(legacy)
        legacy.executescript("""
            DROP TABLE meal_items;
            DROP TABLE food_favorites;
            DROP TABLE meal_templates;
            DROP TABLE meal_records;
            DROP TABLE food_catalog;
            ALTER TABLE meal_event_items DROP COLUMN active_component_name;
            DELETE FROM schema_migrations WHERE version='0.13.0';
        """)
        event_id = legacy.execute(
            "INSERT INTO meal_events(date,meal_type,actual_meal_time) VALUES('2026-07-17','breakfast','08:00')"
        ).lastrowid
        legacy.execute(
            """INSERT INTO meal_event_items(meal_event_id,category,position,item_name,quantity,unit)
               VALUES(?, 'carbohydrate', 1, 'oats', 50, 'g')""", (event_id,)
        )
        legacy.execute(
            """INSERT INTO meal_event_items(meal_event_id,category,position,item_name,quantity,unit)
               VALUES(?, 'supplement', 1, 'fish_oil', 1, 'capsule')""", (event_id,)
        )
        db.apply_migrations(legacy); db.apply_migrations(legacy)
        self.assertEqual(db.current_schema_version(legacy), db.SCHEMA_MIGRATIONS[-1].version)
        migrated = legacy.execute("SELECT * FROM meal_items").fetchone()
        self.assertEqual((migrated["quantity"], migrated["unit"]), (50, "g"))
        self.assertEqual(json.loads(migrated["category_tags_json"]), ["carbohydrate"])
        self.assertEqual(legacy.execute("SELECT COUNT(*) FROM meal_event_items WHERE category='supplement'").fetchone()[0], 1)
        self.assertEqual(legacy.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        legacy.close()

    def test_dashboard_source_defaults_to_simple_dynamic_rows(self):
        page = (Path(__file__).resolve().parents[1] / "src/pages/3_Nutrition.py").read_text(encoding="utf-8")
        self.assertIn('"1. 饮食记录"', page)
        self.assertIn('TR("simple_nutrition.add_item")', page)
        self.assertIn('TR("simple_nutrition.delete_row")', page)
        self.assertIn('use_container_width=True', page)
        self.assertIn('key="simple_active_meal_type"', page)
        self.assertIn('key="simple_active_meal_date"', page)
        self.assertNotIn('TR("simple_nutrition.copy_previous_row")', page)
        self.assertNotIn("categories_for_meal", page)
        self.assertNotIn("def _item_editor", page)

    def test_localized_simple_input_contract(self):
        base = Path(__file__).resolve().parents[1] / "locales"
        zh = json.loads((base / "zh-CN.json").read_text(encoding="utf-8"))["simple_nutrition"]
        en = json.loads((base / "en.json").read_text(encoding="utf-8"))["simple_nutrition"]
        self.assertEqual(zh["food_or_beverage"], "食物或饮品")
        self.assertEqual(en["food_or_beverage"], "Food or beverage")
        self.assertEqual(zh["units"]["piece"], "个")
        self.assertEqual(en["units"]["cup"], "cup")


if __name__ == "__main__":
    unittest.main()
