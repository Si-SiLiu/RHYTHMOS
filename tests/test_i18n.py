import csv
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import db, report
from src.ai_context.builder import build_ai_context
from src.ai_context.exporter import render_csv, render_markdown
from src.branding import brand_icon_path, load_page_icon
from src.i18n import (
    DEFAULT_LANGUAGE, format_date, format_duration, get_translator,
    load_language_preference, normalize_language, save_language_preference,
)
from src.i18n.storage import load_preferences
from src.i18n.traditional import traditionalize
from src.i18n.translator import Translator
from src.i18n.validation import TranslationValidationError, flatten_keys, validate_matching_keys
from src.personal_logging.config import MEAL_TYPES, SESSION_TYPES
from scripts.check_i18n_coverage import scan


BASE_DIR = Path(__file__).resolve().parents[1]


class InternationalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.zh = json.loads((BASE_DIR / "locales" / "zh-CN.json").read_text(encoding="utf-8"))
        cls.zh_tw = json.loads((BASE_DIR / "locales" / "zh-TW.json").read_text(encoding="utf-8"))
        cls.en = json.loads((BASE_DIR / "locales" / "en.json").read_text(encoding="utf-8"))

    def make_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        return connection

    def sample_report(self):
        return {"date": "2026-07-15", "recovery_score": 86, "score_version": "v1.0",
                "recommendation": "normal_training", "steps": 5000, "calories": 2000,
                "active_calories": 500, "activity_duration": "PT1H", "training_count": 1,
                "training_duration": "PT45M", "training_calories": 300,
                "sleep_duration": "PT8H", "sleep_score": 82,
                "confidence_score": 88, "confidence_level": "high",
                "data_completeness_score": 90}

    def test_zh_resource_loads(self):
        self.assertEqual(Translator("zh-CN")("common.no_data"), "暂无数据")

    def test_zh_tw_resource_loads(self):
        self.assertEqual(Translator("zh-TW")("common.no_data"), "暫無資料")

    def test_traditionalize_converts_page_local_copy_only_for_zh_tw(self):
        self.assertEqual(traditionalize("历史训练建议：28分钟"), "歷史訓練建議：28分鐘")
        self.assertEqual(traditionalize("干扰抑制"), "干擾抑制")

    def test_en_resource_loads(self):
        self.assertEqual(Translator("en")("common.no_data"), "No data")

    def test_resource_keys_match(self):
        self.assertGreater(len(validate_matching_keys({"zh-CN": self.zh, "zh-TW": self.zh_tw, "en": self.en})), 300)

    def test_nested_resources_contain_strings_only(self):
        self.assertEqual(flatten_keys(self.zh), flatten_keys(self.zh_tw))
        self.assertEqual(flatten_keys(self.zh), flatten_keys(self.en))

    def test_key_mismatch_is_rejected(self):
        with self.assertRaises(TranslationValidationError):
            validate_matching_keys({"a": {"x": "x"}, "b": {"y": "y"}})

    def test_missing_key_falls_back_to_default_language(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zh-CN.json").write_text('{"only": "中文"}', encoding="utf-8")
            (root / "en.json").write_text("{}", encoding="utf-8")
            self.assertEqual(Translator("en", root)("only"), "中文")

    def test_missing_key_has_safe_marker(self):
        self.assertEqual(get_translator("en")("not.present"), "[missing: not.present]")

    def test_placeholder_formatting(self):
        self.assertEqual(get_translator("en")("common.days", count=3), "3 days")

    def test_placeholder_error_is_safe(self):
        self.assertEqual(get_translator("en")("common.days"), "{count} days")
        self.assertEqual(get_translator("en")("common.days", wrong=3), "[format-error: common.days]")

    def test_locale_aliases(self):
        self.assertEqual(normalize_language("zh"), "zh-CN")
        self.assertEqual(normalize_language("zh-Hant"), "zh-TW")
        self.assertEqual(normalize_language("zh_tw"), "zh-TW")
        self.assertEqual(normalize_language("en-US"), "en")

    def test_unsupported_locale_uses_default(self):
        self.assertEqual(normalize_language("ja"), DEFAULT_LANGUAGE)

    def test_preference_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            self.assertEqual(save_language_preference("en", path), "en")
            self.assertEqual(load_language_preference(path), "en")

    def test_preference_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            save_language_preference("en", path); first = path.read_bytes()
            save_language_preference("en", path)
            self.assertEqual(path.read_bytes(), first)

    def test_missing_preference_defaults_to_chinese(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_language_preference(Path(directory) / "missing.json"), "zh-CN")

    def test_corrupt_preference_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"; path.write_text("{bad", encoding="utf-8")
            self.assertEqual(load_preferences(path), {"language": "zh-CN"})

    def test_preference_contains_no_health_or_identity_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"; save_language_preference("en", path)
            self.assertEqual(set(json.loads(path.read_text())), {"language"})

    def test_chinese_date_format(self):
        self.assertEqual(format_date("2026-07-15", "zh-CN"), "2026年7月15日")
        self.assertEqual(format_date("2026-07-15", "zh-TW"), "2026年7月15日")

    def test_english_date_format(self):
        self.assertEqual(format_date("2026-07-15", "en"), "July 15, 2026")

    def test_missing_date_format(self):
        self.assertEqual(format_date(None, "en"), "No data")

    def test_duration_format_in_both_languages(self):
        self.assertEqual(format_duration(95, "zh-CN"), "1 小时 35 分钟")
        self.assertEqual(format_duration(95, "zh-TW"), "1 小時 35 分鐘")
        self.assertEqual(format_duration(95, "en"), "1 h 35 min")

    def test_navigation_is_localized(self):
        self.assertEqual(get_translator("zh-CN")("navigation.exercise"), "训练")
        self.assertEqual(get_translator("zh-CN")("navigation.personal"), "我的")
        self.assertEqual(get_translator("en")("navigation.system"), "System Information")

    def test_streamlit_navigation_paths_are_entrypoint_relative(self):
        source = (BASE_DIR / "src" / "i18n" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('"dashboard.py"', source)
        self.assertIn('"pages/1_Sleep.py"', source)
        self.assertIn('"pages/2_Recovery.py"', source)
        self.assertIn('"pages/3_Nutrition.py"', source)
        self.assertIn('"pages/7_Overall_Feedback.py"', source)
        self.assertIn('"pages/5_Personal.py"', source)
        self.assertIn('"pages/4_System.py"', source)
        self.assertNotIn('"src/dashboard.py"', source)

    def test_chart_titles_are_localized(self):
        self.assertEqual(get_translator("zh-CN")("dashboard.chart_sleep"), "睡眠评分")
        self.assertEqual(get_translator("en")("dashboard.chart_sleep"), "Sleep Score")

    def test_recovery_and_confidence_are_distinct(self):
        tr = get_translator("en")
        self.assertNotEqual(tr("metrics.recovery_score"), tr("confidence.score"))
        self.assertIn("confidence", tr("recovery.score_confidence_notice").lower())

    def test_confidence_levels_are_localized(self):
        self.assertEqual(get_translator("zh-CN")("confidence.high"), "高可信度")
        self.assertEqual(get_translator("en")("confidence.insufficient"), "Insufficient data")

    def test_local_coach_statuses_are_localized(self):
        self.assertEqual(get_translator("zh-CN")("local_coach.major_reduction"), "明显减量")
        self.assertEqual(get_translator("en")("local_coach.major_reduction"), "Major reduction")

    def test_local_coach_disclaimer_exists_in_both_languages(self):
        self.assertIn("医疗诊断", get_translator("zh-CN")("local_coach.disclaimer"))
        self.assertIn("medical diagnosis", get_translator("en")("local_coach.disclaimer"))

    def test_meal_type_internal_codes_are_unchanged(self):
        self.assertEqual(MEAL_TYPES, ("breakfast", "lunch", "dinner", "snack", "pre_workout", "post_workout", "other"))

    def test_session_type_internal_codes_are_unchanged(self):
        self.assertEqual(SESSION_TYPES, ("strength", "hiphop", "cardio", "mobility", "juggling", "other"))

    def test_personal_logging_labels_are_localized(self):
        self.assertEqual(get_translator("en")("personal_logging.waist"), "Waist (cm, optional)")

    def test_streamlit_pages_have_no_direct_visible_literals(self):
        self.assertFalse(any(scan().values()))

    def test_language_switch_does_not_use_clear_on_submit(self):
        source = (BASE_DIR / "src" / "pages" / "1_Daily_Log.py").read_text(encoding="utf-8")
        self.assertNotIn("clear_on_submit=True", source)
        for stable_key in ("body_notes", "nutrition_food", "strength_exercise", "other_metadata", "ai_custom_question"):
            self.assertIn(f'key="{stable_key}"', source)

    def test_chinese_report(self):
        content = report.render_report(self.sample_report(), "zh-CN")
        self.assertIn("# RHYTHMOS｜律衡 每日状态报告", content)
        self.assertIn("恢复分数：86", content)

    def test_english_report(self):
        content = report.render_report(self.sample_report(), "en")
        self.assertIn("# RHYTHMOS｜律衡 Daily Report", content)
        self.assertIn("Recovery Score: 86", content)

    def test_report_language_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            path = report.save_report("x", "2026-07-15", directory, "en")
            self.assertEqual(path.parent.name, "en")

    def test_ai_context_schema_is_identical_across_languages(self):
        connection = self.make_connection()
        try:
            zh = build_ai_context(connection, "2026-07-15", language="zh-CN")
            en = build_ai_context(connection, "2026-07-15", language="en")
            self.assertEqual(set(zh), set(en))
            self.assertEqual(zh["schema_version"], en["schema_version"])
        finally: connection.close()

    def test_ai_context_localized_summary_and_language(self):
        connection = self.make_connection()
        try:
            payload = build_ai_context(connection, "2026-07-15", language="en")
            self.assertEqual(payload["display_language"], "en")
            self.assertIn("recommendation", payload["localized_summary"])
        finally: connection.close()

    def test_ai_context_markdown_is_localized(self):
        connection = self.make_connection()
        try:
            payload = build_ai_context(connection, "2026-07-15", questions=["Question"], language="zh-CN")
            self.assertIn("用户问题", render_markdown(payload))
        finally: connection.close()

    def test_csv_headers_do_not_change_with_language(self):
        connection = self.make_connection()
        try:
            zh = render_csv(build_ai_context(connection, "2026-07-15", language="zh-CN")).splitlines()[0]
            en = render_csv(build_ai_context(connection, "2026-07-15", language="en")).splitlines()[0]
            self.assertEqual(next(csv.reader(io.StringIO(zh))), next(csv.reader(io.StringIO(en))))
        finally: connection.close()

    def test_language_operations_do_not_modify_database(self):
        connection = self.make_connection()
        before = connection.total_changes
        get_translator("en")("dashboard.latest"); get_translator("zh-CN")("dashboard.latest")
        self.assertEqual(connection.total_changes, before)
        connection.close()

    def test_icon_remains_readable(self):
        self.assertIsNotNone(load_page_icon())
        self.assertTrue(brand_icon_path().is_file())

    def test_i18n_has_no_network_dependency(self):
        for path in (BASE_DIR / "src" / "i18n").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for name in ("requests", "urllib", "httpx", "openai"):
                self.assertNotIn(f"import {name}", source)

    def test_health_engines_do_not_import_i18n(self):
        for relative in ("src/recovery_score.py", "src/baseline.py", "src/recovery_confidence.py", "src/local_coach/engine.py"):
            self.assertNotIn("i18n", (BASE_DIR / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
