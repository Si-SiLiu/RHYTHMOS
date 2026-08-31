"""Transactional persistence and trend queries for neural-fatigue snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import sqlite3
from typing import Any, Iterable


COMPONENT_NAMES = ("cognitive", "recovery", "sleep", "training", "subjective")
MAX_HISTORY_DAYS = 365


@dataclass(frozen=True)
class SnapshotSaveResult:
    status: str
    snapshot: dict[str, Any]


def source_fingerprint(view: dict[str, Any]) -> str:
    """Return a SHA-256 over the stable, user-meaningful snapshot inputs."""
    result = view["result"]
    payload = {
        "snapshot_date": _date_text(view["target_date"]),
        "algorithm_version": result.algorithm_version,
        "status": result.status,
        "burden_score": result.burden_score,
        "confidence": result.confidence,
        "components": [
            {
                "name": row["name"], "score": row["score"], "weight": row["weight"],
                "source": row["source"], "observed_at": row["observed_at"],
                "baseline_sample_count": row["baseline_sample_count"],
                "quality": row["quality"], "included": row["included"],
                "reasons": row.get("reasons", ()),
            }
            for row in sorted(view["component_rows"], key=lambda item: item["name"])
        ],
        "reasons": result.reasons,
        "cautions": result.cautions,
        "available_components": result.available_components,
        "missing_components": result.missing_components,
    }
    encoded = json.dumps(_json_value(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def save_daily_snapshot(connection: sqlite3.Connection, view: dict[str, Any]) -> SnapshotSaveResult:
    """Create, update, or leave unchanged one deterministic daily snapshot."""
    snapshot = _snapshot_values(view)
    component_rows = _component_values(view["component_rows"])
    if {row["component_name"] for row in component_rows} != set(COMPONENT_NAMES):
        raise ValueError("A neural fatigue snapshot requires all five components")

    with connection:
        existing = connection.execute(
            """SELECT * FROM neural_fatigue_daily_snapshots
               WHERE snapshot_date=? AND algorithm_version=?""",
            (snapshot["snapshot_date"], snapshot["algorithm_version"]),
        ).fetchone()
        if existing and existing["source_fingerprint"] == snapshot["source_fingerprint"]:
            return SnapshotSaveResult("unchanged", _snapshot_dict(existing))
        if existing:
            connection.execute(
                """UPDATE neural_fatigue_daily_snapshots SET
                     status=?, burden_score=?, confidence=?, latest_observation_at=?,
                     source_fingerprint=?, computed_at=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    snapshot["status"], snapshot["burden_score"], snapshot["confidence"],
                    snapshot["latest_observation_at"], snapshot["source_fingerprint"],
                    snapshot["computed_at"], existing["id"],
                ),
            )
            snapshot_id, save_status = existing["id"], "updated"
            connection.execute(
                "DELETE FROM neural_fatigue_component_snapshots WHERE daily_snapshot_id=?",
                (snapshot_id,),
            )
        else:
            cursor = connection.execute(
                """INSERT INTO neural_fatigue_daily_snapshots(
                       snapshot_date,algorithm_version,status,burden_score,confidence,
                       latest_observation_at,source_fingerprint,computed_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    snapshot["snapshot_date"], snapshot["algorithm_version"], snapshot["status"],
                    snapshot["burden_score"], snapshot["confidence"], snapshot["latest_observation_at"],
                    snapshot["source_fingerprint"], snapshot["computed_at"],
                ),
            )
            snapshot_id, save_status = cursor.lastrowid, "created"
        _insert_components(connection, snapshot_id, component_rows)
        row = connection.execute(
            "SELECT * FROM neural_fatigue_daily_snapshots WHERE id=?", (snapshot_id,)
        ).fetchone()
    return SnapshotSaveResult(save_status, _snapshot_dict(row))


def get_daily_snapshot(
    connection: sqlite3.Connection, snapshot_date: date | str, algorithm_version: str
) -> dict[str, Any] | None:
    row = connection.execute(
        """SELECT * FROM neural_fatigue_daily_snapshots
           WHERE snapshot_date=? AND algorithm_version=?""",
        (_date_text(snapshot_date), algorithm_version),
    ).fetchone()
    return _snapshot_dict(row) if row else None


def list_daily_snapshots(
    connection: sqlite3.Connection,
    *,
    days: int,
    end_date: date | str,
    algorithm_version: str,
) -> tuple[dict[str, Any], ...]:
    days = _valid_days(days)
    end = date.fromisoformat(_date_text(end_date))
    start = end - timedelta(days=days - 1)
    rows = connection.execute(
        """SELECT * FROM neural_fatigue_daily_snapshots
           WHERE snapshot_date BETWEEN ? AND ? AND algorithm_version=?
           ORDER BY snapshot_date ASC""",
        (start.isoformat(), end.isoformat(), algorithm_version),
    ).fetchall()
    return tuple(_snapshot_dict(row) for row in rows)


def list_component_history(
    connection: sqlite3.Connection,
    *,
    component_name: str,
    days: int,
    end_date: date | str,
    algorithm_version: str,
) -> tuple[dict[str, Any], ...]:
    if component_name not in COMPONENT_NAMES:
        raise ValueError("Unknown neural fatigue component")
    days = _valid_days(days)
    end = date.fromisoformat(_date_text(end_date))
    start = end - timedelta(days=days - 1)
    rows = connection.execute(
        """SELECT d.snapshot_date,d.status,c.component_name,c.score,c.weight,c.source,
                  c.observed_at,c.freshness_hours,c.baseline_sample_count,c.quality,
                  c.included_in_score,c.component_status,c.exclusion_reason
             FROM neural_fatigue_component_snapshots c
             JOIN neural_fatigue_daily_snapshots d ON d.id=c.daily_snapshot_id
            WHERE d.snapshot_date BETWEEN ? AND ? AND d.algorithm_version=?
              AND c.component_name=?
            ORDER BY d.snapshot_date ASC""",
        (start.isoformat(), end.isoformat(), algorithm_version, component_name),
    ).fetchall()
    return tuple(dict(row) for row in rows)


def _snapshot_values(view: dict[str, Any]) -> dict[str, Any]:
    result = view["result"]
    return {
        "snapshot_date": _date_text(view["target_date"]),
        "algorithm_version": result.algorithm_version,
        "status": result.status,
        "burden_score": result.burden_score if result.status == "available" else None,
        "confidence": result.confidence,
        "latest_observation_at": _timestamp(view.get("latest_observation")),
        "source_fingerprint": source_fingerprint(view),
        "computed_at": _timestamp(result.computed_at),
    }


def _component_values(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        included = bool(row["included"])
        score = row["score"]
        component_status = "available" if included else ("missing" if score is None else "excluded")
        reasons = tuple(sorted(str(item) for item in row.get("reasons", ())))
        result.append({
            "component_name": row["name"], "score": score, "weight": row["weight"],
            "source": row["source"], "observed_at": _timestamp(row["observed_at"]),
            "freshness_hours": row["freshness_hours"],
            "baseline_sample_count": row["baseline_sample_count"], "quality": row["quality"],
            "included_in_score": int(included), "component_status": component_status,
            "exclusion_reason": ";".join(reasons) if reasons else None,
        })
    return tuple(sorted(result, key=lambda item: item["component_name"]))


def _insert_components(connection, snapshot_id, component_rows):
    connection.executemany(
        """INSERT INTO neural_fatigue_component_snapshots(
               daily_snapshot_id,component_name,score,weight,source,observed_at,
               freshness_hours,baseline_sample_count,quality,included_in_score,
               component_status,exclusion_reason
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                snapshot_id, row["component_name"], row["score"], row["weight"], row["source"],
                row["observed_at"], row["freshness_hours"], row["baseline_sample_count"],
                row["quality"], row["included_in_score"], row["component_status"],
                row["exclusion_reason"],
            )
            for row in component_rows
        ],
    )


def _snapshot_dict(row) -> dict[str, Any]:
    return dict(row)


def _valid_days(days: int) -> int:
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= MAX_HISTORY_DAYS:
        raise ValueError(f"days must be between 1 and {MAX_HISTORY_DAYS}")
    return days


def _date_text(value: date | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return date.fromisoformat(str(value)[:10]).isoformat()


def _timestamp(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value
