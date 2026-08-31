import unittest
from pathlib import Path

from src.recovery_details import build_recovery_details, normalize_measurement_quality


def record(day, rmssd=30, hr=60, stress=10, respiration=16, quality="GOOD"):
    return {"date": day, "morning_rmssd": rmssd, "morning_mean_hr": hr,
            "stress_index": stress, "respiratory_rate": respiration,
            "measurement_quality": quality}


class RecoveryDetailsTests(unittest.TestCase):
    def history(self, count=14, *, respiration=16, quality="GOOD"):
        return [record(f"2026-07-{day:02d}", rmssd=30 + day % 3, hr=60 + day % 2,
                       respiration=respiration, quality=quality)
                for day in range(1, count + 1)]

    def test_none_never_becomes_zero(self):
        result = build_recovery_details(record("2026-07-23", rmssd=None), self.history())
        self.assertIsNone(result["analyses"]["morning_rmssd"]["current_value"])

    def test_zero_respiration_is_invalid_and_excluded(self):
        history = self.history()
        history[0]["respiratory_rate"] = 0
        result = build_recovery_details(record("2026-07-23", respiration=0), history)
        self.assertEqual(result["analyses"]["respiratory_rate"]["valid_days"], len(history) - 1)
        self.assertEqual(result["analyses"]["respiratory_rate"]["explanation"], "missing")

    def test_low_quality_does_not_enter_baseline(self):
        history = self.history()
        history[0]["morning_rmssd"] = 200
        history[0]["measurement_quality"] = "POOR"
        result = build_recovery_details(record("2026-07-23"), history)
        self.assertEqual(result["analyses"]["morning_rmssd"]["valid_days"], len(history) - 1)

    def test_insufficient_baseline_does_not_make_deterministic_state(self):
        result = build_recovery_details(record("2026-07-23"), self.history(6))
        self.assertEqual(result["status"], "building")

    def test_rmssd_and_hr_direction_rules(self):
        history = self.history(14)
        result = build_recovery_details(record("2026-07-23", rmssd=33, hr=59), history)
        self.assertEqual(result["analyses"]["morning_rmssd"]["impact"], "supportive")
        self.assertEqual(result["analyses"]["morning_mean_hr"]["impact"], "supportive")
        result = build_recovery_details(record("2026-07-23", rmssd=20, hr=72), history)
        self.assertEqual(result["analyses"]["morning_rmssd"]["impact"], "negative")
        self.assertEqual(result["analyses"]["morning_mean_hr"]["impact"], "negative")

    def test_respiration_is_bidirectional(self):
        history = self.history(14)
        low = build_recovery_details(record("2026-07-23", respiration=10), history)
        high = build_recovery_details(record("2026-07-23", respiration=25), history)
        self.assertEqual(low["analyses"]["respiratory_rate"]["impact"], "negative")
        self.assertEqual(high["analyses"]["respiratory_rate"]["impact"], "negative")

    def test_conflicting_signals_return_conflict(self):
        result = build_recovery_details(record("2026-07-23", rmssd=33, hr=59, respiration=25), self.history(14))
        self.assertEqual(result["status"], "conflict")

    def test_quality_normalizes_legacy_and_canonical_values(self):
        self.assertEqual(normalize_measurement_quality("GOOD"), "good")
        self.assertEqual(normalize_measurement_quality("acceptable"), "average")
        self.assertEqual(normalize_measurement_quality(None), "missing")

    def test_quality_changes_confidence_and_availability(self):
        result = build_recovery_details(record("2026-07-23", quality="POOR"), self.history(14))
        self.assertEqual(result["status"], "unusable")
        self.assertEqual(result["confidence"], "unavailable")

    def test_details_are_structured_separately_from_raw_records(self):
        result = build_recovery_details(record("2026-07-23"), self.history(14))
        self.assertNotIn("measurement_quality", result["analyses"]["morning_rmssd"])
        self.assertIn("baseline_center", result["analyses"]["morning_rmssd"])
        self.assertLessEqual(len(result["support_factors"]), 3)
        self.assertLessEqual(len(result["watch_factors"]), 3)

    def test_extended_kubios_metrics_get_baseline_cards_without_changing_recovery_signal(self):
        extended = {
            "pns_index": 0.13, "sns_index": -0.07, "physiological_age": 45,
            "mean_rr_ms": 979.38, "sdnn_ms": 38.57, "poincare_sd1_ms": 25.97,
            "poincare_sd2_ms": 47.87, "lf_power_ms2": 837.58,
            "hf_power_ms2": 395.03, "lf_power_nu": 67.94,
            "hf_power_nu": 32.04, "lf_hf_ratio": 2.12,
        }
        history = self.history(14)
        for item in history:
            item.update(extended)
        current = record("2026-07-23")
        current.update(extended)

        result = build_recovery_details(current, history)

        for metric in extended:
            self.assertIn(metric, result["analyses"])
            self.assertEqual(result["analyses"][metric]["impact"], "neutral")
            self.assertIsNotNone(result["analyses"][metric]["baseline_center"])
        self.assertNotIn("pns_index_support", result["support_factors"])

    def test_history_page_has_selectable_record_and_situation_sections(self):
        page = Path(__file__).resolve().parents[1] / "src" / "pages" / "2_Recovery.py"
        source = page.read_text(encoding="utf-8")
        self.assertIn("def _historical_recovery_record_table", source)
        self.assertIn("def _historical_recovery_situation", source)
        self.assertIn("recovery_history_view_", source)
        self.assertIn("recovery_history_selected", source)

    def test_recovery_page_caches_stable_inputs_with_database_revision(self):
        page = Path(__file__).resolve().parents[1] / "src" / "pages" / "2_Recovery.py"
        source = page.read_text(encoding="utf-8")
        self.assertIn("def _recovery_database_revision", source)
        self.assertIn("@st.cache_data(show_spinner=False, max_entries=4)", source)
        self.assertIn("def _load_recovery_page_inputs", source)
        self.assertIn("_load_recovery_page_inputs(\n        _recovery_database_revision()", source)


if __name__ == "__main__":
    unittest.main()
