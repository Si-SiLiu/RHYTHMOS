"""Local-first data and deterministic rules for Performance Planner."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.db import connect


BLOCK_TYPES = (
    "deep_work",
    "learning",
    "meeting",
    "exercise",
    "recovery",
    "routine",
    "other",
)
# Exercise sessions are sourced from Polar in the user-facing planner. Keep
# the canonical value above for legacy records and deterministic compatibility,
# but do not offer it as a manually planned block type.
PLANNABLE_BLOCK_TYPES = tuple(block_type for block_type in BLOCK_TYPES if block_type != "exercise")
DEMAND_LEVELS = ("low", "moderate", "high")
PRIORITY_LEVELS = ("low", "medium", "high")
BLOCK_DEFAULTS = {
    "deep_work": {"priority": "medium", "cognitive_demand": "high", "physical_demand": "low"},
    "learning": {"priority": "medium", "cognitive_demand": "high", "physical_demand": "low"},
    "meeting": {"priority": "medium", "cognitive_demand": "moderate", "physical_demand": "low"},
    "exercise": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "high"},
    "recovery": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "low"},
    "routine": {"priority": "medium", "cognitive_demand": "low", "physical_demand": "low"},
    "other": {"priority": "medium", "cognitive_demand": "moderate", "physical_demand": "low"},
}
PLAN_STATUSES = ("draft", "active", "completed", "archived")
BLOCK_STATUSES = ("planned", "in_progress", "completed", "skipped", "postponed")
CHECKPOINT_TYPES = (
    "quick_neural_check",
    "control_speed_check",
    "focus_check",
    "working_memory_check",
)
CHECKPOINT_TRIGGERS = ("before_block", "after_block", "fixed_time", "manual")
CHECKPOINT_STATUSES = ("pending", "completed", "skipped")
RECOMMENDATION_TYPES = (
    "continue_as_planned",
    "shorten_block",
    "add_recovery_break",
    "move_high_demand_block",
    "switch_to_low_demand_task",
    "take_neural_check",
    "resume_after_check",
)
ADAPTIVE_RECOVERY_TITLE = "__adaptive_recovery__"
RULE_ENGINE_VERSION = "performance_planner_rules_v2"
COGNITIVE_CHECK_SUGGESTION_LIMIT = 2
SUGGESTED_COGNITIVE_CHECK_TYPE = "focus_check"
SUGGESTED_COGNITIVE_CHECK_TRIGGER = "before_block"
_COGNITIVE_SUGGESTION_EXCLUDED_TYPES = frozenset({"exercise", "recovery", "routine"})


class PlannerError(RuntimeError):
    """Base error for planner operations."""


class PlannerValidationError(PlannerError, ValueError):
    """Raised when planner input violates the domain contract."""


class PlannerConflictError(PlannerError):
    """Raised when an operation conflicts with an existing record."""


class PlannerNotFoundError(PlannerError):
    """Raised when a requested planner record does not exist."""


def get_block_defaults(block_type: str) -> dict[str, str]:
    """Return input defaults for an existing canonical block type."""
    if block_type not in BLOCK_TYPES:
        raise PlannerValidationError(f"block_type is not recognized: {block_type}")
    return dict(BLOCK_DEFAULTS[block_type])


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _parse_datetime(value: datetime | str, field_name: str) -> datetime:
    try:
        return value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PlannerValidationError(f"{field_name} must be an ISO datetime") from exc


def _iso_date(value: date | str) -> str:
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PlannerValidationError("plan_date must be an ISO date") from exc
    return parsed.isoformat()


def _required_text(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise PlannerValidationError(f"{field_name} must not be empty")
    return normalized


def _plan_timezone(timezone_name: str) -> ZoneInfo:
    normalized = _required_text(timezone_name, "timezone")
    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise PlannerValidationError(f"timezone is not recognized: {normalized}") from exc


def _normalized_plan_datetime(
    value: datetime | str,
    timezone_name: str,
    field_name: str,
) -> datetime:
    """Interpret or convert a timestamp into one plan timezone."""
    timezone = _plan_timezone(timezone_name)
    parsed = _parse_datetime(value, field_name)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone, microsecond=0)
    return parsed.astimezone(timezone).replace(microsecond=0)


def _plan_local_iso(
    value: datetime | str,
    timezone_name: str,
    field_name: str,
) -> str:
    """Return the persisted local wall-clock representation for a plan."""
    return _normalized_plan_datetime(value, timezone_name, field_name).replace(
        tzinfo=None
    ).isoformat()


def _choice(value: str, allowed: Iterable[str], field_name: str) -> str:
    if value not in allowed:
        raise PlannerValidationError(f"{field_name} has an unsupported value: {value}")
    return value


def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


@contextmanager
def _database(db_path: Path | str | None = None):
    connection = connect(db_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _require_record(connection, table: str, key: str, value: str) -> sqlite3.Row:
    row = connection.execute(
        f"SELECT * FROM {table} WHERE {key} = ?",
        (value,),
    ).fetchone()
    if row is None:
        raise PlannerNotFoundError(f"{table} record not found: {value}")
    return row


def create_plan(
    plan_date: date | str,
    title: str,
    timezone: str,
    *,
    status: str = "active",
    plan_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    plan_id = plan_id or str(uuid.uuid4())
    values = (
        plan_id,
        _iso_date(plan_date),
        _required_text(title, "title"),
        _choice(status, PLAN_STATUSES, "status"),
        _plan_timezone(timezone).key,
    )
    try:
        with _database(db_path) as connection:
            connection.execute(
                """
                INSERT INTO performance_plans(
                    plan_id, plan_date, title, status, timezone
                ) VALUES(?, ?, ?, ?, ?)
                """,
                values,
            )
            return dict(
                _require_record(connection, "performance_plans", "plan_id", plan_id)
            )
    except sqlite3.IntegrityError as exc:
        if "plan_date" in str(exc):
            raise PlannerConflictError("a plan already exists for this date") from exc
        raise


def get_plan(
    plan_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    with _database(db_path) as connection:
        return _row(
            connection.execute(
                "SELECT * FROM performance_plans WHERE plan_id = ?",
                (plan_id,),
            ).fetchone()
        )


def get_plan_for_date(
    plan_date: date | str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    with _database(db_path) as connection:
        return _row(
            connection.execute(
                "SELECT * FROM performance_plans WHERE plan_date = ?",
                (_iso_date(plan_date),),
            ).fetchone()
        )


def list_plans(*, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM performance_plans ORDER BY plan_date DESC"
            ).fetchall()
        ]


def update_plan(
    plan_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    timezone: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if title is not None:
        changes["title"] = _required_text(title, "title")
    if status is not None:
        changes["status"] = _choice(status, PLAN_STATUSES, "status")
    if timezone is not None:
        changes["timezone"] = _plan_timezone(timezone).key
    with _database(db_path) as connection:
        _require_record(connection, "performance_plans", "plan_id", plan_id)
        if changes:
            changes["updated_at"] = _now().isoformat()
            columns = ", ".join(f"{key} = ?" for key in changes)
            connection.execute(
                f"UPDATE performance_plans SET {columns} WHERE plan_id = ?",
                (*changes.values(), plan_id),
            )
        return dict(
            _require_record(connection, "performance_plans", "plan_id", plan_id)
        )


def delete_plan(plan_id: str, *, db_path: Path | str | None = None) -> bool:
    with _database(db_path) as connection:
        deleted = connection.execute(
            "DELETE FROM performance_plans WHERE plan_id = ?",
            (plan_id,),
        ).rowcount
        return bool(deleted)


def _validate_block_times(
    connection: sqlite3.Connection,
    plan_id: str,
    planned_start: datetime | str,
    planned_end: datetime | str,
    *,
    excluded_block_id: str | None = None,
    allow_overlap: bool = False,
) -> tuple[str, str]:
    plan = _require_record(connection, "performance_plans", "plan_id", plan_id)
    start = _plan_local_iso(planned_start, plan["timezone"], "planned_start")
    end = _plan_local_iso(planned_end, plan["timezone"], "planned_end")
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    if end_dt <= start_dt:
        raise PlannerValidationError("planned_end must be after planned_start")
    if start_dt.date().isoformat() != plan["plan_date"]:
        raise PlannerValidationError("block start must be on the plan date")
    if end_dt.date().isoformat() != plan["plan_date"]:
        raise PlannerValidationError("block end must be on the plan date")
    if allow_overlap:
        return start, end
    rows = connection.execute(
        """
        SELECT block_id, planned_start, planned_end
        FROM performance_plan_blocks
        WHERE plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    for row in rows:
        if row["block_id"] == excluded_block_id:
            continue
        existing_start = datetime.fromisoformat(row["planned_start"])
        existing_end = datetime.fromisoformat(row["planned_end"])
        if start_dt < existing_end and end_dt > existing_start:
            raise PlannerConflictError(
                f"block overlaps existing block: {row['block_id']}"
            )
    return start, end


def add_block(
    plan_id: str,
    title: str,
    block_type: str,
    planned_start: datetime | str,
    planned_end: datetime | str,
    *,
    priority: str = "medium",
    cognitive_demand: str = "moderate",
    physical_demand: str = "moderate",
    context: str | None = None,
    notes: str | None = None,
    sort_order: int | None = None,
    status: str = "planned",
    block_id: str | None = None,
    allow_overlap: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    block_id = block_id or str(uuid.uuid4())
    with _database(db_path) as connection:
        start, end = _validate_block_times(
            connection,
            plan_id,
            planned_start,
            planned_end,
            allow_overlap=allow_overlap,
        )
        if sort_order is None:
            sort_order = connection.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) + 1
                FROM performance_plan_blocks WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO performance_plan_blocks(
                block_id, plan_id, title, block_type, planned_start, planned_end,
                priority, cognitive_demand, physical_demand, context, notes,
                sort_order, status
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block_id,
                plan_id,
                _required_text(title, "title"),
                _choice(block_type, BLOCK_TYPES, "block_type"),
                start,
                end,
                _choice(priority, PRIORITY_LEVELS, "priority"),
                _choice(cognitive_demand, DEMAND_LEVELS, "cognitive_demand"),
                _choice(physical_demand, DEMAND_LEVELS, "physical_demand"),
                context.strip() if context else None,
                notes.strip() if notes else None,
                int(sort_order),
                _choice(status, BLOCK_STATUSES, "status"),
            ),
        )
        return dict(
            _require_record(
                connection,
                "performance_plan_blocks",
                "block_id",
                block_id,
            )
        )


def list_blocks(
    plan_id: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM performance_plan_blocks
                WHERE plan_id = ?
                ORDER BY sort_order, planned_start, created_at
                """,
                (plan_id,),
            ).fetchall()
        ]


def _update_block_in_connection(
    connection: sqlite3.Connection,
    block_id: str,
    *,
    title: str | None = None,
    block_type: str | None = None,
    planned_start: datetime | str | None = None,
    planned_end: datetime | str | None = None,
    priority: str | None = None,
    cognitive_demand: str | None = None,
    physical_demand: str | None = None,
    context: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    allow_overlap: bool = False,
) -> dict[str, Any]:
    current = _require_record(
        connection,
        "performance_plan_blocks",
        "block_id",
        block_id,
    )
    start, end = _validate_block_times(
        connection,
        current["plan_id"],
        planned_start or current["planned_start"],
        planned_end or current["planned_end"],
        excluded_block_id=block_id,
        allow_overlap=allow_overlap,
    )
    changes: dict[str, Any] = {
        "planned_start": start,
        "planned_end": end,
    }
    validators = {
        "title": (
            title,
            lambda value: _required_text(value, "title"),
        ),
        "block_type": (
            block_type,
            lambda value: _choice(value, BLOCK_TYPES, "block_type"),
        ),
        "priority": (
            priority,
            lambda value: _choice(value, PRIORITY_LEVELS, "priority"),
        ),
        "cognitive_demand": (
            cognitive_demand,
            lambda value: _choice(value, DEMAND_LEVELS, "cognitive_demand"),
        ),
        "physical_demand": (
            physical_demand,
            lambda value: _choice(value, DEMAND_LEVELS, "physical_demand"),
        ),
        "status": (
            status,
            lambda value: _choice(value, BLOCK_STATUSES, "status"),
        ),
    }
    for field, (value, validator) in validators.items():
        if value is not None:
            changes[field] = validator(value)
    if context is not None:
        changes["context"] = context.strip() or None
    if notes is not None:
        changes["notes"] = notes.strip() or None
    changes["updated_at"] = _now().isoformat()
    assignments = ", ".join(f"{key} = ?" for key in changes)
    connection.execute(
        f"UPDATE performance_plan_blocks SET {assignments} WHERE block_id = ?",
        (*changes.values(), block_id),
    )
    return dict(
        _require_record(
            connection,
            "performance_plan_blocks",
            "block_id",
            block_id,
        )
    )


def update_block(
    block_id: str,
    *,
    title: str | None = None,
    block_type: str | None = None,
    planned_start: datetime | str | None = None,
    planned_end: datetime | str | None = None,
    priority: str | None = None,
    cognitive_demand: str | None = None,
    physical_demand: str | None = None,
    context: str | None = None,
    notes: str | None = None,
    status: str | None = None,
    allow_overlap: bool = False,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    with _database(db_path) as connection:
        return _update_block_in_connection(
            connection,
            block_id,
            title=title,
            block_type=block_type,
            planned_start=planned_start,
            planned_end=planned_end,
            priority=priority,
            cognitive_demand=cognitive_demand,
            physical_demand=physical_demand,
            context=context,
            notes=notes,
            status=status,
            allow_overlap=allow_overlap,
        )


def delete_block(block_id: str, *, db_path: Path | str | None = None) -> bool:
    with _database(db_path) as connection:
        return bool(
            connection.execute(
                "DELETE FROM performance_plan_blocks WHERE block_id = ?",
                (block_id,),
            ).rowcount
        )


def reorder_blocks(
    plan_id: str,
    ordered_block_ids: list[str],
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        existing = [
            row[0]
            for row in connection.execute(
                "SELECT block_id FROM performance_plan_blocks WHERE plan_id = ?",
                (plan_id,),
            ).fetchall()
        ]
        if len(ordered_block_ids) != len(set(ordered_block_ids)):
            raise PlannerValidationError("ordered block ids must be unique")
        if set(existing) != set(ordered_block_ids):
            raise PlannerValidationError("ordered block ids must exactly match the plan")
        timestamp = _now().isoformat()
        for sort_order, block_id in enumerate(ordered_block_ids):
            connection.execute(
                """
                UPDATE performance_plan_blocks
                SET sort_order = ?, updated_at = ?
                WHERE block_id = ? AND plan_id = ?
                """,
                (sort_order, timestamp, block_id, plan_id),
            )
    return list_blocks(plan_id, db_path=db_path)


def transition_block(
    block_id: str,
    status: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    return update_block(block_id, status=status, db_path=db_path)


def create_checkpoint(
    plan_id: str,
    checkpoint_type: str,
    scheduled_at: datetime | str,
    trigger_type: str,
    *,
    related_block_id: str | None = None,
    status: str = "pending",
    checkpoint_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    checkpoint_id = checkpoint_id or str(uuid.uuid4())
    with _database(db_path) as connection:
        plan = _require_record(
            connection,
            "performance_plans",
            "plan_id",
            plan_id,
        )
        if related_block_id:
            block = _require_record(
                connection,
                "performance_plan_blocks",
                "block_id",
                related_block_id,
            )
            if block["plan_id"] != plan_id:
                raise PlannerValidationError("related block belongs to another plan")
        scheduled = _plan_local_iso(
            scheduled_at,
            plan["timezone"],
            "scheduled_at",
        )
        if datetime.fromisoformat(scheduled).date().isoformat() != plan["plan_date"]:
            raise PlannerValidationError("checkpoint must be on the plan date")
        connection.execute(
            """
            INSERT INTO performance_checkpoints(
                checkpoint_id, plan_id, related_block_id, checkpoint_type,
                scheduled_at, trigger_type, status
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                plan_id,
                related_block_id,
                _choice(checkpoint_type, CHECKPOINT_TYPES, "checkpoint_type"),
                scheduled,
                _choice(trigger_type, CHECKPOINT_TRIGGERS, "trigger_type"),
                _choice(status, CHECKPOINT_STATUSES, "status"),
            ),
        )
        return dict(
            _require_record(
                connection,
                "performance_checkpoints",
                "checkpoint_id",
                checkpoint_id,
            )
        )


def list_checkpoints(
    plan_id: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM performance_checkpoints
                WHERE plan_id = ?
                ORDER BY scheduled_at, created_at
                """,
                (plan_id,),
            ).fetchall()
        ]


def link_checkpoint_run(
    checkpoint_id: str,
    cognitive_run_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    run_id = _required_text(cognitive_run_id, "cognitive_run_id")
    with _database(db_path) as connection:
        checkpoint = _require_record(
            connection,
            "performance_checkpoints",
            "checkpoint_id",
            checkpoint_id,
        )
        if checkpoint["cognitive_run_id"] == run_id:
            return dict(checkpoint)
        if checkpoint["cognitive_run_id"] is not None:
            raise PlannerConflictError("checkpoint is already linked to another run")
        run = connection.execute(
            """
            SELECT s.id AS run_id, s.training_plan, s.session_mode,
                   s.started_at, s.completed_at, s.total_duration_seconds,
                   AVG(r.accuracy) AS average_accuracy,
                   AVG(r.median_rt_ms) AS median_rt_ms,
                   MAX(r.difficulty_end) AS highest_difficulty,
                   COUNT(r.id) AS task_count
            FROM cognitive_training_sessions s
            LEFT JOIN cognitive_training_task_results r
              ON r.session_id = s.id
            WHERE s.id = ? AND s.completed = 1
            GROUP BY s.id
            """,
            (run_id,),
        ).fetchone()
        if run is None:
            raise PlannerNotFoundError(f"cognitive run not found: {run_id}")
        try:
            timestamp = _now().isoformat()
            result_snapshot_json = json.dumps(
                dict(run),
                ensure_ascii=False,
                sort_keys=True,
            )
            connection.execute(
                """
                UPDATE performance_checkpoints
                SET cognitive_run_id = ?, status = 'completed',
                    result_snapshot_json = ?, completed_at = ?, updated_at = ?
                WHERE checkpoint_id = ?
                """,
                (
                    run_id,
                    result_snapshot_json,
                    timestamp,
                    timestamp,
                    checkpoint_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise PlannerConflictError("cognitive run is linked to another checkpoint") from exc
        return dict(
            _require_record(
                connection,
                "performance_checkpoints",
                "checkpoint_id",
                checkpoint_id,
            )
        )


def update_checkpoint_status(
    checkpoint_id: str,
    status: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    normalized = _choice(status, CHECKPOINT_STATUSES, "status")
    with _database(db_path) as connection:
        _require_record(
            connection,
            "performance_checkpoints",
            "checkpoint_id",
            checkpoint_id,
        )
        timestamp = _now().isoformat()
        completed_at = timestamp if normalized == "completed" else None
        connection.execute(
            """
            UPDATE performance_checkpoints
            SET status = ?, completed_at = ?, updated_at = ?
            WHERE checkpoint_id = ?
            """,
            (normalized, completed_at, timestamp, checkpoint_id),
        )
        return dict(
            _require_record(
                connection,
                "performance_checkpoints",
                "checkpoint_id",
                checkpoint_id,
            )
        )


def delete_checkpoint(
    checkpoint_id: str,
    *,
    db_path: Path | str | None = None,
) -> bool:
    with _database(db_path) as connection:
        return bool(
            connection.execute(
                "DELETE FROM performance_checkpoints WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).rowcount
        )


def _cognitive_suggestion_candidates(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return explicit high-cognitive blocks in the order worth sampling."""
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    candidates = [
        block for block in blocks
        if block["cognitive_demand"] == "high"
        and block["block_type"] not in _COGNITIVE_SUGGESTION_EXCLUDED_TYPES
        and block["status"] in {"planned", "in_progress"}
    ]
    return sorted(
        candidates,
        key=lambda block: (
            datetime.fromisoformat(block["planned_start"]),
            priority_rank[block["priority"]],
            -(
                datetime.fromisoformat(block["planned_end"])
                - datetime.fromisoformat(block["planned_start"])
            ).total_seconds(),
            block["sort_order"],
        ),
    )


def build_daily_cognitive_check_suggestions(
    plan_id: str,
    *,
    max_suggestions: int = COGNITIVE_CHECK_SUGGESTION_LIMIT,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Build up to two transparent, before-task cognitive check suggestions.

    This is read-only: it never creates checkpoints, changes a plan, or starts
    a cognitive run. A checkpoint is persisted only after the user starts or
    skips a specific suggestion.
    """
    if max_suggestions < 1:
        return []
    with _database(db_path) as connection:
        plan = _require_record(connection, "performance_plans", "plan_id", plan_id)
        blocks = [
            dict(row)
            for row in connection.execute(
                """SELECT * FROM performance_plan_blocks
                   WHERE plan_id=? ORDER BY sort_order, planned_start""",
                (plan_id,),
            ).fetchall()
        ]
        checkpoints = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM performance_checkpoints WHERE plan_id=?",
                (plan_id,),
            ).fetchall()
        ]
        completed_run_count = connection.execute(
            """SELECT COUNT(*) FROM cognitive_training_sessions
               WHERE substr(started_at, 1, 10)=? AND completed=1""",
            (plan["plan_date"],),
        ).fetchone()[0]

    candidates = _cognitive_suggestion_candidates(blocks)
    candidate_ids = {block["block_id"] for block in candidates}
    recorded = [
        checkpoint for checkpoint in checkpoints
        if checkpoint["related_block_id"] in candidate_ids
        and checkpoint["checkpoint_type"] == SUGGESTED_COGNITIVE_CHECK_TYPE
        and checkpoint["trigger_type"] == SUGGESTED_COGNITIVE_CHECK_TRIGGER
    ]
    recorded_block_ids = {checkpoint["related_block_id"] for checkpoint in recorded}
    remaining_budget = max(0, max_suggestions - max(len(recorded), completed_run_count))
    suggestions = []
    for block in candidates:
        if block["block_id"] in recorded_block_ids or remaining_budget <= 0:
            continue
        starts_at = datetime.fromisoformat(block["planned_start"])
        suggested_at = max(
            starts_at - timedelta(minutes=5),
            datetime.combine(starts_at.date(), datetime.min.time()),
        )
        suggestions.append({
            "suggestion_id": f"before:{block['block_id']}",
            "plan_id": plan_id,
            "related_block_id": block["block_id"],
            "block_title": block["title"],
            "block_type": block["block_type"],
            "scheduled_at": suggested_at.isoformat(),
            "planned_start": block["planned_start"],
            "checkpoint_type": SUGGESTED_COGNITIVE_CHECK_TYPE,
            "trigger_type": SUGGESTED_COGNITIVE_CHECK_TRIGGER,
        })
        remaining_budget -= 1
    return suggestions


def ensure_suggested_cognitive_checkpoint(
    plan_id: str,
    related_block_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create the deterministic before-task checkpoint once, on user action."""
    suggestions = build_daily_cognitive_check_suggestions(plan_id, db_path=db_path)
    suggestion = next(
        (item for item in suggestions if item["related_block_id"] == related_block_id),
        None,
    )
    if suggestion is None:
        with _database(db_path) as connection:
            checkpoint = connection.execute(
                """SELECT * FROM performance_checkpoints
                   WHERE plan_id=? AND related_block_id=?
                     AND checkpoint_type=? AND trigger_type=?
                   ORDER BY created_at DESC LIMIT 1""",
                (
                    plan_id,
                    related_block_id,
                    SUGGESTED_COGNITIVE_CHECK_TYPE,
                    SUGGESTED_COGNITIVE_CHECK_TRIGGER,
                ),
            ).fetchone()
            if checkpoint is not None:
                return dict(checkpoint)
        raise PlannerNotFoundError("cognitive check suggestion not found")
    return create_checkpoint(
        plan_id,
        suggestion["checkpoint_type"],
        suggestion["scheduled_at"],
        suggestion["trigger_type"],
        related_block_id=related_block_id,
        db_path=db_path,
    )


def dismiss_suggested_cognitive_checkpoint(
    plan_id: str,
    related_block_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Persist a user's today-only skip as a checkpoint without a run."""
    checkpoint = ensure_suggested_cognitive_checkpoint(
        plan_id,
        related_block_id,
        db_path=db_path,
    )
    if checkpoint["status"] == "skipped":
        return checkpoint
    return update_checkpoint_status(
        checkpoint["checkpoint_id"],
        "skipped",
        db_path=db_path,
    )


def build_source_snapshot(
    plan_id: str,
    *,
    now: datetime | str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    with _database(db_path) as connection:
        plan = _require_record(connection, "performance_plans", "plan_id", plan_id)
        current_aware = _normalized_plan_datetime(
            now or _now(),
            plan["timezone"],
            "now",
        )
        current = current_aware.replace(tzinfo=None)
        blocks = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM performance_plan_blocks
                WHERE plan_id = ? ORDER BY sort_order, planned_start
                """,
                (plan_id,),
            ).fetchall()
        ]
        checkpoints = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM performance_checkpoints
                WHERE plan_id = ? ORDER BY scheduled_at
                """,
                (plan_id,),
            ).fetchall()
        ]
        recovery = _row(
            connection.execute(
                """
                SELECT recovery_score, readiness_score
                FROM recovery_scores WHERE date = ?
                """,
                (plan["plan_date"],),
            ).fetchone()
        )
        cognitive_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT s.id AS run_id, s.training_plan, s.started_at,
                       s.completed_at, s.timezone,
                       AVG(r.accuracy) AS average_accuracy,
                       AVG(r.median_rt_ms) AS median_rt_ms,
                       MAX(r.difficulty_end) AS highest_difficulty
                FROM cognitive_training_sessions s
                LEFT JOIN cognitive_training_task_results r
                  ON r.session_id = s.id
                WHERE s.completed = 1
                GROUP BY s.id
                """
            ).fetchall()
        ]

    cognitive_candidates: list[tuple[datetime, dict[str, Any]]] = []
    for row in cognitive_rows:
        try:
            started_at = _normalized_plan_datetime(
                row["started_at"],
                row["timezone"],
                "cognitive started_at",
            ).astimezone(current_aware.tzinfo)
        except PlannerValidationError:
            continue
        if started_at <= current_aware:
            row.pop("timezone", None)
            cognitive_candidates.append((started_at, row))
    cognitive = (
        max(cognitive_candidates, key=lambda item: item[0])[1]
        if cognitive_candidates
        else None
    )

    active_blocks = [
        block
        for block in blocks
        if block["status"] not in {"skipped", "postponed"}
    ]
    completed_blocks = [
        block for block in active_blocks if block["status"] == "completed"
    ]
    total_minutes = sum(
        (
            datetime.fromisoformat(block["planned_end"])
            - datetime.fromisoformat(block["planned_start"])
        ).total_seconds()
        / 60
        for block in active_blocks
    )
    completed_minutes = sum(
        (
            datetime.fromisoformat(block["planned_end"])
            - datetime.fromisoformat(block["planned_start"])
        ).total_seconds()
        / 60
        for block in completed_blocks
    )
    current_block = next(
        (
            block
            for block in active_blocks
            if datetime.fromisoformat(block["planned_start"])
            <= current
            < datetime.fromisoformat(block["planned_end"])
        ),
        None,
    )
    upcoming = next(
        (
            block
            for block in active_blocks
            if block["status"] == "planned"
            and datetime.fromisoformat(block["planned_start"]) >= current
        ),
        None,
    )
    delayed = [
        block
        for block in active_blocks
        if block["status"] == "planned"
        and datetime.fromisoformat(block["planned_end"]) < current
    ]
    last_recovery_end: datetime | None = None
    continuous_work_minutes = 0.0
    for block in active_blocks:
        block_start = datetime.fromisoformat(block["planned_start"])
        block_end = datetime.fromisoformat(block["planned_end"])
        if block_start > current:
            break
        effective_end = min(block_end, current)
        if block["block_type"] == "recovery":
            last_recovery_end = effective_end
            continuous_work_minutes = 0.0
        elif block["status"] in {"completed", "in_progress"} or block_start <= current:
            if last_recovery_end is None or block_start >= last_recovery_end:
                continuous_work_minutes += max(
                    0,
                    (effective_end - block_start).total_seconds() / 60,
                )
    signal_count = sum(
        value is not None
        for value in (
            recovery.get("recovery_score") if recovery else None,
            recovery.get("readiness_score") if recovery else None,
            cognitive.get("average_accuracy") if cognitive else None,
        )
    )
    sufficiency = (
        "sufficient" if signal_count >= 2 else "partial" if signal_count == 1 else "insufficient"
    )
    return {
        "plan_id": plan_id,
        "plan_date": plan["plan_date"],
        "generated_at": current.isoformat(),
        "recovery": recovery,
        "latest_cognitive": cognitive,
        "current_block_id": current_block["block_id"] if current_block else None,
        "next_block_id": upcoming["block_id"] if upcoming else None,
        "delayed_block_ids": [block["block_id"] for block in delayed],
        "pending_checkpoint_ids": [
            item["checkpoint_id"]
            for item in checkpoints
            if item["status"] == "pending"
        ],
        "overdue_checkpoint_ids": [
            item["checkpoint_id"]
            for item in checkpoints
            if item["status"] == "pending"
            and datetime.fromisoformat(item["scheduled_at"]) <= current
        ],
        "continuous_work_minutes": round(continuous_work_minutes, 2),
        "total_planned_minutes": round(total_minutes, 2),
        "completed_minutes": round(completed_minutes, 2),
        "completed_block_count": len(completed_blocks),
        "total_block_count": len(active_blocks),
        "high_cognitive_minutes": round(
            sum(
                (
                    datetime.fromisoformat(block["planned_end"])
                    - datetime.fromisoformat(block["planned_start"])
                ).total_seconds()
                / 60
                for block in active_blocks
                if block["cognitive_demand"] == "high"
            ),
            2,
        ),
        "recovery_minutes": round(
            sum(
                (
                    datetime.fromisoformat(block["planned_end"])
                    - datetime.fromisoformat(block["planned_start"])
                ).total_seconds()
                / 60
                for block in active_blocks
                if block["block_type"] == "recovery"
            ),
            2,
        ),
        "data_sufficiency": sufficiency,
    }


def _recommendation(
    recommendation_type: str,
    severity: str,
    rationale: str,
    related_block_id: str | None = None,
) -> dict[str, Any]:
    return {
        "recommendation_type": recommendation_type,
        "severity": severity,
        "title_key": f"performance_planner.recommendations.{recommendation_type}.title",
        "message_key": f"performance_planner.recommendations.{recommendation_type}.message",
        "rationale": rationale,
        "related_block_id": related_block_id,
    }


def _shortened_block_end(block: dict[str, Any]) -> datetime | None:
    """Return a strictly earlier local end, or None when no reduction exists."""
    start = datetime.fromisoformat(block["planned_start"])
    end = datetime.fromisoformat(block["planned_end"])
    duration_minutes = int((end - start).total_seconds() / 60)
    shortened_minutes = max(1, int(duration_minutes * 0.75))
    shortened = start + timedelta(minutes=shortened_minutes)
    return shortened if shortened < end else None


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _recommendation_fingerprint(
    plan_id: str,
    recommendation: dict[str, Any],
    generated_at: str,
    snapshot: dict[str, Any],
) -> str:
    payload = {
        "generated_at": generated_at,
        "plan_id": plan_id,
        "recommendation_type": recommendation["recommendation_type"],
        "related_block_id": recommendation["related_block_id"],
        "rule_engine_version": RULE_ENGINE_VERSION,
        "severity": recommendation["severity"],
        "source_snapshot": snapshot,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def generate_recommendations(
    plan_id: str,
    *,
    now: datetime | str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate deterministic local rules without changing the plan or blocks."""
    snapshot = build_source_snapshot(plan_id, now=now, db_path=db_path)
    blocks = {block["block_id"]: block for block in list_blocks(plan_id, db_path=db_path)}
    current_or_next_id = snapshot["current_block_id"] or snapshot["next_block_id"]
    candidate = blocks.get(current_or_next_id)
    recovery = snapshot["recovery"] or {}
    cognitive = snapshot["latest_cognitive"] or {}
    recommendations: list[dict[str, Any]] = []

    low_recovery = any(
        value is not None and value < 50
        for value in (
            recovery.get("recovery_score"),
            recovery.get("readiness_score"),
        )
    )
    if low_recovery and candidate and candidate["cognitive_demand"] == "high":
        recommendations.append(
            _recommendation(
                "move_high_demand_block",
                "high",
                "low_recovery_high_cognitive_demand",
                candidate["block_id"],
            )
        )
    if snapshot["continuous_work_minutes"] >= 120:
        recommendations.append(
            _recommendation(
                "add_recovery_break",
                "warning",
                "continuous_work_threshold_reached",
                snapshot["current_block_id"],
            )
        )
    if snapshot["delayed_block_ids"]:
        delayed_id = snapshot["delayed_block_ids"][0]
        delayed_block = blocks.get(delayed_id)
        if delayed_block and _shortened_block_end(delayed_block) is not None:
            recommendations.append(
                _recommendation(
                    "shorten_block",
                    "warning",
                    "planned_block_is_delayed",
                    delayed_id,
                )
            )
    accuracy = cognitive.get("average_accuracy")
    if accuracy is not None and accuracy < 0.70 and candidate:
        recommendations.append(
            _recommendation(
                "switch_to_low_demand_task",
                "warning",
                "latest_cognitive_accuracy_below_threshold",
                candidate["block_id"],
            )
        )
    if snapshot["overdue_checkpoint_ids"]:
        recommendations.append(
            _recommendation(
                "take_neural_check",
                "info",
                "scheduled_checkpoint_is_due",
                candidate["block_id"] if candidate else None,
            )
        )
    elif accuracy is not None and accuracy >= 0.85:
        recommendations.append(
            _recommendation(
                "resume_after_check",
                "info",
                "latest_cognitive_accuracy_supports_resuming",
                candidate["block_id"] if candidate else None,
            )
        )
    if not recommendations:
        fallback = (
            "take_neural_check"
            if snapshot["data_sufficiency"] == "insufficient"
            else "continue_as_planned"
        )
        recommendations.append(
            _recommendation(
                fallback,
                "info",
                (
                    "insufficient_signal_data"
                    if fallback == "take_neural_check"
                    else "no_adaptation_rule_triggered"
                ),
                candidate["block_id"] if candidate else None,
            )
        )

    generated_at = snapshot["generated_at"]
    snapshot_json = _canonical_json(snapshot)
    stored: list[dict[str, Any]] = []
    with _database(db_path) as connection:
        _require_record(connection, "performance_plans", "plan_id", plan_id)
        seen_fingerprints: set[str] = set()
        for item in recommendations:
            fingerprint = _recommendation_fingerprint(
                plan_id,
                item,
                generated_at,
                snapshot,
            )
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            recommendation_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT OR IGNORE INTO performance_recommendations(
                    recommendation_id, plan_id, related_block_id,
                    recommendation_type, severity, title_key, message_key,
                    rationale, source_snapshot_json, data_sufficiency,
                    generated_at, recommendation_fingerprint
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    plan_id,
                    item["related_block_id"],
                    item["recommendation_type"],
                    item["severity"],
                    item["title_key"],
                    item["message_key"],
                    item["rationale"],
                    snapshot_json,
                    snapshot["data_sufficiency"],
                    generated_at,
                    fingerprint,
                ),
            )
            stored.append(
                dict(
                    connection.execute(
                        """
                        SELECT * FROM performance_recommendations
                        WHERE recommendation_fingerprint = ?
                        """,
                        (fingerprint,),
                    ).fetchone()
                )
            )
    return stored


def list_recommendations(
    plan_id: str,
    *,
    latest_only: bool = False,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        query = """
            SELECT * FROM performance_recommendations
            WHERE plan_id = ?
        """
        parameters: tuple[Any, ...] = (plan_id,)
        if latest_only:
            query += """
                AND generated_at = (
                    SELECT MAX(generated_at)
                    FROM performance_recommendations
                    WHERE plan_id = ?
                )
            """
            parameters = (plan_id, plan_id)
        query += " ORDER BY generated_at DESC, created_at DESC"
        return [
            dict(row)
            for row in connection.execute(query, parameters).fetchall()
        ]


def acknowledge_recommendation(
    recommendation_id: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    with _database(db_path) as connection:
        row = _require_record(
            connection,
            "performance_recommendations",
            "recommendation_id",
            recommendation_id,
        )
        if row["acknowledged_at"] is None:
            connection.execute(
                """
                UPDATE performance_recommendations
                SET acknowledged_at = ?
                WHERE recommendation_id = ?
                """,
                (_now().isoformat(), recommendation_id),
            )
        return dict(
            _require_record(
                connection,
                "performance_recommendations",
                "recommendation_id",
                recommendation_id,
            )
        )


def apply_recommendation(
    recommendation_id: str,
    *,
    confirmed: bool,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Apply a supported plan change only after an explicit confirmation."""
    if not confirmed:
        raise PlannerValidationError("explicit confirmation is required")
    with _database(db_path) as connection:
        recommendation = _require_record(
            connection,
            "performance_recommendations",
            "recommendation_id",
            recommendation_id,
        )
        if recommendation["applied_at"] is not None:
            return dict(recommendation)
        block = None
        if recommendation["related_block_id"]:
            block = _require_record(
                connection,
                "performance_plan_blocks",
                "block_id",
                recommendation["related_block_id"],
            )
        recommendation_type = recommendation["recommendation_type"]
        timestamp = _now().isoformat()
        if recommendation_type == "shorten_block" and block:
            shortened = _shortened_block_end(dict(block))
            if shortened is None:
                raise PlannerValidationError(
                    "shorten recommendation has no applicable reduction"
                )
            _update_block_in_connection(
                connection,
                block["block_id"],
                planned_end=shortened,
            )
        elif recommendation_type == "move_high_demand_block" and block:
            connection.execute(
                """
                UPDATE performance_plan_blocks
                SET status = 'postponed', updated_at = ? WHERE block_id = ?
                """,
                (timestamp, block["block_id"]),
            )
        elif recommendation_type == "switch_to_low_demand_task" and block:
            connection.execute(
                """
                UPDATE performance_plan_blocks
                SET cognitive_demand = 'low', updated_at = ? WHERE block_id = ?
                """,
                (timestamp, block["block_id"]),
            )
        elif recommendation_type == "add_recovery_break" and block:
            start = datetime.fromisoformat(block["planned_end"])
            end = start + timedelta(minutes=15)
            _validate_block_times(
                connection,
                recommendation["plan_id"],
                start,
                end,
            )
            next_order = connection.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) + 1
                FROM performance_plan_blocks WHERE plan_id = ?
                """,
                (recommendation["plan_id"],),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO performance_plan_blocks(
                    block_id, plan_id, title, block_type, planned_start,
                    planned_end, priority, cognitive_demand, physical_demand,
                    sort_order, status
                ) VALUES(?, ?, ?, 'recovery', ?, ?, 'medium', 'low', 'low', ?, 'planned')
                """,
                (
                    str(uuid.uuid4()),
                    recommendation["plan_id"],
                    ADAPTIVE_RECOVERY_TITLE,
                    start.isoformat(),
                    end.isoformat(),
                    next_order,
                ),
            )
        connection.execute(
            """
            UPDATE performance_recommendations
            SET acknowledged_at = COALESCE(acknowledged_at, ?), applied_at = ?
            WHERE recommendation_id = ?
            """,
            (timestamp, timestamp, recommendation_id),
        )
        return dict(
            _require_record(
                connection,
                "performance_recommendations",
                "recommendation_id",
                recommendation_id,
            )
        )


def get_timeline_summary(
    plan_id: str,
    *,
    now: datetime | str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    snapshot = build_source_snapshot(plan_id, now=now, db_path=db_path)
    total = snapshot["total_block_count"]
    snapshot["completion_percent"] = round(
        snapshot["completed_block_count"] / total * 100 if total else 0,
        1,
    )
    snapshot["recommendation_count"] = len(
        list_recommendations(plan_id, latest_only=True, db_path=db_path)
    )
    return snapshot


def get_progress_lab_rows(
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Stable read-only query surface for a future Progress Lab integration."""
    clauses: list[str] = []
    parameters: list[str] = []
    if start_date is not None:
        clauses.append("p.plan_date >= ?")
        parameters.append(_iso_date(start_date))
    if end_date is not None:
        clauses.append("p.plan_date <= ?")
        parameters.append(_iso_date(end_date))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _database(db_path) as connection:
        return [
            dict(row)
            for row in connection.execute(
                f"""
                SELECT p.plan_id, p.plan_date, p.title, p.status,
                       COUNT(DISTINCT b.block_id) AS block_count,
                       COUNT(DISTINCT CASE WHEN b.status = 'completed'
                           THEN b.block_id END) AS completed_block_count,
                       COUNT(DISTINCT c.checkpoint_id) AS checkpoint_count,
                       COUNT(DISTINCT r.recommendation_id) AS recommendation_count
                FROM performance_plans p
                LEFT JOIN performance_plan_blocks b ON b.plan_id = p.plan_id
                LEFT JOIN performance_checkpoints c ON c.plan_id = p.plan_id
                LEFT JOIN performance_recommendations r ON r.plan_id = p.plan_id
                {where}
                GROUP BY p.plan_id
                ORDER BY p.plan_date DESC
                """,
                parameters,
            ).fetchall()
        ]
