"""Runtime changes must preserve data and numerical results."""

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from src import baseline, db, dashboard_launcher


class RuntimeOptimizationTests(unittest.TestCase):
    def test_current_database_connects_while_another_writer_is_active(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.db"
            writer = db.connect(path)
            try:
                writer.execute("BEGIN IMMEDIATE")
                with patch.object(db, "init_db", wraps=db.init_db) as initialize:
                    reader = db.connect(path)
                    try:
                        self.assertEqual(reader.total_changes, 0)
                        self.assertFalse(reader.in_transaction)
                        self.assertEqual(reader.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                        initialize.assert_not_called()
                    finally:
                        reader.close()
            finally:
                writer.rollback()
                writer.close()

    def test_reopening_detects_ledger_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.db"
            connection = db.connect(path)
            connection.execute("UPDATE schema_migrations SET checksum='invalid' WHERE sequence=1")
            connection.commit()
            connection.close()
            with self.assertRaises(db.DatabaseMigrationError):
                db.connect(path)

    def test_reopening_repairs_legacy_columns_and_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.db"
            connection = db.connect(path)
            connection.execute(
                "INSERT INTO meal_records(uuid,date,meal_type,eaten_at,status,source) "
                "VALUES('test','2026-01-01','breakfast','2026-01-01T08:00:00','draft','manual')"
            )
            connection.execute("ALTER TABLE meal_templates DROP COLUMN template_type")
            connection.commit()
            connection.close()
            connection = db.connect(path)
            try:
                row = connection.execute("SELECT actual_meal_time,meal_slot FROM meal_records").fetchone()
                self.assertEqual(tuple(row), ('2026-01-01T08:00:00', 'meal_1'))
                self.assertIn('template_type', {r[1] for r in connection.execute('PRAGMA table_info(meal_templates)')})
            finally:
                connection.close()

    def test_bulk_baselines_equal_day_by_day_with_fewer_source_queries(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        db.init_db(connection)
        self.addCleanup(connection.close)
        for i in range(45):
            if i % 11 == 0:
                continue
            day = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
            connection.execute(
                "INSERT INTO daily_recovery_metrics(date,steps,nightly_hrv_rmssd,sleep_duration) VALUES(?,?,?,?)",
                (day, 0 if i % 7 == 0 else i * 100, None if i % 5 == 0 else 900 if i == 20 else 40 + i % 9, 'PT7H'),
            )
        connection.commit()
        for day, value, primary in (
            ('2025-12-20', 35, 1), ('2026-01-09', 42, 1),
            ('2026-01-09', 47, 1), ('2026-01-09', 999, 0),
            ('2026-01-10', None, 1), ('2026-01-12', -1, 1),
        ):
            connection.execute(
                "INSERT INTO kubios_hrv_normalized(date,source_raw_table,source_raw_id,source_type,"
                "selection_reason,source_priority,core_data_completeness,normalization_version,"
                "rmssd_ms,selected_as_primary) VALUES(?,'fixture',1,'manual','test',1,100,'test',?,?)",
                (day, value, primary),
            )
        connection.commit()
        config = baseline.load_baseline_config()
        dates = [row[0] for row in connection.execute('SELECT date FROM daily_recovery_metrics ORDER BY date')]
        expected = [result for day in dates for result in baseline.calculate_baseline_for_date(connection, day, config)]
        queries = []
        connection.set_trace_callback(queries.append)
        result = baseline.calculate_all_baselines(connection, config)
        connection.set_trace_callback(None)
        actual = {(row['date'], row['metric_name']): dict(row) for row in connection.execute('SELECT * FROM baseline_metrics')}
        for item in expected:
            stored = actual[item['date'], item['metric_name']]
            self.assertEqual(item, {key: stored[key] for key in item})
        self.assertEqual(result['records'], len(expected))
        source_queries = [q for q in queries if q.startswith('SELECT date,')]
        self.assertLessEqual(len(source_queries), len(config['metrics']))
        # A new invocation sees corrections; no persistent health-data cache.
        connection.execute("UPDATE daily_recovery_metrics SET steps=12345 WHERE date=?", (dates[-1],))
        baseline.calculate_all_baselines(connection, config)
        self.assertEqual(connection.execute("SELECT latest_value FROM baseline_metrics WHERE date=? AND metric_name='steps'", (dates[-1],)).fetchone()[0], 12345)

    def test_fingerprint_tracks_all_component_frontends(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            (root / 'config' / 'versions.json').write_text('{}')
            for name in ('pvt_component_frontend', 'region_calibrator_frontend'):
                folder = root / 'src' / name
                folder.mkdir(parents=True)
                asset = folder / 'index.html'
                asset.write_text('before')
                previous = dashboard_launcher.runtime_fingerprint(root)
                asset.write_text('after')
                self.assertNotEqual(previous, dashboard_launcher.runtime_fingerprint(root))


if __name__ == '__main__':
    unittest.main()
