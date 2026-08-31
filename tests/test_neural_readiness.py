import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import db
from src.neural_readiness import (CALIBRATION_PROTOCOL_VERSION, DAILY_SHORT_PROTOCOL_VERSION,
                                  calculate_pvt_metrics, calculate_work_impact,
                                  get_condition_preferences, get_daily_result, get_work_phase_results,
                                  save_assessment, save_condition_preferences)


def _trials(reaction_time=240, count=12):
    return [
        {
            "trial_index": index + 1,
            "stimulus_time_ms": index * 1000.0,
            "response_time_ms": index * 1000.0 + reaction_time,
            "reaction_time_ms": reaction_time,
        }
        for index in range(count)
    ]


def _payload(assessment_id, assessment_date, reaction_time=240):
    return {
        "id": assessment_id,
        "assessment_date": assessment_date,
        "started_at": f"{assessment_date}T08:00:00+08:00",
        "completed_at": f"{assessment_date}T08:03:00+08:00",
        "timezone": "Asia/Shanghai",
        "mental_fatigue": 3,
        "mental_clarity": 7,
        "task_motivation": 7,
        "physical_heaviness": 2,
        "trials": _trials(reaction_time),
        "valid_for_baseline": True,
        "device_context": {"input_mode": "mouse", "viewport": {"width": 1200}},
    }


class NeuralReadinessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "neural.db"

    def tearDown(self):
        self.directory.cleanup()

    def test_pvt_metrics_classify_false_starts_and_both_lapse_thresholds(self):
        metrics = calculate_pvt_metrics([
            {"stimulus_time_ms": 0, "response_time_ms": 220},
            {"stimulus_time_ms": 1000, "response_time_ms": 1360},
            {"stimulus_time_ms": 2000, "response_time_ms": 2510},
            {"stimulus_time_ms": 3000, "response_time_ms": 3050},
            {"response_time_ms": 4000},
        ])
        self.assertEqual(metrics["trial_count"], 5)
        self.assertEqual(metrics["valid_trial_count"], 3)
        self.assertEqual(metrics["false_start_count"], 2)
        self.assertEqual(metrics["lapse_355_count"], 2)
        self.assertEqual(metrics["lapse_500_count"], 1)
        self.assertAlmostEqual(metrics["mean_response_speed"], (1 / 220 + 1 / 360 + 1 / 510) / 3)

    def test_migration_creates_raw_session_and_daily_projection_tables(self):
        connection = db.connect(self.path)
        try:
            assessment_columns = {row[1] for row in connection.execute("PRAGMA table_info(neural_assessments)")}
            trial_columns = {row[1] for row in connection.execute("PRAGMA table_info(pvt_trials)")}
            daily_columns = {row[1] for row in connection.execute("PRAGMA table_info(daily_neural_features)")}
            self.assertTrue({"id", "protocol_version", "device_context", "valid_for_baseline"} <= assessment_columns)
            self.assertTrue({"assessment_id", "reaction_time_ms", "is_lapse_355", "is_lapse_500"} <= trial_columns)
            self.assertTrue({"mean_response_speed", "baseline_deviations_json", "confidence_level"} <= daily_columns)
            self.assertTrue({"test_mode", "duration_seconds", "baseline_group", "metrics_json"} <= assessment_columns)
            self.assertTrue({"test_mode", "duration_seconds", "fastest_20pct_rt_ms", "slowest_20pct_rt_ms"} <= daily_columns)
            self.assertEqual(db.current_schema_version(connection), db.SCHEMA_MIGRATIONS[-1].version)
        finally:
            connection.close()

    def test_assessment_upsert_keeps_a_single_session_trials_and_daily_projection(self):
        payload = _payload("assessment-a", "2026-01-10", 250)
        first = save_assessment(payload, self.path)
        second = save_assessment(payload, self.path)
        self.assertEqual(first["valid_trial_count"], 12)
        self.assertEqual(second["assessment_id"], "assessment-a")
        connection = sqlite3.connect(self.path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM neural_assessments").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM pvt_trials").fetchone()[0], 12)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM daily_neural_features").fetchone()[0], 1)
        finally:
            connection.close()

    def test_baseline_excludes_today_and_integrates_existing_sleep_hrv_values(self):
        connection = db.connect(self.path)
        try:
            connection.execute(
                """INSERT INTO daily_recovery_metrics(date,sleep_score,nightly_hrv_rmssd,morning_rmssd)
                   VALUES('2026-01-08',82,52.5,48.2)"""
            )
            connection.commit()
        finally:
            connection.close()
        for day, rt in enumerate(range(220, 227), start=1):
            save_assessment(_payload(f"baseline-{day}", f"2026-01-0{day}", rt), self.path)
        result = save_assessment(_payload("today", "2026-01-08", 500), self.path)
        self.assertEqual(result["baseline_sample_count"], 7)
        self.assertEqual(result["baseline_status"], "slower_than_baseline")
        self.assertEqual(result["sleep_score"], 82)
        self.assertEqual(result["confidence_level"], "moderate")
        loaded = get_daily_result("2026-01-08", self.path)
        self.assertEqual(loaded["assessment_id"], "today")
        self.assertIn("median_rt_ms", loaded["baseline_deviations"])

    def test_interrupted_session_is_never_baseline_eligible(self):
        payload = _payload("interrupted", "2026-01-10")
        payload["interrupted"] = True
        result = save_assessment(payload, self.path)
        self.assertFalse(result["valid_for_baseline"])
        self.assertEqual(result["confidence_level"], "unavailable")

    def test_local_component_uses_browser_monotonic_timing_and_one_final_submission(self):
        frontend = (Path(__file__).parents[1] / "src" / "pvt_component_frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("performance.now()", frontend)
        self.assertIn("streamlit:setComponentValue", frontend)
        self.assertIn("document.addEventListener('visibilitychange'", frontend)
        self.assertIn("window.addEventListener('blur'", frontend)
        self.assertIn("开始练习", frontend)
        self.assertIn("正确反馈 ${practiceCorrectCount} / 5", frontend)
        self.assertIn("practiceCorrectCount >= 5", frontend)
        self.assertIn("practice_ready", frontend)
        self.assertIn("跳过练习，开始正式测试", frontend)
        self.assertIn("practice_skipped", frontend)
        page = (Path(__file__).parents[1] / "src" / "pages" / "3_Neural_Readiness.py").read_text(encoding="utf-8")
        self.assertIn("Alertness Probe｜警觉性反应", page)
        self.assertIn('neural_practice_completed_once', page)
        self.assertIn('st.button(_ui("跳过练习，开始警觉性反应"', page)
        self.assertIn("duration = 180 if calibration else 60", page)

    def test_short_and_calibration_protocols_have_separate_baselines(self):
        for day in range(1, 8):
            payload = _payload(f"short-{day}", f"2026-02-0{day}", 220)
            payload.update(test_mode="daily_short", protocol_version=DAILY_SHORT_PROTOCOL_VERSION,
                           baseline_group="daily_short", duration_seconds=60)
            save_assessment(payload, self.path)
        calibration = _payload("calibration", "2026-02-08", 500)
        calibration.update(test_mode="weekly_calibration", protocol_version=CALIBRATION_PROTOCOL_VERSION,
                           baseline_group="weekly_calibration", duration_seconds=180)
        result = save_assessment(calibration, self.path)
        self.assertEqual(result["baseline_sample_count"], 0)
        self.assertEqual(result["test_mode"], "weekly_calibration")

    def test_short_metrics_include_twenty_percent_summaries(self):
        metrics = calculate_pvt_metrics(_trials(200, 10) + _trials(500, 2))
        self.assertIn("fastest_20pct_rt_ms", metrics)
        self.assertIn("slowest_20pct_rt_ms", metrics)
        self.assertEqual(metrics["slowest_20pct_rt_ms"], 400)

    def test_condition_preferences_are_remembered_without_assessment_data(self):
        self.assertTrue(get_condition_preferences(self.path)["quiet"])
        save_condition_preferences({"quiet": False, "dominant": True, "stay": False, "device_ok": True}, self.path)
        self.assertEqual(get_condition_preferences(self.path), {
            "quiet": False, "dominant": True, "stay": False, "device_ok": True,
        })

    def test_work_phase_pair_is_compared_without_double_counting_baseline_days(self):
        before = _payload("before", "2026-03-01", 240)
        before["device_context"]["work_phase"] = "before_work"
        before["mental_fatigue"] = 2
        save_assessment(before, self.path)
        after = _payload("after", "2026-03-01", 300)
        after["device_context"]["work_phase"] = "after_work"
        after["mental_fatigue"] = 6
        after["mental_clarity"] = 4
        save_assessment(after, self.path)
        phases = get_work_phase_results("2026-03-01", self.path)
        impact = calculate_work_impact(phases)
        self.assertEqual(set(phases), {"before_work", "after_work"})
        self.assertEqual(impact["median_rt_delta_ms"], 60)
        self.assertEqual(impact["mental_fatigue_delta"], 4)
        self.assertEqual(impact["level"], "large")


if __name__ == "__main__":
    unittest.main()
