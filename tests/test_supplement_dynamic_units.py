import math
import json
import sqlite3
import unittest
from pathlib import Path

from src import db
from src.ai_context.builder import build_ai_context
from src.nutrition_logging import (
    CUSTOM_SUPPLEMENT, NutritionEventValidationError, SUPPLEMENT_UNITS,
    allowed_units, create_meal_event, default_unit, get_meal_event,
    list_catalog, save_meal_event, summarize_supplements,
)


class SupplementDynamicUnitTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(self.connection)
        self.event = {
            "date": "2026-07-18", "meal_type": "breakfast",
            "actual_meal_time": "08:00:00",
        }

    def tearDown(self):
        self.connection.close()

    def test_catalog_defaults_and_count(self):
        self.assertEqual(len(list_catalog(self.connection)), 10)
        self.assertEqual(default_unit("creatine_monohydrate"), "g")
        self.assertEqual(default_unit("fish_oil"), "capsule")
        self.assertEqual(default_unit("lutein"), "capsule")
        self.assertEqual(default_unit("vitamin_d3k2"), "capsule")
        self.assertEqual(default_unit("magnesium"), "tablet")
        self.assertEqual(set(allowed_units(CUSTOM_SUPPLEMENT)), set(SUPPLEMENT_UNITS))

    def test_supplement_crud_manual_override_and_active_dose(self):
        event_id = create_meal_event(self.connection, self.event, [{
            "category": "supplement", "position": 1,
            "item_name": "fish_oil", "quantity": 1, "unit": "capsule",
            "active_amount": 840, "active_unit": "mg", "item_notes": "EPA+DHA",
        }])
        item = get_meal_event(self.connection, event_id)["items"][0]
        self.assertEqual((item["quantity"], item["unit"]), (1, "capsule"))
        self.assertEqual((item["active_amount"], item["active_unit"]), (840, "mg"))
        save_meal_event(self.connection, self.event, [{
            "category": "supplement", "position": 1,
            "item_name": "creatine_monohydrate", "quantity": 5000, "unit": "mg",
        }], event_id)
        updated = get_meal_event(self.connection, event_id)["items"][0]
        self.assertEqual((updated["quantity"], updated["unit"]), (5000, "mg"))

    def test_invalid_values_units_and_active_pairs_are_rejected(self):
        invalid_items = (
            {"item_name": "fish_oil", "quantity": 0, "unit": "capsule"},
            {"item_name": "fish_oil", "quantity": 1, "unit": "g"},
            {"item_name": "fish_oil", "quantity": 1, "unit": "capsule", "active_amount": 840},
            {"item_name": "fish_oil", "quantity": 1, "unit": "capsule", "active_unit": "mg"},
            {"item_name": "fish_oil", "quantity": math.inf, "unit": "capsule"},
            {"item_name": "", "quantity": 1, "unit": "g"},
            {"item_name": "custom-name", "quantity": 1, "unit": "bottle"},
        )
        for item in invalid_items:
            with self.subTest(item=item), self.assertRaises((NutritionEventValidationError, ValueError)):
                create_meal_event(self.connection, self.event, [{
                    "category": "supplement", "position": 1, **item,
                }])

    def test_null_active_dose_and_custom_unit_are_supported(self):
        event_id = create_meal_event(self.connection, self.event, [{
            "category": "supplement", "position": 1,
            "item_name": "custom-name", "quantity": 2.5, "unit": "drop",
        }])
        item = get_meal_event(self.connection, event_id)["items"][0]
        self.assertIsNone(item["active_amount"])
        self.assertIsNone(item["active_unit"])

    def test_summary_only_combines_matching_name_and_unit(self):
        summary = summarize_supplements([
            {"category": "supplement", "item_name": "creatine_monohydrate", "quantity": 5, "unit": "g"},
            {"category": "supplement", "item_name": "creatine_monohydrate", "quantity": 2, "unit": "g"},
            {"category": "supplement", "item_name": "creatine_monohydrate", "quantity": 1, "unit": "scoop"},
            {"category": "supplement", "item_name": "fish_oil", "quantity": 1, "unit": "capsule"},
        ])
        self.assertEqual(len(summary), 3)
        self.assertIn({
            "name": "creatine_monohydrate", "quantity": 7.0, "unit": "g",
            "record_count": 2, "active_amount": None, "active_unit": None,
            "active_component_name": None, "item_notes": None,
        }, summary)

    def test_single_record_summary_preserves_notes_for_history_display(self):
        summary = summarize_supplements([{
            "category": "supplement", "item_name": "fish_oil",
            "quantity": 1, "unit": "capsule", "active_amount": 840,
            "active_unit": "mg", "item_notes": "EPA+DHA",
        }])
        self.assertEqual(summary[0]["item_notes"], "EPA+DHA")
        self.assertEqual(summary[0]["active_amount"], 840)

    def test_ai_context_preserves_units_and_excludes_notes(self):
        create_meal_event(self.connection, self.event, [{
            "category": "supplement", "position": 1,
            "item_name": "fish_oil", "quantity": 1, "unit": "capsule",
            "active_amount": 840, "active_unit": "mg", "item_notes": "private-note",
        }])
        payload = build_ai_context(self.connection, "2026-07-18", range_days=1)
        supplement = payload["nutrition_summary"]["supplements"][0]
        self.assertEqual((supplement["quantity"], supplement["unit"]), (1, "capsule"))
        self.assertNotIn("private-note", str(payload))

    def test_sqlite_constraints_and_integrity(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO meal_event_items(
                       meal_event_id,category,position,item_name,quantity,unit
                   ) VALUES(1,'supplement',1,'fish_oil',1,'bottle')"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO meal_event_items(
                       meal_event_id,category,position,item_name,quantity,unit
                   ) VALUES(1,'supplement',1,'fish_oil',0,'capsule')"""
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """INSERT INTO meal_event_items(
                       meal_event_id,category,position,item_name,quantity,unit,
                       active_amount
                   ) VALUES(1,'supplement',1,'fish_oil',1,'capsule',840)"""
            )
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_localized_unit_and_field_contract(self):
        base = Path(__file__).resolve().parents[1] / "locales"
        zh = json.loads((base / "zh-CN.json").read_text(encoding="utf-8"))["nutrition_entry"]
        en = json.loads((base / "en.json").read_text(encoding="utf-8"))["nutrition_entry"]
        self.assertEqual((zh["intake_quantity"], zh["unit"]), ("摄入量", "单位"))
        self.assertEqual((en["intake_quantity"], en["unit"]), ("Quantity", "Unit"))
        self.assertEqual(zh["units"], {
            "g": "克", "mg": "毫克", "mcg": "微克", "ml": "毫升",
            "capsule": "粒", "tablet": "片", "sachet": "袋", "scoop": "勺",
            "drop": "滴", "iu": "国际单位",
        })
        self.assertEqual(en["units"]["mcg"], "μg")
        self.assertEqual(en["units"]["iu"], "IU")

    def test_dashboard_uses_dynamic_supplement_controls(self):
        page = (Path(__file__).resolve().parents[1] / "src/pages/3_Nutrition.py").read_text(encoding="utf-8")
        editor = page[page.index("def _supplement_editor"):page.index("def _quick_actions")]
        self.assertIn('"supplement_products.quantity"', editor)
        self.assertIn('"supplement_products.unit"', editor)
        self.assertNotIn('headers = ("brand",', editor)
        self.assertIn('"supplement_products.product_name"', editor)
        self.assertIn(".selectbox(", editor)
        self.assertIn(".number_input(", editor)
        self.assertIn("添加补剂", editor)
        self.assertIn("添加用药", editor)
        self.assertIn("supplement_delete_", editor)
        self.assertNotIn("剂量（克）", editor)
        self.assertNotIn('"simple_nutrition.active_component_name"', editor)
        self.assertNotIn('"nutrition_entry.active_amount"', editor)
        self.assertNotIn('"nutrition_entry.active_unit"', editor)

    def test_legacy_gram_record_migration_preserves_data_and_is_idempotent(self):
        event_id = self.connection.execute(
            "INSERT INTO meal_events(date,meal_type,actual_meal_time) VALUES('2026-07-17','breakfast','08:00')"
        ).lastrowid
        self.connection.execute("ALTER TABLE meal_event_items RENAME TO meal_event_items_new_012")
        self.connection.executescript("""
            CREATE TABLE meal_event_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, meal_event_id INTEGER NOT NULL,
                category TEXT NOT NULL, position INTEGER NOT NULL, item_name TEXT,
                quantity REAL NOT NULL, unit TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(meal_event_id,category,position)
            );
        """)
        self.connection.execute(
            """INSERT INTO meal_event_items(
                   meal_event_id,category,position,item_name,quantity,unit
               ) VALUES(?, 'supplement', 1, 'creatine_monohydrate', 5, 'g')""",
            (event_id,),
        )
        self.connection.execute("DROP TABLE meal_event_items_new_012")
        self.connection.execute("DROP TABLE supplement_catalog")
        self.connection.execute("DELETE FROM schema_migrations WHERE version='0.12.0'")
        self.connection.commit()
        db.apply_migrations(self.connection)
        db.apply_migrations(self.connection)
        row = self.connection.execute(
            "SELECT item_name,quantity,unit FROM meal_event_items WHERE category='supplement'"
        ).fetchone()
        self.assertEqual(tuple(row), ("creatine_monohydrate", 5, "g"))
        self.assertEqual(
            db.current_schema_version(self.connection), db.SCHEMA_MIGRATIONS[-1].version
        )
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
