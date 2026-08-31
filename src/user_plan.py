"""Independent weekly user-intent plans and plan-vs-execution comparison."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.db import connect


WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
PLAN_CATEGORIES = ("work", "study", "training", "meal", "recovery", "personal", "other")
EVENT_COLOR_KEYS = ("blue", "green", "amber", "rose", "purple", "teal", "slate", "coral")
EVENT_COLOR_OVERRIDES = {
    # Keep listening lessons visually distinct from the indoor-strength
    # training cards even when their title hashes collide.
    "听力": "purple",
    "listening": "purple",
}
NUTRITION_RECIPE_MARKERS = (
    "__nutrition_auto_recipe__:",
    "__nutrition_manual_recipe__:",
)


def event_color_key(title: object) -> str:
    """Return a deterministic, title-based colour key for weekly plan cards."""
    normalized = " ".join(str(title or "").casefold().split())
    for token, color_key in EVENT_COLOR_OVERRIDES.items():
        if token in normalized:
            return color_key
    digest = sha256(normalized.encode("utf-8")).digest()
    return EVENT_COLOR_KEYS[int.from_bytes(digest[:4], "big") % len(EVENT_COLOR_KEYS)]


def _time_ranges_overlap(left: tuple[str, str], right: tuple[str, str]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def merge_plan_slots(
    base_slots: tuple[tuple[str, str], ...],
    items: list[dict[str, Any]],
) -> tuple[tuple[str, str], ...]:
    """Use user-entered intervals in place of overlapping reference slots."""
    item_slots = {
        (str(item["start_time"]), str(item["end_time"]))
        for item in items
    }
    custom_slots = item_slots.difference(base_slots)
    visible_base_slots = {
        slot for slot in base_slots
        if not any(_time_ranges_overlap(slot, custom) for custom in custom_slots)
    }
    return tuple(sorted(visible_base_slots | custom_slots))


def _nutrition_meal_type(item: dict[str, Any]) -> str | None:
    """Return a nutrition recipe's meal type without exposing its details."""
    notes = str(item.get("notes") or "")
    for marker in NUTRITION_RECIPE_MARKERS:
        if notes.startswith(marker):
            return notes[len(marker):].split("|", 1)[0] or None
    return None


def group_plan_items_for_display(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return planned events only, without exposing nutrition item details."""
    display_items = []
    for item in items:
        if _nutrition_meal_type(item):
            continue
        display = dict(item)
        display["detail_titles"] = []
        display_items.append(display)

    return display_items


def _required_text(value: object, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def week_start(value: date | str) -> date:
    """Normalize any date to its Monday for the containing planning week."""
    parsed = _date(value)
    return parsed - timedelta(days=parsed.weekday())


def _time(value: time | str, field_name: str) -> time:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must use HH:MM") from exc


def _time_to_minutes(value: str) -> int:
    parsed = _time(value, "time")
    return parsed.hour * 60 + parsed.minute


def _time_text(value: time | str, field_name: str) -> str:
    return _time(value, field_name).strftime("%H:%M")


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


def create_week_plan(
    week: date | str,
    title: str,
    timezone: str,
    *,
    plan_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    plan_id = plan_id or str(uuid4())
    normalized_week = week_start(week).isoformat()
    with _database(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO user_weekly_plans(plan_id, week_start, title, timezone)
                VALUES(?, ?, ?, ?)
                """,
                (plan_id, normalized_week, _required_text(title, "title"), _required_text(timezone, "timezone")),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("a weekly plan already exists for this week") from exc
            raise
        return dict(connection.execute(
            "SELECT * FROM user_weekly_plans WHERE plan_id=?", (plan_id,)
        ).fetchone())


def get_week_plan(week: date | str, *, db_path: Path | str | None = None) -> dict[str, Any] | None:
    normalized_week = week_start(week).isoformat()
    with _database(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM user_weekly_plans WHERE week_start=? AND deleted_at IS NULL",
            (normalized_week,),
        ).fetchone()
        return dict(row) if row else None


def copy_plan_items(
    source_plan_id: str,
    target_plan_id: str,
    *,
    db_path: Path | str | None = None,
) -> int:
    """Copy active items between weekly plans without creating duplicates."""
    if source_plan_id == target_plan_id:
        raise ValueError("source and target plans must be different")
    with _database(db_path) as connection:
        plans = connection.execute(
            """
            SELECT plan_id FROM user_weekly_plans
            WHERE plan_id IN (?, ?) AND deleted_at IS NULL
            """,
            (source_plan_id, target_plan_id),
        ).fetchall()
        if len(plans) != 2:
            raise ValueError("source or target weekly plan not found")
        source_items = connection.execute(
            """
            SELECT weekday, title, start_time, end_time, category, notes
            FROM user_weekly_plan_items
            WHERE plan_id=? AND deleted_at IS NULL
            ORDER BY weekday, start_time, sort_order, created_at
            """,
            (source_plan_id,),
        ).fetchall()
        existing = {
            (
                row["weekday"], row["title"], row["start_time"], row["end_time"],
                row["category"], row["notes"],
            )
            for row in connection.execute(
                """
                SELECT weekday, title, start_time, end_time, category, notes
                FROM user_weekly_plan_items
                WHERE plan_id=? AND deleted_at IS NULL
                """,
                (target_plan_id,),
            ).fetchall()
        }
        next_sort_order = {
            row["weekday"]: row["next_sort_order"]
            for row in connection.execute(
                """
                SELECT weekday, COALESCE(MAX(sort_order), -1)+1 AS next_sort_order
                FROM user_weekly_plan_items
                WHERE plan_id=? AND deleted_at IS NULL
                GROUP BY weekday
                """,
                (target_plan_id,),
            ).fetchall()
        }
        copied = 0
        for item in source_items:
            key = (
                item["weekday"], item["title"], item["start_time"], item["end_time"],
                item["category"], item["notes"],
            )
            if key in existing:
                continue
            weekday = item["weekday"]
            sort_order = next_sort_order.get(weekday, 0)
            connection.execute(
                """
                INSERT INTO user_weekly_plan_items(
                    item_id, plan_id, weekday, title, start_time, end_time,
                    category, notes, sort_order
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), target_plan_id, weekday, item["title"],
                    item["start_time"], item["end_time"], item["category"],
                    item["notes"], sort_order,
                ),
            )
            existing.add(key)
            next_sort_order[weekday] = sort_order + 1
            copied += 1
        return copied


def update_week_plan(plan_id: str, *, title: str | None = None, timezone: str | None = None,
                     db_path: Path | str | None = None) -> dict[str, Any]:
    changes = {}
    if title is not None:
        changes["title"] = _required_text(title, "title")
    if timezone is not None:
        changes["timezone"] = _required_text(timezone, "timezone")
    with _database(db_path) as connection:
        if not connection.execute("SELECT 1 FROM user_weekly_plans WHERE plan_id=?", (plan_id,)).fetchone():
            raise ValueError("weekly plan not found")
        if changes:
            changes["updated_at"] = datetime.now().replace(microsecond=0).isoformat()
            columns = ", ".join(f"{key}=?" for key in changes)
            connection.execute(
                f"UPDATE user_weekly_plans SET {columns} WHERE plan_id=?",
                (*changes.values(), plan_id),
            )
        return dict(connection.execute("SELECT * FROM user_weekly_plans WHERE plan_id=?", (plan_id,)).fetchone())


def create_plan_item(
    plan_id: str,
    weekday: int,
    title: str,
    start_time: time | str,
    end_time: time | str,
    category: str,
    *,
    notes: str | None = None,
    item_id: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    if int(weekday) not in range(7):
        raise ValueError("weekday must be between 0 and 6")
    if category not in PLAN_CATEGORIES:
        raise ValueError(f"unsupported plan category: {category}")
    start = _time(start_time, "start_time")
    end = _time(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be after start_time")
    item_id = item_id or str(uuid4())
    with _database(db_path) as connection:
        if not connection.execute("SELECT 1 FROM user_weekly_plans WHERE plan_id=? AND deleted_at IS NULL", (plan_id,)).fetchone():
            raise ValueError("weekly plan not found")
        sort_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), -1)+1 FROM user_weekly_plan_items WHERE plan_id=? AND weekday=?",
            (plan_id, weekday),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO user_weekly_plan_items(
                item_id, plan_id, weekday, title, start_time, end_time,
                category, notes, sort_order
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id, plan_id, int(weekday), _required_text(title, "title"),
                start.strftime("%H:%M"), end.strftime("%H:%M"), category,
                str(notes or "").strip() or None, sort_order,
            ),
        )
        return dict(connection.execute("SELECT * FROM user_weekly_plan_items WHERE item_id=?", (item_id,)).fetchone())


def update_plan_item(
    item_id: str,
    weekday: int,
    title: str,
    start_time: time | str,
    end_time: time | str,
    category: str,
    *,
    notes: str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    if int(weekday) not in range(7):
        raise ValueError("weekday must be between 0 and 6")
    if category not in PLAN_CATEGORIES:
        raise ValueError(f"unsupported plan category: {category}")
    start = _time(start_time, "start_time")
    end = _time(end_time, "end_time")
    if end <= start:
        raise ValueError("end_time must be after start_time")
    with _database(db_path) as connection:
        if not connection.execute(
            "SELECT 1 FROM user_weekly_plan_items WHERE item_id=? AND deleted_at IS NULL",
            (item_id,),
        ).fetchone():
            raise ValueError("planned item not found")
        connection.execute(
            """
            UPDATE user_weekly_plan_items
            SET weekday=?, title=?, start_time=?, end_time=?, category=?, notes=?, updated_at=?
            WHERE item_id=? AND deleted_at IS NULL
            """,
            (
                int(weekday), _required_text(title, "title"), start.strftime("%H:%M"),
                end.strftime("%H:%M"), category, str(notes or "").strip() or None,
                datetime.now().replace(microsecond=0).isoformat(), item_id,
            ),
        )
        return dict(connection.execute("SELECT * FROM user_weekly_plan_items WHERE item_id=?", (item_id,)).fetchone())


def list_plan_items(plan_id: str, *, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    with _database(db_path) as connection:
        return [dict(row) for row in connection.execute(
            """
            SELECT * FROM user_weekly_plan_items
            WHERE plan_id=? AND deleted_at IS NULL
            ORDER BY weekday, start_time, sort_order, created_at
            """,
            (plan_id,),
        ).fetchall()]


def delete_plan_item(item_id: str, *, db_path: Path | str | None = None) -> bool:
    with _database(db_path) as connection:
        return bool(connection.execute(
            "UPDATE user_weekly_plan_items SET deleted_at=CURRENT_TIMESTAMP WHERE item_id=? AND deleted_at IS NULL",
            (item_id,),
        ).rowcount)


def compare_week_plan(plan_id: str, *, db_path: Path | str | None = None) -> list[dict[str, Any]]:
    """Compare intent entries with the existing daily execution-block status.

    The two layers remain independent. Matching is deliberately read-only and
    uses the same date plus overlapping time range; no execution block is
    created or changed by a plan-table edit.
    """
    with _database(db_path) as connection:
        plan = connection.execute(
            "SELECT * FROM user_weekly_plans WHERE plan_id=? AND deleted_at IS NULL", (plan_id,)
        ).fetchone()
        if not plan:
            raise ValueError("weekly plan not found")
        items = [dict(row) for row in connection.execute(
            """
            SELECT * FROM user_weekly_plan_items
            WHERE plan_id=? AND deleted_at IS NULL
            ORDER BY weekday, start_time, sort_order, created_at
            """, (plan_id,),
        ).fetchall()]
        result = []
        monday = date.fromisoformat(plan["week_start"])
        status_rank = {"completed": 0, "in_progress": 1, "planned": 2, "postponed": 3, "skipped": 4}
        for item in items:
            item_date = monday + timedelta(days=item["weekday"])
            actual = connection.execute(
                """
                SELECT b.* FROM performance_plan_blocks b
                JOIN performance_plans p ON p.plan_id=b.plan_id
                WHERE p.plan_date=?
                  AND b.planned_start < ?
                  AND b.planned_end > ?
                ORDER BY CASE b.status
                    WHEN 'completed' THEN 0 WHEN 'in_progress' THEN 1
                    WHEN 'planned' THEN 2 WHEN 'postponed' THEN 3 ELSE 4 END,
                    b.planned_start
                LIMIT 1
                """,
                (
                    item_date.isoformat(),
                    f"{item_date.isoformat()}T{item['end_time']}:00",
                    f"{item_date.isoformat()}T{item['start_time']}:00",
                ),
            ).fetchone()
            row = dict(item)
            row.update({
                "plan_date": item_date.isoformat(),
                "actual_status": actual["status"] if actual else "unrecorded",
                "actual_title": actual["title"] if actual else None,
                "actual_start": actual["planned_start"] if actual else None,
                "actual_end": actual["planned_end"] if actual else None,
            })
            result.append(row)
        return result
