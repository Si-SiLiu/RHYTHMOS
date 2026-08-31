from pathlib import Path

from .audit import create_audit, create_failure_audit
from .config import load_config
from .field_ocr import parse_template_regions
from .parser import merge_parse_results, parse_ocr_result
from .image_preprocess import UnsupportedImageError
from .ocr_adapter import LocalOCRError, VisionOCRAdapter
from .quality import check_image_quality
from .review import build_review
from .models import StoredImage
from .storage import find_by_hash, resolve_relative_path, sha256_bytes, store_image_bytes
from .template_detector import detect_template
from .templates import get_template, load_template_config


def recognize_prepared(connection, prepared, template_id, adapter=None, config=None, template_config=None):
    config = config or load_config()
    adapter = adapter or VisionOCRAdapter()
    stored = prepared["stored"]
    ocr = prepared.get("ocr") or adapter.recognize(resolve_relative_path(stored.processed_relative_path))
    template = get_template(template_id, template_config or load_template_config())
    parsed = parse_template_regions(resolve_relative_path(stored.original_relative_path), template, adapter, config)
    status = "review_required" if not parsed.missing_required_fields else "needs_manual_input"
    audit_id = create_audit(connection, stored, ocr, parsed, status=status)
    return {
        "status": status, "audit_id": audit_id, "duplicate": False,
        "stored": stored, "quality": prepared.get("quality"), "ocr": ocr,
        "detection": prepared.get("detection"), "template_id": template_id,
        "template": template, "parse": parsed,
        "review": build_review(parsed, config),
    }


def prepare_upload(connection, data, filename, adapter=None, config=None, template_config=None):
    config = config or load_config()
    adapter = adapter or VisionOCRAdapter()
    digest = sha256_bytes(data)
    existing = find_by_hash(connection, digest)
    # A prior attempt can be left at the review stage.  In that case, let the
    # user upload the same image again to resume recognition and confirmation;
    # only a completed import is a true duplicate.
    if existing and existing.get("reviewed"):
        return {"status": "duplicate", "audit_id": existing["id"], "duplicate": True, "review": None}
    if existing:
        stored = StoredImage(
            digest,
            existing["original_relative_path"],
            existing.get("processed_relative_path") or "",
            True,
        )
    else:
        stored = store_image_bytes(data, filename, connection=connection, config=config)
    try:
        quality = check_image_quality(resolve_relative_path(stored.original_relative_path))
        if not quality.acceptable:
            audit_id = create_failure_audit(
                connection, stored, adapter.engine, "unknown", config["parser_version"],
                "image_quality_rejected", "Screenshot quality is not sufficient for template OCR.",
                status="quality_rejected",
            )
            return {"status": "quality_rejected", "audit_id": audit_id,
                    "duplicate": False, "stored": stored, "quality": quality,
                    "review": None}
        ocr = adapter.recognize(resolve_relative_path(stored.processed_relative_path))
        if getattr(adapter, "is_full_image_result", lambda _result: False)(ocr):
            parsed = parse_ocr_result(ocr, config)
            missing_capture_fields = [
                name for name in config["capture_fields"] if name not in parsed.fields
            ]
            if missing_capture_fields and hasattr(adapter, "recognize_missing_fields"):
                try:
                    focused_ocr = adapter.recognize_missing_fields(
                        resolve_relative_path(stored.processed_relative_path),
                        missing_capture_fields,
                    )
                    parsed = merge_parse_results(parsed, parse_ocr_result(focused_ocr, config), config)
                except LocalOCRError:
                    # The first pass remains reviewable if a focused retry is
                    # unavailable or the network briefly fails.
                    pass
            status = "review_required" if not parsed.missing_required_fields else "needs_manual_input"
            audit_id = create_audit(connection, stored, ocr, parsed, status=status)
            return {
                "status": status, "audit_id": audit_id, "duplicate": False,
                "stored": stored, "quality": quality, "ocr": ocr,
                "detection": None, "template_id": None, "template": None,
                "parse": parsed, "review": build_review(parsed, config),
            }
        template_config = template_config or load_template_config()
        detection = detect_template(ocr.image_size, ocr.text_blocks, template_config)
        prepared = {"stored": stored, "quality": quality, "ocr": ocr, "detection": detection}
        if detection.requires_manual_selection or not detection.template_id:
            audit_id = create_failure_audit(
                connection, stored, ocr.engine, ocr.engine_version, config["parser_version"],
                "template_selection_required", "Screenshot type requires explicit user selection.",
                status="template_selection_required",
            )
            return {"status": "template_selection_required", "audit_id": audit_id,
                    "duplicate": False, **prepared, "review": None}
        return recognize_prepared(connection, prepared, detection.template_id, adapter, config, template_config)
    except LocalOCRError as exc:
        audit_id = create_failure_audit(
            connection, stored, adapter.engine, "unknown", config["parser_version"],
            str(exc), "Local OCR could not recognize this image.",
        )
        return {"status": "parsing_failed", "audit_id": audit_id,
                "duplicate": False, "error_code": str(exc), "review": None}


def process_upload(connection, data, filename, adapter=None, config=None, template_config=None):
    return prepare_upload(connection, data, filename, adapter, config, template_config)


def process_batch(connection, uploads, adapter=None, config=None, template_config=None):
    results = []
    for filename, data in uploads:
        try:
            results.append(process_upload(connection, data, filename, adapter, config, template_config))
        except UnsupportedImageError as exc:
            results.append({"status": "unsupported", "filename": Path(filename).name, "error_code": str(exc), "review": None})
        except Exception:
            results.append({"status": "parsing_failed", "filename": Path(filename).name, "error_code": "safe_processing_failure", "review": None})
    return results


def batch_summary(results):
    counts = {key: 0 for key in ("recognized", "needs_manual_input", "template_selection_required", "quality_rejected", "duplicate", "parsing_failed", "imported", "skipped")}
    for result in results:
        status = result.get("status")
        if status == "review_required":
            counts["recognized"] += 1
        elif status in counts:
            counts[status] += 1
        elif status == "unsupported":
            counts["parsing_failed"] += 1
    return counts
