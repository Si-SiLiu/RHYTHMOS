"""Top-level Recovery section with centered display and explicit editing."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date
from html import escape
from importlib import import_module

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_kubios_advanced_metrics, get_latest_local_coach
from src.db import connect, get_current_db_path
from src.demo_sandbox import configure_demo_runtime
from src.domain_dashboard_data import (
    get_latest_recovery,
    get_recovery_baselines,
    get_recovery_history,
)
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.i18n.traditional import traditionalize
from src.recovery_details import build_recovery_details
from src.recovery_metrics_table import recovery_metrics_table_row
from src.ui_scroll import collapse_expander, render_interaction_focus
from src.ui_tables import centered_dataframe
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.recovery.title")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, TR = render_sidebar(st, "recovery")
render_manual_input_styles(st)

# Historical evidence belongs to the current Recovery-page visit only.
if st.session_state.get("drc_previous_page") != "recovery":
    for key in (
        "recovery_history_details_visible",
        "recovery_history_sections_open",
        "recovery_history_focus_nonce",
        "recovery_history_last_scrolled_nonce",
    ):
        st.session_state.pop(key, None)


def _recovery_database_revision():
    """Invalidate cached page inputs only when the SQLite data actually changes."""
    revision = []
    db_path = get_current_db_path()
    for path in (db_path, db_path.with_name(f"{db_path.name}-wal")):
        try:
            stat = path.stat()
            revision.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            revision.append((str(path), None, None))
    return tuple(revision)


@st.cache_data(show_spinner=False, max_entries=4)
def _load_recovery_page_inputs(database_revision, today_value):
    """Reuse stable Recovery inputs during lightweight Streamlit reruns."""
    del database_revision  # Deliberately part of Streamlit's cache key.
    current = get_latest_recovery(log_date=today_value)
    history = get_recovery_history(limit=60)
    target_date = (current or {}).get("date", today_value)
    kubios_rows = get_kubios_advanced_metrics(limit=1, date_value=target_date)
    return (
        current,
        history,
        get_recovery_baselines(target_date=target_date),
        get_latest_local_coach(coach_date=target_date),
        kubios_rows[0] if kubios_rows else {},
    )


def _value(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _ui(zh, en):
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


def _baseline(label, item, suffix):
    if not item or item.get("status") == "insufficient_data":
        st.metric(TR(label), TR("baseline.insufficient_data")); return
    delta = item.get("percent_change")
    st.metric(TR(label), _value(item.get("latest_value"), suffix), None if delta is None else f"{delta:+.1f}%")
    st.caption(TR("domain.common.baseline_median", value=_value(item.get("median_value"), suffix)))


RECOVERY_CORE_CARD_CSS = """
<style>
/* Keep a broad data workspace anchored to the navigation side on ultrawide displays. */
section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] [data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .main .block-container {
    width: 100% !important;
    max-width: 88rem !important;
    margin-right: auto !important;
    margin-left: 0 !important;
}
.drc-core-card {
    border: 1px solid rgba(117, 130, 148, .18);
    border-radius: 16px;
    padding: 1.1rem 1.2rem;
    min-height: 22rem;
    background: rgba(117, 130, 148, .065);
    box-shadow: none;
}
.drc-core-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin-bottom: .7rem;
}
.drc-core-card-title { font-size: 1.25rem; font-weight: 700; color: inherit; }
.drc-core-status {
    border-radius: 999px;
    padding: .25rem .65rem;
    background: rgba(117, 130, 148, .11);
    color: inherit;
    opacity: .76;
    font-size: .85rem;
    font-weight: 600;
    white-space: nowrap;
}
.drc-core-status.good { background: #e7f6ed; color: #1d7a46; }
.drc-core-status.attention { background: #fff0ee; color: #bd443b; }
.drc-core-value { font-size: 2.25rem; font-weight: 750; color: inherit; line-height: 1.1; }
.drc-core-unit { color: inherit; opacity: .65; margin: .2rem 0 1rem; }
.drc-core-detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem .9rem; }
.drc-core-detail { border-top: 1px solid #e3e7ee; padding-top: .55rem; }
.drc-core-detail-label { color: inherit; opacity: .62; font-size: .82rem; }
.drc-core-detail-value { color: inherit; font-size: 1rem; font-weight: 650; margin-top: .15rem; }
.drc-core-foot { color: inherit; opacity: .62; font-size: .82rem; margin-top: 1rem; }
.drc-details-heading-wrap {
    display: flex !important;
    flex-direction: column;
    align-items: flex-start;
    gap: .15rem;
    margin: .45rem 0 .4rem;
}
.drc-details-heading {
    margin: 0 !important;
    padding: 0 !important;
    color: var(--rh-text);
    font-size: 1.35rem;
    font-weight: 650;
    letter-spacing: -.012em;
    line-height: 1.35;
}
.drc-details-context {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem;
    margin: 0 !important;
    color: var(--rh-text-muted);
    font-size: .75rem !important;
    font-weight: 500;
    line-height: 1.45;
}
.drc-details-context-chip {
    display: inline-flex;
    align-items: baseline;
    gap: .3rem;
    padding: .18rem .5rem;
    border: 1px solid rgba(255, 255, 255, .12);
    border-radius: 999px;
    background: rgba(255, 255, 255, .055);
    white-space: nowrap;
}
.drc-details-context-chip strong { color: var(--rh-text-secondary); font-weight: 600; }
.drc-details-context-basis { padding: .18rem .12rem; color: var(--rh-text-muted); }
.drc-detail-overview {
    border: 0;
    border-radius: 0;
    padding: .35rem 0 0;
    background: transparent;
    box-shadow: none;
    margin-bottom: 1.6rem;
}
.drc-detail-overview-head {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: .625rem;
    padding-bottom: 0;
    border-bottom: 0;
}
.drc-detail-overview-title {
    color: var(--rh-text-secondary);
    font-size: .875rem;
    font-weight: 600;
    line-height: 1.45;
}
.drc-detail-overview .drc-core-status {
    border-radius: var(--rh-radius-small);
    padding: .3125rem .625rem;
    background: var(--rh-surface-inset);
    color: var(--rh-text-secondary);
    font-size: .8125rem;
    font-weight: 600;
    line-height: 1.3;
}
.drc-detail-overview--good .drc-core-status {
    background: var(--rh-status-positive-surface);
    color: var(--rh-status-positive);
}
.drc-detail-overview--low .drc-core-status,
.drc-detail-overview--conflict .drc-core-status {
    background: var(--rh-status-caution-surface);
    color: var(--rh-status-caution);
}
.drc-detail-overview--unusable .drc-core-status {
    background: var(--rh-status-negative-surface);
    color: var(--rh-status-negative);
}
.drc-detail-overview-status {
    color: var(--rh-text);
    font-size: 1.8125rem;
    font-weight: 650;
    letter-spacing: -.012em;
    line-height: 1.25;
    margin: .75rem 0 .4rem;
}
.drc-detail-overview-summary {
    color: var(--rh-text-secondary);
    font-size: .9rem;
    line-height: 1.6;
    max-width: 68ch;
}
.drc-detail-meta {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0;
    margin-top: 1.45rem;
}
.drc-detail-meta-item {
    min-width: 0;
    padding: 0 1rem;
    border-left: 1px solid var(--rh-border-subtle);
}
.drc-detail-meta-item:first-child {
    padding-left: 0;
    border-left: 0;
}
.drc-detail-meta-item:last-child { padding-right: 0; }
.drc-detail-meta-label {
    color: var(--rh-text-muted);
    font-size: .8125rem;
    font-weight: 500;
    line-height: 1.4;
}
.drc-detail-meta-value {
    color: var(--rh-text);
    font-size: .9375rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1.45;
    margin-top: .2rem;
}
.drc-detail-confidence {
    border: 1px solid rgba(117, 130, 148, .18); border-radius: 16px; padding: 1rem 1.15rem;
    background: rgba(117, 130, 148, .065);
    box-shadow: none; margin-bottom: 1rem;
}
.drc-detail-card {
    position: relative;
    overflow: hidden;
    min-height: 0;
    padding: 1.1rem 1.15rem;
    border: 1px solid rgba(255, 255, 255, .12);
    border-radius: 20px;
    background: rgba(255, 255, 255, .035);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .10), 0 16px 32px rgba(0, 0, 0, .18);
    backdrop-filter: blur(20px) saturate(115%);
    margin-bottom: .625rem;
}
@supports (background: color-mix(in srgb, white 50%, black)) {
    .drc-details-context-chip {
        border-color: var(--rh-border-subtle);
        background: var(--rh-surface-inset);
    }
    .drc-detail-card {
        background: linear-gradient(
            145deg,
            color-mix(in srgb, var(--secondary-background-color) 94%, var(--text-color) 6%),
            var(--secondary-background-color)
        );
        box-shadow:
            inset 0 1px 0 color-mix(in srgb, var(--text-color) 10%, transparent),
            var(--rh-shadow-raised);
    }
    .drc-detail-card .drc-core-card-head { border-bottom-color: var(--rh-border-subtle); }
    .drc-detail-card .drc-core-status {
        background: var(--rh-surface-inset);
        border-color: var(--rh-border-subtle);
    }
    .drc-detail-card .drc-core-detail-grid,
    .drc-detail-card .drc-core-detail:nth-child(even),
    .drc-detail-card .drc-core-detail:nth-child(n + 3) {
        border-color: var(--rh-border-subtle);
    }
}
@media (hover: hover) and (prefers-reduced-motion: no-preference) {
    .drc-detail-card { transition: transform 180ms ease-out, box-shadow 180ms ease-out, border-color 180ms ease-out; }
    .drc-detail-card:hover { transform: translateY(-1px); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .18), 0 20px 36px rgba(0, 0, 0, .14); }
}
.drc-detail-card .drc-core-card-head {
    align-items: flex-start;
    justify-content: flex-start;
    flex-wrap: wrap;
    gap: .625rem;
    margin: 0;
    padding-bottom: .55rem;
    border-bottom: 1px solid rgba(255, 255, 255, .09);
}
.drc-detail-card .drc-core-card-title {
    min-width: 0;
    color: var(--rh-text);
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.4;
}
.drc-detail-card .drc-core-status {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    flex: 0 1 auto;
    max-width: 100%;
    padding: .3125rem .625rem;
    border-radius: var(--rh-radius-small);
    background: rgba(255, 255, 255, .06);
    border: 1px solid rgba(255, 255, 255, .10);
    color: var(--rh-text-secondary);
    font-size: .8125rem;
    font-weight: 600;
    line-height: 1.3;
    text-align: left;
    white-space: normal;
}
.drc-detail-card .drc-core-status::before {
    content: "";
    flex: 0 0 auto;
    width: .375rem;
    height: .375rem;
    border-radius: 50%;
    background: currentColor;
    opacity: .72;
}
.drc-detail-card--supportive .drc-core-status {
    background: var(--rh-status-positive-surface);
    color: var(--rh-status-positive);
}
.drc-detail-card--negative .drc-core-status,
.drc-detail-card--observe .drc-core-status {
    background: var(--rh-status-caution-surface);
    color: var(--rh-status-caution);
}
.drc-detail-card .drc-core-value {
    display: inline-flex;
    align-items: baseline;
    gap: .35rem;
    margin-top: .8rem;
    color: var(--rh-text);
    font-size: 1.6875rem;
    font-weight: 650;
    font-variant-numeric: tabular-nums;
    letter-spacing: -.012em;
    line-height: 1.25;
    white-space: nowrap;
}
.drc-detail-current-unit {
    color: var(--rh-text-secondary);
    font-size: .9375rem;
    font-weight: 500;
    letter-spacing: 0;
}
.drc-detail-card .drc-core-unit {
    margin: .25rem 0 .75rem;
    color: var(--rh-text-muted);
    font-size: .8125rem;
    line-height: 1.4;
}
.drc-detail-card .drc-core-detail-grid {
    gap: 0;
    margin-top: 0;
    border-top: 1px solid rgba(255, 255, 255, .09);
}
.drc-detail-card .drc-core-detail {
    min-width: 0;
    padding: .65rem .9rem .65rem 0;
    border-top: 0;
}
.drc-detail-card .drc-core-detail:nth-child(even) {
    padding-right: 0;
    padding-left: .9rem;
    border-left: 1px solid rgba(255, 255, 255, .09);
}
.drc-detail-card .drc-core-detail:nth-child(n + 3) {
    border-top: 1px solid rgba(255, 255, 255, .09);
}
.drc-detail-card .drc-core-detail:nth-child(5) {
    grid-column: 1 / -1;
    padding-right: 0;
}
.drc-detail-card .drc-core-detail-label {
    color: var(--rh-text-muted);
    font-size: .8125rem;
    font-weight: 500;
    line-height: 1.4;
}
.drc-detail-card .drc-core-detail-value {
    color: var(--rh-text);
    font-size: .9375rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1.5;
    margin-top: .2rem;
    overflow-wrap: anywhere;
}
.drc-detail-card .drc-core-detail:nth-child(5) {
    padding-top: .75rem;
    padding-bottom: .75rem;
    margin: .1rem -.25rem 0;
    padding-left: .25rem;
    border-radius: 12px;
    background: color-mix(in srgb, var(--rh-surface-inset) 78%, transparent);
}
.drc-detail-card .drc-core-detail:nth-child(5) .drc-core-detail-label {
    color: var(--rh-text-secondary);
    font-size: .875rem;
    font-weight: 600;
}
.drc-detail-card .drc-core-detail:nth-child(5) .drc-core-detail-value {
    color: var(--rh-text-secondary);
    font-size: .9375rem;
    font-weight: 400;
    line-height: 1.6;
    margin-top: .35rem;
}
.drc-detail-card .drc-core-foot {
    margin-top: .75rem;
    color: var(--rh-text-muted);
    font-size: .8125rem;
    line-height: 1.55;
}
.drc-detail-confidence-title { color: inherit; font-weight: 700; }
.drc-detail-confidence-copy { color: inherit; opacity: .72; margin-top: .3rem; line-height: 1.5; }
@media (max-width: 720px) {
    .drc-core-detail-grid { grid-template-columns: 1fr; }
    .drc-detail-card { padding: 1.15rem; }
    .drc-detail-card .drc-core-detail,
    .drc-detail-card .drc-core-detail:nth-child(even) {
        padding: .8rem 0;
        border-left: 0;
    }
    .drc-detail-card .drc-core-detail:nth-child(2) { border-top: 1px solid var(--rh-border-subtle); }
    .drc-detail-card .drc-core-detail:nth-child(5) {
        grid-column: auto;
        padding-top: .7rem;
        padding-bottom: .7rem;
    }
    .drc-detail-overview { padding: .15rem 0 0; }
    .drc-detail-overview-status { font-size: 1.625rem; }
    .drc-detail-meta { grid-template-columns: 1fr; margin-top: 1rem; }
    .drc-detail-meta-item {
        padding: .7rem 0 0;
        margin-top: .7rem;
        border-top: 1px solid var(--rh-border-subtle);
        border-left: 0;
    }
    .drc-detail-meta-item:first-child { margin-top: 0; }
}
</style>
"""


def _recovery_metrics_table_row(date_value, values):
    return recovery_metrics_table_row(
        date_value, values, tr=TR, language=LANGUAGE,
        format_date=format_date, ui=_ui,
    )


def _merge_recovery_evidence(data, kubios_measurement):
    """Use the selected Kubios record as the single source for today's cards."""
    resolved = dict(data or {})
    resolved.setdefault("date", date.today().isoformat())
    kubios_measurement = kubios_measurement or {}
    field_map = {
        "rmssd_ms": "morning_rmssd",
        "mean_hr_bpm": "morning_mean_hr",
        "stress_index": "stress_index",
        "respiratory_rate_bpm": "respiratory_rate",
        "measurement_quality": "measurement_quality",
        "pns_index": "pns_index",
        "sns_index": "sns_index",
        "physiological_age": "physiological_age",
        "mean_rr_ms": "mean_rr_ms",
        "sdnn_ms": "sdnn_ms",
        "poincare_sd1_ms": "poincare_sd1_ms",
        "poincare_sd2_ms": "poincare_sd2_ms",
        "lf_power_ms2": "lf_power_ms2",
        "hf_power_ms2": "hf_power_ms2",
        "lf_power_nu": "lf_power_nu",
        "hf_power_nu": "hf_power_nu",
        "lf_hf_ratio": "lf_hf_ratio",
        "mood_code": "mood_code",
    }
    for source, destination in field_map.items():
        value = kubios_measurement.get(source)
        if value not in (None, ""):
            resolved[destination] = value
    return resolved


def _recovery_panel(data):
    st.subheader(TR("domain.recovery.today_data"))
    today_row = _recovery_metrics_table_row(data.get("date", date.today().isoformat()), data)
    today_row[TR("kubios_screenshot.mood_code")] = data.get("mood_code") or TR("common.no_data")
    centered_dataframe([today_row], max_height="12rem")
    # A confirmed screenshot save returns to the compact recovery summary.
    # It remains closed by default; the one-shot flag is retained so a save
    # cannot reopen it during the refresh that follows.
    expanded = st.session_state.pop("recovery_edit_expanded_after_save", False)
    with st.expander(TR("inline_edit.edit_recovery"), expanded=expanded):
        screenshot_page = import_module("src.pages.2_Kubios_Screenshot_Import")
        screenshot_page.render_kubios_screenshot_import(LANGUAGE, TR, embedded=True)


def _detail_number(value, unit="", signed=False):
    if value is None:
        return TR("common.no_data")
    text = format_number(value, LANGUAGE)
    if signed and float(value) > 0:
        text = "+" + text
    separator = "" if unit == "%" else " "
    return f"{text}{(separator + unit) if unit else ''}"


def _detail_status_text(code):
    return TR(f"domain.recovery.detail_status_{code}")


def _render_detail_metric(name, item):
    label = TR(item["label_key"])
    unit = item.get("unit")
    display_unit = (
        TR("domain.recovery.breaths_per_minute") if unit == "breaths_per_minute"
        else _ui("岁", "years") if unit == "years"
        else unit
    )
    impact = item.get("impact", "unavailable")
    status_text = _detail_status_text(impact)
    current_value = item.get("current_value")
    current_text = _detail_number(current_value, display_unit)
    current_markup = escape(current_text) if current_value is None or not display_unit else (
        f'{escape(_detail_number(current_value))}'
        f'<span class="drc-detail-current-unit">{escape(str(display_unit))}</span>'
    )
    center_text = _detail_number(item.get("baseline_center"), display_unit)
    normal_range = item.get("normal_range")
    range_text = (
        f"{format_number(normal_range[0], LANGUAGE)}–{format_number(normal_range[1], LANGUAGE)} {display_unit}"
        if normal_range else TR("common.no_data")
    )
    # The headline already presents today's value, while the per-metric status
    # is shown beside the title. Keep this grid for distinct baseline evidence
    # and its interpretation instead of repeating those two facts.
    detail_rows = [
        ("baseline_center", center_text),
        ("normal_range", range_text),
        ("absolute_delta", _detail_number(item.get("absolute_delta"), display_unit)),
        ("percent_delta", _detail_number(item.get("percent_delta"), "%", signed=True)),
        ("detail_explanation", TR(f"domain.recovery.detail_explanation_{item.get('explanation', 'missing')}")),
    ]
    detail_html = "".join(
        f'<div class="drc-core-detail"><div class="drc-core-detail-label">{escape(TR(f"domain.recovery.{key}"))}</div>'
        f'<div class="drc-core-detail-value">{escape(str(value))}</div></div>'
        for key, value in detail_rows
    )
    card_html = (
        f'<div class="drc-core-card drc-detail-card drc-detail-card--{escape(impact)}"><div class="drc-core-card-head">'
        f'<div class="drc-core-card-title">{escape(label)}</div>'
        f'<div class="drc-core-status">{escape(status_text)}</div></div>'
        f'<div class="drc-core-value">{current_markup}</div>'
        f'<div class="drc-core-unit">{escape(TR("domain.recovery.today_detail_value"))}</div>'
        f'<div class="drc-core-detail-grid">{detail_html}</div>'
        f'<div class="drc-core-foot">{escape(TR("domain.recovery.detail_range_basis"))}</div></div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_today_recovery_details(data, history, *, historical=False):
    details = build_recovery_details(data, history, target_date=(data or {}).get("date"))
    metric_names = (
        "morning_rmssd", "morning_mean_hr", "pns_index", "sns_index",
        "physiological_age", "mean_rr_ms", "sdnn_ms", "poincare_sd1_ms",
        "poincare_sd2_ms", "stress_index", "respiratory_rate", "lf_power_ms2",
        "hf_power_ms2", "lf_power_nu", "hf_power_nu", "lf_hf_ratio",
    )
    # Historical drill-down remains compact; today's view carries every
    # confirmed measurement from the former wide table as an equal card.
    if historical:
        metric_names = ("morning_rmssd", "morning_mean_hr", "stress_index", "respiratory_rate")
    for index in range(0, len(metric_names), 2):
        left, right = st.columns(2)
        with left:
            name = metric_names[index]
            _render_detail_metric(name, details["analyses"][name])
        if index + 1 < len(metric_names):
            with right:
                name = metric_names[index + 1]
                _render_detail_metric(name, details["analyses"][name])


def _baseline_context(baselines):
    """Return compact maturity facts for the merged baseline context."""
    labels = (
        ("morning_rmssd", "domain.recovery.morning_rmssd"),
        ("morning_mean_hr", "domain.recovery.morning_resting_hr"),
    )
    segments = []
    for metric_name, label_key in labels:
        baseline = (baselines or {}).get(metric_name) or {}
        valid_days = int(baseline.get("valid_days") or 0)
        window_days = int(baseline.get("window_days") or 28)
        percent = min(100, round(valid_days / window_days * 100)) if window_days else 0
        maturity = TR(
            "domain.recovery.maturity_days",
            valid=valid_days,
            window=window_days,
            percent=percent,
        )
        segments.append((TR(label_key), maturity))
    return segments


def _missing_recovery_evidence(current):
    """Translate the confidence engine's exact missing groups for the coach banner."""
    labels = {
        "activity_load": "local_coach.recovery_advice.missing_activity_load",
        "training_load": "local_coach.recovery_advice.missing_training_load",
        "sleep": "local_coach.recovery_advice.missing_sleep",
        "hrv": "local_coach.recovery_advice.missing_hrv",
        "resting_heart_rate": "local_coach.recovery_advice.missing_resting_heart_rate",
        "readiness_support": "local_coach.recovery_advice.missing_readiness_support",
    }
    current = current or {}
    resolved = {
        "hrv": any(current.get(key) not in (None, "") for key in ("nightly_hrv_rmssd", "morning_rmssd")),
        "resting_heart_rate": any(current.get(key) not in (None, "") for key in ("nightly_resting_hr", "morning_mean_hr")),
        "readiness_support": any(current.get(key) not in (None, "") for key in ("respiratory_rate", "kubios_readiness")),
    }
    return [
        TR(labels[group])
        for group in current.get("missing_groups", [])
        if group in labels and not resolved.get(group, False)
    ]


def _render_recovery_guidance(coach, current=None):
    """Show a safe, concrete plan instead of a status-only coach message."""
    if not coach:
        st.info(TR("local_coach.missing"))
        return

    advice = coach.get("recovery_advice") or {}
    status = advice.get("status", "insufficient_data")
    if status != "insufficient_data":
        st.success(TR(f"local_coach.recovery_advice.{status}"))
        monitoring = advice.get("monitoring")
        if monitoring:
            st.caption(monitoring)
        return

    missing = _missing_recovery_evidence(current)
    st.warning(TR(
        "local_coach.recovery_advice.insufficient_data_summary",
        missing="、".join(missing) if missing else TR("local_coach.recovery_advice.missing_key_metrics"),
    ))
    actions = (
        ("insufficient_data_training_label", "insufficient_data_training"),
        ("insufficient_data_check_label", "insufficient_data_check"),
        ("insufficient_data_measure_label", "insufficient_data_measure"),
    )
    action_text = "\n".join(
        f"- **{TR(f'local_coach.recovery_advice.{label_key}')}**：{TR(f'local_coach.recovery_advice.{body_key}')}"
        for label_key, body_key in actions
    )
    st.markdown(action_text)


def _recovery_history_row(item):
    return _recovery_metrics_table_row(item["date"], item)


def _historical_recovery_record_table(history):
    """Render the selectable history catalogue directly inside its expander."""
    sections_open = st.session_state.get("recovery_history_sections_open", False)
    if not history:
        with st.expander(TR("history.recovery_browser_title"), expanded=sections_open):
            st.info(TR("common.no_data"))
        return None

    dates = [item["date"] for item in history]
    selected_date = st.session_state.get("recovery_history_selected")
    if selected_date not in dates:
        selected_date = dates[0]
        st.session_state["recovery_history_selected"] = selected_date

    # The expander itself is the only disclosure control. It starts collapsed;
    # selecting a row opens all three history sections for the rerun that
    # follows, without requiring a second "view history" click.
    with st.expander(TR("history.recovery_browser_title"), expanded=sections_open):
        centered_dataframe([_recovery_history_row(item) for item in history], max_height="26rem")
        selected_date = st.selectbox(
            _ui("查看日期", "View date"),
            dates,
            index=dates.index(selected_date),
            format_func=lambda value: format_date(value, LANGUAGE),
            key="recovery_history_date_picker",
        )
        if st.button(_ui("查看", "View"), key="recovery_history_view_button", use_container_width=False):
            st.session_state["recovery_history_selected"] = selected_date
            st.session_state["recovery_history_details_visible"] = True
            st.session_state["recovery_history_sections_open"] = True
            st.session_state["recovery_history_focus_nonce"] = (
                st.session_state.get("recovery_history_focus_nonce", 0) + 1
            )
            st.rerun()
    return selected_date


def _historical_recovery_situation(history, *, auto_expand=False, focus_nonce=0):
    """Show the selected raw recovery record and its date-specific interpretation."""
    data_title = _ui("历史恢复数据", "Historical Recovery Data")
    details_title = _ui("历史恢复详情", "Historical Recovery Details")

    # Historical records are the first child directory of the situation.
    selected_date = _historical_recovery_record_table(history)
    if not st.session_state.get("recovery_history_details_visible", False):
        return

    selected = next((item for item in history if item["date"] == selected_date), None)
    sections_open = st.session_state.get("recovery_history_sections_open", False)
    # Keep each evidence layer in its own expander, but show the content
    # immediately when the section is opened. The old nested action buttons
    # added an unnecessary second click and collapsed after a selection rerun.
    with st.expander(data_title, expanded=sections_open):
        if selected:
            centered_dataframe([_recovery_history_row(selected)])
        else:
            st.info(TR("common.no_data"))

    with st.expander(details_title, expanded=sections_open):
        if selected:
            _render_today_recovery_details(selected, history, historical=True)
        else:
            st.info(TR("common.no_data"))

    if auto_expand:
        render_interaction_focus(
            components,
            target_expander_label=data_title,
            nonce=focus_nonce,
            top_offset=80,
        )


def main():
    intro = TR("domain.recovery.intro")
    st.title(TR("domain.recovery.title")); st.caption(intro)
    notice = st.session_state.pop("recovery_save_notice", None)
    collapse_editor_nonce = st.session_state.pop("recovery_collapse_editor_nonce", None)
    data, history, baselines, coach, kubios_measurement = _load_recovery_page_inputs(
        _recovery_database_revision(), date.today().isoformat()
    )
    has_measurement = bool(data or kubios_measurement)
    data = _merge_recovery_evidence(data, kubios_measurement)
    if notice:
        st.success(notice)
        st.toast(notice, icon="✅")
    if not has_measurement: st.info(TR("domain.recovery.empty"))
    _recovery_panel(data)
    if collapse_editor_nonce is not None:
        collapse_expander(
            components,
            target_expander_label=TR("inline_edit.edit_recovery"),
            nonce=collapse_editor_nonce,
        )
    st.markdown(RECOVERY_CORE_CARD_CSS, unsafe_allow_html=True)
    baseline_context = _baseline_context(baselines)
    baseline_chips = "".join(
        f'<span class="drc-details-context-chip"><strong>{escape(label)}</strong>{escape(value)}</span>'
        for label, value in baseline_context
    )
    baseline_basis = _ui("基于近 28 天个人波动", "Based on 28-day personal variation")
    st.markdown(
        f'<div class="drc-details-heading-wrap"><h3 class="drc-details-heading">'
        f'{escape(TR("domain.recovery.today_details"))}</h3>'
        f'<div class="drc-details-context">{baseline_chips}'
        f'<span class="drc-details-context-basis">{escape(baseline_basis)}</span></div></div>',
        unsafe_allow_html=True,
    )
    _render_today_recovery_details(data, history)

    history_focus_nonce = st.session_state.get("recovery_history_focus_nonce", 0)
    last_history_focus_nonce = st.session_state.get("recovery_history_last_scrolled_nonce", 0)
    should_focus_history = history_focus_nonce > last_history_focus_nonce
    _historical_recovery_situation(
        history,
        auto_expand=should_focus_history,
        focus_nonce=history_focus_nonce,
    )
    if should_focus_history:
        st.session_state["recovery_history_last_scrolled_nonce"] = history_focus_nonce

    st.info(TR("domain.recovery.boundary")); st.caption(TR("safety.medical"))


if __name__ == "__main__": main()
