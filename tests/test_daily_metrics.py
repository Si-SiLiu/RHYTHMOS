import sqlite3
import unittest

from src import daily_metrics, db


class DailyMetricsTests(unittest.TestCase):
    def make_connection(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        return connection

    def test_duration_helpers(self):
        self.assertEqual(daily_metrics.duration_to_seconds("PT2H4M30S"), 7470)
        self.assertEqual(daily_metrics.duration_to_seconds("PT45M"), 2700)
        self.assertEqual(daily_metrics.seconds_to_iso_duration(7470), "PT2H4M30S")
        self.assertEqual(daily_metrics.seconds_to_iso_duration(2700), "PT45M")
        self.assertIsNone(daily_metrics.seconds_to_iso_duration(0))

    def test_build_daily_metrics_merges_activity_and_training(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO polar_daily_activity_raw (
                source, external_id, date, raw_json, steps, calories, active_calories, duration
            )
            VALUES ('polar', 'activity-1', '2026-07-10', '{}', 1000, 2200, 500, 'PT1H')
            """
        )
        connection.execute(
            """
            INSERT INTO polar_training_sessions_raw (
                source, external_id, date, raw_json, sport, start_time, duration, calories
            )
            VALUES ('polar', 'session-1', '2026-07-10', '{}', 'RUNNING', '2026-07-10T07:00:00', 'PT30M', 300)
            """
        )
        connection.execute(
            """
            INSERT INTO polar_training_sessions_raw (
                source, external_id, date, raw_json, sport, start_time, duration, calories
            )
            VALUES ('polar', 'session-2', '2026-07-10', '{}', 'CYCLING', '2026-07-10T18:00:00', 'PT45M', 450)
            """
        )
        connection.commit()

        metrics = daily_metrics.build_daily_metrics(connection)

        self.assertEqual(len(metrics), 1)
        metric = metrics[0]
        self.assertEqual(metric["date"], "2026-07-10")
        self.assertEqual(metric["steps"], 1000)
        self.assertEqual(metric["calories"], 2200)
        self.assertEqual(metric["active_calories"], 500)
        self.assertEqual(metric["activity_duration"], "PT1H")
        self.assertEqual(metric["training_count"], 2)
        self.assertEqual(metric["training_duration"], "PT1H15M")
        self.assertEqual(metric["training_calories"], 750)
        connection.close()

    def test_rebuild_upserts_daily_metrics(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO polar_daily_activity_raw (
                source, external_id, date, raw_json, steps, calories, active_calories, duration
            )
            VALUES ('polar', 'activity-1', '2026-07-10', '{}', 1000, 2200, 500, 'PT1H')
            """
        )
        connection.commit()

        first_count = daily_metrics.rebuild_daily_recovery_metrics(connection)
        connection.execute(
            """
            UPDATE polar_daily_activity_raw
            SET steps = 1500, calories = 2300
            WHERE date = '2026-07-10'
            """
        )
        connection.commit()
        second_count = daily_metrics.rebuild_daily_recovery_metrics(connection)

        row_count = connection.execute(
            "SELECT COUNT(*) FROM daily_recovery_metrics"
        ).fetchone()[0]
        row = connection.execute("SELECT * FROM daily_recovery_metrics").fetchone()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertEqual(row_count, 1)
        self.assertEqual(row["steps"], 1500)
        self.assertEqual(row["calories"], 2300)
        self.assertEqual(row["training_count"], 0)
        connection.close()

    def test_training_only_day_is_included(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO polar_training_sessions_raw (
                source, external_id, date, raw_json, sport, start_time, duration, calories
            )
            VALUES ('polar', 'session-1', '2026-07-11', '{}', 'RUNNING', '2026-07-11T07:00:00', 'PT30M', 300)
            """
        )
        connection.commit()

        daily_metrics.rebuild_daily_recovery_metrics(connection)
        row = connection.execute("SELECT * FROM daily_recovery_metrics").fetchone()

        self.assertEqual(row["date"], "2026-07-11")
        self.assertIsNone(row["steps"])
        self.assertEqual(row["training_count"], 1)
        self.assertEqual(row["training_duration"], "PT30M")
        self.assertEqual(row["training_calories"], 300)
        connection.close()

    def test_sleep_and_nightly_fields_are_included(self):
        connection = self.make_connection()
        connection.execute(
            """
            INSERT INTO polar_sleep_raw (
                source, external_id, date, raw_json, sleep_duration, sleep_score
            )
            VALUES ('polar', 'sleep-1', '2026-07-10', '{}', 'PT7H30M', 82)
            """
        )
        connection.execute(
            """
            INSERT INTO polar_nightly_recharge_raw (
                source, external_id, date, raw_json, hrv_rmssd, resting_hr, respiration_rate
            )
            VALUES ('polar', 'nightly-1', '2026-07-10', '{}', 42, 58, 14.2)
            """
        )
        connection.commit()

        daily_metrics.rebuild_daily_recovery_metrics(connection)
        row = connection.execute("SELECT * FROM daily_recovery_metrics").fetchone()

        self.assertEqual(row["date"], "2026-07-10")
        self.assertEqual(row["sleep_duration"], "PT7H30M")
        self.assertEqual(row["sleep_score"], 82)
        self.assertEqual(row["nightly_hrv_rmssd"], 42)
        self.assertEqual(row["nightly_resting_hr"], 58)
        self.assertEqual(row["respiration_rate"], 14.2)
        connection.close()

    def test_rebuild_projects_resolved_morning_recovery_values(self):
        connection = self.make_connection()
        connection.execute(
            """INSERT INTO kubios_morning_hrv_raw(
                   source,external_id,date,raw_json,rmssd,mean_hr,readiness,reviewed
               ) VALUES('kubios','kubios-1','2026-07-10','{}',35,55,'good',1)"""
        )
        connection.execute(
            """INSERT INTO manual_recovery_logs(
                   date,morning_rmssd_ms,morning_resting_hr_bpm
               ) VALUES('2026-07-10',41,61)"""
        )
        connection.commit()

        daily_metrics.rebuild_daily_recovery_metrics(connection)
        row = connection.execute(
            """SELECT morning_rmssd,morning_mean_hr,kubios_readiness
               FROM daily_recovery_metrics WHERE date='2026-07-10'"""
        ).fetchone()

        # Recovery source priority is manual for the two morning measurements,
        # while Kubios is the sole permitted source for readiness.
        self.assertEqual(row["morning_rmssd"], 41)
        self.assertEqual(row["morning_mean_hr"], 61)
        self.assertEqual(row["kubios_readiness"], "good")
        connection.close()

    def test_manual_morning_fields_can_supply_typed_kubios_trends(self):
        from src.kubios_morning_input import sync_manual_morning_measurements
        from src.kubios_metrics.normalizer import rebuild as rebuild_kubios_normalized

        connection = self.make_connection()
        connection.execute(
            """INSERT INTO kubios_morning_hrv_raw(
                   source,external_id,date,raw_json,rmssd,mean_hr,stress_index,
                   respiratory_rate,measurement_quality,source_type,reviewed,import_method
               ) VALUES('kubios_manual','manual:2026-07-10','2026-07-10','{}',41,61,12.5,
                        17.2,'GOOD','manual',1,'manual')"""
        )
        connection.commit()

        self.assertEqual(sync_manual_morning_measurements(connection), 1)
        self.assertEqual(rebuild_kubios_normalized(connection)["normalized_records"], 1)
        row = connection.execute(
            """SELECT rmssd_ms,mean_hr_bpm,stress_index,respiratory_rate_bpm,
                      readiness_percent,source_type
               FROM kubios_hrv_normalized WHERE date='2026-07-10'"""
        ).fetchone()

        self.assertEqual(tuple(row), (41, 61, 12.5, 17.2, None, "manual"))
        connection.close()


if __name__ == "__main__":
    unittest.main()
