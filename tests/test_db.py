import sqlite3
import tempfile
import unittest
from pathlib import Path

from src import db


class DatabaseTests(unittest.TestCase):
    def test_connect_creates_expected_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "recovery.db"
            connection = db.connect(db_path)

            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            self.assertIn("polar_daily_activity_raw", tables)
            self.assertIn("polar_training_sessions_raw", tables)
            self.assertIn("daily_recovery_metrics", tables)
            self.assertIn("recovery_scores", tables)
            self.assertIn("polar_sleep_raw", tables)
            self.assertIn("polar_nightly_recharge_raw", tables)
            self.assertIn("kubios_morning_hrv_raw", tables)
            self.assertIn("polar_flow_import_files", tables)
            self.assertIn("polar_cardio_load_raw", tables)
            self.assertIn("polar_continuous_hr_raw", tables)
            self.assertIn("baseline_metrics", tables)
            self.assertIn("schema_migrations", tables)
            connection.close()

    def test_daily_activity_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_daily_activity_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "steps",
            "calories",
            "active_calories",
            "duration",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_recovery_scores_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(recovery_scores)")
        }

        for column in (
            "id",
            "date",
            "recovery_score",
            "activity_load_score",
            "training_load_score",
            "hrv_score",
            "morning_hr_score",
            "readiness_score",
            "score_version",
            "recommendation",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_baseline_metrics_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(baseline_metrics)")
        }

        for column in (
            "id",
            "date",
            "window_days",
            "valid_days",
            "metric_name",
            "mean_value",
            "median_value",
            "std_value",
            "mad_value",
            "min_value",
            "max_value",
            "latest_value",
            "percent_change",
            "z_score",
            "robust_z_score",
            "status",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_daily_recovery_metrics_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(daily_recovery_metrics)")
        }

        for column in (
            "id",
            "date",
            "steps",
            "calories",
            "active_calories",
            "activity_duration",
            "training_count",
            "training_duration",
            "training_calories",
            "sleep_duration",
            "sleep_score",
            "nightly_hrv_rmssd",
            "nightly_resting_hr",
            "respiration_rate",
            "morning_rmssd",
            "morning_mean_hr",
            "kubios_readiness",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_sleep_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_sleep_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "sleep_duration",
            "sleep_score",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_nightly_recharge_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_nightly_recharge_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "ans_status",
            "hrv_rmssd",
            "resting_hr",
            "respiration_rate",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_kubios_morning_hrv_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(kubios_morning_hrv_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "rmssd",
            "mean_hr",
            "readiness",
            "measurement_time",
            "stress_index",
            "respiratory_rate",
            "measurement_quality",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_cardio_load_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_cardio_load_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "cardio_load",
            "strain",
            "tolerance",
            "status",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_continuous_hr_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_continuous_hr_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_training_sessions_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_training_sessions_raw)")
        }

        for column in (
            "id",
            "source",
            "external_id",
            "date",
            "raw_json",
            "sport",
            "start_time",
            "duration",
            "calories",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_polar_flow_import_files_schema_contains_common_fields(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(polar_flow_import_files)")
        }

        for column in (
            "id",
            "source_path",
            "stored_path",
            "filename",
            "file_type",
            "sha256",
            "status",
            "created_at",
            "updated_at",
        ):
            self.assertIn(column, columns)
        connection.close()

    def test_schema_migration_ledger_is_complete_and_idempotent(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        db.init_db(connection)

        rows = connection.execute(
            """
            SELECT version, sequence, name, checksum
            FROM schema_migrations
            ORDER BY sequence
            """
        ).fetchall()
        self.assertEqual([row["version"] for row in rows], [migration.version for migration in db.SCHEMA_MIGRATIONS])
        self.assertEqual([row["sequence"] for row in rows], [migration.sequence for migration in db.SCHEMA_MIGRATIONS])
        self.assertTrue(all(len(row["checksum"]) == 64 for row in rows))
        self.assertEqual(db.current_schema_version(connection), db.SCHEMA_MIGRATIONS[-1].version)
        connection.close()

    def test_legacy_database_is_baselined_without_data_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy.db"
            legacy = sqlite3.connect(db_path)
            legacy.execute("CREATE TABLE user_marker (value TEXT NOT NULL)")
            legacy.execute("INSERT INTO user_marker VALUES ('preserved')")
            legacy.commit()
            legacy.close()

            connection = db.connect(db_path)
            self.assertEqual(
                connection.execute("SELECT value FROM user_marker").fetchone()[0],
                "preserved",
            )
            self.assertEqual(db.current_schema_version(connection), db.SCHEMA_MIGRATIONS[-1].version)
            connection.close()

    def test_migration_checksum_drift_is_rejected(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        connection.execute(
            "UPDATE schema_migrations SET checksum = 'invalid' WHERE version = '0.1.0'"
        )
        connection.commit()

        with self.assertRaises(db.DatabaseMigrationError):
            db.init_db(connection)
        connection.close()

    def test_manual_health_schema_and_link_xor_are_enforced(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(connection)
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue({
            "manual_activity_sessions", "manual_sleep_logs",
            "manual_recovery_logs", "resolved_daily_fields",
            "meal_events", "meal_event_items",
        }.issubset(tables))
        manual_id = connection.execute(
            "INSERT INTO manual_activity_sessions(date) VALUES('2026-07-15')"
        ).lastrowid
        workout_id = connection.execute(
            "INSERT INTO workout_sessions(date,session_type) VALUES('2026-07-15','other')"
        ).lastrowid
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO polar_manual_session_links (
                       polar_session_external_id,workout_session_id,
                       manual_activity_session_id,match_method
                   ) VALUES ('p',?,?,'manual')""",
                (workout_id, manual_id),
            )
        connection.close()


if __name__ == "__main__":
    unittest.main()
