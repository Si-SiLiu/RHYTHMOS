import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import ai_feedback
from src.dashboard_data import get_latest_ai_feedback
from src.db import connect
from tests.test_ai_coach_contract import valid_output


class AIFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "feedback.db"
        connection = connect(self.path)
        connection.execute(
            """INSERT INTO daily_recovery_metrics(
                   date,training_count,training_duration,active_calories
               ) VALUES ('2026-08-23',1,'PT45M',420)"""
        )
        connection.execute(
            """INSERT INTO daily_recovery_metrics(
                   date,sleep_duration,sleep_score,nightly_hrv_rmssd,
                   nightly_resting_hr,respiration_rate,training_count,
                   training_duration,active_calories,kubios_readiness
               ) VALUES ('2026-08-24','PT7H30M',76,48,56,15,1,'PT45M',420,'76')"""
        )
        connection.execute(
            """INSERT INTO recovery_scores(
                   date,recovery_score,activity_load_score,training_load_score,
                   score_version,recommendation
               ) VALUES ('2026-08-24',74,70,71,'1.0.0','moderate_training')"""
        )
        connection.execute(
            """INSERT INTO recovery_confidence(
                   date,data_completeness_score,baseline_maturity_score,
                   confidence_score,confidence_level,group_scores_json,
                   available_groups_json,missing_groups_json,confidence_version
               ) VALUES ('2026-08-24',90,82,86,'high','{}',
                   '[\"sleep\",\"hrv\"]','[\"readiness_support\"]','1.0.0')"""
        )
        connection.execute(
            """INSERT INTO baseline_metrics(
                   date,window_days,valid_days,metric_name,percent_change,
                   robust_z_score,status
               ) VALUES ('2026-08-24',28,24,'nightly_hrv_rmssd',3.2,0.4,'within_baseline')"""
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_context_contains_only_bands_and_deterministic_fields(self):
        connection = connect(self.path)
        try:
            source = ai_feedback.build_feedback_source(connection, "2026-08-24")
        finally:
            connection.close()
        serialized = json.dumps(source, ensure_ascii=False)
        self.assertEqual(source["daily_metrics"]["hrv_band"], "typical")
        self.assertEqual(source["daily_metrics"]["kubios_readiness_label"], "available")
        self.assertEqual(source["daily_metrics"]["local_readiness_status"], "steady")
        self.assertEqual(source["daily_metrics"]["local_readiness_basis"], "sleep_and_recovery")
        self.assertNotIn("48", serialized)
        self.assertNotIn("56", serialized)
        self.assertNotIn("PT7H30M", serialized)
        self.assertNotIn("raw_json", serialized)

    def test_modern_saved_meals_drive_nutrition_bands(self):
        connection = connect(self.path)
        try:
            connection.execute(
                """INSERT INTO meal_records(
                       uuid,date,meal_type,eaten_at,status,source
                   ) VALUES ('meal-1','2026-08-23','breakfast','08:00:00','completed','manual')"""
            )
            connection.commit()
            source = ai_feedback.build_feedback_source(connection, "2026-08-24")
        finally:
            connection.close()
        self.assertEqual(source["nutrition"]["recording_band"], "partial")
        self.assertEqual(source["nutrition"]["coverage_band"], "limited")

    def test_morning_feedback_uses_previous_day_training_context(self):
        connection = connect(self.path)
        try:
            source = ai_feedback.build_feedback_source(connection, "2026-08-24")
        finally:
            connection.close()
        self.assertEqual(source["daily_metrics"]["training_count_band"], "single")
        self.assertEqual(source["daily_metrics"]["training_duration_band"], "moderate")

    def test_generated_output_is_stored_for_the_feedback_page(self):
        output = valid_output()
        output["audit"]["model_version"] = "gpt-5.4"
        output["audit"]["provider_mode"] = "cloud_standard_retention"
        original_connect = ai_feedback.connect
        with mock.patch("src.ai_feedback.connect", side_effect=lambda: original_connect(self.path)), mock.patch(
            "src.ai_feedback.generate_coach_output", return_value=output
        ):
            ai_feedback.generate_feedback_for_date("2026-08-24")
        stored = get_latest_ai_feedback(self.path, analysis_date="2026-08-24")
        self.assertEqual(stored["summary"], output["summary"])
        self.assertEqual(stored["model_version"], "gpt-5.4")
        self.assertEqual(stored["data_retention_mode"], "standard_api_retention")


if __name__ == "__main__":
    unittest.main()
