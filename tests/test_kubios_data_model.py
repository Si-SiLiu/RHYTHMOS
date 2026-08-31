import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from src import db, dashboard_data, report
from src.ai_context.builder import build_ai_context
from src.ai_context.exporter import render_markdown
from src.kubios_metrics import derived, normalizer, selector, trends
from src.kubios_metrics.config import load_metric_config, source_priority
from src.kubios_metrics.storage import RAW_VALUE_FIELDS


class KubiosDataModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def raw(self, day="2026-07-01", source="csv", **values):
        row = {
            "date": day,
            "measurement_time": values.pop("measurement_time", "07:00:00"),
            "source_file_sha256": values.pop("source_file_sha256", f"{source}-{day}"),
            "reviewed": values.pop("reviewed", True),
            **values,
        }
        return normalizer.import_raw(self.connection, row, source, reviewed=row["reviewed"])

    def rebuild(self):
        return normalizer.rebuild(self.connection)

    def audit(self, digest, detected_date="2026-07-01"):
        cursor = self.connection.execute(
            """INSERT INTO kubios_screenshot_imports(
                file_sha256,original_relative_path,import_status,ocr_engine,
                ocr_engine_version,parser_version,detected_date,ocr_text_summary,
                required_fields_found,review_required,reviewed)
                VALUES (?,?,'review_required','fixture','1','1.2.0',?,'',0,1,0)""",
            (digest, f"data/{digest}.png", detected_date),
        )
        self.connection.commit()
        return cursor.lastrowid

    def test_versions_are_v1(self):
        versions = json.loads((db.BASE_DIR / "config/versions.json").read_text())
        self.assertEqual(versions["kubios_data_model_version"], "1.1.0")
        self.assertEqual(versions["database_schema_version"], db.SCHEMA_MIGRATIONS[-1].version)

    def test_migration_creates_three_layers(self):
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"kubios_hrv_measurements_raw", "kubios_hrv_normalized", "kubios_hrv_derived"} <= tables)

    def test_raw_schema_has_every_supported_value(self):
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(kubios_hrv_measurements_raw)")}
        self.assertTrue(set(RAW_VALUE_FIELDS) <= columns)

    def test_full_raw_record_is_saved(self):
        values = {field: 1 for field in RAW_VALUE_FIELDS if field not in {"measurement_quality", "mood_code", "recovery_status"}}
        values.update(measurement_quality="good", mood_code="neutral", recovery_status="low")
        raw_id = self.raw(**values)
        row = self.connection.execute("SELECT * FROM kubios_hrv_measurements_raw WHERE id=?", (raw_id,)).fetchone()
        self.assertEqual(row["measurement_quality"], "good")
        self.assertEqual(row["lf_power_ms2"], 1)

    def test_missing_values_remain_null(self):
        raw_id = self.raw(rmssd_ms=40)
        row = self.connection.execute("SELECT * FROM kubios_hrv_measurements_raw WHERE id=?", (raw_id,)).fetchone()
        self.assertIsNone(row["sdnn_ms"])

    def test_out_of_range_values_become_null(self):
        raw_id = self.raw(mean_hr_bpm=999)
        value = self.connection.execute("SELECT mean_hr_bpm FROM kubios_hrv_measurements_raw WHERE id=?", (raw_id,)).fetchone()[0]
        self.assertIsNone(value)

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):
            self.raw(day="07/01/2026", rmssd_ms=40)

    def test_source_priority_order(self):
        self.assertLess(source_priority("csv"), source_priority("reviewed_screenshot_ocr"))
        self.assertLess(source_priority("reviewed_screenshot_ocr"), source_priority("manual"))

    def test_unreviewed_source_is_not_selected(self):
        self.raw(source="reviewed_screenshot_ocr", reviewed=False, rmssd_ms=40)
        self.assertEqual(self.rebuild()["normalized_records"], 0)

    def test_csv_is_preferred_over_reviewed_screenshot(self):
        self.raw(source="reviewed_screenshot_ocr", source_file_sha256="screen", rmssd_ms=30)
        csv_id = self.raw(source="csv", source_file_sha256="csv", rmssd_ms=50)
        self.rebuild()
        selected = self.connection.execute("SELECT id FROM kubios_hrv_measurements_raw WHERE selected_as_primary=1").fetchone()[0]
        self.assertEqual(selected, csv_id)

    def test_reviewed_screenshot_is_preferred_over_manual(self):
        screen_id = self.raw(source="reviewed_screenshot_ocr", source_file_sha256="screen", rmssd_ms=30)
        self.raw(source="manual", source_file_sha256="manual", rmssd_ms=50)
        self.rebuild()
        selected = self.connection.execute("SELECT id FROM kubios_hrv_measurements_raw WHERE selected_as_primary=1").fetchone()[0]
        self.assertEqual(selected, screen_id)

    def test_explicit_user_selection_is_respected(self):
        self.raw(source="csv", source_file_sha256="csv", rmssd_ms=50)
        manual_id = self.raw(source="manual", source_file_sha256="manual", selected_as_primary=True, rmssd_ms=30)
        self.rebuild()
        selected = self.connection.execute("SELECT id FROM kubios_hrv_measurements_raw WHERE selected_as_primary=1").fetchone()[0]
        self.assertEqual(selected, manual_id)

    def test_latest_time_breaks_equal_priority_tie(self):
        self.raw(source_file_sha256="a", measurement_time="06:00:00", rmssd_ms=30)
        later = self.raw(source_file_sha256="b", measurement_time="07:00:00", rmssd_ms=31)
        self.rebuild()
        self.assertEqual(self.connection.execute("SELECT id FROM kubios_hrv_measurements_raw WHERE selected_as_primary=1").fetchone()[0], later)

    def test_raw_import_is_idempotent(self):
        first = self.raw(rmssd_ms=40)
        second = self.raw(rmssd_ms=41)
        self.assertEqual(first, second)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kubios_hrv_measurements_raw").fetchone()[0], 1)

    def test_normalized_record_is_built(self):
        self.raw(rmssd_ms=40, mean_hr_bpm=60)
        self.rebuild()
        row = self.connection.execute("SELECT * FROM kubios_hrv_normalized").fetchone()
        self.assertEqual((row["rmssd_ms"], row["mean_hr_bpm"]), (40, 60))

    def test_normalized_rebuild_is_idempotent(self):
        self.raw(rmssd_ms=40)
        self.rebuild(); self.rebuild()
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kubios_hrv_normalized").fetchone()[0], 1)

    def test_core_completeness_is_explicit(self):
        self.raw(rmssd_ms=40, mean_hr_bpm=60, readiness_percent=70)
        self.rebuild()
        self.assertEqual(self.connection.execute("SELECT core_data_completeness FROM kubios_hrv_normalized").fetchone()[0], 50)

    def test_group_requires_confirmation(self):
        a, b = self.audit("a"), self.audit("b")
        with self.assertRaises(ValueError):
            selector.create_measurement_group(self.connection, [a, b], "2026-07-01")

    def test_group_requires_two_screenshots(self):
        a = self.audit("a")
        with self.assertRaises(ValueError):
            selector.create_measurement_group(self.connection, [a], "2026-07-01", confirmed_by_user=True)

    def test_group_rejects_date_mismatch(self):
        a, b = self.audit("a"), self.audit("b", "2026-07-02")
        with self.assertRaises(ValueError):
            selector.create_measurement_group(self.connection, [a, b], "2026-07-01", confirmed_by_user=True)

    def test_group_rejects_excessive_time_window(self):
        a, b = self.audit("a"), self.audit("b")
        with self.assertRaises(ValueError):
            selector.create_measurement_group(self.connection, [a, b], "2026-07-01", ["07:00", "07:30"], True)

    def test_confirmed_group_is_persisted(self):
        a, b = self.audit("a"), self.audit("b")
        group_id = selector.create_measurement_group(self.connection, [a, b], "2026-07-01", ["07:00", "07:05"], True)
        row = self.connection.execute("SELECT confirmed_by_user FROM kubios_measurement_groups WHERE id=?", (group_id,)).fetchone()
        self.assertEqual(row[0], 1)

    def test_confirmed_group_merges_complementary_fields(self):
        a, b = self.audit("a"), self.audit("b")
        group_id = selector.create_measurement_group(self.connection, [a, b], "2026-07-01", confirmed_by_user=True)
        self.raw(source="reviewed_screenshot_ocr", source_file_sha256="a", measurement_group_id=group_id, rmssd_ms=40)
        self.raw(source="reviewed_screenshot_ocr", source_file_sha256="b", measurement_group_id=group_id, sdnn_ms=35)
        self.rebuild()
        row = self.connection.execute("SELECT rmssd_ms,sdnn_ms,selection_reason FROM kubios_hrv_normalized").fetchone()
        self.assertEqual((row[0], row[1], row[2]), (40, 35, "confirmed_measurement_group"))

    def test_linear_trend_positive(self):
        self.assertGreater(trends.linear_trend([1, 2, 3]), 0)

    def test_linear_trend_needs_two_points(self):
        self.assertIsNone(trends.linear_trend([None, 1]))

    def test_consecutive_below_baseline(self):
        rows = [{"x": 10}, {"x": 8}, {"x": 7}]
        self.assertEqual(trends.consecutive_direction(rows, "x", 9, "below"), 2)

    def test_consecutive_declines(self):
        self.assertEqual(trends.consecutive_declines([{"x": 4}, {"x": 3}, {"x": 2}], "x"), 2)

    def test_baseline_is_null_when_history_is_insufficient(self):
        self.raw(rmssd_ms=40); self.rebuild()
        self.assertIsNone(derived.derive_for_date(self.connection, "2026-07-01")["rmssd_vs_baseline_percent"])

    def test_derived_baseline_uses_seven_prior_days(self):
        start = date(2026, 6, 1)
        for offset in range(8):
            day = (start + timedelta(days=offset)).isoformat()
            self.raw(day=day, source_file_sha256=day, rmssd_ms=40 + offset)
        self.rebuild()
        row = derived.derive_for_date(self.connection, (start + timedelta(days=7)).isoformat())
        self.assertIsNotNone(row["rmssd_vs_baseline_percent"])

    def test_derived_rebuild_is_idempotent(self):
        self.raw(rmssd_ms=40); self.rebuild()
        derived.rebuild(self.connection); derived.rebuild(self.connection)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM kubios_hrv_derived").fetchone()[0], 1)

    def test_dashboard_core_query_is_read_only(self):
        self.raw(rmssd_ms=40); self.rebuild(); derived.rebuild(self.connection)
        before = self.connection.total_changes
        self.assertEqual(dashboard_data.get_latest_kubios_core(self.path)["rmssd_ms"], 40)
        self.assertEqual(self.connection.total_changes, before)

    def test_dashboard_advanced_query_returns_raw_metrics(self):
        self.raw(rmssd_ms=40, mean_rr_ms=900); self.rebuild(); derived.rebuild(self.connection)
        self.assertEqual(dashboard_data.get_kubios_advanced_metrics(self.path)[0]["mean_rr_ms"], 900)

    def test_dashboard_advanced_query_merges_confirmed_group(self):
        a, b = self.audit("a"), self.audit("b")
        group_id = selector.create_measurement_group(self.connection, [a, b], "2026-07-01", confirmed_by_user=True)
        self.raw(source="reviewed_screenshot_ocr", source_file_sha256="a", measurement_group_id=group_id, rmssd_ms=40)
        self.raw(source="reviewed_screenshot_ocr", source_file_sha256="b", measurement_group_id=group_id, lf_power_ms2=123)
        self.rebuild(); derived.rebuild(self.connection)
        self.assertEqual(dashboard_data.get_kubios_advanced_metrics(self.path)[0]["lf_power_ms2"], 123)

    def test_ai_context_contains_default_core_summary(self):
        self.raw(rmssd_ms=40); self.rebuild(); derived.rebuild(self.connection)
        payload = build_ai_context(self.connection, "2026-07-01")
        self.assertEqual(payload["kubios_summary"]["rmssd_ms"]["value"], 40)

    def test_ai_context_default_excludes_raw_advanced_metrics(self):
        self.raw(rmssd_ms=40, lf_power_ms2=123); self.rebuild()
        serialized = json.dumps(build_ai_context(self.connection, "2026-07-01"))
        self.assertNotIn("lf_power_ms2", serialized)

    def test_ai_advanced_requires_two_confirmations(self):
        with self.assertRaises(ValueError):
            build_ai_context(self.connection, "2026-07-01", include_advanced_kubios=True, advanced_first_confirmation=True)

    def test_ai_advanced_includes_allowlisted_raw_metrics(self):
        self.raw(rmssd_ms=40, lf_power_ms2=123); self.rebuild()
        payload = build_ai_context(
            self.connection, "2026-07-01", include_advanced_kubios=True,
            advanced_first_confirmation=True, advanced_second_confirmation=True,
        )
        self.assertEqual(payload["kubios_summary"]["advanced_metrics"]["lf_power_ms2"]["value"], 123)

    def test_ai_markdown_preview_contains_kubios_summary(self):
        payload = build_ai_context(self.connection, "2026-07-01")
        self.assertIn("## kubios_summary", render_markdown(payload))

    def test_ai_context_never_contains_raw_json_or_group_id(self):
        self.raw(rmssd_ms=40); self.rebuild()
        serialized = json.dumps(build_ai_context(self.connection, "2026-07-01")).lower()
        self.assertNotIn("raw_json", serialized)
        self.assertNotIn("measurement_group_id", serialized)

    def test_report_contains_core_but_not_frequency_metrics(self):
        content = report.render_report({"date": "2026-07-01", "kubios_summary": {"rmssd_ms": 40}})
        self.assertIn("RMSSD", content)
        self.assertNotIn("LF/HF", content)

    def test_locales_have_identical_keys(self):
        def flatten(value, prefix=""):
            result = set()
            if isinstance(value, dict):
                for key, child in value.items(): result |= flatten(child, f"{prefix}.{key}" if prefix else key)
            else: result.add(prefix)
            return result
        en = json.loads((db.BASE_DIR / "locales/en.json").read_text())
        zh = json.loads((db.BASE_DIR / "locales/zh-CN.json").read_text())
        self.assertEqual(flatten(en), flatten(zh))

    def test_home_visibility_is_limited_to_six_core_metrics(self):
        visible = [row["internal_name"] for row in load_metric_config()["metrics"] if row["dashboard_home_visible"]]
        self.assertEqual(len(visible), 6)

    def test_new_metrics_are_not_enabled_in_recovery_formula(self):
        metrics = load_metric_config()["metrics"]
        protected = [row for row in metrics if row["internal_name"] in {"pns_index", "sns_index", "sdnn_ms", "stress_index"}]
        self.assertTrue(all(row["recovery_formula_allowed"] is False for row in protected))

    def test_engine_versions_are_unchanged(self):
        versions = json.loads((db.BASE_DIR / "config/versions.json").read_text())
        self.assertEqual(versions["recovery_engine_version"], "1.0.0")
        self.assertEqual(versions["confidence_engine_version"], "1.0.0")
        self.assertEqual(versions["local_coach_engine_version"], "1.0.0")

    def test_modules_have_no_network_dependency(self):
        for path in (db.BASE_DIR / "src/kubios_metrics").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("import requests", source)
            self.assertNotIn("import httpx", source)

    def test_database_integrity_is_ok(self):
        self.assertEqual(db.integrity_check(self.connection), "ok")


if __name__ == "__main__":
    unittest.main()
