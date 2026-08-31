"""Training-plan and structured-prescription data access.

The plan layer is intentionally separate from Polar and actual-set storage.
Plans describe intent; ``training_sessions``, ``training_exercises`` and
``training_sets`` remain the source of actual completion data.
"""

from __future__ import annotations

from datetime import date
import json
import sqlite3
from uuid import uuid4


MODULES = (
    "mobility", "core_activation", "isometric_overload", "explosive",
    "main_strength", "accessory_strength", "small_muscle", "daily_plan",
)
MODULE_COLORS = {
    "mobility": "#dbeafe",
    "core_activation": "#d8f3f0",
    "isometric_overload": "#ffedd5",
    "explosive": "#dcfce7",
    "main_strength": "#fee2e2",
    "accessory_strength": "#fce7f3",
    "small_muscle": "#ede9fe",
    "daily_plan": "#e5e7eb",
}
WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SPORT_TYPES = ("performance_dance", "indoor_strength", "track_field")


def _uuid():
    return str(uuid4())


def _json(value, fallback):
    try:
        parsed = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
    return parsed


def create_training_program(connection: sqlite3.Connection, name, *, description=None,
                            start_date=None, end_date=None, status="active"):
    with connection:
        return connection.execute(
            """INSERT INTO training_programs(uuid,name,description,status,start_date,end_date)
               VALUES(?,?,?,?,?,?)""",
            (_uuid(), str(name).strip(), description, status, start_date, end_date),
        ).lastrowid


def create_training_day_template(connection: sqlite3.Connection, program_id, day_key,
                                 day_label, *, sequence_order=1, notes=None,
                                 sport_type="indoor_strength", planned_date=None):
    normalized_date = (
        date.fromisoformat(str(planned_date)).isoformat()
        if planned_date not in (None, "") else None
    )
    with connection:
        return connection.execute(
            """INSERT INTO training_day_templates(
                   uuid,training_program_id,day_key,day_label,sequence_order,notes,sport_type,planned_date
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (_uuid(), program_id, day_key, day_label, sequence_order, notes, sport_type, normalized_date),
        ).lastrowid


def update_training_day_template_notes(connection: sqlite3.Connection, day_template_id, notes):
    """Save the short plan note shown under a date in the weekly matrix."""
    with connection:
        connection.execute(
            "UPDATE training_day_templates SET notes=? WHERE id=?",
            (str(notes).strip() or None, day_template_id),
        )


def update_training_day_sport_type(connection: sqlite3.Connection, day_template_id, sport_type):
    if sport_type not in SPORT_TYPES:
        raise ValueError(f"Unsupported sport type: {sport_type}")
    with connection:
        connection.execute(
            "UPDATE training_day_templates SET sport_type=? WHERE id=?",
            (sport_type, day_template_id),
        )


def update_training_day_planned_date(connection: sqlite3.Connection, day_template_id, planned_date):
    """Persist the manually chosen date for a weekly-plan day."""
    normalized_date = (
        date.fromisoformat(str(planned_date)).isoformat()
        if planned_date not in (None, "") else None
    )
    with connection:
        connection.execute(
            "UPDATE training_day_templates SET planned_date=? WHERE id=?",
            (normalized_date, day_template_id),
        )


def training_day_plan_entries(day):
    """Read sport-type-specific freeform plan entries from a day template."""
    try:
        payload = json.loads(day.get("notes") or "")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    entries = payload.get("sport_plans", {}) if isinstance(payload, dict) else {}
    return entries if isinstance(entries, dict) else {}


def update_training_day_plan_entry(connection: sqlite3.Connection, day_template_id,
                                   sport_type, content):
    """Save one sport type's concrete daily plan while preserving other types."""
    row = connection.execute(
        "SELECT notes FROM training_day_templates WHERE id=?", (day_template_id,)
    ).fetchone()
    entries = training_day_plan_entries(dict(row) if row else {})
    value = str(content or "").strip()
    if value:
        entries[sport_type] = value
    else:
        entries.pop(sport_type, None)
    payload = json.dumps({"sport_plans": entries}, ensure_ascii=False) if entries else None
    with connection:
        connection.execute(
            "UPDATE training_day_templates SET notes=? WHERE id=?",
            (payload, day_template_id),
        )


def create_training_block(connection: sqlite3.Connection, day_template_id, module_key,
                          module_label, *, sequence_order=1, notes=None):
    if module_key not in MODULES:
        raise ValueError(f"Unsupported training module: {module_key}")
    with connection:
        return connection.execute(
            """INSERT INTO training_blocks(
                   uuid,training_day_template_id,module_key,module_label,sequence_order,notes
               ) VALUES(?,?,?,?,?,?)""",
            (_uuid(), day_template_id, module_key, module_label, sequence_order, notes),
        ).lastrowid


def get_or_create_training_block(connection: sqlite3.Connection, day_template_id,
                                 module_key, module_label, *, sequence_order=1):
    block = connection.execute(
        """SELECT id FROM training_blocks
           WHERE training_day_template_id=? AND module_key=? AND deleted_at IS NULL
           ORDER BY id LIMIT 1""",
        (day_template_id, module_key),
    ).fetchone()
    if block:
        return block["id"]
    return create_training_block(
        connection, day_template_id, module_key, module_label,
        sequence_order=sequence_order,
    )


def create_training_prescription(connection: sqlite3.Connection, block_id, *,
                                 exercise_catalog_id=None, custom_exercise_name=None,
                                 prescription_name=None, sequence_order=1,
                                 planned_sets=None, target_notes=None,
                                 hprs_snapshot=None):
    planned_sets = planned_sets if planned_sets is not None else []
    with connection:
        return connection.execute(
            """INSERT INTO training_prescriptions(
                   uuid,training_block_id,exercise_catalog_id,custom_exercise_name,
                   sequence_order,prescription_name,planned_sets_json,target_notes,
                   hprs_snapshot_json
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (_uuid(), block_id, exercise_catalog_id, custom_exercise_name,
             sequence_order, prescription_name, json.dumps(planned_sets, ensure_ascii=False),
             target_notes, json.dumps(hprs_snapshot, ensure_ascii=False) if hprs_snapshot else None),
        ).lastrowid


def delete_training_prescription(connection: sqlite3.Connection, prescription_id):
    with connection:
        connection.execute(
            "UPDATE training_prescriptions SET deleted_at=CURRENT_TIMESTAMP WHERE id=?",
            (prescription_id,),
        )


def import_weekly_training_plan(connection: sqlite3.Connection, day_specs, *,
                                program_name="本周训练计划"):
    """Import a compact weekly prescription matrix without duplicating entries.

    ``day_specs`` is deliberately small and UI-independent so a plan can be
    imported from a spreadsheet/image/manual mapping without changing the
    existing editor. Each prescription accepts ``name``, ``planned_sets`` and
    optional ``target_notes``.
    """
    program = connection.execute(
        """SELECT * FROM training_programs
           WHERE deleted_at IS NULL AND status='active' AND name=?
           ORDER BY id DESC LIMIT 1""",
        (program_name,),
    ).fetchone()
    if program is None:
        program_id = create_training_program(connection, program_name)
        program = connection.execute(
            "SELECT * FROM training_programs WHERE id=?", (program_id,)
        ).fetchone()
    program_id = program["id"]

    day_labels = {
        "mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四",
        "fri": "周五", "sat": "周六", "sun": "周日",
    }
    imported = {"days": 0, "blocks": 0, "prescriptions": 0, "skipped": 0}
    for day_order, day_spec in enumerate(day_specs, start=1):
        day_key = day_spec["day_key"]
        day = connection.execute(
            """SELECT * FROM training_day_templates
               WHERE training_program_id=? AND day_key=? AND deleted_at IS NULL
               ORDER BY id LIMIT 1""",
            (program_id, day_key),
        ).fetchone()
        if day is None:
            day_id = create_training_day_template(
                connection, program_id, day_key,
                day_spec.get("day_label") or day_labels.get(day_key, day_key),
                sequence_order=day_order,
                planned_date=day_spec.get("planned_date"),
            )
            day = connection.execute(
                "SELECT * FROM training_day_templates WHERE id=?", (day_id,)
            ).fetchone()
            imported["days"] += 1

        for block_order, block_spec in enumerate(day_spec.get("blocks", []), start=1):
            block = connection.execute(
                """SELECT * FROM training_blocks
                   WHERE training_day_template_id=? AND module_key=? AND deleted_at IS NULL
                   ORDER BY id LIMIT 1""",
                (day["id"], block_spec["module_key"]),
            ).fetchone()
            if block is None:
                block_id = create_training_block(
                    connection, day["id"], block_spec["module_key"],
                    block_spec["module_label"], sequence_order=block_order,
                )
                block = connection.execute(
                    "SELECT * FROM training_blocks WHERE id=?", (block_id,)
                ).fetchone()
                imported["blocks"] += 1

            for prescription_order, prescription in enumerate(
                block_spec.get("prescriptions", []), start=1
            ):
                name = prescription["name"].strip()
                exists = connection.execute(
                    """SELECT id FROM training_prescriptions
                       WHERE training_block_id=? AND deleted_at IS NULL
                         AND COALESCE(prescription_name, custom_exercise_name)=?
                       LIMIT 1""",
                    (block["id"], name),
                ).fetchone()
                if exists:
                    imported["skipped"] += 1
                    continue
                create_training_prescription(
                    connection, block["id"],
                    custom_exercise_name=name,
                    prescription_name=name,
                    sequence_order=prescription_order,
                    planned_sets=prescription.get("planned_sets", []),
                    target_notes=prescription.get("target_notes"),
                )
                imported["prescriptions"] += 1
    return {"program_id": program_id, **imported}


def _active_program(connection, target_date):
    return connection.execute(
        """SELECT * FROM training_programs
           WHERE deleted_at IS NULL AND status='active'
             AND (start_date IS NULL OR start_date<=?)
             AND (end_date IS NULL OR end_date>=?)
           ORDER BY start_date DESC,id DESC LIMIT 1""",
        (target_date.isoformat(), target_date.isoformat()),
    ).fetchone()


def get_weekly_training_plan(connection: sqlite3.Connection, anchor_date=None):
    anchor = anchor_date or date.today()
    program = _active_program(connection, anchor)
    result = {"program": dict(program) if program else None, "days": []}
    if not program:
        return result
    day_rows = connection.execute(
        """SELECT * FROM training_day_templates
           WHERE training_program_id=? AND deleted_at IS NULL
           ORDER BY sequence_order,id""", (program["id"],)
    ).fetchall()
    for day_row in day_rows:
        day = dict(day_row)
        blocks = []
        for block_row in connection.execute(
            """SELECT * FROM training_blocks
               WHERE training_day_template_id=? AND deleted_at IS NULL
               ORDER BY sequence_order,id""", (day["id"],)
        ).fetchall():
            block = dict(block_row)
            prescriptions = []
            for item in connection.execute(
                """SELECT p.*, c.display_name_zh, c.display_name_en, c.measurement_mode
                   FROM training_prescriptions p
                   LEFT JOIN exercise_catalog c ON c.id=p.exercise_catalog_id
                   WHERE p.training_block_id=? AND p.deleted_at IS NULL
                   ORDER BY p.sequence_order,p.id""", (block["id"],)
            ).fetchall():
                prescription = dict(item)
                prescription["planned_sets"] = _json(prescription.pop("planned_sets_json"), [])
                prescription["hprs_snapshot"] = _json(prescription.pop("hprs_snapshot_json"), None)
                prescriptions.append(prescription)
            block["prescriptions"] = prescriptions
            blocks.append(block)
        day["blocks"] = blocks
        day["prescription_count"] = sum(len(block["prescriptions"]) for block in blocks)
        result["days"].append(day)
    return result


def plan_day_for_date(plan, target_date=None):
    target = target_date or date.today()
    target_iso = target.isoformat()
    dated_days = [day for day in plan.get("days", []) if day.get("planned_date")]
    if dated_days:
        exact = next((day for day in dated_days if day["planned_date"] == target_iso), None)
        if exact:
            return exact
    key = WEEKDAY_KEYS[target.weekday()]
    fallback = next((day for day in plan.get("days", []) if day["day_key"] == key), None)
    return fallback if fallback and not fallback.get("planned_date") else None


def prescription_snapshot(day):
    if not day:
        return []
    return [
        {
            "module_key": block["module_key"],
            "module_label": block["module_label"],
            "prescriptions": [
                {
                    "id": item["id"],
                    "exercise_catalog_id": item.get("exercise_catalog_id"),
                    "name": item.get("display_name_zh") or item.get("display_name_en") or item.get("custom_exercise_name"),
                    "planned_sets": item.get("planned_sets", []),
                    "hprs_snapshot": item.get("hprs_snapshot"),
                }
                for item in block.get("prescriptions", [])
            ],
        }
        for block in day.get("blocks", [])
    ]


def build_hprs_snapshot(planned_sets, *, status="unknown", volume_adjustment_percent=None,
                        intensity_adjustment_percent=None, reason=None):
    """Create an immutable, explainable adjustment snapshot for a prescription."""
    original = [dict(item) for item in (planned_sets or [])]
    volume_factor = 1 + (volume_adjustment_percent or 0) / 100
    intensity_factor = 1 + (intensity_adjustment_percent or 0) / 100
    regulated = []
    for item in original:
        adjusted = dict(item)
        if item.get("reps") is not None:
            adjusted["reps"] = max(1, round(float(item["reps"]) * volume_factor))
        if item.get("load_value") is not None:
            adjusted["load_value"] = max(0, round(float(item["load_value"]) * intensity_factor, 2))
        regulated.append(adjusted)
    return {
        "version": "hprs-v1",
        "status": status,
        "volume_adjustment_percent": volume_adjustment_percent,
        "intensity_adjustment_percent": intensity_adjustment_percent,
        "reason": reason,
        "original_sets": original,
        "regulated_sets": regulated,
    }


def analyze_plan_actual(day, exercises):
    """Return compact plan-vs-actual metrics for a selected training day."""
    prescriptions = [
        (block, item)
        for block in (day or {}).get("blocks", [])
        for item in block.get("prescriptions", [])
    ]
    actual_by_prescription = {
        item.get("training_prescription_id"): item
        for item in (exercises or []) if item.get("training_prescription_id") is not None
    }
    planned_count = len(prescriptions)
    matched = sum(item["id"] in actual_by_prescription for _, item in prescriptions)
    actual_sets = [set_item for exercise in (exercises or []) for set_item in exercise.get("sets", [])]
    completed_sets = sum(bool(item.get("completed")) for item in actual_sets)
    planned_sets = sum(len(item.get("planned_sets", [])) for _, item in prescriptions)
    planned_volume = sum(
        float(set_item.get("load_value") or 0) * float(set_item.get("reps") or 0)
        for _, item in prescriptions for set_item in item.get("planned_sets", [])
    )
    actual_volume = sum(
        float(set_item.get("load_value") or 0) * float(set_item.get("reps") or 0)
        for set_item in actual_sets
    )
    module_rates = {}
    for block in (day or {}).get("blocks", []):
        block_prescriptions = block.get("prescriptions", [])
        block_ids = {item["id"] for item in block_prescriptions}
        block_actual = [item for item in (exercises or []) if item.get("training_prescription_id") in block_ids]
        block_planned = sum(len(item.get("planned_sets", [])) for item in block_prescriptions)
        block_completed = sum(bool(set_item.get("completed")) for item in block_actual for set_item in item.get("sets", []))
        module_rates[block["module_key"]] = round(block_completed / block_planned * 100, 1) if block_planned else None
    return {
        "planned_exercises": planned_count,
        "matched_exercises": matched,
        "exercise_completion_rate": round(matched / planned_count * 100, 1) if planned_count else None,
        "planned_sets": planned_sets,
        "actual_sets": len(actual_sets),
        "completed_sets": completed_sets,
        "set_completion_rate": round(completed_sets / planned_sets * 100, 1) if planned_sets else None,
        "planned_volume": planned_volume,
        "actual_volume": actual_volume,
        "module_rates": module_rates,
    }
