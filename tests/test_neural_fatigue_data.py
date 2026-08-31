import inspect
import unittest
from datetime import datetime, timezone

from src import neural_fatigue_data


NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
BASE = {"observed_at": NOW, "baseline_sample_count": 28, "quality": 0.9}


class NeuralFatigueDataAdapterTests(unittest.TestCase):
    def test_missing_cognitive_fields_return_none(self):
        self.assertIsNone(neural_fatigue_data.adapt_cognitive({**BASE, "completed": True}))
        self.assertIsNone(neural_fatigue_data.adapt_cognitive({**BASE, "median_rt_ms": 500, "baseline_median_rt_ms": 0}))

    def test_cognitive_conversion_uses_personal_baseline_deviation(self):
        component = neural_fatigue_data.adapt_cognitive({
            **BASE, "median_rt_ms": 600, "baseline_median_rt_ms": 500,
            "accuracy": 0.8, "baseline_accuracy": 0.9,
        })
        self.assertEqual(component.score, 75)
        self.assertEqual(component.source, "cognitive_training")

    def test_recovery_sleep_and_training_conversion(self):
        recovery = neural_fatigue_data.adapt_recovery({**BASE, "recovery_score": 70})
        sleep = neural_fatigue_data.adapt_sleep({**BASE, "sleep_score": 80})
        training = neural_fatigue_data.adapt_training({**BASE, "percent_difference": 25})
        self.assertEqual((recovery.score, sleep.score, training.score), (30, 20, 50))
        self.assertEqual(recovery.source, "recovery_scores")
        self.assertEqual(sleep.source, "daily_recovery_metrics.sleep_score")
        self.assertEqual(training.source, "training_baseline")

    def test_invalid_or_insufficient_mapping_returns_none_without_default_burden(self):
        self.assertIsNone(neural_fatigue_data.adapt_recovery({**BASE, "recovery_score": None}))
        self.assertIsNone(neural_fatigue_data.adapt_sleep({**BASE, "sleep_score": "bad"}))
        self.assertIsNone(neural_fatigue_data.adapt_training({**BASE, "percent_difference": None}))
        self.assertIsNone(neural_fatigue_data.adapt_subjective({**BASE, "score": 99}))

    def test_combined_input_and_source_mapping(self):
        inputs = neural_fatigue_data.adapt_inputs(
            cognitive={**BASE, "median_rt_ms": 550, "baseline_median_rt_ms": 500},
            recovery={**BASE, "recovery_score": 75},
            sleep={**BASE, "sleep_score": 90},
            training={**BASE, "percent_difference": 10},
        )
        self.assertEqual(inputs.cognitive.source, "cognitive_training")
        self.assertEqual(inputs.recovery.score, 25)
        self.assertEqual(inputs.sleep.score, 10)
        self.assertEqual(inputs.training.score, 20)

    def test_adapter_has_no_database_or_network_access(self):
        source = inspect.getsource(neural_fatigue_data)
        for forbidden in ("sqlite3", "requests", "urllib", "streamlit", "connect("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
