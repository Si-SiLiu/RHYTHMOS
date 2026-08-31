"""Validated manual input storage for Kubios morning autonomic measurements."""

from __future__ import annotations

import json


MEASUREMENT_QUALITIES = ("GOOD", "ACCEPTABLE", "POOR", "INVALID")
MANUAL_SOURCE = "kubios_manual"


def normalize_measurement_quality(value):
    if value in (None, ""):
        return None
    normalized = str(value).strip().upper()
    if normalized not in MEASUREMENT_QUALITIES:
        raise ValueError("measurement_quality_invalid")
    return normalized


def _optional_number(value, field, *, minimum=None, maximum=None, strict_minimum=False):
    if value in (None, ""):
        return None
    number = float(value)
    if minimum is not None and (number <= minimum if strict_minimum else number < minimum):
        raise ValueError(f"{field}_out_of_range")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field}_out_of_range")
    return number


def validate_morning_measurement(values):
    return {
        "rmssd": _optional_number(values.get("rmssd"), "rmssd", minimum=0, strict_minimum=True),
        "mean_hr": _optional_number(values.get("mean_hr"), "mean_hr", minimum=20, maximum=300),
        "stress_index": _optional_number(values.get("stress_index"), "stress_index", minimum=0),
        "respiratory_rate": _optional_number(
            values.get("respiratory_rate"), "respiratory_rate", minimum=0, maximum=80,
            strict_minimum=True,
        ),
        "measurement_quality": normalize_measurement_quality(values.get("measurement_quality")),
    }


def get_manual_morning_measurement(connection, date_value):
    row = connection.execute(
        """SELECT * FROM kubios_morning_hrv_raw
           WHERE source=? AND external_id=? AND date=? LIMIT 1""",
        (MANUAL_SOURCE, f"manual:{date_value}", date_value),
    ).fetchone()
    return dict(row) if row else None


def upsert_manual_morning_measurement(connection, date_value, values):
    normalized = validate_morning_measurement(values)
    raw_json = json.dumps(
        {"input_method": "dashboard_manual", **normalized},
        ensure_ascii=False,
        sort_keys=True,
    )
    connection.execute(
        """INSERT INTO kubios_morning_hrv_raw (
               source,external_id,date,raw_json,rmssd,mean_hr,stress_index,
               respiratory_rate,measurement_quality,source_type,reviewed,
               import_method,is_daily_preferred
           ) VALUES (?,?,?,?,?,?,?,?,?,'manual',1,'manual',1)
           ON CONFLICT(source,external_id,date) DO UPDATE SET
               raw_json=excluded.raw_json,rmssd=excluded.rmssd,
               mean_hr=excluded.mean_hr,stress_index=excluded.stress_index,
               respiratory_rate=excluded.respiratory_rate,
               measurement_quality=excluded.measurement_quality,
               reviewed=1,import_method='manual',is_daily_preferred=1,
               updated_at=CURRENT_TIMESTAMP""",
        (
            MANUAL_SOURCE, f"manual:{date_value}", date_value, raw_json,
            normalized["rmssd"], normalized["mean_hr"], normalized["stress_index"],
            normalized["respiratory_rate"], normalized["measurement_quality"],
        ),
    )
    connection.commit()
    return get_manual_morning_measurement(connection, date_value)


def sync_manual_morning_measurements(connection, dates=None):
    """Mirror reviewed manual morning fields into the typed Kubios pipeline.

    The legacy recovery table remains the source of record for the form.  This
    projection gives its already-reviewed RMSSD, heart-rate, stress, and
    respiratory-rate fields a typed, provenance-labelled representation for
    trend and baseline calculations.  It deliberately does not infer any
    absent Kubios-only fields such as readiness, PNS/SNS, or SDNN.
    """
    query = """
        SELECT * FROM kubios_morning_hrv_raw
        WHERE source=? AND reviewed=1
    """
    params = [MANUAL_SOURCE]
    if dates:
        placeholders = ",".join("?" for _ in dates)
        query += f" AND date IN ({placeholders})"
        params.extend(sorted(set(dates)))
    rows = [dict(row) for row in connection.execute(query, params).fetchall()]
    if not rows:
        return 0

    try:
        from .kubios_metrics.normalizer import import_raw
    except ImportError:
        from kubios_metrics.normalizer import import_raw

    for row in rows:
        import_raw(
            connection,
            {
                "date": row["date"],
                "measurement_time": row["measurement_time"],
                "rmssd": row["rmssd"],
                "mean_hr": row["mean_hr"],
                "stress_index": row["stress_index"],
                "respiratory_rate_bpm": row["respiratory_rate"],
                "measurement_quality": row["measurement_quality"],
                "reviewed": True,
                "is_daily_preferred": bool(row["is_daily_preferred"]),
                "raw_json": {"input_method": "dashboard_manual"},
            },
            "manual",
            "manual",
            True,
        )
    connection.commit()
    return len(rows)
