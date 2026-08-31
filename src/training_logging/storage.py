"""Repository/service layer for Polar-linked and manual structured training."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
import sqlite3
from uuid import uuid4

from src.sport_catalog import resolve_sport_name

from .catalog import exercise_catalog_by_id
from .summary import summarize_training
from .validation import (
    EXERCISE_CATEGORIES, LOAD_UNITS, MEASUREMENT_MODES, SET_TYPES, SIDES,
    TRAINING_STATUSES, enum_value, finite_number, text_value, valid_date,
    valid_time,
)


TRAINING_LOGGING_VERSION = "2.0.0"
_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


def _uuid():
    return str(uuid4())


def _json(value):
    try:
        data = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _first(mapping, *keys):
    for key in keys:
        value = mapping.get(key) if isinstance(mapping, dict) else None
        if value not in (None, ""):
            if isinstance(value, dict):
                for nested in ("id", "value", "name", "code"):
                    if value.get(nested) not in (None, ""):
                        return value[nested]
            return value
    return None


def duration_seconds(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return finite_number("duration_seconds", value, 0)
    match = _DURATION_RE.fullmatch(str(value).strip().upper())
    if not match:
        return None
    parts = {name: float(number or 0) for name, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _polar_values(row):
    raw = _json(row.get("raw_json"))
    exercises = raw.get("exercises") if isinstance(raw.get("exercises"), list) else []
    first_exercise = exercises[0] if exercises and isinstance(exercises[0], dict) else {}
    start = row.get("start_time") or _first(raw, "startTime", "start_time")
    end = _first(raw, "stopTime", "endTime", "end_time") or _first(
        first_exercise, "stopTime", "endTime", "end_time"
    )
    sport = row.get("sport") or _first(raw, "sport") or _first(first_exercise, "sport")
    return {
        "date": row.get("date"), "start_time": start, "end_time": end,
        "duration_seconds": duration_seconds(row.get("duration")) or (
            finite_number("duration_millis", raw.get("durationMillis"), 0) / 1000
            if raw.get("durationMillis") is not None else None
        ),
        "polar_sport_type": str(sport) if sport is not None else None,
        "sport_display": resolve_sport_name(sport),
        "average_hr": finite_number("average_hr", _first(raw, "hrAvg", "averageHr", "average_hr"), 0),
        "max_hr": finite_number("max_hr", _first(raw, "hrMax", "maximumHr", "max_hr"), 0),
        "calories": finite_number("calories", row.get("calories"), 0),
        "distance_meters": finite_number(
            "distance_meters", _first(raw, "distance", "distanceMeters", "distance_meters"), 0
        ),
    }


def ensure_polar_session_index(connection: sqlite3.Connection):
    # Page navigation calls this guard frequently. Only project raw sessions
    # that are not indexed yet; rescanning every historical Polar payload made
    # each Training-page visit progressively slower as the database grew.
    rows = connection.execute(
        """SELECT raw.* FROM polar_training_sessions_raw raw
           WHERE NOT EXISTS (
               SELECT 1 FROM training_sessions session
               WHERE session.polar_external_id=raw.external_id
           )
           ORDER BY raw.date,raw.start_time,raw.id"""
    ).fetchall()
    inserted = 0
    with connection:
        for raw_row in rows:
            row = dict(raw_row)
            values = _polar_values(row)
            cursor = connection.execute(
                """INSERT OR IGNORE INTO training_sessions(
                       uuid,date,start_time,end_time,duration_seconds,polar_sport_type,
                       resolved_sport_type,resolved_sport_type_source,source,
                       polar_external_id,average_hr,max_hr,calories,distance_meters,status
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uuid(), values["date"], values["start_time"], values["end_time"],
                    values["duration_seconds"], values["polar_sport_type"],
                    values["polar_sport_type"], "polar", "polar", row["external_id"],
                    values["average_hr"], values["max_hr"], values["calories"],
                    values["distance_meters"], "completed",
                ),
            )
            inserted += cursor.rowcount
    # Match only still-unlinked sessions that now have exactly one viable
    # same-day plan. Existing links are already authoritative and no longer
    # need a comparison rebuild during every page switch.
    from src.training_plan_actual import auto_match_actual_session
    matchable = connection.execute(
        """SELECT session.id FROM training_sessions session
           LEFT JOIN plan_actual_session_links link
             ON link.actual_training_session_id=session.id
           WHERE session.source='polar' AND session.deleted_at IS NULL
             AND link.id IS NULL
             AND 1=(
                 SELECT COUNT(*) FROM planned_training_sessions planned
                 WHERE planned.planned_date=session.date
                   AND planned.status!='archived'
             )"""
    ).fetchall()
    for actual in matchable:
        auto_match_actual_session(connection, actual["id"])
    return inserted


def _session_exercises(connection, session_id):
    exercises = []
    for row in connection.execute(
        """SELECT * FROM training_exercises WHERE training_session_id=?
           AND deleted_at IS NULL ORDER BY sequence_order,id""", (session_id,)
    ).fetchall():
        exercise = dict(row)
        exercise["sets"] = [dict(item) for item in connection.execute(
            """SELECT * FROM training_sets WHERE training_exercise_id=?
               AND deleted_at IS NULL ORDER BY set_number,id""", (exercise["id"],)
        ).fetchall()]
        exercises.append(exercise)
    return exercises


def get_training_session(connection: sqlite3.Connection, session_id):
    row = connection.execute(
        "SELECT * FROM training_sessions WHERE id=? AND deleted_at IS NULL", (session_id,)
    ).fetchone()
    if not row:
        return None
    session = dict(row)
    polar = None
    if session.get("polar_external_id"):
        raw = connection.execute(
            """SELECT * FROM polar_training_sessions_raw WHERE external_id=?
               ORDER BY updated_at DESC,id DESC LIMIT 1""", (session["polar_external_id"],)
        ).fetchone()
        polar = _polar_values(dict(raw)) if raw else None
    if polar:
        for key in (
            "date", "start_time", "end_time", "duration_seconds", "average_hr",
            "max_hr", "calories", "distance_meters", "polar_sport_type",
        ):
            session[key] = polar.get(key)
        session["polar_sport_display"] = polar.get("sport_display")
    else:
        session["polar_sport_display"] = None
    resolved = session.get("resolved_sport_type")
    if session["resolved_sport_type_source"] == "polar":
        resolved = session.get("polar_sport_type")
    session["sport_display"] = resolve_sport_name(resolved) or resolved
    session["polar_readonly"] = bool(session.get("polar_external_id"))
    session["exercises"] = _session_exercises(connection, session["id"])
    session["summary"] = summarize_training(session["exercises"])
    return session


def list_training_sessions(connection: sqlite3.Connection, limit=100):
    ids = [row[0] for row in connection.execute(
        """SELECT id FROM training_sessions WHERE deleted_at IS NULL
           ORDER BY date DESC,start_time DESC,id DESC LIMIT ?""", (limit,)
    ).fetchall()]
    return [get_training_session(connection, session_id) for session_id in ids]


def create_manual_training_session(connection: sqlite3.Connection, data):
    values = {
        "date": valid_date(data.get("date")),
        "start_time": valid_time(data.get("start_time")),
        "end_time": valid_time(data.get("end_time")),
        "duration_seconds": finite_number("duration_seconds", data.get("duration_seconds"), 0),
        "resolved_sport_type": text_value(data.get("resolved_sport_type")) or "other",
        "average_hr": finite_number("average_hr", data.get("average_hr"), 0),
        "max_hr": finite_number("max_hr", data.get("max_hr"), 0),
        "calories": finite_number("calories", data.get("calories"), 0),
        "distance_meters": finite_number("distance_meters", data.get("distance_meters"), 0),
        "status": enum_value("training_status", data.get("status", "draft"), TRAINING_STATUSES),
        "notes": text_value(data.get("notes")),
    }
    with connection:
        record_id = connection.execute(
            """INSERT INTO training_sessions(
                   uuid,date,start_time,end_time,duration_seconds,resolved_sport_type,
                   resolved_sport_type_source,source,average_hr,max_hr,calories,
                   distance_meters,status,notes
               ) VALUES(?,?,?,?,?,?,'manual','manual',?,?,?,?,?,?)""",
            (_uuid(), *values.values()),
        ).lastrowid
    from src.training_plan_actual import auto_match_actual_session
    auto_match_actual_session(connection, int(record_id))
    return int(record_id)


def _blank_set(raw):
    return not any(
        raw.get(name) is not None
        and raw.get(name) != ""
        and raw.get(name) is not False
        for name in (
        "load_value", "reps", "duration_seconds", "distance_meters",
        "resistance_level", "incline_percent", "rpe", "rir", "rest_seconds", "notes",
        )
    )


def _clean_set(raw, measurement_mode, number):
    if _blank_set(raw):
        return None
    load_unit = enum_value("load_unit", raw.get("load_unit", "none"), LOAD_UNITS)
    item = {
        "uuid": str(raw.get("uuid") or _uuid()), "set_number": number,
        "set_type": enum_value("set_type", raw.get("set_type", "working"), SET_TYPES),
        "load_value": finite_number("load_value", raw.get("load_value"), 0),
        "load_unit": load_unit,
        "reps": finite_number("reps", raw.get("reps"), 0, integer=True),
        "duration_seconds": finite_number("duration_seconds", raw.get("duration_seconds"), 0),
        "distance_meters": finite_number("distance_meters", raw.get("distance_meters"), 0),
        "resistance_level": finite_number("resistance_level", raw.get("resistance_level"), 0),
        "incline_percent": finite_number("incline_percent", raw.get("incline_percent"), 0),
        "rpe": finite_number("rpe", raw.get("rpe"), 1, 10),
        "rir": finite_number("rir", raw.get("rir"), 0, 10),
        "rest_seconds": finite_number("rest_seconds", raw.get("rest_seconds"), 0),
        "side": enum_value("side", raw.get("side", "not_applicable"), SIDES),
        "completed": int(bool(raw.get("completed", True))),
        "notes": text_value(raw.get("notes")),
    }
    if load_unit in {"kg", "lb", "assisted_kg"} and item["load_value"] is None:
        raise ValueError("LOAD_VALUE_REQUIRED")
    if load_unit in {"bodyweight", "none"} and item["load_value"] is not None:
        raise ValueError("LOAD_VALUE_NOT_APPLICABLE")
    if measurement_mode in {"weight_reps", "bodyweight_reps", "assisted_reps"} and item["reps"] is None:
        raise ValueError("REPS_REQUIRED")
    if measurement_mode == "duration" and item["duration_seconds"] is None:
        raise ValueError("DURATION_REQUIRED")
    if measurement_mode == "distance_duration" and item["duration_seconds"] is None and item["distance_meters"] is None:
        raise ValueError("DISTANCE_OR_DURATION_REQUIRED")
    if measurement_mode == "dance_practice" and item["duration_seconds"] is None and item["reps"] is None:
        raise ValueError("DANCE_DURATION_OR_COUNT_REQUIRED")
    return item


def _clean_exercises(connection, exercises):
    catalog = exercise_catalog_by_id(connection)
    result = []
    for sequence, raw in enumerate(exercises, 1):
        catalog_id = raw.get("exercise_catalog_id")
        selected = catalog.get(int(catalog_id)) if catalog_id not in (None, "") else None
        custom = text_value(raw.get("custom_exercise_name"))
        if not selected and not custom:
            raise ValueError("EXERCISE_NAME_REQUIRED")
        mode = enum_value(
            "measurement_mode", raw.get("measurement_mode") or (
                selected["measurement_mode"] if selected else "freeform"
            ), MEASUREMENT_MODES,
        )
        category = enum_value(
            "exercise_category", raw.get("exercise_category") or (
                selected["exercise_category"] if selected else "other"
            ), EXERCISE_CATEGORIES,
        )
        sets = []
        for number, set_raw in enumerate(raw.get("sets") or [], 1):
            cleaned = _clean_set(set_raw, mode, number)
            if cleaned:
                sets.append(cleaned)
        result.append({
            "uuid": str(raw.get("uuid") or _uuid()),
            "exercise_catalog_id": selected["id"] if selected else None,
            "custom_exercise_name": None if selected else custom,
            "sequence_order": sequence, "exercise_category": category,
            "measurement_mode": mode,
            "primary_muscle_group": text_value(raw.get("primary_muscle_group")) or (
                selected.get("primary_muscle_group") if selected else None
            ),
            "equipment": text_value(raw.get("equipment")) or (
                selected.get("equipment") if selected else None
            ),
            "is_unilateral": int(bool(raw.get("is_unilateral", selected.get("is_unilateral") if selected else False))),
            "skill_proficiency": finite_number("skill_proficiency", raw.get("skill_proficiency"), 1, 10),
            "notes": text_value(raw.get("notes")), "sets": sets,
            "training_prescription_id": raw.get("training_prescription_id"),
            "module_key": text_value(raw.get("module_key")),
            "planned_sets_json": raw.get("planned_sets_json"),
            "completion_status": text_value(raw.get("completion_status")),
        })
    return result


def save_training_details(connection: sqlite3.Connection, session_id, details, exercises):
    current = get_training_session(connection, session_id)
    if not current:
        raise ValueError("TRAINING_SESSION_NOT_FOUND")
    forbidden = {
        "average_hr", "max_hr", "calories", "distance_meters", "duration_seconds",
        "start_time", "end_time", "date",
    }
    if current["polar_readonly"] and forbidden.intersection(details):
        raise ValueError("POLAR_OBJECTIVE_FIELDS_READ_ONLY")
    status = enum_value("training_status", details.get("status", current["status"]), TRAINING_STATUSES)
    sport = text_value(details.get("resolved_sport_type"))
    if sport == current.get("sport_display"):
        sport = current.get("resolved_sport_type")
    source = current["resolved_sport_type_source"]
    if sport and sport != current.get("resolved_sport_type"):
        source = "manual_override" if current["polar_readonly"] else "manual"
    cleaned = _clean_exercises(connection, exercises)
    with connection:
        connection.execute(
            """UPDATE training_sessions SET resolved_sport_type=?,
                   resolved_sport_type_source=?,status=?,notes=?,
                   training_program_id=COALESCE(?,training_program_id),
                   training_day_template_id=COALESCE(?,training_day_template_id),
                   prescription_snapshot_json=COALESCE(?,prescription_snapshot_json),
                   hprs_adjustment_json=COALESCE(?,hprs_adjustment_json),
                   updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                sport or current.get("resolved_sport_type"), source, status,
                text_value(details.get("notes")), details.get("training_program_id"),
                details.get("training_day_template_id"), details.get("prescription_snapshot_json"),
                details.get("hprs_adjustment_json"), session_id,
            ),
        )
        connection.execute(
            """UPDATE training_sets SET deleted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
               WHERE training_exercise_id IN (
                   SELECT id FROM training_exercises WHERE training_session_id=? AND deleted_at IS NULL
               ) AND deleted_at IS NULL""", (session_id,),
        )
        connection.execute(
            """UPDATE training_exercises SET deleted_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE training_session_id=? AND deleted_at IS NULL""",
            (session_id,),
        )
        for exercise in cleaned:
            exercise_id = connection.execute(
                """INSERT INTO training_exercises(
                       uuid,training_session_id,exercise_catalog_id,custom_exercise_name,
                       sequence_order,exercise_category,measurement_mode,
                       primary_muscle_group,equipment,is_unilateral,
                       skill_proficiency,notes,training_prescription_id,module_key,
                       planned_sets_json,completion_status
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    exercise["uuid"], session_id, exercise["exercise_catalog_id"],
                    exercise["custom_exercise_name"], exercise["sequence_order"],
                    exercise["exercise_category"], exercise["measurement_mode"],
                    exercise["primary_muscle_group"], exercise["equipment"],
                    exercise["is_unilateral"], exercise["skill_proficiency"], exercise["notes"],
                    exercise.get("training_prescription_id"), exercise.get("module_key"),
                    exercise.get("planned_sets_json"), exercise.get("completion_status"),
                ),
            ).lastrowid
            connection.executemany(
                """INSERT INTO training_sets(
                       uuid,training_exercise_id,set_number,set_type,load_value,
                       load_unit,reps,duration_seconds,distance_meters,
                       resistance_level,incline_percent,rpe,rir,rest_seconds,
                       side,completed,notes
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(
                    item["uuid"], exercise_id, item["set_number"], item["set_type"],
                    item["load_value"], item["load_unit"], item["reps"],
                    item["duration_seconds"], item["distance_meters"],
                    item["resistance_level"], item["incline_percent"], item["rpe"],
                    item["rir"], item["rest_seconds"], item["side"],
                    item["completed"], item["notes"],
                ) for item in exercise["sets"]],
            )
    from src.training_plan_actual import auto_match_actual_session
    auto_match_actual_session(connection, session_id)
    return session_id


def soft_delete_training_session(connection, session_id):
    with connection:
        cursor = connection.execute(
            """UPDATE training_sessions SET deleted_at=CURRENT_TIMESTAMP,
                   updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL""",
            (session_id,),
        )
    return cursor.rowcount > 0


def copy_set(set_row):
    return {
        key: value for key, value in set_row.items() if key in {
            "set_type", "load_value", "load_unit", "reps", "duration_seconds",
            "distance_meters", "resistance_level", "incline_percent", "rpe",
            "rir", "rest_seconds", "side", "notes",
        }
    } | {"uuid": _uuid(), "completed": False}


def copy_exercise(exercise, reset_completed=False):
    return {
        key: value for key, value in exercise.items() if key in {
            "exercise_catalog_id", "custom_exercise_name", "exercise_category",
            "measurement_mode", "primary_muscle_group", "equipment",
            "is_unilateral", "skill_proficiency", "notes", "training_prescription_id",
            "module_key", "planned_sets_json", "completion_status",
        }
    } | {
        "uuid": _uuid(),
        "sets": [
            {**copy_set(item), "completed": False if reset_completed else bool(item.get("completed"))}
            for item in exercise.get("sets", [])
        ],
    }


def previous_exercises(connection, before_session_id=None, limit=20):
    params = (before_session_id,) if before_session_id else ()
    where = "AND s.id<>?" if before_session_id else ""
    rows = connection.execute(
        f"""SELECT e.id FROM training_exercises e JOIN training_sessions s
             ON s.id=e.training_session_id WHERE e.deleted_at IS NULL
             AND s.deleted_at IS NULL {where}
             ORDER BY s.date DESC,s.start_time DESC,e.sequence_order LIMIT ?""",
        (*params, limit),
    ).fetchall()
    result = []
    for row in rows:
        exercise = dict(connection.execute("SELECT * FROM training_exercises WHERE id=?", (row[0],)).fetchone())
        exercise["sets"] = [dict(item) for item in connection.execute(
            "SELECT * FROM training_sets WHERE training_exercise_id=? AND deleted_at IS NULL ORDER BY set_number",
            (row[0],),
        ).fetchall()]
        result.append(exercise)
    return result


def ai_training_summaries(connection, summary_date):
    sessions = []
    for row in connection.execute(
        """SELECT id FROM training_sessions WHERE date=? AND status='completed'
           AND deleted_at IS NULL ORDER BY start_time,id""", (summary_date,)
    ).fetchall():
        item = get_training_session(connection, row[0])
        sessions.append({
            "date": item["date"], "sport_type": item.get("resolved_sport_type"),
            "duration_minutes": round(item["duration_seconds"] / 60, 2)
            if item.get("duration_seconds") is not None else None,
            "average_hr": item.get("average_hr"), "max_hr": item.get("max_hr"),
            "calories": item.get("calories"), **item["summary"],
        })
    return sessions
