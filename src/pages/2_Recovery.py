"""Top-level Recovery section with centered display and explicit editing."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

import math
from datetime import date
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_latest_local_coach
from src.db import connect
from src.demo_sandbox import configure_demo_runtime, is_demo_mode
from src.domain_dashboard_data import (
    get_latest_recovery,
    get_recovery_baselines,
    get_recovery_history,
)
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.kubios_morning_input import MEASUREMENT_QUALITIES, upsert_manual_morning_measurement
from src.manual_logging import create_recovery_log, update_recovery_log
from src.post_save_sync import start_recovery_post_save_sync
from src.recovery_details import build_recovery_details
from src.ui_scroll import render_interaction_focus
from src.ui_tables import centered_dataframe
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.recovery.title")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, TR = render_sidebar(st, "recovery")
render_manual_input_styles(st)


def _value(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _clean(value):
    if value is None or (isinstance(value, float) and math.isnan(value)): return None
    return value.strip() or None if isinstance(value, str) else float(value)


def _ui(zh, en):
    return zh if LANGUAGE != "en" else en


def _baseline(label, item, suffix):
    if not item or item.get("status") == "insufficient_data":
        st.metric(TR(label), TR("baseline.insufficient_data")); return
    delta = item.get("percent_change")
    st.metric(TR(label), _value(item.get("latest_value"), suffix), None if delta is None else f"{delta:+.1f}%")
    st.caption(TR("domain.common.baseline_median", value=_value(item.get("median_value"), suffix)))


RECOVERY_CORE_CARD_CSS = """
<style>
.drc-core-card {
    border: 1px solid #d9dee7;
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    min-height: 22rem;
    background: linear-gradient(145deg, #ffffff, #f7f9fc);
    box-shadow: 0 4px 14px rgba(36, 52, 71, .06);
}
.drc-core-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin-bottom: .7rem;
}
.drc-core-card-title { font-size: 1.25rem; font-weight: 700; color: #273142; }
.drc-core-status {
    border-radius: 999px;
    padding: .25rem .65rem;
    background: #eef2f7;
    color: #5b6575;
    font-size: .85rem;
    font-weight: 600;
    white-space: nowrap;
}
.drc-core-status.good { background: #e7f6ed; color: #1d7a46; }
.drc-core-status.attention { background: #fff0ee; color: #bd443b; }
.drc-core-value { font-size: 2.25rem; font-weight: 750; color: #222b3a; line-height: 1.1; }
.drc-core-unit { color: #697386; margin: .2rem 0 1rem; }
.drc-core-detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem .9rem; }
.drc-core-detail { border-top: 1px solid #e3e7ee; padding-top: .55rem; }
.drc-core-detail-label { color: #788294; font-size: .82rem; }
.drc-core-detail-value { color: #2f3848; font-size: 1rem; font-weight: 650; margin-top: .15rem; }
.drc-core-foot { color: #788294; font-size: .82rem; margin-top: 1rem; }
.drc-detail-overview, .drc-detail-confidence {
    border: 1px solid #d9dee7; border-radius: 16px; padding: 1rem 1.15rem;
    background: linear-gradient(145deg, #ffffff, #f7f9fc);
    box-shadow: 0 4px 14px rgba(36, 52, 71, .06); margin-bottom: 1rem;
}
.drc-detail-overview-head { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
.drc-detail-overview-title { color: #273142; font-size: 1.15rem; font-weight: 700; }
.drc-detail-overview-status { color: #273142; font-size: 1.5rem; font-weight: 750; margin: .4rem 0; }
.drc-detail-overview-summary { color: #5f6b7c; line-height: 1.55; }
.drc-detail-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-top: .9rem; }
.drc-detail-meta-item { border-top: 1px solid #e3e7ee; padding-top: .55rem; }
.drc-detail-meta-label { color: #788294; font-size: .82rem; }
.drc-detail-meta-value { color: #2f3848; font-size: 1rem; font-weight: 650; margin-top: .15rem; }
.drc-detail-card { min-height: 25rem; }
.drc-detail-card .drc-core-value { margin-top: .35rem; }
.drc-detail-confidence-title { color: #273142; font-weight: 700; }
.drc-detail-confidence-copy { color: #5f6b7c; margin-top: .3rem; line-height: 1.5; }
@media (max-width: 720px) {
    .drc-core-detail-grid { grid-template-columns: 1fr; }
    .drc-detail-meta { grid-template-columns: 1fr; }
}
</style>
"""


def _core_normal_range(item):
    """Return a robust personal normal range from existing baseline fields."""
    center = item.get("median_value") if item else None
    if center is None:
        return None
    mad = item.get("mad_value")
    if mad is not None and float(mad) > 0:
        spread = 1.4826 * float(mad)
        return max(0.0, float(center) - spread), float(center) + spread
    std = item.get("std_value")
    if std is not None and float(std) > 0:
        spread = float(std)
        return max(0.0, float(center) - spread), float(center) + spread
    minimum, maximum = item.get("min_value"), item.get("max_value")
    if minimum is not None and maximum is not None:
        return float(minimum), float(maximum)
    return float(center), float(center)


def _core_metric_card(title, current, unit, baseline, higher_is_better):
    """Render one RMSSD/resting-HR card without inventing missing values."""
    baseline = baseline or {}
    center = baseline.get("median_value")
    delta = None if current is None or center is None else float(current) - float(center)
    percent = baseline.get("percent_change")
    if percent is None and delta is not None and float(center) != 0:
        percent = delta / abs(float(center)) * 100
    baseline_status = baseline.get("status")
    has_baseline_stats = center is not None
    baseline_ready = baseline_status != "insufficient_data" and has_baseline_stats
    arrow = "↑" if delta is not None and delta > 0 else "↓" if delta is not None and delta < 0 else "→"
    if not baseline_ready:
        status_key, status_class = "status_no_data", ""
    else:
        if baseline_status == "within_baseline":
            status_key, status_class = "status_near", ""
        elif (higher_is_better and baseline_status == "above_baseline") or (
            not higher_is_better and baseline_status == "below_baseline"
        ):
            status_key, status_class = "status_good", "good"
        else:
            status_key, status_class = "status_attention", "attention"

    normal_range = _core_normal_range(baseline) if has_baseline_stats else None
    valid_days = int(baseline.get("valid_days") or 0)
    window_days = int(baseline.get("window_days") or 28)
    maturity_percent = min(100, round(valid_days / window_days * 100)) if window_days else 0

    def number(value, signed=False):
        if value is None:
            return TR("common.no_data")
        text = format_number(value, LANGUAGE)
        if signed and float(value) > 0:
            text = "+" + text
        return f"{text} {unit}"

    def plain_number(value):
        return TR("common.no_data") if value is None else format_number(value, LANGUAGE)

    current_number = plain_number(current)
    center_text = number(center) if has_baseline_stats else TR("common.no_data")
    range_text = (
        f"{format_number(normal_range[0], LANGUAGE)}–{format_number(normal_range[1], LANGUAGE)} {unit}"
        if normal_range else TR("common.no_data")
    )
    delta_text = number(delta, signed=True) if has_baseline_stats else TR("common.no_data")
    percent_text = (
        f"{'+' if float(percent) > 0 else ''}{format_number(percent, LANGUAGE)}%"
        if has_baseline_stats and percent is not None else TR("common.no_data")
    )
    status_text = (
        TR("baseline.insufficient_data")
        if baseline_status == "insufficient_data"
        else TR(f"domain.recovery.{status_key}")
    )
    maturity_text = TR(
        "domain.recovery.maturity_days",
        valid=valid_days, window=window_days, percent=maturity_percent,
    )

    details = [
        ("baseline_center", center_text),
        ("normal_range", range_text),
        ("absolute_delta", delta_text),
        ("percent_delta", percent_text),
        ("direction", arrow),
        ("status", status_text),
        ("maturity", maturity_text),
    ]
    detail_html = "".join(
        f'<div class="drc-core-detail"><div class="drc-core-detail-label">'
        f'{escape(TR(f"domain.recovery.{label}"))}</div><div class="drc-core-detail-value">'
        f'{escape(str(value))}</div></div>'
        for label, value in details
    )
    card_html = (
        f'<div class="drc-core-card"><div class="drc-core-card-head">'
        f'<div class="drc-core-card-title">{escape(str(title))}</div>'
        f'<div class="drc-core-status {status_class}">{escape(arrow)} {escape(status_text)}</div></div>'
        f'<div class="drc-core-value">{escape(current_number)}</div>'
        f'<div class="drc-core-unit">{escape(unit)}</div>'
        f'<div class="drc-core-detail-grid">{detail_html}</div>'
        f'<div class="drc-core-foot">{escape(TR("domain.recovery.range_basis"))}</div></div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _recovery_panel(data):
    st.subheader(TR("domain.recovery.today_data"))
    original = {
        "date": (data or {}).get("date", date.today().isoformat()),
        "morning_rmssd_ms": (data or {}).get("morning_rmssd"),
        "morning_resting_hr_bpm": (data or {}).get("morning_mean_hr"),
        "stress_index": (data or {}).get("stress_index"),
        "respiratory_rate": (data or {}).get("respiratory_rate"),
        "measurement_quality": (data or {}).get("measurement_quality"),
    }
    centered_dataframe([{
        TR("reports.date"): original["date"],
        TR("domain.recovery.morning_rmssd"): original["morning_rmssd_ms"],
        TR("domain.recovery.morning_resting_hr"): original["morning_resting_hr_bpm"],
        TR("domain.recovery.stress_index"): original["stress_index"],
        TR("domain.recovery.respiratory_rate"): original["respiratory_rate"],
        TR("domain.recovery.measurement_quality"): (
            TR("domain.recovery.quality_" + original["measurement_quality"].lower())
            if original["measurement_quality"] in MEASUREMENT_QUALITIES else None
        ),
    }])
    with st.expander(TR("inline_edit.edit_recovery")):
        st.caption(TR("inline_edit.edit_recovery_hint"))
        with st.form("recovery_edit_form"):
            left, right = st.columns(2)
            with left:
                edited_rmssd = st.number_input(
                    TR("domain.recovery.morning_rmssd"), min_value=0.01,
                    value=None if original["morning_rmssd_ms"] is None else float(original["morning_rmssd_ms"]),
                    step=0.1, format="%.2f",
                )
            with right:
                edited_hr = st.number_input(
                    TR("domain.recovery.morning_resting_hr"), min_value=20.0,
                    max_value=300.0,
                    value=None if original["morning_resting_hr_bpm"] is None else float(original["morning_resting_hr_bpm"]),
                    step=0.1, format="%.2f",
                )
            left, right = st.columns(2)
            with left:
                edited_stress = st.number_input(
                    TR("domain.recovery.stress_index"), min_value=0.0,
                    value=None if original["stress_index"] is None else float(original["stress_index"]),
                    step=0.1, format="%.2f",
                )
            with right:
                edited_respiration = st.number_input(
                    TR("domain.recovery.respiratory_rate"), min_value=0.01, max_value=80.0,
                    value=None if original["respiratory_rate"] is None else float(original["respiratory_rate"]),
                    step=0.1, format="%.2f",
                )
            quality_options = [None, *MEASUREMENT_QUALITIES]
            quality_index = quality_options.index(original["measurement_quality"]) if original["measurement_quality"] in quality_options else 0
            edited_quality = st.selectbox(
                TR("domain.recovery.measurement_quality"), quality_options, index=quality_index,
                format_func=lambda value: TR("common.no_data") if value is None else TR("domain.recovery.quality_" + value.lower()),
            )
            submitted = st.form_submit_button(TR("inline_edit.save_changes"), type="primary")

    if submitted:
        edited = {
            "morning_rmssd_ms": edited_rmssd,
            "morning_resting_hr_bpm": edited_hr,
            "stress_index": edited_stress,
            "respiratory_rate": edited_respiration,
            "measurement_quality": edited_quality,
        }
        changes = {name: _clean(edited[name]) for name in edited if _clean(edited[name]) != _clean(original[name])}
        if not changes:
            st.info(TR("inline_edit.no_changes")); return
        connection = connect(migrate=False)
        try:
            if data and data.get("manual_record_id"):
                core_changes = {key: value for key, value in changes.items() if key in ("morning_rmssd_ms", "morning_resting_hr_bpm")}
                if core_changes: update_recovery_log(connection, data["manual_record_id"], core_changes)
            else:
                core_changes = {key: value for key, value in changes.items() if key in ("morning_rmssd_ms", "morning_resting_hr_bpm")}
                if core_changes: create_recovery_log(connection, {"date": original["date"], **core_changes})
            upsert_manual_morning_measurement(connection, original["date"], {
                "rmssd": changes.get("morning_rmssd_ms", original["morning_rmssd_ms"]),
                "mean_hr": changes.get("morning_resting_hr_bpm", original["morning_resting_hr_bpm"]),
                "stress_index": changes.get("stress_index", original["stress_index"]),
                "respiratory_rate": changes.get("respiratory_rate", original["respiratory_rate"]),
                "measurement_quality": changes.get("measurement_quality", original["measurement_quality"]),
            })
            final_rmssd = changes.get("morning_rmssd_ms", original["morning_rmssd_ms"])
            final_hr = changes.get("morning_resting_hr_bpm", original["morning_resting_hr_bpm"])
            if (
                not is_demo_mode()
                and original["date"] == date.today().isoformat()
                and final_rmssd is not None
                and final_hr is not None
            ):
                try:
                    start_recovery_post_save_sync()
                    st.session_state["recovery_save_notice"] = TR("inline_edit.recovery_saved_sync_started")
                except (OSError, RuntimeError):
                    st.session_state["recovery_save_notice"] = TR("inline_edit.recovery_saved_sync_failed")
            else:
                st.session_state["recovery_save_notice"] = TR("manual_logging.saved")
            st.rerun()
        except Exception as exc:
            st.error(TR("manual_logging.submit_failed", message=str(exc)))
        finally: connection.close()


def _detail_number(value, unit="", signed=False):
    if value is None:
        return TR("common.no_data")
    text = format_number(value, LANGUAGE)
    if signed and float(value) > 0:
        text = "+" + text
    return f"{text}{(' ' + unit) if unit else ''}"


def _detail_status_text(code):
    return TR(f"domain.recovery.detail_status_{code}")


def _render_detail_metric(name, item):
    label = TR(f"domain.recovery.{name if name != 'morning_mean_hr' else 'morning_resting_hr'}")
    unit = item.get("unit")
    display_unit = TR("domain.recovery.breaths_per_minute") if unit == "breaths_per_minute" else unit
    status_text = _detail_status_text(item.get("impact", "unavailable"))
    current_text = _detail_number(item.get("current_value"), display_unit)
    center_text = _detail_number(item.get("baseline_center"), display_unit)
    normal_range = item.get("normal_range")
    range_text = (
        f"{format_number(normal_range[0], LANGUAGE)}–{format_number(normal_range[1], LANGUAGE)} {display_unit}"
        if normal_range else TR("common.no_data")
    )
    detail_rows = [
        ("today_value", current_text),
        ("baseline_center", center_text),
        ("normal_range", range_text),
        ("absolute_delta", _detail_number(item.get("absolute_delta"), display_unit)),
        ("percent_delta", _detail_number(item.get("percent_delta"), "%", signed=True)),
        ("status", status_text),
        ("detail_explanation", TR(f"domain.recovery.detail_explanation_{item.get('explanation', 'missing')}")),
    ]
    detail_html = "".join(
        f'<div class="drc-core-detail"><div class="drc-core-detail-label">{escape(TR(f"domain.recovery.{key}"))}</div>'
        f'<div class="drc-core-detail-value">{escape(str(value))}</div></div>'
        for key, value in detail_rows
    )
    card_html = (
        f'<div class="drc-core-card drc-detail-card"><div class="drc-core-card-head">'
        f'<div class="drc-core-card-title">{escape(label)}</div>'
        f'<div class="drc-core-status">{escape(status_text)}</div></div>'
        f'<div class="drc-core-value">{escape(current_text)}</div>'
        f'<div class="drc-core-unit">{escape(TR("domain.recovery.today_detail_value"))}</div>'
        f'<div class="drc-core-detail-grid">{detail_html}</div>'
        f'<div class="drc-core-foot">{escape(TR("domain.recovery.detail_range_basis"))}</div></div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_today_recovery_details(data, history, *, historical=False):
    details = build_recovery_details(data, history, target_date=(data or {}).get("date"))
    status = details["status"]
    quality = details["quality"]
    maturity = details["maturity"]
    confidence = details["confidence"]
    overview_title = TR("domain.recovery.detail_overview") if not historical else _ui(
        "历史恢复总览", "Historical Recovery Overview"
    )
    overview_html = (
        f'<div class="drc-detail-overview"><div class="drc-detail-overview-head">'
        f'<div class="drc-detail-overview-title">{escape(overview_title)}</div>'
        f'<div class="drc-core-status">{escape(TR(f"domain.recovery.detail_status_{status}"))}</div></div>'
        f'<div class="drc-detail-overview-status">{escape(TR(f"domain.recovery.detail_status_{status}"))}</div>'
        f'<div class="drc-detail-overview-summary">{escape(TR(f"domain.recovery.detail_summary_{status}"))}</div>'
        '<div class="drc-detail-meta">'
        f'<div class="drc-detail-meta-item"><div class="drc-detail-meta-label">{escape(TR("domain.recovery.measurement_quality"))}</div>'
        f'<div class="drc-detail-meta-value">{escape(TR(f"domain.recovery.detail_quality_{quality}"))}</div></div>'
        f'<div class="drc-detail-meta-item"><div class="drc-detail-meta-label">{escape(TR("domain.recovery.maturity"))}</div>'
        f'<div class="drc-detail-meta-value">{escape(TR(f"domain.recovery.detail_maturity_{maturity}", valid=details["maturity_days"], window=details["window_days"]))}</div></div>'
        f'<div class="drc-detail-meta-item"><div class="drc-detail-meta-label">{escape(TR("domain.recovery.detail_confidence"))}</div>'
        f'<div class="drc-detail-meta-value">{escape(TR(f"domain.recovery.detail_confidence_{confidence}"))}</div></div>'
        '</div></div>'
    )
    st.markdown(overview_html, unsafe_allow_html=True)

    left, right = st.columns(2)
    with left:
        _render_detail_metric("morning_rmssd", details["analyses"]["morning_rmssd"])
    with right:
        _render_detail_metric("morning_mean_hr", details["analyses"]["morning_mean_hr"])
    left, right = st.columns(2)
    with left:
        _render_detail_metric("stress_index", details["analyses"]["stress_index"])
    with right:
        _render_detail_metric("respiratory_rate", details["analyses"]["respiratory_rate"])

    if not historical:
        advice_box = f'<div class="drc-detail-confidence"><div class="drc-detail-confidence-title">{escape(TR("domain.recovery.detail_advice"))}</div><div class="drc-detail-confidence-copy">{escape(TR(f"domain.recovery.detail_advice_{details["advice"]}"))}</div></div>'
        st.markdown(advice_box, unsafe_allow_html=True)
        confidence_box = f'<div class="drc-detail-confidence"><div class="drc-detail-confidence-title">{escape(TR("domain.recovery.detail_confidence"))}</div><div class="drc-detail-confidence-copy">{escape(TR(f"domain.recovery.detail_confidence_copy_{confidence}"))}</div></div>'
        st.markdown(confidence_box, unsafe_allow_html=True)


def _recovery_quality_label(value):
    if value in MEASUREMENT_QUALITIES:
        return TR("domain.recovery.quality_" + value.lower())
    return TR("common.no_data")


def _recovery_history_row(item):
    return {
        TR("reports.date"): format_date(item["date"], LANGUAGE),
        TR("domain.recovery.morning_rmssd"): item.get("morning_rmssd"),
        TR("domain.recovery.morning_resting_hr"): item.get("morning_mean_hr"),
        TR("domain.recovery.stress_index"): item.get("stress_index"),
        TR("domain.recovery.respiratory_rate"): item.get("respiratory_rate"),
        TR("domain.recovery.measurement_quality"): _recovery_quality_label(item.get("measurement_quality")),
    }


def _historical_recovery_record_table(history):
    """Render selectable raw records; the selected row drives historical details."""
    st.subheader(TR("history.recovery_title"))
    if not history:
        st.info(TR("common.no_data"))
        return None

    dates = [item["date"] for item in history]
    selected_date = st.session_state.get("recovery_history_selected")
    if selected_date not in dates:
        selected_date = dates[0]
        st.session_state["recovery_history_selected"] = selected_date

    rows = [_recovery_history_row(item) for item in history]
    view_label = _ui("查看", "View")
    headers = list(rows[0]) + [_ui("操作", "Action")]
    widths = [1.0, 1.35, 1.55, 1.0, 1.3, 1.0, .7]
    with st.container(height=430, border=True):
        header_columns = st.columns(widths)
        for column, label in zip(header_columns, headers):
            header_html = f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>'
            column.markdown(header_html, unsafe_allow_html=True)
        for item, row in zip(history, rows):
            columns = st.columns(widths, vertical_alignment="center")
            for column, label in zip(columns[:-1], headers[:-1]):
                cell_html = f'<div style="text-align:center;">{escape(str(row[label]))}</div>'
                column.markdown(cell_html, unsafe_allow_html=True)
            if columns[-1].button(
                view_label,
                key=f"recovery_history_view_{item['date']}",
                use_container_width=True,
            ):
                st.session_state["recovery_history_selected"] = item["date"]
                st.session_state["recovery_history_focus_nonce"] = (
                    st.session_state.get("recovery_history_focus_nonce", 0) + 1
                )
                st.rerun()
    return selected_date


def _historical_recovery_situation(history, selected_date, *, auto_expand=False, focus_nonce=0):
    """Show the selected raw recovery record and its date-specific interpretation."""
    selected = next((item for item in history if item["date"] == selected_date), None)
    situation_title = _ui("历史恢复情况", "Historical Recovery Situation")
    data_title = _ui("历史恢复数据", "Historical Recovery Data")
    details_title = _ui("历史恢复详情", "Historical Recovery Details")
    focus_target_id = "recovery-history-situation"
    focus_anchor = f'<div id="{focus_target_id}"></div>'
    st.markdown(focus_anchor, unsafe_allow_html=True)
    st.subheader(situation_title)

    with st.expander(data_title, expanded=auto_expand):
        centered_dataframe([_recovery_history_row(selected)] if selected else [])
    with st.expander(details_title, expanded=auto_expand):
        if selected:
            _render_today_recovery_details(selected, history, historical=True)
        else:
            st.info(TR("common.no_data"))

    if auto_expand:
        render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)


def main():
    intro = TR("domain.recovery.intro")
    intro = intro.replace("确定性恢复建议", "恢复建议").replace("deterministic recovery guidance", "recovery guidance")
    st.title(TR("domain.recovery.title")); st.caption(intro)
    notice = st.session_state.pop("recovery_save_notice", None)
    data = get_latest_recovery(log_date=date.today().isoformat())
    if not data: st.info(TR("domain.recovery.empty"))
    _recovery_panel(data)
    if notice: st.success(notice)
    history = get_recovery_history(limit=60)
    st.subheader(TR("domain.recovery.today_details"))
    st.markdown(RECOVERY_CORE_CARD_CSS, unsafe_allow_html=True)
    _render_today_recovery_details(data, history)

    selected_history_date = _historical_recovery_record_table(history)
    history_focus_nonce = st.session_state.get("recovery_history_focus_nonce", 0)
    last_history_focus_nonce = st.session_state.get("recovery_history_last_scrolled_nonce", 0)
    should_focus_history = history_focus_nonce > last_history_focus_nonce
    _historical_recovery_situation(
        history,
        selected_history_date,
        auto_expand=should_focus_history,
        focus_nonce=history_focus_nonce,
    )
    if should_focus_history:
        st.session_state["recovery_history_last_scrolled_nonce"] = history_focus_nonce

    st.subheader("个人恢复基线" if LANGUAGE != "en" else "Personal Recovery Baseline")
    target_date = (data or {}).get("date", date.today().isoformat())
    baselines = get_recovery_baselines(target_date=target_date)
    st.markdown(RECOVERY_CORE_CARD_CSS, unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        _core_metric_card(
            TR("baseline.morning_rmssd"),
            (data or {}).get("morning_rmssd"),
            "ms",
            baselines.get("morning_rmssd"),
            higher_is_better=True,
        )
    with right:
        _core_metric_card(
            TR("baseline.resting_hr"),
            (data or {}).get("morning_mean_hr"),
            "bpm",
            baselines.get("morning_mean_hr"),
            higher_is_better=False,
        )
    st.subheader("恢复建议" if LANGUAGE != "en" else "Recovery Guidance")
    coach = get_latest_local_coach()
    if not coach: st.info(TR("local_coach.missing"))
    else: st.success(TR(f"local_coach.recovery_advice.{coach['recovery_advice'].get('status', 'insufficient_data')}"))
    st.info(TR("domain.recovery.boundary")); st.caption(TR("safety.medical"))


if __name__ == "__main__": main()
