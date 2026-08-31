import unittest

from src.recovery_metrics_table import recovery_metrics_table_row


class RecoveryMetricsTableTests(unittest.TestCase):
    def test_row_has_the_complete_shared_metric_set(self):
        row = recovery_metrics_table_row(
            "2026-08-30",
            {"morning_rmssd": 35, "mean_rr_ms": 900, "measurement_quality": "GOOD"},
            tr=lambda key: key,
            language="en",
            format_date=lambda value, language: value,
            ui=lambda zh, en: en,
        )
        self.assertEqual(len(row), 18)
        self.assertIn("kubios_metrics.sdnn.name (ms)", row)
        self.assertEqual(row["domain.recovery.measurement_quality"], "domain.recovery.quality_good")


if __name__ == "__main__":
    unittest.main()
