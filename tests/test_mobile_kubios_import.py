import tempfile
import unittest

from src import db
from src.mobile_kubios_import import (
    MobileKubiosImportError,
    import_mobile_morning_hrv_measurement,
    import_mobile_screenshot_measurement,
)


class MobileKubiosImportTests(unittest.TestCase):
    def valid_payload(self):
        return {
            "date": "2026-09-07", "rmssd": 41.2, "mean_hr": 56,
            "measurement_quality": "GOOD", "image_sha256": "b" * 64,
            "user_confirmed": True,
        }

    def test_reviewed_values_use_screenshot_provenance_and_select_daily_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/recovery.db"
            outcome = import_mobile_screenshot_measurement(
                self.valid_payload(), db_path=path, rebuild_recovery=False,
            )
            with db.connect(path) as connection:
                row = connection.execute(
                    "SELECT rmssd,mean_hr,source_type,import_method,reviewed,is_daily_preferred "
                    "FROM kubios_morning_hrv_raw"
                ).fetchone()
            self.assertEqual(outcome["date"], "2026-09-07")
            self.assertEqual(tuple(row), (41.2, 56.0, "screenshot_ocr", "ios_local_vision", 1, 1))

    def test_reviewed_screenshot_preserves_complete_kubios_result_metrics(self):
        payload = self.valid_payload() | {
            "pns_index": -0.02, "sns_index": 0.41, "physiological_age": 45,
            "mean_rr_ms": 976.26, "sdnn": 30.59,
            "poincare_sd1_ms": 21.69, "poincare_sd2_ms": 37.48,
            "stress_index": 14.03, "respiratory_rate_bpm": 19.44,
            "lf_power_ms2": 437.35, "hf_power_ms2": 316.37,
            "lf_power_nu": 58.02, "hf_power_nu": 41.97, "lf_hf_ratio": 1.38,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/recovery.db"
            import_mobile_screenshot_measurement(payload, db_path=path, rebuild_recovery=False)
            with db.connect(path) as connection:
                row = connection.execute(
                    "SELECT pns_index,sns_index,sdnn_ms,mean_rr_ms,poincare_sd1_ms,"
                    "poincare_sd2_ms,stress_index,respiratory_rate_bpm,lf_power_ms2,"
                    "hf_power_ms2,lf_power_nu,hf_power_nu,lf_hf_ratio,physiological_age,"
                    "measurement_quality FROM kubios_hrv_measurements_raw"
                ).fetchone()
        self.assertEqual(
            tuple(row),
            (-0.02, 0.41, 30.59, 976.26, 21.69, 37.48, 14.03, 19.44,
             437.35, 316.37, 58.02, 41.97, 1.38, 45.0, "good"),
        )

    def test_unconfirmed_value_never_writes_a_recovery_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/recovery.db"
            payload = self.valid_payload()
            payload["user_confirmed"] = False
            with self.assertRaisesRegex(MobileKubiosImportError, "SCREENSHOT_REVIEW_REQUIRED"):
                import_mobile_screenshot_measurement(payload, db_path=path, rebuild_recovery=False)
            with db.connect(path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM kubios_morning_hrv_raw").fetchone()[0]
            self.assertEqual(count, 0)

    def test_reviewed_bluetooth_measurement_preserves_derived_metrics_and_source(self):
        payload = {
            "date": "2026-09-07", "measurement_time": "2026-09-07T07:00:00+08:00",
            "source_type": "ios_bluetooth_hrv", "device_name": "H10",
            "rmssd": 42.5, "mean_hr": 56, "sdnn": 35.2, "mean_rr_ms": 1071,
            "poincare_sd1_ms": 30.1, "poincare_sd2_ms": 39.2,
            "artefact_correction_percent": 1.5, "measurement_duration_seconds": 300,
            "valid_rr_count": 280, "measurement_sha256": "c" * 64,
            "user_confirmed": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/recovery.db"
            outcome = import_mobile_morning_hrv_measurement(
                payload, db_path=path, rebuild_recovery=False,
            )
            with db.connect(path) as connection:
                legacy = connection.execute(
                    "SELECT rmssd,mean_hr,source_type,import_method,reviewed,is_daily_preferred "
                    "FROM kubios_morning_hrv_raw"
                ).fetchone()
                normalized = connection.execute(
                    "SELECT rmssd_ms,mean_hr_bpm,sdnn_ms,measurement_duration_seconds,source_type "
                    "FROM kubios_hrv_measurements_raw"
                ).fetchone()
            self.assertEqual(outcome["date"], "2026-09-07")
            self.assertEqual(tuple(legacy), (42.5, 56.0, "ios_bluetooth_hrv", "ios_bluetooth", 1, 1))
            self.assertEqual(tuple(normalized), (42.5, 56.0, 35.2, 300.0, "ios_bluetooth_hrv"))
