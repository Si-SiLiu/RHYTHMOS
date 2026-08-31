import math
import unittest
from datetime import datetime, timedelta, timezone

from src.neural_fatigue import (
    ALGORITHM_VERSION,
    NeuralFatigueComponent,
    NeuralFatigueInputError,
    NeuralFatigueInputs,
    calculate_neural_fatigue,
)


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


def component(score=50, *, age=0, samples=28, quality=1.0, source="fixture"):
    return NeuralFatigueComponent(
        score=score,
        observed_at=NOW - timedelta(hours=age),
        baseline_sample_count=samples,
        source=source,
        freshness_hours=age,
        quality=quality,
    )


class NeuralFatigueCalculationTests(unittest.TestCase):
    def calculate(self, **components):
        return calculate_neural_fatigue(NeuralFatigueInputs(**components), computed_at=NOW)

    def test_two_valid_components_are_equally_aggregated(self):
        result = self.calculate(cognitive=component(20), training=component(80))
        self.assertEqual(result.status, "available")
        self.assertEqual(result.burden_score, 50)
        self.assertEqual(result.component_weights, {"cognitive": 0.5, "training": 0.5})
        self.assertEqual(result.confidence, 0.4)

    def test_three_components_renormalize_weights(self):
        result = self.calculate(cognitive=component(30), recovery=component(60), training=component(90))
        self.assertEqual(result.burden_score, 60)
        self.assertEqual(sum(result.component_weights.values()), 1.0)
        self.assertEqual(result.component_weights["recovery"], 1 / 3)

    def test_five_components_are_aggregated(self):
        result = self.calculate(**{name: component(index * 20) for index, name in enumerate(("cognitive", "recovery", "sleep", "training", "subjective"))})
        self.assertEqual(result.burden_score, 40)
        self.assertEqual(result.confidence, 1.0)

    def test_missing_component_is_not_zero(self):
        result = self.calculate(cognitive=component(40), recovery=component(80))
        self.assertEqual(result.burden_score, 60)
        self.assertIn("sleep", result.missing_components)

    def test_minimum_data_conditions(self):
        self.assertEqual(self.calculate().status, "insufficient_data")
        self.assertEqual(self.calculate(training=component()).status, "insufficient_data")
        self.assertEqual(self.calculate(cognitive=component()).status, "insufficient_data")
        self.assertEqual(self.calculate(training=component(), subjective=component()).status, "insufficient_data")
        self.assertEqual(self.calculate(cognitive=component(), training=component()).status, "available")
        self.assertEqual(self.calculate(recovery=component(), sleep=component()).status, "available")
        self.assertEqual(self.calculate(sleep=component(), training=component()).status, "available")

    def test_invalid_component_inputs_raise_clear_errors(self):
        cases = (
            {"score": -1}, {"score": 101}, {"score": math.nan}, {"score": math.inf},
            {"score": "not-a-score"}, {"baseline_sample_count": -1},
            {"freshness_hours": -1}, {"quality": -0.1}, {"quality": 1.1},
        )
        for overrides in cases:
            values = dict(score=50, observed_at=NOW, baseline_sample_count=28, source="fixture")
            values.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(NeuralFatigueInputError):
                NeuralFatigueComponent(**values)

    def test_future_and_naive_timestamps_raise(self):
        with self.assertRaises(NeuralFatigueInputError):
            self.calculate(cognitive=NeuralFatigueComponent(50, NOW + timedelta(seconds=1), 28, "fixture"), training=component())
        with self.assertRaises(NeuralFatigueInputError):
            NeuralFatigueComponent(50, datetime(2026, 7, 30, 12), 28, "fixture")

    def test_stale_and_small_baseline_reduce_confidence(self):
        fresh = self.calculate(cognitive=component(), recovery=component())
        stale = self.calculate(cognitive=component(age=100), recovery=component(age=100))
        short = self.calculate(cognitive=component(samples=7), recovery=component(samples=7))
        self.assertLess(stale.confidence, fresh.confidence)
        self.assertLess(short.confidence, fresh.confidence)
        self.assertIn("some_component_data_is_not_recent", stale.cautions)
        self.assertIn("personal_baseline_samples_are_limited", short.cautions)

    def test_hard_stale_component_is_excluded(self):
        result = self.calculate(cognitive=component(age=169), recovery=component(), training=component())
        self.assertEqual(result.available_components, ("recovery", "training"))
        self.assertIn("component_cognitive_stale_excluded", result.reasons)

    def test_more_valid_data_increases_confidence_and_order_is_stable(self):
        two = self.calculate(cognitive=component(), recovery=component())
        three = self.calculate(cognitive=component(), recovery=component(), sleep=component())
        reordered = self.calculate(sleep=component(), recovery=component(), cognitive=component())
        self.assertGreater(three.confidence, two.confidence)
        self.assertEqual(three, reordered)

    def test_result_metadata_and_reason_codes_are_stable(self):
        result = self.calculate(cognitive=component(40), sleep=component(60))
        self.assertEqual(result.algorithm_version, ALGORITHM_VERSION)
        self.assertEqual(result.computed_at, NOW)
        self.assertIn("component_cognitive_available", result.reasons)
        self.assertIn("component_training_missing", result.reasons)
        self.assertIn("confidence_reflects_data_coverage_and_quality", result.cautions)


if __name__ == "__main__":
    unittest.main()
