import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import db


PLANNER_TABLES = {
    "performance_plans",
    "performance_plan_blocks",
    "performance_checkpoints",
    "performance_recommendations",
}


class PerformancePlannerMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "migration.db"
        self.connection = db.connect(self.path)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def test_migration_is_sequence_38_and_version_0380(self):
        migration = next(
            migration
            for migration in db.SCHEMA_MIGRATIONS
            if migration.version == "0.38.0"
        )
        self.assertEqual((migration.sequence, migration.version), (38, "0.38.0"))
        self.assertEqual(
            db.current_schema_version(self.connection),
            db.SCHEMA_MIGRATIONS[-1].version,
        )

    def test_fresh_database_has_all_planner_tables(self):
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue(PLANNER_TABLES <= tables)

    def test_required_indexes_exist(self):
        indexes = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertTrue(
            {
                "idx_performance_plans_plan_date",
                "idx_performance_blocks_plan_id",
                "idx_performance_checkpoints_scheduled_at",
                "idx_performance_checkpoints_related_block",
                "idx_performance_checkpoints_run_id",
                "idx_performance_recommendations_fingerprint",
            }
            <= indexes
        )

    def test_migration_replay_is_idempotent(self):
        db.apply_migrations(self.connection)
        db.apply_migrations(self.connection)
        self.connection.commit()
        count = self.connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='0.38.0'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_upgrade_preserves_existing_cognitive_rows(self):
        self.connection.execute(
            """
            INSERT INTO cognitive_training_sessions(
                id, training_plan, session_mode, started_at, timezone,
                completed, interrupted, device_context, protocol_version
            ) VALUES(
                'preserved-run', 'focus_alertness', 'quick',
                '2026-07-29T08:00:00', 'UTC', 1, 0, '{}', 'test-v1'
            )
            """
        )
        self.connection.execute("PRAGMA foreign_keys=OFF")
        for table in (
            "performance_recommendations",
            "performance_checkpoints",
            "performance_plan_blocks",
            "performance_plans",
        ):
            self.connection.execute(f"DROP TABLE {table}")
        self.connection.execute(
            "DELETE FROM schema_migrations WHERE version IN ('0.37.0', '0.38.0')"
        )
        self.connection.commit()
        self.connection.execute("PRAGMA foreign_keys=ON")

        db.apply_migrations(self.connection)
        db.apply_migrations(self.connection)
        self.connection.commit()

        count = self.connection.execute(
            "SELECT COUNT(*) FROM cognitive_training_sessions WHERE id='preserved-run'"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_upgrade_from_037_adds_recommendation_fingerprint(self):
        path = Path(self.temp.name) / "upgrade-037.db"
        migrations_through_037 = tuple(
            migration
            for migration in db.SCHEMA_MIGRATIONS
            if migration.sequence <= 37
        )
        with patch.object(db, "SCHEMA_MIGRATIONS", migrations_through_037):
            legacy = db.connect(path)
            self.assertEqual(db.current_schema_version(legacy), "0.37.0")
            legacy.close()

        upgraded = db.connect(path)
        try:
            columns = {
                row["name"]
                for row in upgraded.execute(
                    "PRAGMA table_info(performance_recommendations)"
                )
            }
            indexes = {
                row["name"]
                for row in upgraded.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                )
            }
            self.assertEqual(
                db.current_schema_version(upgraded),
                db.SCHEMA_MIGRATIONS[-1].version,
            )
            self.assertIn("recommendation_fingerprint", columns)
            self.assertIn("idx_performance_recommendations_fingerprint", indexes)
        finally:
            upgraded.close()

    def test_foreign_keys_and_integrity_checks_pass(self):
        self.assertEqual(self.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO performance_plan_blocks(
                    block_id, plan_id, title, block_type,
                    planned_start, planned_end
                ) VALUES('orphan', 'missing', 'Orphan', 'other',
                         '2026-07-29T09:00:00', '2026-07-29T10:00:00')
                """
            )
        self.connection.rollback()

    def test_versions_json_matches_migration(self):
        versions = json.loads(
            (Path(__file__).parents[1] / "config" / "versions.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            versions["database_schema_version"],
            db.SCHEMA_MIGRATIONS[-1].version,
        )


if __name__ == "__main__":
    unittest.main()
