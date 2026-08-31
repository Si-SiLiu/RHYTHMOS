import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import dashboard_data, db


class DashboardDataTests(unittest.TestCase):
    def make_db(self):
        directory = tempfile.TemporaryDirectory()
        db_path = Path(directory.name) / "recovery.db"
        connection = db.connect(db_path)
        return directory, db_path, connection

    def insert_day(
        self,
        connection,
        date,
        recovery_score=80,
        sleep_score=None,
        nightly_hrv_rmssd=None,
        morning_rmssd=None,
    ):
        connection.execute(
            """
            INSERT INTO daily_recovery_metrics (
                date,
                steps,
                calories,
                active_calories,
                activity_duration,
                training_count,
                training_duration,
                training_calories,
                sleep_score,
                nightly_hrv_rmssd,
                morning_rmssd
            )
            VALUES (?, 1000, 2000, 500, 'PT1H', 1, 'PT30M', 300, ?, ?, ?)
            """,
            (date, sleep_score, nightly_hrv_rmssd, morning_rmssd),
        )
        connection.execute(
            """
            INSERT INTO recovery_scores (
                date,
                recovery_score,
                activity_load_score,
                training_load_score,
                recommendation,
                score_version
            )
            VALUES (?, ?, 10, 20, '正常训练', 'v0.1')
            """,
            (date, recovery_score),
        )
        connection.commit()

    def test_empty_database_returns_no_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "empty.db"
            db_path.write_text("", encoding="utf-8")

            self.assertIsNone(dashboard_data.get_latest_day(db_path))
            self.assertEqual(dashboard_data.get_last_7_days(db_path), [])
            self.assertEqual(dashboard_data.get_last_30_days(db_path), [])

    def test_readonly_connection_does_not_initialize_or_migrate_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "readonly.db"
            writable = sqlite3.connect(db_path)
            writable.execute("CREATE TABLE marker (value TEXT)")
            writable.execute("INSERT INTO marker VALUES ('kept')")
            writable.commit()
            writable.close()

            connection = dashboard_data.connect_readonly(db_path)
            self.assertEqual(
                connection.execute("SELECT value FROM marker").fetchone()[0],
                "kept",
            )
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE forbidden (id INTEGER)")
            connection.close()

            inspected = sqlite3.connect(db_path)
            tables = {
                row[0]
                for row in inspected.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            inspected.close()
            self.assertEqual(tables, {"marker"})

    def test_duration_conversion(self):
        self.assertEqual(dashboard_data.duration_to_seconds("PT2H4M30S"), 7470)
        self.assertEqual(dashboard_data.duration_to_hours("PT1H30M"), 1.5)
        self.assertEqual(dashboard_data.duration_to_minutes("PT30M"), 30.0)
        self.assertIsNone(dashboard_data.duration_to_seconds(None))
        self.assertIsNone(dashboard_data.duration_to_seconds("not-a-duration"))

    def test_latest_day_handles_missing_hrv_and_sleep(self):
        directory, db_path, connection = self.make_db()
        try:
            self.insert_day(connection, "2026-07-10")

            latest = dashboard_data.get_latest_day(db_path)

            self.assertEqual(latest["date"], "2026-07-10")
            self.assertIsNone(latest["sleep_score"])
            self.assertIsNone(latest["nightly_hrv_rmssd"])
            self.assertIsNone(latest["morning_rmssd"])
            self.assertEqual(latest["training_duration_hours"], 0.5)
        finally:
            connection.close()
            directory.cleanup()

    def test_latest_baselines_returns_metric_map(self):
        directory, db_path, connection = self.make_db()
        try:
            connection.execute(
                """
                INSERT INTO baseline_metrics (
                    date,
                    window_days,
                    valid_days,
                    metric_name,
                    median_value,
                    latest_value,
                    percent_change,
                    status
                )
                VALUES ('2026-07-10', 28, 10, 'nightly_hrv_rmssd', 50, 55, 10, 'above_baseline')
                """
            )
            connection.commit()

            baselines = dashboard_data.get_latest_baselines(
                db_path,
                metric_names=["nightly_hrv_rmssd", "sleep_score"],
            )

            self.assertEqual(baselines["nightly_hrv_rmssd"]["latest_value"], 55)
            self.assertEqual(baselines["sleep_score"], None)
        finally:
            connection.close()
            directory.cleanup()

    def test_recent_7_and_30_day_queries(self):
        directory, db_path, connection = self.make_db()
        try:
            for index in range(35):
                self.insert_day(
                    connection,
                    f"2026-07-{index + 1:02d}",
                    recovery_score=index,
                    sleep_score=70 + index,
                    nightly_hrv_rmssd=40 + index,
                    morning_rmssd=50 + index,
                )

            rows7 = dashboard_data.get_last_7_days(db_path)
            rows30 = dashboard_data.get_last_30_days(db_path)

            self.assertEqual(len(rows7), 7)
            self.assertEqual(len(rows30), 30)
            self.assertEqual(rows7[0]["date"], "2026-07-29")
            self.assertEqual(rows7[-1]["date"], "2026-07-35")
            self.assertEqual(rows30[0]["date"], "2026-07-06")
            self.assertEqual(rows30[-1]["date"], "2026-07-35")
        finally:
            connection.close()
            directory.cleanup()

    def test_latest_confidence_is_read_only_and_decodes_missing_groups(self):
        directory, db_path, connection = self.make_db()
        try:
            connection.execute(
                """INSERT INTO recovery_confidence (
                    date,data_completeness_score,baseline_maturity_score,
                    confidence_score,confidence_level,group_scores_json,
                    available_groups_json,missing_groups_json,confidence_version
                ) VALUES ('2026-07-10',80,70,76,'medium','{}','[]','[\"sleep\"]','1.0.0')"""
            )
            connection.commit()
            result = dashboard_data.get_latest_confidence(db_path)
            self.assertEqual(result["confidence_score"], 76)
            self.assertEqual(result["missing_groups"], ["sleep"])
        finally:
            connection.close()
            directory.cleanup()

    def test_local_coach_missing_table_degrades_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            sqlite3.connect(path).close()
            self.assertIsNone(dashboard_data.get_latest_local_coach(path))

    def test_latest_local_coach_decodes_json(self):
        directory, db_path, connection = self.make_db()
        try:
            values = ('2026-07-08',) + tuple('{}' for _ in range(7)) + ('[]', '[]', '1.0.0', '1.0.0', 1)
            connection.execute("""INSERT INTO local_coach_recommendations
                (date,morning_training_json,evening_training_json,sleep_advice_json,hydration_advice_json,
                 nutrition_advice_json,recovery_advice_json,rationale_json,data_limitations_json,safety_notices_json,
                 engine_version,rule_config_version,generated_without_cloud_ai)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            connection.execute(
                """INSERT INTO recovery_scores
                   (date,recovery_score,activity_load_score,training_load_score,score_version,recommendation)
                   VALUES ('2026-07-08', 75, 20, 20, 'v1.0', '适度训练')"""
            )
            connection.commit()
            result = dashboard_data.get_latest_local_coach(db_path)
            self.assertEqual(result["date"], "2026-07-08")
            self.assertTrue(result["generated_without_cloud_ai"])
        finally:
            connection.close()
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
