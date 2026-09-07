"""Template-based, bilingual, local-only Kubios screenshot review page."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

import hashlib
from datetime import date

import streamlit as st

from src.ui_tables import centered_dataframe

from src.branding import browser_page_title, load_page_icon
from src.db import connect
from src.demo_sandbox import configure_demo_runtime
from src.i18n import get_translator
from src.i18n.ui import current_language, render_sidebar
from src.kubios_screenshot.audit import list_recent
from src.kubios_screenshot.calibration import save_calibration
from src.kubios_screenshot.confidence import confidence_band
from src.kubios_screenshot.config import load_config
from src.kubios_screenshot.downstream import run_downstream
from src.kubios_screenshot.importer import import_reviewed_result
from src.kubios_screenshot.cloud_ocr import PreferredVisionOCRAdapter
from src.kubios_screenshot.region_extractor import render_region_overlay
from src.region_calibrator import render_region_calibrator
from src.kubios_screenshot.service import batch_summary, process_batch, recognize_prepared
from src.kubios_screenshot.storage import BASE_DIR, delete_import
from src.kubios_screenshot.templates import get_template, list_templates
from src.kubios_metrics.selector import create_measurement_group
from src.ui_controls import render_manual_input_styles


LANGUAGE = "zh-CN"
TR = get_translator(LANGUAGE)

FIELD_ORDER = (
    "mean_hr", "rmssd", "pns_index", "sns_index", "physiological_age",
    "mean_rr_ms", "sdnn", "poincare_sd1_ms", "poincare_sd2_ms",
    "stress_index", "respiratory_rate_bpm", "lf_power_ms2", "hf_power_ms2",
    "lf_power_nu", "hf_power_nu", "lf_hf_ratio",
    "measurement_quality", "mood_code",
)


def _empty_review():
    return {
        "fields": {}, "missing_required_fields": ["rmssd", "mean_hr"],
        "warnings": [], "overall_confidence": 0.0,
        "overall_confidence_band": "reject", "review_required": True,
        "user_confirmed": False, "parser_version": load_config()["parser_version"],
    }


def _manual_fallback(result):
    if result.get("audit_id") and st.button(
        TR("kubios_screenshot.manual_fallback"),
        key=f"kubios_manual_fallback_{result['audit_id']}",
    ):
        result["status"] = "needs_manual_input"
        result["review"] = _empty_review()
        st.rerun()


def _select_template(result, adapter):
    audit_id = result["audit_id"]
    st.warning(TR("kubios_screenshot.template_selection_required"))
    detection = result.get("detection")
    if detection and detection.template_id:
        detected = get_template(detection.template_id)
        st.caption(TR("kubios_screenshot.detected_template", template=detected["display_name"], confidence=f"{detection.confidence:.0%}"))
    st.info(TR("kubios_screenshot.template_unverified"))
    templates = list_templates()
    template_ids = [item["template_id"] for item in templates]
    default = template_ids.index(detection.template_id) if detection and detection.template_id in template_ids else 0
    selected = st.selectbox(
        TR("kubios_screenshot.choose_template"), template_ids, index=default,
        format_func=lambda value: get_template(value)["display_name"],
        key=f"kubios_template_{audit_id}",
    )
    if st.button(TR("kubios_screenshot.confirm_template"), key=f"kubios_template_confirm_{audit_id}"):
        with st.spinner(TR("kubios_screenshot.recognizing_regions")):
            with connect(migrate=False) as connection:
                recognized = recognize_prepared(connection, result, selected, adapter=adapter)
        result.clear()
        result.update(recognized)
        st.rerun()


def _show_image(result, active_field):
    stored = result.get("stored")
    if not stored:
        return
    path = BASE_DIR / stored.original_relative_path
    template = result.get("template")
    if template:
        st.image(render_region_overlay(path, template["field_regions"], active_field), width="stretch")
    else:
        st.image(str(path), width="stretch")


def _calibration_editor(result, active_field):
    template = result.get("template")
    if not template or active_field not in template["field_regions"]:
        return
    audit_id = result["audit_id"]
    with st.expander(TR("kubios_screenshot.calibration")):
        st.warning(TR("kubios_screenshot.calibration_notice"))
        current = template["field_regions"][active_field]
        keys = (("x", "region_x"), ("y", "region_y"), ("width", "region_width"), ("height", "region_height"))
        edited = dict(current)
        stored = result.get("stored")
        if stored:
            preview_key = f"kubios_roi_drag_{audit_id}_{active_field}"
            moved = render_region_calibrator(
                image_path=BASE_DIR / stored.original_relative_path,
                region=edited,
                key=preview_key,
            )
            if isinstance(moved, dict) and all(name in moved for name, _ in keys):
                for name, _ in keys:
                    value = float(moved[name])
                    edited[name] = value
                    st.session_state[f"kubios_roi_{audit_id}_{active_field}_{name}"] = value
        for key, label in keys:
            edited[key] = st.number_input(
                TR(f"kubios_screenshot.{label}"), min_value=0.0, max_value=1.0,
                value=float(current[key]), step=0.005, format="%.3f",
                key=f"kubios_roi_{audit_id}_{active_field}_{key}",
            )
        regions = {field: {name: value for name, value in region.items() if name in {"x", "y", "width", "height"}} for field, region in template["field_regions"].items()}
        regions[active_field] = edited
        confirmed = st.checkbox(TR("kubios_screenshot.save_calibration_confirm"), key=f"kubios_calibration_confirm_{audit_id}")
        if st.button(TR("kubios_screenshot.save_calibration"), disabled=not confirmed, key=f"kubios_calibration_save_{audit_id}"):
            try:
                save_calibration(template["template_id"], regions, confirmed=True)
            except (TypeError, ValueError):
                st.error(TR("errors.invalid_value"))
            else:
                st.success(TR("kubios_screenshot.calibration_saved"))


def _show_review(result, *, embedded=False):
    review = result["review"]
    audit_id = result["audit_id"]
    active_key = f"kubios_active_field_{audit_id}"
    active_field = st.session_state.get(active_key, "rmssd")
    st.subheader(TR("kubios_screenshot.recognition_results"))
    confidence = review["overall_confidence"]
    st.metric(TR("kubios_screenshot.ocr_confidence"), f"{confidence:.0%}")
    (st.success if confidence_band(confidence) == "high" else st.warning)(
        TR("kubios_screenshot.high_confidence" if confidence_band(confidence) == "high" else "kubios_screenshot.low_confidence")
    )

    left, right = st.columns([1.05, 1])
    with left:
        _show_image(result, active_field)
        _calibration_editor(result, active_field)
    with right:
        # Screenshot import belongs to today's Recovery entry. The date is
        # assigned internally so it is never an OCR target or a form field.
        values = {"date": date.today().isoformat()}
        # Keep every supported recovery metric editable. Recognition simply
        # pre-fills the values; users can fill gaps or correct any value in
        # the same confirmation step.
        for name in FIELD_ORDER:
            field = review.get("fields", {}).get(name, {})
            if st.button(TR("kubios_screenshot.focus_field", field=TR(f"kubios_screenshot.{name}")), key=f"kubios_focus_{audit_id}_{name}"):
                st.session_state[active_key] = name
                st.rerun()
            values[name] = st.text_input(
                TR(f"kubios_screenshot.{name}"),
                value=str(field.get("value", "")),
                key=f"kubios_field_{audit_id}_{name}",
            )
            if field:
                consistency = "candidate_consistent" if field.get("candidates_consistent") else "candidate_inconsistent"
                st.caption(TR("kubios_screenshot.field_confidence", value=f"{field['confidence']:.0%}") + " · " + TR(f"kubios_screenshot.{consistency}"))

        confirmed = st.checkbox(TR("kubios_screenshot.confirm_checkbox"), value=False, key=f"kubios_confirm_{audit_id}")
        if st.button(TR("kubios_screenshot.confirm_import"), key=f"kubios_import_{audit_id}"):
            if not confirmed:
                st.error(TR("kubios_screenshot.confirmation_required"))
                return
            with connect(migrate=False) as connection:
                imported = import_reviewed_result(
                    connection, audit_id, values, user_confirmed=True,
                    # Confirming the reviewed screenshot is the one save
                    # action: persist it and immediately refresh Recovery.
                    run_analysis=True,
                    downstream_runner=run_downstream,
            )
            if imported.success:
                downstream_ok = imported.status != "imported" or imported.downstream.get("success")
                message = TR(
                    "kubios_screenshot.downstream_success"
                    if downstream_ok else "kubios_screenshot.downstream_failed"
                )
                if embedded:
                    # Keep the already-selected upload from reopening the
                    # review after the Recovery page refreshes.
                    result.clear()
                    result["status"] = "saved"
                    st.session_state["recovery_edit_expanded_after_save"] = False
                    st.session_state["recovery_collapse_editor_nonce"] = (
                        st.session_state.get("recovery_collapse_editor_nonce", 0) + 1
                    )
                    st.session_state["recovery_save_notice"] = (
                        f"{TR('kubios_screenshot.import_success')} · {message}"
                    )
                    st.rerun()
                else:
                    st.success(TR("kubios_screenshot.import_success"))
                    (st.success if downstream_ok else st.warning)(message)
            else:
                st.error(TR("kubios_screenshot.validation_failed"))


def _show_result(result, adapter, *, embedded=False):
    status = result.get("status")
    if status == "duplicate":
        st.warning(TR("kubios_screenshot.duplicate")); return
    if status == "template_selection_required":
        _show_image(result, None); _select_template(result, adapter); return
    if status == "quality_rejected":
        st.error(TR("kubios_screenshot.quality_rejected"))
        quality = result.get("quality")
        if quality:
            st.warning(TR("kubios_screenshot.quality_warnings", warnings=", ".join(TR(f"kubios_screenshot.{code}") for code in quality.warnings)))
        _show_image(result, None); _manual_fallback(result); return
    if status in {"parsing_failed", "unsupported"}:
        st.error(TR(f"kubios_screenshot.{status}")); _manual_fallback(result); return
    if result.get("review"):
        _show_review(result, embedded=embedded)


def _show_recent_and_delete():
    st.subheader(TR("kubios_screenshot.recent"))
    with connect(migrate=False) as connection:
        rows = list_recent(connection)
    if not rows:
        st.info(TR("kubios_screenshot.no_imports")); return
    centered_dataframe([{"id": row["id"], TR("kubios_screenshot.status"): row["import_status"], TR("kubios_screenshot.ocr_confidence"): row["overall_ocr_confidence"], TR("kubios_screenshot.reviewed"): bool(row["reviewed"]), TR("kubios_screenshot.downstream"): bool(row["downstream_updated"]), TR("kubios_screenshot.group_id"): row.get("measurement_group_id")} for row in rows])
    with st.expander(TR("kubios_screenshot.group_title")):
        st.info(TR("kubios_screenshot.group_notice"))
        selected_rows = st.multiselect(
            TR("kubios_screenshot.group_select"), [row["id"] for row in rows],
            max_selections=2, key="kubios_group_ids",
        )
        by_id = {row["id"]: row for row in rows}
        detected_dates = {
            by_id[value].get("detected_date") for value in selected_rows
            if by_id[value].get("detected_date")
        }
        default_date = next(iter(detected_dates)) if len(detected_dates) == 1 else ""
        group_date = st.text_input(
            TR("kubios_screenshot.group_date"), value=default_date,
            placeholder="YYYY-MM-DD", key="kubios_group_date",
        )
        group_confirmed = st.checkbox(
            TR("kubios_screenshot.group_confirm"), key="kubios_group_confirm",
        )
        if st.button(
            TR("kubios_screenshot.group_button"),
            disabled=len(selected_rows) != 2 or not group_date or not group_confirmed,
        ):
            measurement_times = [
                by_id[value].get("detected_measurement_time") for value in selected_rows
                if by_id[value].get("detected_measurement_time")
            ]
            try:
                with connect(migrate=False) as connection:
                    create_measurement_group(
                        connection, selected_rows, group_date,
                        measurement_times=measurement_times, confirmed_by_user=True,
                    )
            except (TypeError, ValueError) as exc:
                code = str(exc)
                key = f"kubios_screenshot.{code}"
                st.error(TR(key) if TR(key) != key else TR("errors.invalid_value"))
            else:
                st.success(TR("kubios_screenshot.group_success"))
                st.rerun()
    with st.expander(TR("kubios_screenshot.delete_title")):
        selected = st.selectbox(TR("kubios_screenshot.delete_id"), [row["id"] for row in rows])
        delete_files = st.checkbox(TR("kubios_screenshot.delete_files"), key="kubios_delete_files")
        delete_formal = st.checkbox(TR("kubios_screenshot.delete_formal"), key="kubios_delete_formal")
        confirmed = st.checkbox(TR("kubios_screenshot.delete_confirm"), key="kubios_delete_confirm")
        if st.button(TR("kubios_screenshot.delete_button"), disabled=not confirmed):
            with connect(migrate=False) as connection:
                outcome = delete_import(connection, selected, delete_files, delete_formal)
            if outcome.get("deleted"):
                st.success(TR("kubios_screenshot.delete_success"))
                if outcome.get("formal_record_preserved"): st.info(TR("kubios_screenshot.delete_preserved"))


def render_kubios_screenshot_import(language, translator, *, embedded=False):
    """Render the local screenshot workflow, standalone or inside Recovery."""
    global LANGUAGE, TR
    LANGUAGE, TR = language, translator
    (st.subheader if embedded else st.title)(TR("kubios_screenshot.title"))
    adapter = PreferredVisionOCRAdapter()
    if not adapter.readiness()["ready"]: st.error(TR("kubios_screenshot.ocr_unavailable"))
    # Streamlit versions differ in how faithfully they apply
    # ``label_visibility`` to file uploaders. Keep the drop zone clean in all
    # supported builds rather than leaving a duplicate "Upload screenshot"
    # line above it.
    st.html("<style>div[data-testid='stFileUploader'] > label { display: none !important; }</style>")
    uploads = st.file_uploader(
        "\u200b",
        type=("png", "jpg", "jpeg", "heic", "webp"),
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    cache = st.session_state.setdefault("kubios_upload_results", {})
    new_uploads = [(upload.name, upload.getvalue()) for upload in uploads or [] if hashlib.sha256(upload.getvalue()).hexdigest() not in cache]
    if new_uploads and adapter.readiness()["ready"]:
        with connect(migrate=False) as connection:
            results = process_batch(connection, new_uploads, adapter=adapter)
        for (_, data), result in zip(new_uploads, results): cache[hashlib.sha256(data).hexdigest()] = result
    visible = [cache[digest] for upload in uploads or [] if (digest := hashlib.sha256(upload.getvalue()).hexdigest()) in cache]
    if visible:
        summary = batch_summary(visible)
        manual = summary["needs_manual_input"] + summary["template_selection_required"] + summary["quality_rejected"]
        st.info(TR("kubios_screenshot.batch_summary", recognized=summary["recognized"], manual=manual, duplicate=summary["duplicate"], failed=summary["parsing_failed"]))
        for result in visible:
            _show_result(result, adapter, embedded=embedded)


def main():
    global LANGUAGE, TR
    configure_demo_runtime(st)
    page_language = current_language(st.session_state)
    st.set_page_config(
        page_title=browser_page_title(get_translator(page_language)("kubios_screenshot.title")),
        page_icon=load_page_icon(), layout="wide",
    )
    LANGUAGE, TR = render_sidebar(st, "kubios_screenshot")
    render_manual_input_styles(st)
    render_kubios_screenshot_import(LANGUAGE, TR)


if __name__ == "__main__": main()
