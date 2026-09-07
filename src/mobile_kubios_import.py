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


def _validated_fields(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if payload.get("user_confirmed") is not True:
        raise MobileKubiosImportError("SCREENSHOT_REVIEW_REQUIRED")
    image_sha256 = str(payload.get("image_sha256") or "").lower()
    if not _SHA256.fullmatch(image_sha256):
        raise MobileKubiosImportError("INVALID_SCREENSHOT_FINGERPRINT")
    fields = {
        "date": payload.get("date"),
        "rmssd": payload.get("rmssd"),
        "mean_hr": payload.get("mean_hr"),
        "measurement_quality": payload.get("measurement_quality"),
    }
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
