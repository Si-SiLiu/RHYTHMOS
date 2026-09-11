"""Reviewed iPhone screenshot measurements entering the existing Kubios model.

The iPhone recognizes screenshot text locally.  This module deliberately
receives no image bytes or OCR text: only the user-reviewed core values and a
SHA-256 fingerprint are persisted, with screenshot provenance.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from . import kubios_import
from .db import connect
from .kubios_metrics.normalizer import rebuild as rebuild_kubios_normalized
from .kubios_screenshot.validation import validate_confirmed_fields


class MobileKubiosImportError(ValueError):
    """A validation failure safe to return to the iPhone."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DIRECT_SOURCES = {"ios_bluetooth_hrv", "ios_healthkit_hrv"}
_SCREENSHOT_FIELDS = (
    "date", "rmssd", "mean_hr", "sdnn", "pns_index", "sns_index",
    "stress_index", "mean_rr_ms", "poincare_sd1_ms", "poincare_sd2_ms",
    "respiratory_rate_bpm", "lf_power_ms2", "hf_power_ms2", "lf_power_nu",
    "hf_power_nu", "lf_hf_ratio", "physiological_age", "measurement_quality",
)


def _validated_fields(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if payload.get("user_confirmed") is not True:
        raise MobileKubiosImportError("SCREENSHOT_REVIEW_REQUIRED")
    image_sha256 = str(payload.get("image_sha256") or "").lower()
    if not _SHA256.fullmatch(image_sha256):
        raise MobileKubiosImportError("INVALID_SCREENSHOT_FINGERPRINT")
    fields = {name: payload.get(name) for name in _SCREENSHOT_FIELDS}
    normalized, errors = validate_confirmed_fields(fields)
    if errors:
        raise MobileKubiosImportError("INVALID_SCREENSHOT_VALUES")
    return normalized, image_sha256


def import_mobile_screenshot_measurement(
    payload: dict[str, Any],
    *,
    db_path=None,
    rebuild_recovery: bool = True,
) -> dict[str, Any]:
    """Persist one reviewed iOS screenshot as the selected morning source."""
    fields, image_sha256 = _validated_fields(payload)
    date_value = fields["date"]
    reviewed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    row = {
        "external_id": f"mobile-screenshot:{image_sha256}",
        "date": date_value,
        "measurement_time": None,
        "rmssd": fields.get("rmssd"),
        "mean_hr": fields.get("mean_hr"),
        "readiness": None,
        "measurement_quality": fields.get("measurement_quality"),
        "raw": {
            "input_method": "ios_local_vision_review",
            "image_sha256": image_sha256,
            "fields": fields,
        },
        "source_type": "screenshot_ocr",
        "source_file_sha256": image_sha256,
        "ocr_confidence": None,
        "reviewed": True,
        "reviewed_at": reviewed_at,
        "import_method": "ios_local_vision",
        "is_daily_preferred": True,
    }
    # Keep the reviewed extended values in the normalized Kubios measurement
    # model as well as the compact legacy row.  The normalizer maps ``sdnn``
    # and the other screenshot field names to its canonical columns.
    row.update({
        name: fields.get(name)
        for name in _SCREENSHOT_FIELDS
        if name not in {"date", "rmssd", "mean_hr", "measurement_quality"}
    })
    connection = connect(db_path)
    try:
        connection.execute(
            "UPDATE kubios_morning_hrv_raw SET is_daily_preferred=0 WHERE date=?",
            (date_value,),
        )
        kubios_import.upsert_kubios_rows(connection, [row])
        kubios_import.sync_daily_metrics(connection, [row])
        rebuild_kubios_normalized(connection, dates=[date_value])
        record = connection.execute(
            "SELECT id FROM kubios_morning_hrv_raw WHERE source_file_sha256=? AND date=?",
            (image_sha256, date_value),
        ).fetchone()
    finally:
        connection.close()
    if rebuild_recovery:
        if db_path is not None:
            raise MobileKubiosImportError("CUSTOM_DATABASE_REBUILD_UNSUPPORTED")
        _rebuild_recovery_projection()
    return {"date": date_value, "raw_record_id": record[0] if record else None}


def import_mobile_morning_hrv_measurement(
    payload: dict[str, Any],
    *,
    db_path=None,
    rebuild_recovery: bool = True,
) -> dict[str, Any]:
    """Persist an explicitly reviewed iPhone device or HealthKit measurement.

    Only derived metrics and a stable fingerprint reach the service; RR traces
    and HealthKit payloads never leave the iPhone.
    """
    if payload.get("user_confirmed") is not True:
        raise MobileKubiosImportError("DEVICE_MEASUREMENT_REVIEW_REQUIRED")
    source_type = str(payload.get("source_type") or "")
    if source_type not in _DIRECT_SOURCES:
        raise MobileKubiosImportError("UNSUPPORTED_DEVICE_MEASUREMENT_SOURCE")
    fingerprint = str(payload.get("measurement_sha256") or "").lower()
    if not _SHA256.fullmatch(fingerprint):
        raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT_FINGERPRINT")
    try:
        date_value = datetime.fromisoformat(str(payload.get("date"))).date().isoformat()
        duration = float(payload.get("measurement_duration_seconds"))
    except (TypeError, ValueError):
        raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT") from None
    if not 60 <= duration <= 900:
        raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT_DURATION")

    def number(name: str, low: float, high: float, *, required=False):
        value = payload.get(name)
        if value in (None, ""):
            if required:
                raise MobileKubiosImportError("MISSING_DEVICE_MEASUREMENT_METRIC")
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT") from None
        if not low <= result <= high:
            raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT")
        return result

    rmssd = number("rmssd", 0.1, 1000)
    sdnn = number("sdnn", 0.1, 1000)
    mean_hr = number("mean_hr", 20, 250, required=True)
    if rmssd is None and sdnn is None:
        raise MobileKubiosImportError("MISSING_DEVICE_MEASUREMENT_METRIC")
    measurement_time = str(payload.get("measurement_time") or "").strip() or None
    if measurement_time and not measurement_time.startswith(date_value):
        raise MobileKubiosImportError("INVALID_DEVICE_MEASUREMENT_TIME")
    row = {
        "external_id": f"{source_type}:{fingerprint}",
        "date": date_value,
        "measurement_time": measurement_time,
        "rmssd": rmssd,
        "mean_hr": mean_hr,
        "readiness": None,
        "sdnn_ms": sdnn,
        "mean_rr_ms": number("mean_rr_ms", 100, 3000),
        "poincare_sd1_ms": number("poincare_sd1_ms", 0.1, 1000),
        "poincare_sd2_ms": number("poincare_sd2_ms", 0.1, 2000),
        "artefact_correction_percent": number("artefact_correction_percent", 0, 100),
        "measurement_duration_seconds": duration,
        "measurement_quality": "GOOD",
        "raw": {
            "input_method": "ios_local_device_measurement",
            "measurement_sha256": fingerprint,
            "source_type": source_type,
            "device_name": str(payload.get("device_name") or "")[:120],
            "valid_rr_count": payload.get("valid_rr_count"),
        },
        "source_type": source_type,
        "source_file_sha256": fingerprint,
        "reviewed": True,
        "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "import_method": "ios_bluetooth" if source_type == "ios_bluetooth_hrv" else "ios_healthkit",
        "is_daily_preferred": True,
    }
    connection = connect(db_path)
    try:
        connection.execute(
            "UPDATE kubios_morning_hrv_raw SET is_daily_preferred=0 WHERE date=?",
            (date_value,),
        )
        kubios_import.upsert_kubios_rows(connection, [row])
        kubios_import.sync_daily_metrics(connection, [row])
        rebuild_kubios_normalized(connection, dates=[date_value])
        record = connection.execute(
            "SELECT id FROM kubios_morning_hrv_raw WHERE source_file_sha256=? AND date=?",
            (fingerprint, date_value),
        ).fetchone()
    finally:
        connection.close()
    if rebuild_recovery:
        if db_path is not None:
            raise MobileKubiosImportError("CUSTOM_DATABASE_REBUILD_UNSUPPORTED")
        _rebuild_recovery_projection()
    return {"date": date_value, "raw_record_id": record[0] if record else None}


def _rebuild_recovery_projection() -> None:
    """Apply the same deterministic recovery updates as the desktop workflow."""
    from .pipeline import baseline, confidence, local_coach, metrics, recovery

    context: dict[str, Any] = {"results": {}}
    for name, runner in (
        ("metrics", metrics.run),
        ("baseline", baseline.run),
        ("recovery", recovery.run),
        ("confidence", confidence.run),
        ("local-coach", local_coach.run),
    ):
        context["results"][name] = runner(context, dry_run=False)
