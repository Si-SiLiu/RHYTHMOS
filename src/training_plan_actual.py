"""Planned-training, actual-training matching, and transparent comparisons.

Planned records are deliberately stored apart from ``training_sessions`` and
its exercise/set children.  The latter remains the single source of truth for
what actually happened; this module only creates durable links and derived,
recomputable comparison rows.
"""

from __future__ import annotations

from datetime import date, timedelta
import sqlite3
import unicodedata
from uuid import uuid4


CYCLE_STATUSES = ("planned", "active", "completed", "archived")
SESSION_STATUSES = ("planned", "active", "completed", "archived")
TRAINING_DOMAINS = ("indoor_strength", "outdoor_running_jumping")
COMPARISON_STATUSES = (
    "completed", "partially_completed", "not_completed", "substituted", "unplanned", "unmatched",
)
PLAN_MODULES = (
    "mobility", "core_activation", "isometric_overload", "explosive",
    "main_strength", "accessory_strength", "small_muscle",
)
OUTDOOR_PLAN_MODULES = (
    "warmup",
    "coordination",
    "double_leg_running_form",
    "single_leg_running_form",
    "acceleration",
)
# Keep legacy module keys valid for existing saved outdoor plans while the
# matrix presents the new five-category structure.
OUTDOOR_PLAN_LEGACY_MODULES = ("running", "jumping")
ALL_PLAN_MODULES = PLAN_MODULES + OUTDOOR_PLAN_MODULES + OUTDOOR_PLAN_LEGACY_MODULES


def _uuid():
    return str(uuid4())


def _clean_text(value, *, required=False):
    text = str(value or "").strip()
    if required and not text:
        raise ValueError("TEXT_REQUIRED")
    return text or None


def _iso_date(value):
    return date.fromisoformat(str(value)).isoformat()


def cycle_end_date_for_weeks(start_date, duration_weeks):
    """Return the inclusive end date for a cycle measured in whole weeks."""
    start = date.fromisoformat(_iso_date(start_date))
    try:
        weeks = int(duration_weeks)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_CYCLE_DURATION") from exc
    if weeks < 1 or weeks != float(duration_weeks):
        raise ValueError("INVALID_CYCLE_DURATION")
    return start + timedelta(days=weeks * 7 - 1)


def cycle_week_segments(cycle):
    """Split a cycle into consecutive seven-day periods for plan navigation."""
    start = date.fromisoformat(_iso_date(cycle["start_date"]))
    end = date.fromisoformat(_iso_date(cycle["end_date"]))
    if end < start:
        raise ValueError("CYCLE_END_BEFORE_START")
    segments = []
    segment_start = start
    index = 1
    while segment_start <= end:
        segment_end = min(segment_start + timedelta(days=6), end)
        segments.append({
            "index": index,
            "start_date": segment_start.isoformat(),
            "end_date": segment_end.isoformat(),
            "matrix_week_start": (segment_start - timedelta(days=segment_start.weekday())).isoformat(),
        })
        segment_start += timedelta(days=7)
        index += 1
    return segments


def current_cycle_week_segment(cycle, *, on_date=None):
    """Return the cycle week that contains the requested date, if any."""
    target = date.fromisoformat(_iso_date(on_date or date.today()))
    for segment in cycle_week_segments(cycle):
        if segment["start_date"] <= target.isoformat() <= segment["end_date"]:
            return segment
    return None


def _number(value, *, minimum=0):
    if value in (None, ""):
        return None
    result = float(value)
    if result < minimum:
        raise ValueError("INVALID_TARGET")
    return result


def _integer(value, *, minimum=0):
    number = _number(value, minimum=minimum)
    if number is None:
        return None
    if int(number) != number:
        raise ValueError("INVALID_TARGET")
    return int(number)


def _normal_name(value):
    return "".join(
        character for character in unicodedata.normalize("NFKC", str(value or "")).casefold()
        if character.isalnum()
    )


def create_training_cycle(
    connection, name, start_date, end_date, *, notes=None, status="planned",
    training_domain="indoor_strength",
):
    if status not in CYCLE_STATUSES:
        raise ValueError("INVALID_CYCLE_STATUS")
    if training_domain not in TRAINING_DOMAINS:
        raise ValueError("INVALID_TRAINING_DOMAIN")
    start, end = _iso_date(start_date), _iso_date(end_date)
    if end < start:
        raise ValueError("CYCLE_END_BEFORE_START")
    if (date.fromisoformat(end) - date.fromisoformat(start)).days < 6:
        raise ValueError("CYCLE_MIN_ONE_WEEK")
    with connection:
        return connection.execute(
            """INSERT INTO training_cycles(
                   uuid,name,start_date,end_date,notes,status,training_domain
               ) VALUES(?,?,?,?,?,?,?)""",
            (_uuid(), _clean_text(name, required=True), start, end, _clean_text(notes), status, training_domain),
        ).lastrowid


def list_training_cycles(connection, *, include_archived=False, training_domain="indoor_strength"):
    clauses, params = [], []
    if not include_archived:
        clauses.append("status!='archived'")
    if training_domain is not None:
        if training_domain not in TRAINING_DOMAINS:
            raise ValueError("INVALID_TRAINING_DOMAIN")
        clauses.append("training_domain=?")
        params.append(training_domain)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM training_cycles {where} ORDER BY start_date DESC,id DESC", params
    ).fetchall()]


def get_current_training_cycle(connection, *, on_date=None, training_domain="indoor_strength"):
    """Return the active or planned cycle that covers the requested date."""
    if training_domain not in TRAINING_DOMAINS:
        raise ValueError("INVALID_TRAINING_DOMAIN")
    target_date = _iso_date(on_date or date.today())
    row = connection.execute(
        """SELECT * FROM training_cycles
             WHERE status IN ('active','planned')
               AND training_domain=?
               AND start_date<=? AND end_date>=?
             ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,
                      start_date DESC,id DESC
             LIMIT 1""",
        (training_domain, target_date, target_date),
    ).fetchone()
    return dict(row) if row else None


def update_training_cycle(connection, cycle_id, *, start_date, end_date, name=None):
    """Update a cycle's name and dates while preserving the one-week minimum."""
    cycle = connection.execute(
        "SELECT id FROM training_cycles WHERE id=?", (cycle_id,)
    ).fetchone()
    if not cycle:
        raise ValueError("TRAINING_CYCLE_NOT_FOUND")
    start, end = _iso_date(start_date), _iso_date(end_date)
    if end < start:
        raise ValueError("CYCLE_END_BEFORE_START")
    if (date.fromisoformat(end) - date.fromisoformat(start)).days < 6:
        raise ValueError("CYCLE_MIN_ONE_WEEK")
    fields, values = ["start_date=?", "end_date=?"], [start, end]
    if name is not None:
        fields.insert(0, "name=?")
        values.insert(0, _clean_text(name, required=True))
    values.append(cycle_id)
    with connection:
        connection.execute(
            f"UPDATE training_cycles SET {','.join(fields)} WHERE id=?",
            values,
        )
    return cycle_id


def delete_training_cycle(connection, cycle_id):
    """Delete one cycle and its planned content, leaving actual training intact."""
    cycle = connection.execute("SELECT id FROM training_cycles WHERE id=?", (cycle_id,)).fetchone()
    if not cycle:
        raise ValueError("TRAINING_CYCLE_NOT_FOUND")
    with connection:
        connection.execute(
            "DELETE FROM planned_training_sessions WHERE training_cycle_id=?",
            (cycle_id,),
        )
        connection.execute("DELETE FROM training_cycles WHERE id=?", (cycle_id,))
    return cycle_id


def create_planned_session(connection, planned_date, session_name, training_type, *, cycle_id=None, notes=None, status="planned"):
    if status not in SESSION_STATUSES:
        raise ValueError("INVALID_PLANNED_SESSION_STATUS")
    if cycle_id is not None:
        exists = connection.execute("SELECT 1 FROM training_cycles WHERE id=?", (cycle_id,)).fetchone()
        if not exists:
            raise ValueError("TRAINING_CYCLE_NOT_FOUND")
    with connection:
        return connection.execute(
            """INSERT INTO planned_training_sessions(
                   uuid,training_cycle_id,planned_date,session_name,training_type,notes,status
               ) VALUES(?,?,?,?,?,?,?)""",
            (_uuid(), cycle_id, _iso_date(planned_date), _clean_text(session_name, required=True),
             _clean_text(training_type, required=True), _clean_text(notes), status),
        ).lastrowid


def _session_snapshot(connection, session_id):
    session = connection.execute("SELECT * FROM planned_training_sessions WHERE id=?", (session_id,)).fetchone()
    exercises = connection.execute(
        "SELECT * FROM planned_training_exercises WHERE planned_session_id=? ORDER BY order_index,id", (session_id,)
    ).fetchall()
    return {"session": dict(session), "exercises": [dict(item) for item in exercises]}


def _snapshot_plan_if_actual(connection, session_id, reason):
    actual_exists = connection.execute(
        "SELECT 1 FROM plan_actual_session_links WHERE planned_session_id=?", (session_id,)
    ).fetchone()
    if not actual_exists:
        return
    import json
    connection.execute(
        """INSERT INTO planned_session_revisions(planned_session_id,snapshot_json,reason)
           VALUES(?,?,?)""", (session_id, json.dumps(_session_snapshot(connection, session_id), ensure_ascii=False), reason),
    )


def update_planned_session(connection, session_id, **changes):
    """Update a plan, preserving a snapshot before any linked actual exists."""
    current = connection.execute("SELECT * FROM planned_training_sessions WHERE id=?", (session_id,)).fetchone()
    if not current:
        raise ValueError("PLANNED_SESSION_NOT_FOUND")
    allowed = {"planned_date", "session_name", "training_type", "notes", "status", "training_cycle_id"}
    values = {key: changes[key] for key in allowed if key in changes}
    if not values:
        return
    if "planned_date" in values:
        values["planned_date"] = _iso_date(values["planned_date"])
    if "session_name" in values:
        values["session_name"] = _clean_text(values["session_name"], required=True)
    if "training_type" in values:
        values["training_type"] = _clean_text(values["training_type"], required=True)
    if "notes" in values:
        values["notes"] = _clean_text(values["notes"])
    if "status" in values and values["status"] not in SESSION_STATUSES:
        raise ValueError("INVALID_PLANNED_SESSION_STATUS")
    assignments = ",".join(f"{key}=?" for key in values)
    with connection:
        _snapshot_plan_if_actual(connection, session_id, "updated_after_actual")
        connection.execute(
            f"UPDATE planned_training_sessions SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*values.values(), session_id),
        )


def create_planned_exercise(connection, planned_session_id, *, exercise_catalog_id=None, canonical_name=None,
                            display_name=None, order_index=None, target_sets=None, target_reps=None,
                            target_weight=None, target_load_unit="kg", target_duration=None,
                            target_distance=None, target_rpe=None, notes=None, substitution_allowed=False,
                            module_key="main_strength"):
    if not connection.execute("SELECT 1 FROM planned_training_sessions WHERE id=?", (planned_session_id,)).fetchone():
        raise ValueError("PLANNED_SESSION_NOT_FOUND")
    catalog = None
    if exercise_catalog_id not in (None, ""):
        catalog = connection.execute("SELECT * FROM exercise_catalog WHERE id=?", (exercise_catalog_id,)).fetchone()
        if not catalog:
            raise ValueError("EXERCISE_CATALOG_NOT_FOUND")
    canonical = _clean_text(canonical_name) or (catalog["canonical_name"] if catalog else None)
    display = _clean_text(display_name) or (catalog["display_name_zh"] if catalog else None)
    if not canonical and not display:
        raise ValueError("PLANNED_EXERCISE_NAME_REQUIRED")
    if module_key not in ALL_PLAN_MODULES:
        raise ValueError("INVALID_PLAN_MODULE")
    order = _integer(order_index, minimum=1) if order_index is not None else None
    if order is None:
        order = connection.execute(
            "SELECT COALESCE(MAX(order_index),0)+1 FROM planned_training_exercises WHERE planned_session_id=?",
            (planned_session_id,),
        ).fetchone()[0]
    with connection:
        return connection.execute(
            """INSERT INTO planned_training_exercises(
                   uuid,planned_session_id,exercise_catalog_id,exercise_canonical_name,exercise_display_name,
                   order_index,target_sets,target_reps,target_weight,target_load_unit,target_duration_seconds,
                   target_distance_meters,target_rpe,notes,substitution_allowed,module_key
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_uuid(), planned_session_id, catalog["id"] if catalog else None, canonical, display, order,
             _integer(target_sets), _integer(target_reps), _number(target_weight), target_load_unit or "kg",
             _number(target_duration), _number(target_distance), _number(target_rpe), _clean_text(notes),
             int(bool(substitution_allowed)), module_key),
        ).lastrowid


def update_planned_exercise(connection, planned_exercise_id, **changes):
    row = connection.execute(
        "SELECT planned_session_id FROM planned_training_exercises WHERE id=?", (planned_exercise_id,)
    ).fetchone()
    if not row:
        raise ValueError("PLANNED_EXERCISE_NOT_FOUND")
    allowed = {
        "exercise_canonical_name", "exercise_display_name", "target_sets", "target_reps", "target_weight",
        "target_duration_seconds", "target_distance_meters", "target_rpe", "notes", "substitution_allowed", "module_key",
    }
    values = {key: changes[key] for key in allowed if key in changes}
    if not values:
        return
    for field in ("target_sets", "target_reps"):
        if field in values:
            values[field] = _integer(values[field])
    for field in ("target_weight", "target_duration_seconds", "target_distance_meters", "target_rpe"):
        if field in values:
            values[field] = _number(values[field])
    if "module_key" in values and values["module_key"] not in ALL_PLAN_MODULES:
        raise ValueError("INVALID_PLAN_MODULE")
    if "substitution_allowed" in values:
        values["substitution_allowed"] = int(bool(values["substitution_allowed"]))
    assignments = ",".join(f"{key}=?" for key in values)
    with connection:
        _snapshot_plan_if_actual(connection, row["planned_session_id"], "exercise_updated_after_actual")
        connection.execute(
            f"UPDATE planned_training_exercises SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*values.values(), planned_exercise_id),
        )


def delete_planned_exercise(connection, planned_exercise_id):
    row = connection.execute(
        "SELECT planned_session_id FROM planned_training_exercises WHERE id=?", (planned_exercise_id,)
    ).fetchone()
    if not row:
        return False
    with connection:
        _snapshot_plan_if_actual(connection, row["planned_session_id"], "exercise_deleted_after_actual")
        connection.execute("DELETE FROM planned_training_exercises WHERE id=?", (planned_exercise_id,))
    return True


def copy_previous_week_training_content(connection, week_start, *, cycle_id=None):
    """Copy the previous calendar week's plans into empty dates of ``week_start``.

    The destination keeps its own training cycle and deliberately never
    overwrites a date that already contains a plan. This makes the shortcut
    safe to use repeatedly while preserving edits made for the current week.
    """
    target_start = date.fromisoformat(_iso_date(week_start))
    target_start -= timedelta(days=target_start.weekday())
    source_start = target_start - timedelta(days=7)
    destination_domain = "indoor_strength"
    if cycle_id is not None:
        cycle_row = connection.execute(
            "SELECT training_domain FROM training_cycles WHERE id=?", (cycle_id,)
        ).fetchone()
        if cycle_row:
            destination_domain = cycle_row["training_domain"]
    source_dates = [source_start + timedelta(days=offset) for offset in range(7)]
    source_sessions = [
        session
        for source_date in source_dates
        for session in list_planned_sessions(
            connection, planned_date=source_date, training_domain=destination_domain
        )
    ]
    destination_dates = [target_start + timedelta(days=offset) for offset in range(7)]
    existing_dates = {
        destination_date.isoformat()
        for destination_date in destination_dates
        if list_planned_sessions(
            connection, planned_date=destination_date, training_domain=destination_domain
        )
    }
    copied_sessions = 0
    skipped_dates = set()
    for source in source_sessions:
        source_date = date.fromisoformat(source["planned_date"])
        destination_date = target_start + (source_date - source_start)
        destination_key = destination_date.isoformat()
        if destination_key in existing_dates:
            skipped_dates.add(destination_key)
            continue
        destination_session_id = create_planned_session(
            connection,
            destination_date,
            source["session_name"],
            source["training_type"],
            cycle_id=cycle_id,
            notes=source.get("notes"),
            status="planned",
        )
        for exercise in source["exercises"]:
            create_planned_exercise(
                connection,
                destination_session_id,
                exercise_catalog_id=exercise.get("exercise_catalog_id"),
                canonical_name=exercise.get("exercise_canonical_name"),
                display_name=exercise.get("exercise_display_name"),
                order_index=exercise.get("order_index"),
                target_sets=exercise.get("target_sets"),
                target_reps=exercise.get("target_reps"),
                target_weight=exercise.get("target_weight"),
                target_load_unit=exercise.get("target_load_unit"),
                target_duration=exercise.get("target_duration_seconds"),
                target_distance=exercise.get("target_distance_meters"),
                target_rpe=exercise.get("target_rpe"),
                notes=exercise.get("notes"),
                substitution_allowed=exercise.get("substitution_allowed"),
                module_key=exercise.get("module_key"),
            )
        copied_sessions += 1
    return {
        "source_session_count": len(source_sessions),
        "copied_session_count": copied_sessions,
        "skipped_date_count": len(skipped_dates),
    }


def list_planned_sessions(connection, *, cycle_id=None, planned_date=None, training_domain=None):
    clauses, params = [], []
    if cycle_id is not None:
        clauses.append("s.training_cycle_id=?"); params.append(cycle_id)
    if planned_date is not None:
        clauses.append("s.planned_date=?"); params.append(_iso_date(planned_date))
    if training_domain is not None:
        if training_domain not in TRAINING_DOMAINS:
            raise ValueError("INVALID_TRAINING_DOMAIN")
        clauses.append("(c.training_domain=? OR (s.training_cycle_id IS NULL AND ?='indoor_strength'))")
        params.extend((training_domain, training_domain))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"""SELECT s.*,c.name AS cycle_name FROM planned_training_sessions s
               LEFT JOIN training_cycles c ON c.id=s.training_cycle_id {where}
               ORDER BY s.planned_date,s.id""", params
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["exercises"] = [dict(exercise) for exercise in connection.execute(
            "SELECT * FROM planned_training_exercises WHERE planned_session_id=? ORDER BY order_index,id", (item["id"],)
        ).fetchall()]
        result.append(item)
    return result


def _recent_planned_action_defaults(connection, module_key, fields):
    """Return the latest user-saved values for each action in one module."""
    if module_key not in ALL_PLAN_MODULES:
        raise ValueError("INVALID_PLAN_MODULE")
    rows = connection.execute(
        """SELECT e.exercise_display_name,e.exercise_canonical_name,
                  COALESCE(e.target_sets,e.target_reps) AS target_sets,
                  e.target_reps,e.target_weight,e.target_distance_meters
             FROM planned_training_exercises e
             JOIN planned_training_sessions s ON s.id=e.planned_session_id
             WHERE e.module_key=?
             ORDER BY s.updated_at DESC,s.id DESC,e.id DESC""",
        (module_key,),
    ).fetchall()
    defaults = {}
    for row in rows:
        item = dict(row)
        name = item["exercise_display_name"] or item["exercise_canonical_name"]
        if name and name not in defaults:
            defaults[name] = {field: item[field] for field in fields}
    return defaults


def recent_planned_action_defaults(connection, module_key):
    """Return recent strength-action defaults from the user's saved plans."""
    return _recent_planned_action_defaults(
        connection, module_key, ("target_sets", "target_reps", "target_weight")
    )


def recent_outdoor_action_defaults(connection, module_key):
    """Return recent outdoor-action defaults from the user's saved plans."""
    return _recent_planned_action_defaults(
        connection, module_key,
        ("target_sets", "target_distance_meters"),
    )


def _actual_session(connection, session_id):
    session = connection.execute(
        "SELECT * FROM training_sessions WHERE id=? AND deleted_at IS NULL", (session_id,)
    ).fetchone()
    if not session:
        return None
    item = dict(session)
    exercises = []
    for row in connection.execute(
        """SELECT e.*,c.canonical_name,c.display_name_zh,c.display_name_en
           FROM training_exercises e LEFT JOIN exercise_catalog c ON c.id=e.exercise_catalog_id
           WHERE e.training_session_id=? AND e.deleted_at IS NULL ORDER BY e.sequence_order,e.id""", (session_id,)
    ).fetchall():
        exercise = dict(row)
        exercise["sets"] = [dict(set_row) for set_row in connection.execute(
            "SELECT * FROM training_sets WHERE training_exercise_id=? AND deleted_at IS NULL ORDER BY set_number,id",
            (exercise["id"],),
        ).fetchall()]
        exercises.append(exercise)
    item["exercises"] = exercises
    return item


def _exercise_name(exercise):
    return exercise.get("exercise_canonical_name") or exercise.get("canonical_name") or exercise.get("exercise_display_name") or exercise.get("custom_exercise_name")


def _link_session(connection, planned_session_id, actual_training_session_id, source):
    with connection:
        connection.execute(
            """INSERT INTO plan_actual_session_links(uuid,planned_session_id,actual_training_session_id,match_source)
               VALUES(?,?,?,?)
               ON CONFLICT(actual_training_session_id) DO UPDATE SET
                 planned_session_id=excluded.planned_session_id,match_source=excluded.match_source,
                 updated_at=CURRENT_TIMESTAMP""",
            (_uuid(), planned_session_id, actual_training_session_id, source),
        )


def auto_match_actual_session(connection, actual_training_session_id):
    """Link an actual session only when exactly one same-date plan exists."""
    actual = _actual_session(connection, actual_training_session_id)
    if not actual:
        return {"status": "unmatched", "planned_session_id": None}
    existing = connection.execute(
        "SELECT planned_session_id FROM plan_actual_session_links WHERE actual_training_session_id=?", (actual_training_session_id,)
    ).fetchone()
    if existing:
        calculate_session_comparison(connection, existing["planned_session_id"])
        return {"status": "matched", "planned_session_id": existing["planned_session_id"]}
    candidates = list_planned_sessions(connection, planned_date=actual["date"])
    candidates = [item for item in candidates if item["status"] != "archived"]
    if len(candidates) != 1:
        return {"status": "unmatched", "planned_session_id": None}
    _link_session(connection, candidates[0]["id"], actual_training_session_id, "automatic")
    calculate_session_comparison(connection, candidates[0]["id"])
    return {"status": "matched", "planned_session_id": candidates[0]["id"]}


def confirm_actual_session_match(connection, planned_session_id, actual_training_session_id):
    if not connection.execute("SELECT 1 FROM planned_training_sessions WHERE id=?", (planned_session_id,)).fetchone():
        raise ValueError("PLANNED_SESSION_NOT_FOUND")
    if not _actual_session(connection, actual_training_session_id):
        raise ValueError("ACTUAL_SESSION_NOT_FOUND")
    _link_session(connection, planned_session_id, actual_training_session_id, "manual")
    return calculate_session_comparison(connection, planned_session_id)


def get_actual_session_plan_link(connection, actual_training_session_id):
    row = connection.execute(
        """SELECT planned_session_id,match_source FROM plan_actual_session_links
           WHERE actual_training_session_id=?""", (actual_training_session_id,)
    ).fetchone()
    return dict(row) if row else None


def confirm_exercise_match(connection, planned_exercise_id, actual_training_exercise_id, *, relationship="matched", reason=None):
    if relationship not in {"matched", "substituted"}:
        raise ValueError("INVALID_EXERCISE_RELATIONSHIP")
    with connection:
        connection.execute(
            """INSERT INTO plan_actual_exercise_links(
                   uuid,planned_exercise_id,actual_training_exercise_id,relationship,match_source,reason
               ) VALUES(?,?,?,?,?,?)
               ON CONFLICT(planned_exercise_id) DO UPDATE SET
                 actual_training_exercise_id=excluded.actual_training_exercise_id,relationship=excluded.relationship,
                 match_source=excluded.match_source,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP""",
            (_uuid(), planned_exercise_id, actual_training_exercise_id, relationship, "manual", _clean_text(reason)),
        )
    planned = connection.execute(
        "SELECT planned_session_id FROM planned_training_exercises WHERE id=?", (planned_exercise_id,)
    ).fetchone()
    return calculate_session_comparison(connection, planned["planned_session_id"])


def confirm_exercise_substitution(connection, planned_exercise_id, actual_training_exercise_id, *, reason=None):
    return confirm_exercise_match(
        connection, planned_exercise_id, actual_training_exercise_id, relationship="substituted", reason=reason,
    )


def _auto_link_exercises(connection, planned_session_id, actual):
    planned = connection.execute(
        "SELECT * FROM planned_training_exercises WHERE planned_session_id=? ORDER BY order_index,id", (planned_session_id,)
    ).fetchall()
    linked_actual_ids = {
        row[0] for row in connection.execute(
            """SELECT actual_training_exercise_id FROM plan_actual_exercise_links l
               JOIN planned_training_exercises p ON p.id=l.planned_exercise_id
               WHERE p.planned_session_id=?""", (planned_session_id,)
        ).fetchall()
    }
    for planned_exercise in planned:
        existing = connection.execute(
            "SELECT 1 FROM plan_actual_exercise_links WHERE planned_exercise_id=?", (planned_exercise["id"],)
        ).fetchone()
        if existing:
            continue
        target = _normal_name(_exercise_name(dict(planned_exercise)))
        candidates = [
            exercise for exercise in actual["exercises"]
            if exercise["id"] not in linked_actual_ids and _normal_name(_exercise_name(exercise)) == target
        ]
        if len(candidates) == 1:
            with connection:
                connection.execute(
                    """INSERT INTO plan_actual_exercise_links(
                           uuid,planned_exercise_id,actual_training_exercise_id,relationship,match_source
                       ) VALUES(?,?,?,?,?)""",
                    (_uuid(), planned_exercise["id"], candidates[0]["id"], "matched", "automatic"),
                )
            linked_actual_ids.add(candidates[0]["id"])


def _metrics(planned, actual):
    target_sets, target_reps, target_weight = planned.get("target_sets"), planned.get("target_reps"), planned.get("target_weight")
    completed_sets = [item for item in (actual or {}).get("sets", []) if item.get("completed")]
    actual_sets = len(completed_sets)
    actual_reps = sum(item.get("reps") or 0 for item in completed_sets)
    actual_volume = sum((item.get("load_value") or 0) * (item.get("reps") or 0) for item in completed_sets)
    planned_reps = target_sets * target_reps if target_sets is not None and target_reps is not None else None
    planned_volume = planned_reps * target_weight if planned_reps is not None and target_weight is not None else None
    def ratio(actual_value, planned_value):
        return None if planned_value is None else (actual_value / planned_value if planned_value else 0.0)
    loads = [item.get("load_value") for item in completed_sets if item.get("load_value") is not None]
    load_completion = None if target_weight is None else (sum(loads) / len(loads) / target_weight if loads and target_weight else 0.0)
    values = [ratio(actual_sets, target_sets), ratio(actual_reps, planned_reps), ratio(actual_volume, planned_volume)]
    available = [value for value in values if value is not None]
    return {
        "planned_sets": target_sets, "actual_sets": actual_sets if target_sets is not None else None,
        "planned_reps": planned_reps, "actual_reps": actual_reps if planned_reps is not None else None,
        "planned_volume": planned_volume, "actual_volume": actual_volume if planned_volume is not None else None,
        "sets_completion": ratio(actual_sets, target_sets), "reps_completion": ratio(actual_reps, planned_reps),
        "load_completion": load_completion, "volume_completion": ratio(actual_volume, planned_volume),
        "overall_completion": sum(available) / len(available) if available else None,
    }


def calculate_session_comparison(connection, planned_session_id):
    """Recompute one session without mutating planned or actual records."""
    planned_session = connection.execute("SELECT * FROM planned_training_sessions WHERE id=?", (planned_session_id,)).fetchone()
    if not planned_session:
        raise ValueError("PLANNED_SESSION_NOT_FOUND")
    session_link = connection.execute(
        "SELECT * FROM plan_actual_session_links WHERE planned_session_id=?", (planned_session_id,)
    ).fetchone()
    actual = _actual_session(connection, session_link["actual_training_session_id"]) if session_link else None
    if actual:
        _auto_link_exercises(connection, planned_session_id, actual)
    exercises = [dict(row) for row in connection.execute(
        "SELECT * FROM planned_training_exercises WHERE planned_session_id=? ORDER BY order_index,id", (planned_session_id,)
    ).fetchall()]
    links = {
        row["planned_exercise_id"]: dict(row) for row in connection.execute(
            """SELECT * FROM plan_actual_exercise_links WHERE planned_exercise_id IN
               (SELECT id FROM planned_training_exercises WHERE planned_session_id=?)""", (planned_session_id,)
        ).fetchall()
    }
    actual_by_id = {item["id"]: item for item in (actual or {}).get("exercises", [])}
    with connection:
        connection.execute("DELETE FROM plan_actual_comparisons WHERE planned_session_id=?", (planned_session_id,))
        for exercise in exercises:
            link = links.get(exercise["id"])
            matched = actual_by_id.get(link["actual_training_exercise_id"]) if link else None
            metrics = _metrics(exercise, matched)
            relationship = link["relationship"] if link else "unmatched"
            if relationship == "substituted":
                status = "substituted"
            elif not matched:
                status = "not_completed"
            elif (metrics["overall_completion"] or 0) >= 0.999:
                status = "completed"
            else:
                status = "partially_completed"
            connection.execute(
                """INSERT INTO plan_actual_comparisons(
                   planned_session_id,actual_training_session_id,planned_exercise_id,actual_training_exercise_id,
                   relationship,status,planned_sets,actual_sets,planned_reps,actual_reps,planned_volume,actual_volume,
                   sets_completion,reps_completion,load_completion,volume_completion,overall_completion
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (planned_session_id, actual["id"] if actual else None, exercise["id"], matched["id"] if matched else None,
                 relationship, status, metrics["planned_sets"], metrics["actual_sets"], metrics["planned_reps"],
                 metrics["actual_reps"], metrics["planned_volume"], metrics["actual_volume"], metrics["sets_completion"],
                 metrics["reps_completion"], metrics["load_completion"], metrics["volume_completion"], metrics["overall_completion"]),
            )
        linked_actual = set(links_item["actual_training_exercise_id"] for links_item in links.values())
        for exercise in (actual or {}).get("exercises", []):
            if exercise["id"] not in linked_actual:
                connection.execute(
                    """INSERT INTO plan_actual_comparisons(
                       planned_session_id,actual_training_session_id,actual_training_exercise_id,relationship,status
                   ) VALUES(?,?,?,?,?)""", (planned_session_id, actual["id"], exercise["id"], "unplanned", "unplanned"),
                )
    return get_session_comparison(connection, planned_session_id)


def get_session_comparison(connection, planned_session_id):
    rows = [dict(row) for row in connection.execute(
        """SELECT c.*,p.exercise_display_name,p.exercise_canonical_name,a.custom_exercise_name,
                  ac.display_name_zh AS actual_display_name
           FROM plan_actual_comparisons c
           LEFT JOIN planned_training_exercises p ON p.id=c.planned_exercise_id
           LEFT JOIN training_exercises a ON a.id=c.actual_training_exercise_id
           LEFT JOIN exercise_catalog ac ON ac.id=a.exercise_catalog_id
           WHERE c.planned_session_id=?
           ORDER BY CASE WHEN c.planned_exercise_id IS NULL THEN 1 ELSE 0 END,p.order_index,c.id""", (planned_session_id,)
    ).fetchall()]
    planned = [row for row in rows if row.get("planned_exercise_id")]
    overall_values = [row["overall_completion"] for row in planned if row["overall_completion"] is not None]
    return {
        "rows": rows,
        "planned_exercise_count": len(planned),
        "completed_count": sum(row["status"] == "completed" for row in planned),
        "partial_count": sum(row["status"] == "partially_completed" for row in planned),
        "missed_count": sum(row["status"] == "not_completed" for row in planned),
        "substituted_count": sum(row["status"] == "substituted" for row in planned),
        "unplanned_count": sum(row["status"] == "unplanned" for row in rows),
        "planned_volume": sum(row["planned_volume"] or 0 for row in planned) if planned else None,
        "actual_volume": sum(row["actual_volume"] or 0 for row in planned) if planned else None,
        "overall_completion": sum(overall_values) / len(overall_values) if overall_values else None,
        "overall_completion_rule": "mean_available_sets_reps_volume_completion",
    }


def cycle_statistics(connection, cycle_id):
    sessions = list_planned_sessions(connection, cycle_id=cycle_id)
    summaries = [calculate_session_comparison(connection, item["id"]) for item in sessions]
    values = [item["overall_completion"] for item in summaries if item["overall_completion"] is not None]
    return {
        "planned_session_count": len(sessions),
        "completed_count": sum(item["completed_count"] for item in summaries),
        "partial_count": sum(item["partial_count"] for item in summaries),
        "missed_count": sum(item["missed_count"] for item in summaries),
        "substituted_count": sum(item["substituted_count"] for item in summaries),
        "unplanned_count": sum(item["unplanned_count"] for item in summaries),
        "overall_completion": sum(values) / len(values) if values else None,
    }
