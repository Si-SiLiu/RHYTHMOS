"""Read-only task history queries used by the Cognitive history presentation."""

from __future__ import annotations

import hashlib
import json

from .db import connect, get_current_db_path


def get_training_task_history(training_plan, days=30, db_path=None):
    """Return task-level records for one plan without changing persistence."""
    connection = connect(db_path or get_current_db_path(), migrate=False)
    try:
        rows = connection.execute(
            """SELECT r.id AS task_result_id, s.started_at, s.training_plan, s.session_mode,
                      r.task_type, r.protocol_version, r.difficulty_end, r.accuracy,
                      r.median_rt_ms, r.metrics_json
                 FROM cognitive_training_sessions s
                 JOIN cognitive_training_task_results r ON r.session_id=s.id
                WHERE s.training_plan=? AND s.completed=1
                  AND s.started_at>=datetime('now', ?)
                ORDER BY s.started_at DESC""",
            (training_plan, f"-{int(days)} days"),
        ).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            metrics = json.loads(item.pop("metrics_json") or "{}")
            config = metrics.get("difficulty_config") or {"difficulty_end": item.get("difficulty_end")}
            config_hash = hashlib.sha256(
                json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()[:12]
            item.update(
                metrics=metrics,
                difficulty_config_hash=config_hash,
                comparable_group="|".join((
                    item.get("task_type") or "",
                    item.get("protocol_version") or "",
                    item.get("session_mode") or "",
                    config_hash,
                )),
            )
            output.append(item)
        return output
    except Exception:
        return []
    finally:
        connection.close()
