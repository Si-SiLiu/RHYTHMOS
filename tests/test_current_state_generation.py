import tempfile
import unittest
from pathlib import Path

from scripts import update_project_state


class CurrentStateGenerationTests(unittest.TestCase):
    def make_state(self):
        return {
            "app_version": "0.10.0",
            "current_phase": "Governance Finalization & Release Readiness",
            "phase_status": "completed",
            "recovery_engine_version": "1.0.0",
            "baseline_engine_version": "1.0.0",
            "confidence_engine_version": "1.0.0",
            "local_coach_engine_version": "1.0.0",
            "personal_logging_version": "1.0.0",
            "nutrition_logging_engine_version": "1.0.0",
            "food_catalog_version": "1.1.0",
            "training_logging_version": "1.0.0",
            "exercise_catalog_version": "1.0.0",
            "training_entry_ui_version": "1.0.0",
            "training_entry_default_mode": "simple",
            "conditional_training_fields_ready": True,
            "rpe_rir_preference_supported": True,
            "simplified_training_entry_ready": True,
            "supplement_unit_system_version": "1.0.0",
            "supplement_catalog_version": "1.0.0",
            "supplement_product_enrichment_version": "1.0.0",
            "brand_based_supplement_logging_ready": True,
            "supplement_product_count": 0,
            "verified_supplement_product_count": 0,
            "unverified_supplement_product_count": 0,
            "supplement_ingredient_count": 0,
            "latest_supplement_product_update": None,
            "supplement_enrichment_runtime_status": "provider_blocked",
            "supplement_dynamic_units_ready": True,
            "supplement_catalog_count": 10,
            "simple_nutrition_input_ready": True,
            "food_catalog_count": 18,
            "meal_record_count": 0,
            "meal_item_count": 0,
            "meal_template_count": 0,
            "structured_training_ready": True,
            "training_session_count": 42,
            "training_exercise_count": 0,
            "training_set_count": 0,
            "latest_training_detail_date": None,
            "latest_meal_date": None,
            "manual_logging_engine_version": "1.0.0",
            "data_resolution_version": "1.0.0",
            "scheduler_version": "1.0.0",
            "scheduled_sync_enabled": True,
            "scheduled_sync_time": "06:00",
            "launch_agent_installed": False,
            "latest_scheduled_sync_at": None,
            "latest_scheduled_sync_success": None,
            "manual_activity_count": 0,
            "manual_sleep_count": 0,
            "manual_recovery_count": 0,
            "resolved_field_count": 0,
            "manual_logging_ready": True,
            "data_resolution_ready": True,
            "ai_context_export_version": "1.0.0",
            "i18n_engine_version": "1.0.0",
            "kubios_screenshot_import_version": "1.0.0",
            "kubios_data_model_version": "1.0.0",
            "supported_languages": ["zh-CN", "zh-TW", "en"],
            "default_language": "zh-CN",
            "current_language": "zh-CN",
            "translation_key_count": 320,
            "translation_coverage": "100%",
            "language_setting_ready": True,
            "kubios_screenshot_count": 0,
            "kubios_screenshot_imported_count": 0,
            "kubios_screenshot_review_pending_count": 0,
            "latest_kubios_screenshot_import_date": None,
            "local_ocr_ready": True,
            "real_kubios_screenshot_verified": False,
            "kubios_raw_measurement_count": 0,
            "kubios_normalized_count": 0,
            "kubios_derived_count": 0,
            "latest_kubios_measurement_date": None,
            "kubios_core_metrics_ready": True,
            "kubios_advanced_metrics_ready": True,
            "database_schema_version": "0.1.0",
            "schema_migration_count": 2,
            "latest_schema_migration": "0.1.0",
            "dashboard_version": "0.2.0",
            "test_total": 12,
            "test_passed": 12,
            "test_failed": 0,
            "test_success": True,
            "baseline_record_count": 30,
            "scored_day_count": 20,
            "recovery_v1_day_count": 10,
            "confidence_record_count": 20,
            "local_coach_record_count": 20,
            "latest_local_coach_date": "2026-07-08",
            "local_coach_ready": True,
            "cloud_ai_runtime_ready": False,
            "body_measurement_count": 0,
            "nutrition_log_count": 0,
            "workout_session_count": 0,
            "exercise_set_count": 0,
            "ai_context_export_count": 0,
            "latest_body_measurement_date": None,
            "latest_nutrition_log_date": None,
            "latest_manual_workout_date": None,
            "manual_chatgpt_sync_ready": True,
            "automatic_cloud_sync_ready": False,
            "prospective_evaluation_eligible_days": 0,
            "prospective_evaluation_target_days": 14,
            "prospective_evaluation_remaining_days": 14,
            "prospective_evaluation_status": "collecting",
            "prospective_evaluation_ready": False,
            "daily_collection_status": "awaiting_today",
            "daily_collection_on_track": True,
            "today_collection_completed": False,
            "current_collection_streak_days": 0,
            "overdue_collection_days": 0,
            "latest_source_data_date": "2026-07-08",
            "source_data_lag_days": 4,
            "database_aligned_with_source": True,
            "today_source_data_available": False,
            "prospective_collection_blocker": "source_data_not_available_for_today",
            "latest_data_date": "2026-07-08",
            "next_goal": "One-Click Sync Pipeline",
            "updated_at": "2026-07-10T12:00:00+08:00",
            "prioritized_issues": [
                {
                    "priority": "P2",
                    "description": "Example issue",
                    "status": "planned",
                    "owner": "Codex",
                    "target_phase": "Next",
                }
            ],
        }

    def test_replaces_auto_region_and_preserves_manual_regions(self):
        source = "# State\n\nmanual before\n\n<!-- AUTO_STATE_START -->\nold\n<!-- AUTO_STATE_END -->\n\nmanual after\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CURRENT_STATE.md"
            path.write_text(source, encoding="utf-8")
            update_project_state.sync_current_state(self.make_state(), path)
            result = path.read_text(encoding="utf-8")
            parsed = update_project_state.parse_current_state(path)

        self.assertIn("manual before", result)
        self.assertIn("manual after", result)
        self.assertNotIn("\nold\n", result)
        self.assertEqual(result.count(update_project_state.AUTO_STATE_START), 1)
        self.assertEqual(result.count(update_project_state.AUTO_STATE_END), 1)
        self.assertEqual(parsed["app_version"], self.make_state()["app_version"])
        self.assertTrue(parsed["test_success"])

    def test_repeated_sync_is_byte_identical(self):
        source = "manual\n<!-- AUTO_STATE_START -->\nold\n<!-- AUTO_STATE_END -->\ntail\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CURRENT_STATE.md"
            path.write_text(source, encoding="utf-8")
            update_project_state.sync_current_state(self.make_state(), path)
            first = path.read_bytes()
            update_project_state.sync_current_state(self.make_state(), path)
            self.assertEqual(path.read_bytes(), first)

    def test_missing_or_duplicate_markers_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "CURRENT_STATE.md"
            path.write_text("manual only\n", encoding="utf-8")
            with self.assertRaises(update_project_state.ProjectStateError):
                update_project_state.sync_current_state(self.make_state(), path)

            path.write_text(
                "<!-- AUTO_STATE_START -->\n<!-- AUTO_STATE_START -->\n<!-- AUTO_STATE_END -->\n",
                encoding="utf-8",
            )
            with self.assertRaises(update_project_state.ProjectStateError):
                update_project_state.sync_current_state(self.make_state(), path)

    def test_updated_at_is_preserved_only_when_facts_are_unchanged(self):
        previous = self.make_state()
        current = dict(previous, updated_at="2026-07-10T13:00:00+08:00")
        update_project_state.preserve_updated_at_when_unchanged(current, previous)
        self.assertEqual(current["updated_at"], previous["updated_at"])

        changed = dict(current, test_total=13, updated_at="2026-07-10T14:00:00+08:00")
        update_project_state.preserve_updated_at_when_unchanged(changed, previous)
        self.assertEqual(changed["updated_at"], "2026-07-10T14:00:00+08:00")


if __name__ == "__main__":
    unittest.main()
