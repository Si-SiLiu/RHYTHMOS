import json
import unittest
from dataclasses import replace

from src.local_coach.config import LocalCoachConfigError, load_rules, validate_output
from src.local_coach.engine import generate_recommendation
from src.local_coach.models import CoachInput


class LocalCoachEngineTests(unittest.TestCase):
    def data(self, score=85, level="high", completeness=90, **kwargs):
        return CoachInput(date="2026-07-12", recovery_score=score,
                          confidence_level=level, data_completeness=completeness, **kwargs)

    def test_config_is_versioned_and_not_clinically_validated(self):
        rules = load_rules()
        self.assertEqual(rules["rule_config_version"], "1.0.0")
        self.assertFalse(rules["clinically_validated"])

    def test_high_recovery_keeps_both_sessions_normal(self):
        result = generate_recommendation(self.data())
        self.assertEqual(result["morning_training"]["status"], "normal")
        self.assertEqual(result["evening_training"]["status"], "normal")

    def test_medium_and_low_recovery_reduce_training(self):
        medium = generate_recommendation(self.data(score=65))
        low = generate_recommendation(self.data(score=45))
        self.assertEqual(medium["evening_training"]["status"], "moderate_reduction")
        self.assertEqual(low["morning_training"]["status"], "major_reduction")

    def test_very_low_recovery_rests_morning(self):
        result = generate_recommendation(self.data(score=20))
        self.assertEqual(result["morning_training"]["status"], "rest")

    def test_high_load_alone_does_not_force_rest(self):
        result = generate_recommendation(self.data(stress_load_score=95))
        self.assertEqual(result["morning_training"]["status"], "normal")
        self.assertIn("训练负荷偏高", result["training_summary"]["advice"])

    def test_sleep_and_neural_pressure_are_combined(self):
        result = generate_recommendation(self.data(
            sleep_duration_hours=5.0,
            neural_available=True,
            neural_mental_fatigue=8,
        ))
        self.assertEqual(result["morning_training"]["status"], "major_reduction")
        self.assertEqual(result["evening_training"]["status"], "technique_only")
        self.assertEqual(result["training_summary"]["status"], "adjusted")
        self.assertEqual(len(result["training_summary"]["drivers"]), 2)

    def test_nutrition_shortfall_changes_summary_and_fueling_direction(self):
        result = generate_recommendation(self.data(
            nutrition_logged_meals=3,
            nutrition_data_completeness=100,
            nutrition_protein_g=10,
            nutrition_targets={"protein_g": (80, None)},
        ))
        self.assertEqual(result["morning_training"]["status"], "normal")
        self.assertEqual(result["training_summary"]["status"], "adjusted")
        self.assertIn("营养", result["training_summary"]["advice"])

    def test_low_confidence_and_completeness_fail_conservative(self):
        result = generate_recommendation(self.data(level="very_low", completeness=20))
        self.assertEqual(result["morning_training"]["status"], "technique_only")
        self.assertTrue(result["data_limitations"])

    def test_missing_recovery_has_no_adjustment_conclusion(self):
        result = generate_recommendation(self.data(score=None, level=None, completeness=None))
        self.assertIsNone(result["morning_training"]["intensity_adjustment_percent"])
        self.assertEqual(result["recovery_advice"]["status"], "insufficient_data")

    def test_sleep_low_prioritizes_earlier_bedtime(self):
        result = generate_recommendation(self.data(sleep_duration_hours=5.5))
        self.assertEqual(result["sleep_advice"]["tonight_sleep_target_direction"], "earlier_bedtime")

    def test_hydration_and_nutrition_are_directional(self):
        result = generate_recommendation(self.data(stress_load_score=90, previous_training_duration_minutes=90))
        serialized = json.dumps(result, ensure_ascii=False).lower()
        self.assertEqual(result["hydration_advice"]["status"], "consider_electrolytes")
        for forbidden in ("克", "升水", "毫克钠", "mg sodium"):
            self.assertNotIn(forbidden, serialized)

    def test_explicit_urgent_symptom_stops_training(self):
        result = generate_recommendation(self.data(), symptoms=["出现胸痛"])
        self.assertEqual(result["morning_training"]["status"], "rest")
        self.assertEqual(result["evening_training"]["status"], "rest")

    def test_output_is_schema_valid_and_cloud_false(self):
        result = generate_recommendation(self.data())
        self.assertEqual(validate_output(result), result)
        self.assertTrue(result["generated_without_cloud_ai"])

    def test_explanation_never_copies_raw_values(self):
        explanation = {"positive": [{"label": "Nightly HRV", "status": "above_baseline",
                                      "current_value": 42.123, "message": "secret raw 42.123"}]}
        result = generate_recommendation(self.data(explanation_json=explanation))
        self.assertNotIn("42.123", json.dumps(result["rationale"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
