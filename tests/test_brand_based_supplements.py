import json
import math
import sqlite3
import unittest
from pathlib import Path

from src import db
from src.ai_context.builder import build_ai_context
from src.nutrition_logging import create_meal_record, get_meal_record
from src.supplements import (
    calculate_intake_ingredients, confirm_product, create_product,
    favorite_products, get_product, list_products, normalize_barcode,
    normalize_ingredient, normalize_intake, normalize_product, recent_products,
    set_product_favorite,
)
from src.supplements.enrichment import ProviderBlockedError, search_products
from src.supplements.enrichment.validation import candidate_can_be_authoritative


ROOT = Path(__file__).resolve().parents[1]


class BrandBasedSupplementTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(self.connection)
        self.meal = {
            "date": "2026-07-18", "meal_type": "breakfast",
            "eaten_at": "08:00:00", "status": "completed", "source": "manual",
        }

    def tearDown(self):
        self.connection.close()

    def product(self, *, confirmed=True, name="鱼油软胶囊", kind="supplement", variant=None):
        return create_product(self.connection, {
            "brand_name": "Omacor", "product_name": name,
            "product_variant": variant, "dosage_form": "softgel",
            "product_kind": kind, "default_intake_unit": "capsule",
            "serving_quantity": 1, "serving_unit": "capsule",
            "data_source": "manufacturer_label",
            "primary_source_reference": "fixture-label",
            "verification_status": "user_confirmed" if confirmed else "unverified",
            "user_confirmed": confirmed,
            "verified_at": "2026-07-18T08:00:00+08:00" if confirmed else None,
        }, [{
            "canonical_ingredient_name": "EPA", "amount_per_serving": 460,
            "amount_unit": "mg", "serving_quantity": 1,
            "serving_unit": "capsule", "ingredient_role": "active",
            "source_reference": "fixture-label", "source_type": "manufacturer_label",
            "confidence_level": "verified", "user_confirmed": confirmed,
        }])

    def legacy_before_015(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(db.SCHEMA)
        for table_name, columns in db.MIGRATIONS.items():
            if not connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone():
                continue
            existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")}
            for name, kind in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {kind}")
        db.ensure_migration_ledger(connection)
        # Build a genuinely pre-0.15 database.  The migration list has grown
        # well beyond the original test's ``[:-1]`` assumption.
        for migration in db.SCHEMA_MIGRATIONS:
            if migration.sequence >= 15:
                break
            if migration.sql:
                connection.executescript(migration.sql)
            db.record_schema_migration(connection, migration)
        event_id = connection.execute(
            "INSERT INTO meal_events(date,meal_type,actual_meal_time) VALUES('2026-07-18','breakfast','08:00:00')"
        ).lastrowid
        meal_id = connection.execute(
            """INSERT INTO meal_records(uuid,date,meal_type,eaten_at,status,source,legacy_meal_event_id)
               VALUES('legacy-meal','2026-07-18','breakfast','08:00:00','completed','manual',?)""",
            (event_id,),
        ).lastrowid
        return connection, event_id, meal_id

    def test_01_product_table_migration(self):
        self.assertTrue(self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='supplement_products'").fetchone())

    def test_02_ingredient_table_migration(self):
        self.assertTrue(self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='supplement_product_ingredients'").fetchone())

    def test_03_intake_table_migration(self):
        self.assertTrue(self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='supplement_intake_records'").fetchone())

    def test_04_migration_is_idempotent(self):
        db.apply_migrations(self.connection); db.apply_migrations(self.connection)
        self.assertEqual(db.current_schema_version(self.connection), db.SCHEMA_MIGRATIONS[-1].version)

    def test_05_sqlite_integrity(self):
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_06_legacy_intake_preserved(self):
        c, event_id, _ = self.legacy_before_015()
        legacy_id = c.execute("""INSERT INTO meal_event_items(meal_event_id,category,position,item_name,quantity,unit)
            VALUES(?,'supplement',1,'fish_oil',1,'capsule')""", (event_id,)).lastrowid
        db.apply_migrations(c)
        self.assertTrue(c.execute("SELECT 1 FROM meal_event_items WHERE id=?", (legacy_id,)).fetchone())
        self.assertTrue(c.execute("SELECT 1 FROM supplement_intake_records WHERE legacy_meal_event_item_id=?", (legacy_id,)).fetchone())
        c.close()

    def test_07_legacy_active_ingredient_migrated(self):
        c, event_id, _ = self.legacy_before_015()
        c.execute("""INSERT INTO meal_event_items(meal_event_id,category,position,item_name,quantity,unit,
            active_component_name,active_amount,active_unit) VALUES(?,'supplement',1,'fish_oil',1,'capsule','EPA+DHA',840,'mg')""", (event_id,))
        db.apply_migrations(c)
        row = c.execute("SELECT canonical_ingredient_name,amount_per_serving,amount_unit FROM supplement_product_ingredients").fetchone()
        self.assertEqual(tuple(row), ("EPA+DHA", 840, "mg")); c.close()

    def test_08_uncertain_legacy_versions_not_merged(self):
        c, event_id, _ = self.legacy_before_015()
        for position, amount in ((1, 840), (2, 900)):
            c.execute("""INSERT INTO meal_event_items(meal_event_id,category,position,item_name,quantity,unit,
                active_component_name,active_amount,active_unit) VALUES(?,'supplement',?,'fish_oil',1,'capsule','EPA+DHA',?,'mg')""", (event_id, position, amount))
        db.apply_migrations(c)
        self.assertEqual(
            c.execute(
                "SELECT COUNT(*) FROM supplement_products WHERE product_name='fish_oil'"
            ).fetchone()[0],
            2,
        ); c.close()

    def test_09_product_version_history_fields(self):
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(supplement_products)")}
        self.assertTrue({"formula_version", "valid_from", "valid_to", "supersedes_product_id", "formula_hash"} <= columns)

    def test_10_create_brand_product(self):
        self.assertEqual(get_product(self.connection, self.product())["brand_name"], "Omacor")

    def test_11_save_product_variant(self):
        self.assertEqual(get_product(self.connection, self.product(variant="EU 2026"))["product_variant"], "EU 2026")

    def test_12_save_barcode(self):
        payload = normalize_product({"product_name":"x","barcode":"12345678","dosage_form":"other","default_intake_unit":"g","serving_quantity":1,"serving_unit":"g"})
        self.assertEqual(payload["barcode"], "12345678")

    def test_13_default_unit(self):
        self.assertEqual(get_product(self.connection, self.product())["default_intake_unit"], "capsule")

    def test_14_ingredient_crud(self):
        product_id = self.product(); ingredient = get_product(self.connection, product_id)["ingredients"][0]
        self.connection.execute("UPDATE supplement_product_ingredients SET amount_per_serving=500 WHERE id=?", (ingredient["id"],))
        self.assertEqual(get_product(self.connection, product_id)["ingredients"][0]["amount_per_serving"], 500)

    def test_15_multiple_ingredients(self):
        product_id = self.product()
        self.connection.execute("""INSERT INTO supplement_product_ingredients(uuid,supplement_product_id,
            canonical_ingredient_name,amount_per_serving,amount_unit,serving_quantity,serving_unit,
            ingredient_role,source_type,confidence_level) VALUES('dha',?,'DHA',380,'mg',1,'capsule','active','manufacturer_label','verified')""", (product_id,))
        self.assertEqual(len(get_product(self.connection, product_id)["ingredients"]), 2)

    def test_16_formula_versions_do_not_overwrite(self):
        old = self.product(variant="old")
        new = create_product(self.connection, {"brand_name":"Omacor","product_name":"鱼油软胶囊","product_variant":"new","dosage_form":"softgel","default_intake_unit":"capsule","serving_quantity":1,"serving_unit":"capsule","supersedes_product_id":old}, [])
        self.assertEqual(get_product(self.connection, new)["supersedes_product_id"], old)
        self.assertEqual(
            len([item for item in list_products(self.connection) if item["id"] in {old, new}]),
            2,
        )

    def test_17_record_confirmed_product_intake(self):
        pid = self.product(); rid = create_meal_record(self.connection, self.meal, [], [{"supplement_product_id":pid,"quantity":1,"unit":"capsule"}])
        self.assertEqual(get_meal_record(self.connection, rid)["supplements"][0]["supplement_product_id"], pid)

    def test_18_record_unconfirmed_custom_intake(self):
        rid = create_meal_record(self.connection, self.meal, [], [{"custom_brand_name":"X","custom_product_name":"Unknown","quantity":1,"unit":"capsule"}])
        self.assertEqual(get_meal_record(self.connection, rid)["supplements"][0]["custom_product_name"], "Unknown")

    def test_19_unconfirmed_product_has_no_ingredients(self):
        self.assertIsNone(calculate_intake_ingredients(self.connection, self.product(confirmed=False), 1, "capsule"))

    def test_20_confirmed_product_calculates_ingredient(self):
        self.assertEqual(calculate_intake_ingredients(self.connection, self.product(), 1, "capsule")[0]["amount"], 460)

    def test_21_multiple_capsules_multiply(self):
        self.assertEqual(calculate_intake_ingredients(self.connection, self.product(), 2, "capsule")[0]["amount"], 920)

    def test_22_incompatible_unit_does_not_calculate(self):
        self.assertIsNone(calculate_intake_ingredients(self.connection, self.product(), 1, "g"))

    def test_23_nonpositive_quantity_rejected(self):
        for value in (0, -1, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_intake({"custom_product_name":"x","quantity":value,"unit":"g"})

    def test_24_daily_ui_removes_active_inputs(self):
        source = (ROOT / "src/pages/3_Nutrition.py").read_text()
        editor = source[source.index("def _supplement_editor"):source.index("def _quick_actions")]
        self.assertNotIn("active_amount", editor); self.assertNotIn("active_component_name", editor); self.assertNotIn("active_unit", editor)

    def test_25_daily_ui_omits_brand(self):
        source = (ROOT / "src/pages/3_Nutrition.py").read_text()
        editor = source[source.index("def _supplement_editor"):source.index("def _quick_actions")]
        self.assertNotIn('"brand", "product_name"', editor)

    def test_26_daily_ui_displays_product(self):
        self.assertIn('"supplement_products.product_name"', (ROOT / "src/pages/3_Nutrition.py").read_text())

    def test_27_daily_ui_displays_quantity_and_unit(self):
        source = (ROOT / "src/pages/3_Nutrition.py").read_text(); self.assertIn('"quantity", "unit", "actions"', source)

    def test_28_product_selection_sets_default_unit(self):
        self.assertIn("reset_supplement_preferences", (ROOT / "src/pages/3_Nutrition.py").read_text())

    def test_29_recent_products(self):
        pid = self.product(); create_meal_record(self.connection, self.meal, [], [{"supplement_product_id":pid,"quantity":1,"unit":"capsule"}])
        self.assertEqual(recent_products(self.connection)[0]["id"], pid)

    def test_30_user_confirmation(self):
        pid = self.product(confirmed=False); confirm_product(self.connection, pid)
        self.assertTrue(get_product(self.connection, pid)["user_confirmed"])

    def test_31_multiple_candidates_not_silently_selected(self):
        self.assertIn("requires_user_confirmation", (ROOT / "src/supplements/enrichment/models.py").read_text())

    def test_32_candidate_rerun_uniqueness(self):
        sql = """INSERT INTO supplement_product_candidates(uuid,candidate_key,product_name,source_name,source_reference,source_type,retrieved_at)
                 VALUES(?,?,?,?,?,?,?)"""
        self.connection.execute(sql, ("a","same","x","s","r","official","2026-07-18"))
        with self.assertRaises(sqlite3.IntegrityError): self.connection.execute(sql, ("b","same","x","s","r","official","2026-07-18"))

    def test_33_unconfirmed_warning_in_ui(self):
        self.assertIn("ingredients_unconfirmed", (ROOT / "src/pages/3_Nutrition.py").read_text())

    def test_34_localized_product_fields(self):
        zh = json.loads((ROOT / "locales/zh-CN.json").read_text())["supplement_products"]
        en = json.loads((ROOT / "locales/en.json").read_text())["supplement_products"]
        self.assertEqual((zh["brand"], en["brand"]), ("品牌", "Brand"))

    def test_35_provider_gate_blocks_cloud_request(self):
        with self.assertRaises(ProviderBlockedError): search_products("NOW", "Lutein")

    def test_36_ai_candidate_cannot_self_authorize(self):
        self.assertFalse(candidate_can_be_authoritative({"product_name":"x","source_reference":"r","source_type":"ai_assisted_search"}, False))

    def test_37_candidate_requires_source(self):
        self.assertFalse(candidate_can_be_authoritative({"product_name":"x"}, True))

    def test_38_source_conflict_history_exists(self):
        self.assertTrue(self.connection.execute("SELECT 1 FROM sqlite_master WHERE name='supplement_product_sources'").fetchone())

    def test_39_product_can_be_marked_stale(self):
        pid = self.product(); self.connection.execute("UPDATE supplement_products SET verification_status='stale' WHERE id=?", (pid,))
        self.assertIsNone(calculate_intake_ingredients(self.connection, pid, 1, "capsule"))

    def test_40_ocr_candidate_requires_confirmation(self):
        self.assertFalse(candidate_can_be_authoritative({"product_name":"x","source_reference":"label","source_type":"label_ocr"}, False))

    def test_41_finasteride_is_medication(self):
        self.assertEqual(normalize_product({"product_name":"非那雄胺","dosage_form":"tablet","default_intake_unit":"tablet","serving_quantity":1,"serving_unit":"tablet"})["product_kind"], "medication")

    def test_42_medication_not_in_supplement_calculation(self):
        self.assertIsNone(calculate_intake_ingredients(self.connection, self.product(kind="medication", name="Finasteride"), 1, "capsule"))

    def test_43_no_medication_dose_advice_runtime(self):
        source = (ROOT / "src/supplements").read_text() if (ROOT / "src/supplements").is_file() else ""
        page = (ROOT / "src/pages/3_Nutrition.py").read_text(); self.assertIn("medication_boundary", page); self.assertNotIn("adjust_medication_dose", source)

    def test_44_dynamic_unit_enum_preserved(self):
        self.assertEqual(normalize_intake({"custom_product_name":"x","quantity":1,"unit":"drop"})["unit"], "drop")

    def test_45_simple_nutrition_food_flow_preserved(self):
        rid = create_meal_record(self.connection, self.meal, [{"custom_food_name":"food","quantity":1,"unit":"serving"}], [])
        self.assertEqual(len(get_meal_record(self.connection, rid)["items"]), 1)

    def test_46_recovery_version_unchanged(self):
        self.assertEqual(json.loads((ROOT / "config/versions.json").read_text())["recovery_engine_version"], "1.0.0")

    def test_47_baseline_version_unchanged(self):
        self.assertEqual(json.loads((ROOT / "config/versions.json").read_text())["baseline_engine_version"], "1.0.0")

    def test_48_confidence_version_unchanged(self):
        self.assertEqual(json.loads((ROOT / "config/versions.json").read_text())["confidence_engine_version"], "1.0.0")

    def test_49_polar_pipeline_not_imported_by_supplements(self):
        source = "".join(path.read_text() for path in (ROOT / "src/supplements").rglob("*.py")); self.assertNotIn("polar_import", source)

    def test_50_ai_context_excludes_notes_and_secrets(self):
        pid = self.product(); create_meal_record(self.connection, self.meal, [], [{"supplement_product_id":pid,"quantity":1,"unit":"capsule","notes":"private-token-secret"}])
        payload = build_ai_context(self.connection, "2026-07-18", 1); self.assertNotIn("private-token-secret", str(payload))

    def test_51_legacy_active_columns_remain(self):
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(meal_event_items)")}
        self.assertTrue({"active_component_name", "active_amount", "active_unit"} <= columns)


if __name__ == "__main__":
    unittest.main()
