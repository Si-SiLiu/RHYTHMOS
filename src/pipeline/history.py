import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
HISTORY_PATH = BASE_DIR / "data" / "sync_history.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    finish_time TEXT NOT NULL,
    duration REAL NOT NULL,
    success INTEGER NOT NULL,
    step TEXT NOT NULL,
    message TEXT NOT NULL,
    records_imported INTEGER NOT NULL DEFAULT 0,
    metrics_updated INTEGER NOT NULL DEFAULT 0,
    baseline_updated INTEGER NOT NULL DEFAULT 0,
    recovery_updated INTEGER NOT NULL DEFAULT 0,
    reports_generated INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    confidence_updated INTEGER NOT NULL DEFAULT 0,
    local_coach_records_updated INTEGER NOT NULL DEFAULT 0,
    prospective_eligible_days INTEGER NOT NULL DEFAULT 0,
    trigger_type TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_sync_history_run_step
ON sync_history (run_id, step, id);
"""


class SyncHistory:
    def __init__(self, path=HISTORY_PATH):
        self.path = Path(path)

    def _connect(self, create=False):
        if not create and not self.path.exists():
            return None
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        if create:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sync_history)").fetchall()
            }
            additions = {
                "metrics_updated": "INTEGER NOT NULL DEFAULT 0",
                "warning_count": "INTEGER NOT NULL DEFAULT 0",
                "confidence_updated": "INTEGER NOT NULL DEFAULT 0",
                "local_coach_records_updated": "INTEGER NOT NULL DEFAULT 0",
                "prospective_eligible_days": "INTEGER NOT NULL DEFAULT 0",
                "trigger_type": "TEXT NOT NULL DEFAULT 'manual'",
            }
            for column, definition in additions.items():
                if column not in columns:
                    connection.execute(
                        f"ALTER TABLE sync_history ADD COLUMN {column} {definition}"
                    )
            connection.commit()
        return connection

    def initialize(self):
        connection = self._connect(create=True)
        connection.close()

    def record(
        self,
        run_id,
        start_time,
        finish_time,
        duration,
        success,
        step,
        message,
        records_imported=0,
        metrics_updated=0,
        baseline_updated=0,
        recovery_updated=0,
        reports_generated=0,
        warning_count=0,
        confidence_updated=0,
        local_coach_records_updated=0,
        prospective_eligible_days=0,
        trigger_type="manual",
    ):
        if trigger_type not in {"manual", "scheduled", "catch_up"}:
            raise ValueError("INVALID_SYNC_TRIGGER_TYPE")
        connection = self._connect(create=True)
        try:
            cursor = connection.execute(
                """
                INSERT INTO sync_history (
                    run_id, start_time, finish_time, duration, success, step,
                    message, records_imported, metrics_updated, baseline_updated,
                    recovery_updated, reports_generated, warning_count, confidence_updated,
                    local_coach_records_updated, prospective_eligible_days,
                    trigger_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    start_time,
                    finish_time,
                    float(duration),
                    int(bool(success)),
                    step,
                    message,
                    int(records_imported or 0),
                    int(metrics_updated or 0),
                    int(baseline_updated or 0),
                    int(recovery_updated or 0),
                    int(reports_generated or 0),
                    int(warning_count or 0),
                    int(confidence_updated or 0),
                    int(local_coach_records_updated or 0),
                    int(prospective_eligible_days or 0),
                    trigger_type,
                ),
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def latest_failed_run_id(self):
        connection = self._connect()
        if connection is None:
            return None
        try:
            row = connection.execute(
                """
                SELECT run_id
                FROM sync_history
                WHERE step = 'pipeline' AND success = 0
                  AND run_id NOT IN (
                      SELECT run_id FROM sync_history
                      WHERE step = 'pipeline' AND success = 1
                  )
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            return row["run_id"] if row else None
        except sqlite3.OperationalError:
            return None
        finally:
            connection.close()

    def completed_steps(self, run_id):
        connection = self._connect()
        if connection is None:
            return set()
        try:
            rows = connection.execute(
                """
                SELECT DISTINCT step FROM sync_history
                WHERE run_id = ? AND success = 1 AND step != 'pipeline'
                """,
                (run_id,),
            ).fetchall()
            return {row["step"] for row in rows}
        except sqlite3.OperationalError:
            return set()
        finally:
            connection.close()

    def aggregate_run(self, run_id):
        connection = self._connect()
        if connection is None:
            return {}
        try:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(records_imported), 0) AS records_imported,
                    COALESCE(SUM(metrics_updated), 0) AS metrics_updated,
                    COALESCE(SUM(baseline_updated), 0) AS baseline_updated,
                    COALESCE(SUM(recovery_updated), 0) AS recovery_updated,
                    COALESCE(SUM(reports_generated), 0) AS reports_generated,
                    COALESCE(SUM(warning_count), 0) AS warning_count,
                    COALESCE(SUM(confidence_updated), 0) AS confidence_updated,
                    COALESCE(SUM(local_coach_records_updated), 0) AS local_coach_records_updated,
                    COALESCE(SUM(prospective_eligible_days), 0) AS prospective_eligible_days
                FROM sync_history
                WHERE run_id = ? AND success = 1 AND step != 'pipeline'
                """,
                (run_id,),
            ).fetchone()
            return dict(row) if row else {}
        except sqlite3.OperationalError:
            return {}
        finally:
            connection.close()

    def last_sync(self):
        connection = self._connect()
        if connection is None:
            return None
        try:
            row = connection.execute(
                """
                SELECT h.start_time, h.finish_time,
                       COALESCE(
                           (
                               SELECT SUM(s.duration)
                               FROM sync_history s
                               WHERE s.run_id = h.run_id
                                 AND s.success = 1
                                 AND s.step != 'pipeline'
                           ),
                           h.duration
                       ) AS duration,
                       h.success, h.message, h.records_imported,
                       h.baseline_updated, h.recovery_updated,
                       h.reports_generated, h.warning_count,
                       h.local_coach_records_updated, h.prospective_eligible_days,
                       h.trigger_type,
                       COALESCE(
                           (
                               SELECT s.warning_count
                               FROM sync_history s
                               WHERE s.run_id = h.run_id
                                 AND s.step = 'fetch'
                                 AND s.success = 1
                               ORDER BY s.id DESC
                               LIMIT 1
                           ),
                           0
                       ) AS source_warning_count
                FROM sync_history h
                WHERE h.step = 'pipeline'
                ORDER BY h.id DESC
                LIMIT 1
                """
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError:
            return None
        finally:
            connection.close()

    def last_sync_by_trigger(self, trigger_type):
        if trigger_type not in {"manual", "scheduled", "catch_up"}:
            raise ValueError("INVALID_SYNC_TRIGGER_TYPE")
        connection = self._connect()
        if connection is None:
            return None
        try:
            row = connection.execute(
                """
                SELECT h.start_time, h.finish_time, h.duration, h.success,
                       h.message, h.records_imported, h.warning_count,
                       h.trigger_type
                FROM sync_history h
                WHERE h.step = 'pipeline' AND h.trigger_type = ?
                ORDER BY h.id DESC
                LIMIT 1
                """,
                (trigger_type,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.OperationalError:
            return None
        finally:
            connection.close()


def get_last_sync(path=HISTORY_PATH):
    return SyncHistory(path).last_sync()
