import json
import tempfile
import unittest
from pathlib import Path

from src import db
from src.domain_dashboard_data import (
    get_domain_baselines,
    get_latest_nutrition,
    get_latest_recovery,
    get_recovery_baselines,
    get_latest_sleep,
    get_sleep_history,
    get_latest_training,
    get_recent_nutrition,
    get_training_history,
)


class DomainDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_training_projection_contains_requested_fields(self):
        raw = {"sport": {"id": "running"}, "hrAvg": 130, "hrMax": 165, "fatPercentage": 32}
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(source,external_id,date,raw_json,sport,start_time,duration,calories)
               VALUES('polar','session','2026-07-01',?,'running','2026-07-01T07:00:00','PT1H',500)""",
            (json.dumps(raw),),
        )
        self.connection.commit()
        result = get_latest_training(self.path)
        self.assertEqual(result["sports"], ["running"])
        self.assertEqual(result["duration_minutes"], 60)
        self.assertEqual(result["average_hr_bpm"], 130)
        self.assertEqual(result["maximum_hr_bpm"], 165)
        self.assertEqual(result["calories"], 500)
        self.assertEqual(result["fat_percentage"], 32)

    def test_training_projection_aggregates_same_day_sessions(self):
        for index in range(2):
            raw = {"hrAvg": 100 + index * 20, "hrMax": 140 + index * 20, "fatPercentage": 30 + index * 10}
            self.connection.execute(
                """INSERT INTO polar_training_sessions_raw(source,external_id,date,raw_json,sport,duration,calories)
                   VALUES('polar',?,'2026-07-01',?,?,'PT30M',200)""",
                (f"s{index}", json.dumps(raw), f"sport{index}"),
            )
        self.connection.commit()
        result = get_latest_training(self.path)
        self.assertEqual(result["duration_minutes"], 60)
        self.assertEqual(result["calories"], 400)
        self.assertEqual(result["maximum_hr_bpm"], 160)

    def test_blank_newer_manual_rows_do_not_hide_latest_observed_training(self):
        self.connection.execute(
            """INSERT INTO polar_training_sessions_raw(source,external_id,date,raw_json,sport,duration)
               VALUES('polar','observed','2026-07-01','{}','running','PT30M')"""
        )
        self.connection.execute(
            "INSERT INTO manual_activity_sessions(date) VALUES('2026-07-02')"
        )
        self.connection.commit()

        result = get_latest_training(self.path)

        self.assertEqual(result["date"], "2026-07-01")
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual([row["date"] for row in get_training_history(self.path)], ["2026-07-01"])

    def test_sleep_projection_preserves_missing_structure(self):
        self.connection.execute(
            """INSERT INTO daily_recovery_metrics(date,sleep_duration,sleep_score,nightly_hrv_rmssd,nightly_resting_hr,respiration_rate)
               VALUES('2026-07-01','PT8H',80,45,55,15)"""
        )
        self.connection.execute(
            "INSERT INTO polar_sleep_raw(source,external_id,date,raw_json) VALUES('polar','sleep','2026-07-01','{}')"
        )
        self.connection.commit()
        result = get_latest_sleep(self.path)
        self.assertEqual(result["total_sleep_duration"], "PT8H")
        self.assertIsNone(result["deep_sleep_duration"])
        self.assertIsNone(result["rem_sleep_duration"])
        self.assertEqual(result["nightly_hrv_rmssd"], 45)

    def test_sleep_projection_reads_future_structured_fields(self):
        raw = {"bedtimeStart": "2026-07-01T23:00:00", "bedtimeEnd": "2026-07-02T07:00:00", "deepSleepDuration": "PT2H", "remSleepDuration": "PT90M", "lowestHeartRate": 48}
        self.connection.execute("INSERT INTO daily_recovery_metrics(date,sleep_duration) VALUES('2026-07-02','PT8H')")
        self.connection.execute(
            "INSERT INTO polar_sleep_raw(source,external_id,date,raw_json) VALUES('polar','sleep','2026-07-02',?)",
            (json.dumps(raw),),
        )
        self.connection.commit()
        result = get_latest_sleep(self.path)
        self.assertEqual(result["deep_sleep_duration"], "PT2H")
        self.assertEqual(result["minimum_sleep_hr_bpm"], 48)

    def test_sleep_projection_reads_v4_details_and_sleep_window_hr(self):
        raw = {
            "sleepResult": {
                "hypnogram": {
                    "sleepStart": "2026-07-01T23:00:00+08:00",
                    "sleepEnd": "2026-07-02T07:00:00+08:00",
                }
            },
            "sleepEvaluation": {
                "sleepSpan": "28800s",
                "asleepDuration": "27000s",
                "phaseDurations": {"deep": "7200s", "rem": "5400s"},
            },
        }
        continuous = {
            "date": "2026-07-02",
            "samples": [
                {"heartRate": 50, "offsetMillis": 60 * 60 * 1000},
                {"heartRate": 60, "offsetMillis": 6 * 60 * 60 * 1000},
                {"heartRate": 90, "offsetMillis": 12 * 60 * 60 * 1000},
            ],
        }
        self.connection.execute(
            "INSERT INTO daily_recovery_metrics(date,sleep_duration) VALUES('2026-07-02','PT7H30M')"
        )
        self.connection.execute(
            "INSERT INTO polar_sleep_raw(source,external_id,date,raw_json) VALUES('polar','sleep','2026-07-02',?)",
            (json.dumps(raw),),
        )
        self.connection.execute(
            "INSERT INTO polar_continuous_hr_raw(source,external_id,date,raw_json) VALUES('polar','hr','2026-07-02',?)",
            (json.dumps(continuous),),
        )
        self.connection.commit()

        result = get_latest_sleep(self.path)

        self.assertEqual(result["total_sleep_duration"], 28800)
        self.assertEqual(result["actual_sleep_duration"], 27000)
        self.assertEqual(result["deep_sleep_duration"], 7200)
        self.assertEqual(result["rem_sleep_duration"], 5400)
        self.assertEqual(result["average_sleep_hr_bpm"], 55)
        self.assertEqual(result["minimum_sleep_hr_bpm"], 50)

        compact = get_latest_sleep(self.path, include_continuous_hr=False)
        self.assertIsNone(compact["average_sleep_hr_bpm"])
        self.assertIsNone(compact["minimum_sleep_hr_bpm"])

    def test_polar_only_sleep_history_uses_continuous_hr_and_never_manual_fill(self):
        raw = {
            "sleepResult": {
                "hypnogram": {
                    "sleepStart": "2026-07-01T23:00:00+08:00",
                    "sleepEnd": "2026-07-02T07:00:00+08:00",
                }
            },
            "sleepEvaluation": {"sleepSpan": "28800s"},
        }
        continuous = {
            "date": "2026-07-02",
            "samples": [
                {"heartRate": 50, "offsetMillis": 60 * 60 * 1000},
                {"heartRate": 60, "offsetMillis": 6 * 60 * 60 * 1000},
            ],
        }
        self.connection.execute(
            "INSERT INTO polar_sleep_raw(source,external_id,date,raw_json) VALUES('polar','sleep','2026-07-02',?)",
            (json.dumps(raw),),
        )
        self.connection.execute(
            "INSERT INTO polar_continuous_hr_raw(source,external_id,date,raw_json) VALUES('polar','hr','2026-07-02',?)",
            (json.dumps(continuous),),
        )
        self.connection.execute(
            """INSERT INTO manual_sleep_logs(
                   sleep_date,average_sleep_hr_bpm,deep_sleep_duration_minutes
               ) VALUES('2026-07-02',54,90)"""
        )
        self.connection.execute(
            "INSERT INTO manual_sleep_logs(sleep_date,average_sleep_hr_bpm) VALUES('2026-07-03',53)"
        )
        self.connection.commit()

        compact = get_sleep_history(
            self.path, include_continuous_hr=False, polar_only=True,
        )[0]
        self.assertEqual(
            [item["date"] for item in get_sleep_history(self.path, polar_only=True)],
            ["2026-07-02"],
        )
        self.assertIsNone(compact["resolved_fields"]["average_sleep_hr_bpm"]["value"])
        self.assertIsNone(compact["resolved_fields"]["deep_sleep_duration_minutes"]["value"])

        record = get_sleep_history(
            self.path, include_continuous_hr=True, polar_only=True,
        )[0]
        average_hr = record["resolved_fields"]["average_sleep_hr_bpm"]
        self.assertEqual(average_hr["value"], 55)
        self.assertEqual(average_hr["value_source"], "polar")
        self.assertIsNone(record["resolved_fields"]["deep_sleep_duration_minutes"]["value"])

    def test_recovery_projection_uses_morning_fields(self):
        self.connection.execute("INSERT INTO daily_recovery_metrics(date,morning_rmssd,morning_mean_hr) VALUES('2026-07-01',42,58)")
        self.connection.commit()
        result = get_latest_recovery(self.path)
        self.assertEqual((result["morning_rmssd"], result["morning_mean_hr"]), (42, 58))

    def test_recovery_baseline_uses_resolved_manual_morning_values(self):
        for day, rmssd, heart_rate in (
            ("2026-07-01", 20, 60),
            ("2026-07-02", 22, 61),
            ("2026-07-03", 24, 62),
            ("2026-07-04", 26, 63),
            ("2026-07-05", 28, 64),
            ("2026-07-06", 30, 65),
            ("2026-07-07", 32, 66),
            ("2026-07-08", 34, 67),
        ):
            self.connection.execute(
                """INSERT INTO manual_recovery_logs(
                       date,morning_rmssd_ms,morning_resting_hr_bpm
                   ) VALUES(?,?,?)""",
                (day, rmssd, heart_rate),
            )
        self.connection.commit()

        result = get_recovery_baselines(self.path, target_date="2026-07-08")

        self.assertEqual(result["morning_rmssd"]["valid_days"], 7)
        self.assertEqual(result["morning_rmssd"]["median_value"], 26)
        self.assertEqual(result["morning_rmssd"]["latest_value"], 34)
        self.assertNotEqual(result["morning_rmssd"]["status"], "insufficient_data")

    def test_recovery_baseline_excludes_target_and_marks_short_history(self):
        for day, rmssd in (("2026-07-01", 20), ("2026-07-02", 22), ("2026-07-03", 100)):
            self.connection.execute(
                "INSERT INTO manual_recovery_logs(date,morning_rmssd_ms) VALUES(?,?)",
                (day, rmssd),
            )
        self.connection.commit()

        result = get_recovery_baselines(self.path, target_date="2026-07-03")["morning_rmssd"]

        self.assertEqual(result["valid_days"], 2)
        self.assertEqual(result["median_value"], 21)
        self.assertEqual(result["latest_value"], 100)
        self.assertEqual(result["status"], "insufficient_data")

    def test_recovery_baseline_keeps_legacy_daily_metric_fallback(self):
        for index in range(8):
            self.connection.execute(
                "INSERT INTO daily_recovery_metrics(date,morning_rmssd) VALUES(?,?)",
                (f"2026-07-{index + 1:02d}", 20 + index),
            )
        self.connection.commit()

        result = get_recovery_baselines(self.path, target_date="2026-07-08")["morning_rmssd"]

        self.assertEqual(result["valid_days"], 7)
        self.assertEqual(result["median_value"], 23)
        self.assertEqual(result["latest_value"], 27)

    def test_recovery_baseline_recalculates_after_history_changes(self):
        record_ids = []
        for index in range(7):
            cursor = self.connection.execute(
                """INSERT INTO manual_recovery_logs(
                       date,morning_rmssd_ms,morning_resting_hr_bpm
                   ) VALUES(?,?,?)""",
                (f"2026-07-{index + 1:02d}", 20 + index, 60 + index),
            )
            record_ids.append(cursor.lastrowid)
        self.connection.commit()

        before = get_recovery_baselines(self.path, target_date="2026-07-07")
        self.connection.execute(
            "UPDATE manual_recovery_logs SET morning_rmssd_ms=40 WHERE id=?",
            (record_ids[0],),
        )
        self.connection.commit()
        after = get_recovery_baselines(self.path, target_date="2026-07-07")

        self.assertNotEqual(
            before["morning_rmssd"]["median_value"],
            after["morning_rmssd"]["median_value"],
        )

    def test_nutrition_projection_and_trend(self):
        self.connection.execute(
            """INSERT INTO daily_nutrition_summary(date,logged_meals,calories,protein_g,data_completeness)
               VALUES('2026-07-01',3,2000,100,75)"""
        )
        self.connection.commit()
        self.assertEqual(get_latest_nutrition(self.path)["logged_meals"], 3)
        self.assertEqual(len(get_recent_nutrition(self.path)), 1)

    def test_domain_baselines_are_selected_by_name(self):
        self.connection.execute(
            """INSERT INTO baseline_metrics(date,window_days,valid_days,metric_name,median_value,latest_value,status)
               VALUES('2026-07-01',28,7,'training_duration',45,60,'above_baseline')"""
        )
        self.connection.commit()
        result = get_domain_baselines(("training_duration",), self.path)
        self.assertEqual(result["training_duration"]["median_value"], 45)

    def test_empty_database_degrades_safely(self):
        self.assertIsNone(get_latest_training(self.path))
        self.assertIsNone(get_latest_sleep(self.path))
        self.assertIsNone(get_latest_nutrition(self.path))

    def test_navigation_has_exact_new_top_level_sections(self):
        source = (db.BASE_DIR / "src/i18n/ui.py").read_text(encoding="utf-8")
        for path in ("dashboard.py", "pages/1_Sleep.py", "pages/2_Recovery.py", "pages/3_Nutrition.py", "pages/5_Personal.py", "pages/4_System.py"):
            self.assertIn(f'"{path}"', source)
        self.assertNotIn("Kubios_Screenshot", source)
        self.assertNotIn("Kubios_Advanced", source)
        self.assertNotIn("1_Daily_Log.py", source)

    def test_domain_queries_are_read_only(self):
        before = self.connection.total_changes
        get_latest_training(self.path); get_latest_sleep(self.path); get_latest_recovery(self.path)
        self.assertEqual(self.connection.total_changes, before)


if __name__ == "__main__":
    unittest.main()
