"""Sleep recovery analysis page with Polar-backed local interpretation."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date, datetime, timedelta
from html import escape
import re
import statistics

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.db import get_current_db_path
from src.demo_sandbox import configure_demo_runtime
from src.domain_dashboard_data import get_domain_baselines, get_latest_sleep, get_sleep_history
from src.exercise_format import hours_to_hms, minutes_to_hms, time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.i18n.traditional import traditionalize
from src.sleep_regularity import SleepRegularityService
from src.sleep_baseline_view import build_sleep_baseline_summary, build_sleep_regularity_points
from src.ui_tables import centered_dataframe
from src.ui_scroll import render_interaction_focus
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.sleep.title")),
    page_icon=load_page_icon(), layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "sleep")
render_manual_input_styles(st)

# A selection is only meant to expand the historical evidence for the current
# visit. Returning from another page should always start with every history
# section collapsed.
if st.session_state.get("drc_previous_page") != "sleep":
    st.session_state.pop("sleep_history_details_focus_nonce", None)
    st.session_state.pop("sleep_history_details_last_scrolled_nonce", None)
    st.session_state.pop("sleep_history_details_visible", None)


def _sleep_database_revision():
    """Invalidate page data only when the SQLite database (or WAL) changes."""
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
def _load_sleep_page_inputs(database_revision, today_value):
    """Reuse parsed history during record selection reruns."""
    del database_revision  # It is intentionally part of Streamlit's cache key.
    return (
        get_latest_sleep(),
        get_latest_sleep(log_date=today_value),
        # Fill historical gaps from the full Polar sleep window. Fields that
        # Polar did not provide remain missing instead of being estimated.
        get_sleep_history(limit=60, include_continuous_hr=True, polar_only=True),
        get_domain_baselines((
            "sleep_duration", "sleep_score", "nightly_hrv_rmssd",
            "nightly_resting_hr", "respiration_rate",
        )),
    )


def _sleep_regularity_artifacts(history, target_date):
    """Build regularity inputs without hashing the full raw sleep history."""
    # Streamlit's cache key serialization was slower than this calculation:
    # every call hashed nested hypnogram and source metadata for all 60 nights.
    return (
        build_sleep_regularity_points(history, target_date),
        SleepRegularityService.calculate_regularity(history).score,
    )


SLEEP_CSS = """
<style>
.drc-sleep-card,.drc-baseline-card{border:1px solid rgba(117,130,148,.18);border-radius:var(--rh-radius-standard);padding:1.25rem 1.35rem;background:rgba(117,130,148,.065);box-shadow:none;color:var(--rh-text)}
.drc-sleep-card{position:relative;overflow:hidden;box-sizing:border-box;min-height:12.75rem;padding:1.1rem 1.15rem;border:1px solid rgba(255,255,255,.12);border-radius:20px;background:rgba(255,255,255,.035);box-shadow:inset 0 1px 0 rgba(255,255,255,.10),0 16px 32px rgba(0,0,0,.18);backdrop-filter:blur(20px) saturate(115%);-webkit-backdrop-filter:blur(20px) saturate(115%)}.drc-sleep-card.primary,.drc-sleep-card.metric{height:auto;min-height:12.75rem}.drc-sleep-card-head{display:flex;align-items:flex-start;justify-content:flex-start;flex-wrap:wrap;gap:.625rem;margin:0;padding-bottom:.55rem;border-bottom:1px solid rgba(255,255,255,.09)}.drc-baseline-card-head{display:flex;align-items:flex-start;padding-bottom:.55rem;border-bottom:1px solid var(--rh-border-subtle)}
.drc-sleep-card h3,.drc-baseline-card h3{margin:0;min-width:0;color:var(--rh-text);font-size:1rem;font-weight:600;letter-spacing:-.006em;line-height:1.4}.drc-sleep-card-value{color:var(--rh-text);font-size:1.6875rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.012em;line-height:1.25;margin:.8rem 0 0;white-space:nowrap}.drc-sleep-card.primary .drc-sleep-card-value{font-size:2.15rem;letter-spacing:-.022em}.drc-sleep-card-meta{border-top:1px solid rgba(255,255,255,.09);color:var(--rh-text-muted);font-size:.8125rem;line-height:1.6;margin-top:.75rem;padding-top:.7rem}.drc-sleep-card-explanation{margin:.15rem -.25rem 0;padding:.7rem .75rem;border-radius:12px;background:color-mix(in srgb,var(--rh-surface-inset) 78%,transparent);color:var(--rh-text-secondary);font-size:.8125rem;line-height:1.55}.drc-sleep-card-explanation-label{color:var(--rh-text-secondary);font-size:.75rem;font-weight:600;line-height:1.35;margin-bottom:.2rem}.drc-sleep-card-problem{border-top:1px solid var(--rh-border-subtle);color:var(--rh-text-secondary);font-size:.875rem;font-weight:550;line-height:1.55;margin-top:.8rem;padding-top:.75rem}
.drc-sleep-card-label{color:var(--rh-text-secondary);font-size:.875rem;font-weight:600}.drc-sleep-card-delta{font-size:.9375rem;font-weight:600;margin-top:.5rem}.drc-sleep-card-status{display:inline-flex;align-items:center;gap:.35rem;flex:0 1 auto;max-width:100%;justify-self:auto;white-space:normal;border:1px solid rgba(255,255,255,.10);border-radius:var(--rh-radius-small);background:rgba(255,255,255,.06);color:var(--rh-text-secondary);font-size:.8125rem;font-weight:600;line-height:1.3;padding:.3125rem .625rem;text-align:left}.drc-sleep-card-status:before{content:"";flex:0 0 auto;width:.375rem;height:.375rem;border-radius:50%;background:currentColor;opacity:.72}.drc-sleep-card.good .drc-sleep-card-status{background:var(--rh-status-positive-surface);color:var(--rh-status-positive)}.drc-sleep-card.warn .drc-sleep-card-status{background:var(--rh-status-caution-surface);color:var(--rh-status-caution)}.drc-sleep-card.bad .drc-sleep-card-status{background:var(--rh-status-negative-surface);color:var(--rh-status-negative)}.drc-sleep-card.good .drc-sleep-card-delta{color:var(--rh-status-positive)}.drc-sleep-card.warn .drc-sleep-card-delta{color:var(--rh-status-caution)}.drc-sleep-card.bad .drc-sleep-card-delta{color:var(--rh-status-negative)}.drc-sleep-card.neutral .drc-sleep-card-delta{color:var(--rh-text-secondary)}
.drc-sleep-sparkline{display:block;width:100%;height:38px;margin:.625rem 0 .75rem;padding:0 .25rem}.drc-sleep-baseline-plot{position:relative;height:6.75rem;margin:.5rem 0 0}.drc-sleep-baseline-chart{display:block;width:100%;height:100%;margin:0}.drc-baseline-point{position:absolute;width:4px;height:4px;border-radius:50%;pointer-events:none;transform:translate(-50%,-50%)}.drc-baseline-point--previous{background:#a7b0bf}.drc-baseline-point--recent{background:#3979bd}.drc-baseline-anomaly{position:absolute;width:9px;height:9px;border:2px solid #d95c5c;border-radius:50%;pointer-events:none;transform:translate(-50%,-50%)}.drc-baseline-current{position:absolute;width:8px;height:8px;border:1px solid #fff;background:#2f9d63;pointer-events:none;transform:translate(-50%,-50%) rotate(45deg)}.drc-sleep-baseline-legend{display:flex;gap:.5rem;flex-wrap:wrap;color:var(--rh-text-muted);font-size:.625rem;line-height:1.35;margin-top:.25rem}.drc-sleep-baseline-legend span:before{content:"";display:inline-block;width:8px;height:3px;margin:0 3px 2px 0;vertical-align:middle;background:#3979bd}.drc-sleep-baseline-legend .range:before{height:6px;background:rgba(79,127,191,.20)}.drc-sleep-baseline-legend .median:before{background:#60718a}.drc-sleep-baseline-legend .current:before{background:#2f9d63}
.drc-sleep-problem{border-radius:10px;padding:10px 14px;margin:5px 0;font-weight:600}.drc-sleep-problem.good{background:#eaf7f0;color:#24704f}.drc-sleep-problem.bad{background:#fff0f0;color:#a43c3c}.drc-sleep-problem.neutral{background:#f3f5f8;color:#697386}
.drc-sleep-guidance{margin:.2rem 0 1.25rem}.drc-sleep-guidance-card{position:relative;overflow:hidden;min-width:0;border:1px solid rgba(117,130,148,.22);border-radius:1.25rem;padding:1.15rem 1.2rem 1.2rem;background:linear-gradient(135deg,rgba(255,255,255,.66),rgba(117,130,148,.07));box-shadow:0 1px 1px rgba(15,23,42,.04),0 10px 24px rgba(15,23,42,.05);backdrop-filter:blur(18px) saturate(135%);-webkit-backdrop-filter:blur(18px) saturate(135%)}.drc-sleep-guidance-card:before{content:"";position:absolute;inset:0 0 auto;height:1px;background:rgba(255,255,255,.52);pointer-events:none}.drc-sleep-guidance-top{display:flex;align-items:center;gap:.55rem;margin-bottom:.75rem}.drc-sleep-guidance-icon{display:grid;place-items:center;width:1.75rem;height:1.75rem;border-radius:50%;background:rgba(64,111,181,.14);color:#3979bd;font-size:1rem;line-height:1}.drc-sleep-guidance-kicker{color:var(--rh-text-muted);font-size:.6875rem;font-weight:650;letter-spacing:.055em;line-height:1.2;text-transform:uppercase}.drc-sleep-guidance-card h3{color:var(--rh-text);font-size:1.0625rem;font-weight:650;letter-spacing:-.008em;line-height:1.35;margin:0}.drc-sleep-guidance-copy{color:var(--rh-text-secondary);font-size:.875rem;line-height:1.65;margin:.5rem 0 0}.drc-sleep-guidance-card.good{border-color:rgba(58,166,117,.28)}.drc-sleep-guidance-card.warn{border-color:rgba(224,160,43,.34)}.drc-sleep-guidance-card.neutral{border-color:rgba(117,130,148,.24)}
.drc-baseline-card{margin-bottom:.625rem;padding:.95rem 1rem}.drc-baseline-card-head{padding-bottom:.55rem}.drc-baseline-summary{min-height:0;padding-top:.6rem}.drc-baseline-kicker{color:var(--rh-text-secondary);font-size:.6875rem;font-weight:500;line-height:1.35}.drc-baseline-main{color:var(--rh-text);font-size:1.625rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.016em;line-height:1.2;margin:.25rem 0 .6rem}.drc-baseline-grid{border-top:1px solid var(--rh-border-subtle);display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0}.drc-baseline-item{min-width:0;padding:.5rem .75rem .5rem 0}.drc-baseline-item:nth-child(even){border-left:1px solid var(--rh-border-subtle);padding-left:.75rem;padding-right:0}.drc-baseline-item:nth-child(n+3){border-top:1px solid var(--rh-border-subtle)}.drc-baseline-item-label{color:var(--rh-text-muted);font-size:.6875rem;font-weight:500;line-height:1.3}.drc-baseline-item-value{color:var(--rh-text);font-size:.8125rem;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.4;margin-top:.1rem;overflow-wrap:anywhere}.drc-baseline-chart-wrap{border-top:1px solid var(--rh-border-subtle);margin-top:.05rem;padding-top:.1rem}
@supports (background:color-mix(in srgb,white 50%,black)){.drc-sleep-card{background:linear-gradient(145deg,color-mix(in srgb,var(--secondary-background-color) 94%,var(--text-color) 6%),var(--secondary-background-color));box-shadow:inset 0 1px 0 color-mix(in srgb,var(--text-color) 10%,transparent),var(--rh-shadow-raised)}.drc-sleep-card-head,.drc-sleep-card-meta{border-color:var(--rh-border-subtle)}.drc-sleep-card-status{background:var(--rh-surface-inset);border-color:var(--rh-border-subtle)}}
@media (hover:hover) and (prefers-reduced-motion:no-preference){.drc-sleep-card{transition:transform 180ms ease-out,box-shadow 180ms ease-out,border-color 180ms ease-out}.drc-sleep-card:hover{transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.18),0 20px 36px rgba(0,0,0,.14)}}
@media (prefers-color-scheme: dark){.drc-sleep-guidance-card{background:linear-gradient(135deg,rgba(73,91,157,.26),rgba(117,130,148,.09));border-color:rgba(172,188,231,.20);box-shadow:inset 0 1px 0 rgba(255,255,255,.10),0 12px 28px rgba(0,0,0,.15)}.drc-sleep-guidance-card:before{background:rgba(255,255,255,.14)}.drc-sleep-guidance-icon{background:rgba(127,145,229,.20);color:#aebcff}}
@media (max-width: 720px){.drc-sleep-card,.drc-baseline-card{padding:1.1rem}.drc-sleep-card.primary .drc-sleep-card-value{font-size:2.375rem}.drc-baseline-grid{grid-template-columns:1fr}.drc-baseline-item,.drc-baseline-item:nth-child(even){border-left:0;padding:.8rem 0}.drc-baseline-item:nth-child(2){border-top:1px solid var(--rh-border-subtle)}}
@media (prefers-reduced-transparency: reduce){.drc-sleep-guidance-card{background:var(--rh-surface-inset);backdrop-filter:none;-webkit-backdrop-filter:none}}
</style>
"""
st.markdown(SLEEP_CSS, unsafe_allow_html=True)
BASELINE_LEGEND_OPEN = '<div class="drc-sleep-baseline-legend">'
BASELINE_LEGEND_CLOSE = "</div>"


def _number(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _ui(zh, en):
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


def _field(data, name):
    return (data or {}).get("resolved_fields", {}).get(name, {}).get("value")


def _today_sleep_values(data):
    """Single source of truth for values shared by the table and detail cards."""
    return {
        "date": (data or {}).get("date"),
        "score": (data or {}).get("sleep_score"),
        "bedtime": _field(data, "sleep_start_time"),
        "wake_time": _field(data, "wake_time"),
        "total_duration_minutes": _field(data, "total_sleep_duration_minutes"),
        "actual_duration_minutes": _field(data, "actual_sleep_duration_minutes"),
        "deep_duration_minutes": _field(data, "deep_sleep_duration_minutes"),
        "rem_duration_minutes": _field(data, "rem_sleep_duration_minutes"),
        "average_hr": _field(data, "average_sleep_hr_bpm"),
        "hrv": _field(data, "nightly_hrv_rmssd"),
        "resting_hr": _field(data, "nightly_resting_hr"),
        "respiration": _field(data, "respiration_rate"),
        "minimum_hr": _field(data, "minimum_sleep_hr_bpm"),
    }


SLEEP_TABLE_FIELDS = (
    "sleep_score",
    "sleep_start_time",
    "wake_time",
    "total_sleep_duration_minutes",
    "actual_sleep_duration_minutes",
    "deep_sleep_duration_minutes",
    "rem_sleep_duration_minutes",
    "average_sleep_hr_bpm",
    "nightly_hrv_rmssd",
    "nightly_resting_hr",
    "respiration_rate",
    "minimum_sleep_hr_bpm",
)


def _is_complete_sleep_record(data):
    """A baseline record is valid only when every table field is present."""
    if not data or not data.get("date"):
        return False
    values = _today_sleep_values(data)
    return all(
        (values["score"] if field == "sleep_score" else _field(data, field))
        not in (None, "")
        for field in SLEEP_TABLE_FIELDS
    )


def _hours(value):
    return None if value in (None, "") else float(value) / 60


def _duration_hms(value):
    return TR("common.no_data") if value in (None, "") else minutes_to_hms(value)


def _signed_duration_hms(value):
    if value in (None, ""):
        return TR("common.no_data")
    sign = "+" if float(value) >= 0 else "−"
    return f"{sign}{minutes_to_hms(abs(float(value)))}"


def _signed_number(value, suffix=""):
    if value in (None, ""):
        return TR("common.no_data")
    number = float(value)
    sign = "+" if number >= 0 else "−"
    return f"{sign}{format_number(abs(number), LANGUAGE)}{suffix}"


def _percent_difference(current, baseline):
    if current is None or baseline in (None, 0):
        return None
    return (float(current) - float(baseline)) / abs(float(baseline)) * 100


def _difference_with_percent(current, baseline, suffix="", duration=False):
    if current is None or baseline in (None, 0):
        return TR("common.no_data")
    difference = float(current) - float(baseline)
    difference_text = _signed_duration_hms(difference) if duration else _signed_number(difference, suffix)
    percent_text = _signed_number(_percent_difference(current, baseline), "%")
    return f"{difference_text}（{percent_text}）"


def _actual_sleep_baseline_minutes(history, limit=28, exclude_date=None):
    return _history_baseline_value(
        history,
        "actual_sleep_duration",
        limit=limit,
        exclude_date=exclude_date,
    )


def _sleep_history_metric(item, key):
    values = _today_sleep_values(item)
    return {
        "actual_sleep_duration": values["actual_duration_minutes"],
        "sleep_duration": (
            None
            if values["total_duration_minutes"] in (None, "")
            else float(values["total_duration_minutes"]) / 60
        ),
        "sleep_score": values["score"],
        "nightly_hrv_rmssd": values["hrv"],
        "nightly_resting_hr": values["resting_hr"],
        "respiration_rate": values["respiration"],
    }.get(key)


def _history_baseline_value(history, key, limit=28, exclude_date=None):
    """Recalculate a baseline from the latest history on every page rerun."""
    values = []
    for item in history:
        if not _is_complete_sleep_record(item):
            continue
        if item.get("date") == exclude_date:
            continue
        value = _sleep_history_metric(item, key)
        if value in (None, ""):
            continue
        values.append(float(value))
        if len(values) == limit:
            break
    return statistics.median(values) if values else None


def _synchronized_sleep_baselines(history, persisted, exclude_date=None, limit=28):
    """Overlay persisted metadata with medians computed from current history."""
    synchronized = {key: dict(value) for key, value in (persisted or {}).items()}
    for key in (
        "sleep_duration",
        "sleep_score",
        "nightly_hrv_rmssd",
        "nightly_resting_hr",
        "respiration_rate",
    ):
        valid_values = [
            _sleep_history_metric(item, key)
            for item in history
            if _is_complete_sleep_record(item) and item.get("date") != exclude_date
        ]
        valid_values = [value for value in valid_values if value not in (None, "")][:limit]
        synchronized[key] = {
            **synchronized.get(key, {}),
            "median_value": statistics.median(float(value) for value in valid_values)
            if valid_values else None,
            "valid_days": len(valid_values),
            "window_days": limit,
        }
    return synchronized


def _sleep_datetime(value, day):
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        for pattern in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(str(value), pattern).time()
                return datetime.combine(date.fromisoformat(day), parsed_time)
            except ValueError:
                continue
    return None


def _offset_seconds(value):
    if value in (None, ""):
        return None
    match = re.fullmatch(r"(?:PT)?(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?", str(value))
    if match and any(part is not None for part in match.groups()):
        hours, minutes, seconds = (float(part or 0) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stage_segments(data):
    start = _sleep_datetime(_field(data, "sleep_start_time"), data["date"])
    end = _sleep_datetime(_field(data, "wake_time"), data["date"])
    changes = data.get("sleep_state_changes") or []
    if not start or not end or end <= start or not isinstance(changes, list):
        return []
    total_seconds = (end - start).total_seconds()
    labels = {
        "SLEEP_STATE_WAKE": ("domain.sleep.stage_awake", "#f1b44c"),
        "SLEEP_STATE_REM": ("domain.sleep.stage_rem", "#9b7bd3"),
        "SLEEP_STATE_NON_REM3": ("domain.sleep.stage_deep", "#38598b"),
        "SLEEP_STATE_NON_REM2": ("domain.sleep.stage_light", "#70a6d8"),
        "SLEEP_STATE_NON_REM1": ("domain.sleep.stage_light", "#70a6d8"),
    }
    parsed = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        offset = _offset_seconds(change.get("offsetFromStart"))
        state = change.get("newState")
        if offset is not None and state in labels and 0 <= offset < total_seconds:
            parsed.append((offset, state))
    parsed.sort(key=lambda item: item[0])
    segments = []
    for index, (offset, state) in enumerate(parsed):
        next_offset = parsed[index + 1][0] if index + 1 < len(parsed) else total_seconds
        if next_offset <= offset:
            continue
        label_key, color = labels[state]
        segments.append({
            "label": TR(label_key), "color": color,
            "start": start + timedelta(seconds=offset),
            "end": start + timedelta(seconds=min(next_offset, total_seconds)),
        })
    return segments


def _sleep_timeline(data):
    segments = _stage_segments(data)
    st.subheader(TR("domain.sleep.sleep_timeline"))
    if not segments:
        st.info(TR("domain.sleep.timeline_no_data"))
        return
    figure = go.Figure()
    seen = set()
    for segment in segments:
        show_legend = segment["label"] not in seen
        seen.add(segment["label"])
        figure.add_trace(go.Scatter(
            x=[segment["start"], segment["end"]],
            y=[segment["label"], segment["label"]],
            mode="lines",
            line=dict(color=segment["color"], width=22),
            name=segment["label"],
            showlegend=show_legend,
            hovertemplate=(
                f"{segment['label']}<br>"
                f"%{{x|%H:%M}}<extra></extra>"
            ),
        ))
    figure.update_layout(
        height=250, margin=dict(l=20, r=20, t=20, b=35),
        xaxis=dict(type="date", tickformat="%H:%M", title=None),
        yaxis=dict(title=None, categoryorder="array", categoryarray=[
            TR("domain.sleep.stage_awake"), TR("domain.sleep.stage_rem"),
            TR("domain.sleep.stage_light"), TR("domain.sleep.stage_deep"),
        ]),
        legend=dict(orientation="h", y=-0.22), plot_bgcolor="white",
    )
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _status(score):
    if score is None:
        return "neutral", TR("domain.sleep.status_no_data")
    if score >= 85:
        return "good", TR("domain.sleep.status_excellent")
    if score >= 70:
        return "good", TR("domain.sleep.status_good")
    if score >= 55:
        return "warn", TR("domain.sleep.status_fair")
    return "bad", TR("domain.sleep.status_poor")


def _overview(data):
    score = data.get("sleep_score") if data else None
    tone, status = _status(score)
    summary = TR("domain.sleep.summary_no_data")
    if score is not None:
        summary = TR("domain.sleep.summary_with_score", score=format_number(score, LANGUAGE), status=status)
    left, right = st.columns([1, 2])
    with left:
        st.metric(TR("domain.sleep.composite_score"), _number(score))
        (st.success if tone == "good" else st.warning if tone == "warn" else st.error if tone == "bad" else st.info)(status)
    with right:
        st.markdown(f"### {TR('domain.sleep.one_line_summary')}")
        st.write(summary)
        st.info(TR("domain.sleep.ai_placeholder"))


def _baseline_progress(baseline):
    valid = int((baseline or {}).get("valid_days") or 0)
    target = 28
    return valid, target, max(0, target - valid)


def _metric_state(current, baseline, higher_is_better=True, tolerance=5):
    if current is None:
        return "neutral", _ui("当前数据待同步", "Current data is pending sync")
    if baseline is None:
        return "neutral", _ui("基线建立中", "Baseline is being established")
    delta = (current - baseline) / abs(baseline) * 100 if baseline else 0
    if abs(delta) <= tolerance:
        return "good", _ui("处于个人正常范围", "Within your normal range")
    adverse = delta < -tolerance if higher_is_better else delta > tolerance
    return ("bad" if adverse else "warn"), _ui("明显偏离" if abs(delta) >= 12 else "轻度偏离", "Material deviation" if abs(delta) >= 12 else "Mild deviation")


def _sparkline_svg(values, color, css_class="drc-sleep-sparkline"):
    numeric_values = [float(value) for value in values if value is not None]
    if len(numeric_values) < 2:
        return ""
    width, height, padding = 360, 48, 5
    low, high = min(numeric_values), max(numeric_values)
    spread = max(high - low, 1.0)
    low -= spread * 0.08
    high += spread * 0.08
    segments, active_segment, points = [], [], []
    for index, value in enumerate(values):
        if value is None:
            if active_segment:
                segments.append(active_segment)
                active_segment = []
            continue
        x = padding + index * (width - padding * 2) / max(1, len(values) - 1)
        y = height - padding - (float(value) - low) / (high - low) * (height - padding * 2)
        point = (x, y)
        active_segment.append(point)
        points.append(point)
    if active_segment:
        segments.append(active_segment)
    polylines = "".join(
        f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in segment)}" '
        f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />'
        for segment in segments if len(segment) >= 2
    )
    circles = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{color}" />' for x, y in points)
    return (
        f'<svg class="{css_class}" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'role="img" aria-label="{escape(_ui("睡眠趋势", "Sleep trend"))}">'
        f'{polylines}{circles}</svg>'
    )


def _trend_svg(values, tone):
    color = {"good": "#3aa675", "warn": "#e0a02b", "bad": "#d95c5c", "neutral": "#8290a5"}[tone]
    return _sparkline_svg(values, color)


def _card_html(title, value, meta, status, tone, trend_svg="", explanation=None, primary=False, metric=False):
    explanation_markup = ""
    if explanation:
        explanation_markup = (
            '<div class="drc-sleep-card-explanation">'
            f'<div class="drc-sleep-card-explanation-label">{escape(_ui("简短解释", "Brief explanation"))}</div>'
            f'{escape(explanation)}</div>'
        )
    card_class = f"drc-sleep-card {tone}{' primary' if primary else ''}{' metric' if metric else ''}"
    return (
        f'<div class="{card_class}">'
        f'<div class="drc-sleep-card-head"><h3>{escape(title)}</h3>'
        f'<div class="drc-sleep-card-status">{escape(status)}</div></div>'
        f'<div class="drc-sleep-card-value">{escape(value)}</div>'
        f'<div class="drc-sleep-card-meta">{meta}</div>{trend_svg}{explanation_markup}</div>'
    )


def _today_detail_baselines(data, history):
    """Return compact, current-cycle-excluded baseline summaries for detail cards."""
    target_date = (data or {}).get("date") or date.today().isoformat()
    regularity_points, current_regularity_score = _sleep_regularity_artifacts(history, target_date)
    summaries = {}
    for key in (
        "actual_sleep_duration",
        "sleep_score",
        "nightly_hrv_rmssd",
        "nightly_resting_hr",
        "respiration_rate",
    ):
        points = []
        for item in history:
            value = _sleep_history_metric(item, key)
            if value in (None, "") or (key == "respiration_rate" and float(value) <= 0):
                continue
            points.append((item["date"], float(value)))
        summaries[key] = build_sleep_baseline_summary(points, target_date)
    summaries["sleep_regularity"] = build_sleep_baseline_summary(regularity_points, target_date)
    return summaries, current_regularity_score


def _card_trend_values(summary, current_value):
    """Use only recorded trailing values and the current real measurement."""
    return [*summary["series"][-6:], current_value]


def _sleep_card_explanation(key, current_value, summary, context):
    """Summarize the night's situation rather than restating a metric's value."""
    if current_value is None:
        return _ui("这项睡眠情况暂未同步，无法纳入本晚判断。", "This sleep signal has not synced yet, so it is not included in tonight’s interpretation.")
    if int(summary["valid_nights"] or 0) < 7 or summary["lower"] is None or summary["upper"] is None:
        return _ui("个人基线仍在建立中，先连续观察这项睡眠情况。", "Your personal baseline is still being established; continue observing this sleep signal.")
    position = "low" if current_value < summary["lower"] else "high" if current_value > summary["upper"] else "within"
    actual = context["actual"]
    hrv_low = _outside_personal_range(
        context["hrv"], context["summaries"]["nightly_hrv_rmssd"], direction="low"
    )
    hr_high = _outside_personal_range(
        context["resting"], context["summaries"]["nightly_resting_hr"], direction="high"
    )
    regularity_low = _outside_personal_range(
        context["regularity"], context["summaries"]["sleep_regularity"], direction="low"
    )

    if key == "sleep_score":
        problems = []
        if actual is not None and actual < 7 * 60:
            problems.append(_ui("睡眠机会不足", "insufficient sleep opportunity"))
        if hrv_low:
            problems.append(_ui("恢复信号偏弱", "weaker recovery signal"))
        if hr_high:
            problems.append(_ui("夜间心率负荷偏高", "higher overnight heart-rate load"))
        if regularity_low:
            problems.append(_ui("作息节律不稳", "irregular sleep timing"))
        if problems:
            return _ui(f"本晚主要问题：{_ui('、', '; ').join(problems[:2])}。", f"Main issues tonight: {'; '.join(problems[:2])}.")
        return _ui(
            "本晚未见突出睡眠问题，整体表现与近期节律相近。",
            "No prominent sleep issue is evident tonight; overall pattern is close to your recent rhythm.",
        )

    explanations = {
        "actual_sleep_duration": {
            "low": _ui("这晚可恢复的睡眠机会不足，时长被压缩。", "This night offered insufficient recovery opportunity; sleep time was compressed."),
            "high": _ui("这晚获得的睡眠机会多于近期常态。", "This night provided more sleep opportunity than your recent norm."),
            "within": _ui("这晚的睡眠机会与近期节律基本一致。", "This night’s sleep opportunity is broadly consistent with your recent rhythm."),
        },
        "nightly_hrv_rmssd": {
            "low": _ui("这晚的恢复信号偏弱，可优先补足睡眠机会。", "Recovery signal was weaker tonight; prioritize adequate sleep opportunity."),
            "high": _ui("这晚的恢复信号优于近期常态。", "Recovery signal was stronger than your recent norm tonight."),
            "within": _ui("这晚的恢复信号与近期常态相近。", "Recovery signal is close to your recent norm tonight."),
        },
        "nightly_resting_hr": {
            "low": _ui("这晚的夜间心率负荷低于近期常态。", "Overnight heart-rate load was lower than your recent norm."),
            "high": _ui("这晚的夜间心率负荷偏高，结合其他睡眠指标继续观察。", "Overnight heart-rate load was higher; continue observing it with the other sleep signals."),
            "within": _ui("这晚的夜间心率负荷与近期常态相近。", "Overnight heart-rate load is close to your recent norm."),
        },
        "respiration_rate": {
            "low": _ui("这晚的呼吸节律与近期不同，先连续观察变化。", "Respiratory rhythm differed from recent nights; continue observing the change."),
            "high": _ui("这晚的呼吸节律与近期不同，先连续观察变化。", "Respiratory rhythm differed from recent nights; continue observing the change."),
            "within": _ui("这晚的呼吸节律与近期常态相近。", "Respiratory rhythm is close to your recent norm tonight."),
        },
        "sleep_regularity": {
            "low": _ui("近期入睡或起床时点更分散，作息节律需要收拢。", "Bedtime or wake time has become more dispersed recently; the sleep rhythm needs tightening."),
            "high": _ui("近期入睡和起床时点比平时更稳定。", "Bedtime and wake time have been more stable than usual recently."),
            "within": _ui("近期作息节律保持稳定。", "Recent sleep timing remains stable."),
        },
    }
    return explanations[key][position]


def _outside_personal_range(value, summary, *, direction):
    """Return whether a real value is outside a mature personal range."""
    if value is None or int(summary["valid_nights"] or 0) < 7:
        return False
    lower, upper = summary["lower"], summary["upper"]
    if lower is None or upper is None:
        return False
    return value < lower if direction == "low" else value > upper


def _sleep_guidance(data, detail_baseline_data):
    """Create data-bound night and daytime actions from current sleep deviations."""
    def plan(tone, context, night_title, night_action, day_title, day_action):
        return tone, {
            "context": context,
            "night": (night_title, night_action),
            "day": (day_title, day_action),
        }

    if not data or not detail_baseline_data:
        return plan(
            "neutral",
            _ui("尚无足够记录判断个人波动。先建立连续、可信的睡眠记录。", "There is not yet enough data to assess personal variation. First establish a consistent, reliable sleep record."),
            _ui("为睡眠腾出时间", "Make room for sleep"),
            _ui("今晚预留至少 8 小时睡眠机会；睡前 60 分钟停止高刺激屏幕和工作。", "Allow at least 8 hours for sleep tonight; stop stimulating screen use and work 60 minutes before bed."),
            _ui("完成连续记录", "Complete a continuous record"),
            _ui("起床时间尽量与平时相差不超过 30 分钟，并连续佩戴设备记录至少 7 晚。", "Keep wake time within 30 minutes of usual and wear the device for at least 7 consecutive nights."),
        )

    summaries, regularity = detail_baseline_data
    values = _today_sleep_values(data)
    actual = values["actual_duration_minutes"]
    hrv = values["hrv"]
    resting = values["resting_hr"]
    score = values["score"]

    if actual is not None and (
        actual < 7 * 60
        or _outside_personal_range(actual, summaries["actual_sleep_duration"], direction="low")
    ):
        return plan(
            "warn",
            _ui(f"实际睡眠 {_duration_hms(actual)}；个人常见范围 {_sleep_baseline_range('actual_sleep_duration', summaries['actual_sleep_duration'])}。", f"Actual sleep was {_duration_hms(actual)}; your personal range is {_sleep_baseline_range('actual_sleep_duration', summaries['actual_sleep_duration'])}."),
            _ui("补回睡眠机会", "Restore sleep opportunity"),
            _ui("把入睡时间比平时提前 30–60 分钟，并预留至少 8 小时的睡眠窗口。", "Start your sleep window 30–60 minutes earlier than usual and allow at least 8 hours for sleep."),
            _ui("保护今晚的节律", "Protect tonight’s rhythm"),
            _ui("白天保持日常活动；午后避免延长小睡，起床时间仍保持在平时±30分钟内。", "Keep normal daytime activity; avoid an extended late-day nap and keep wake time within 30 minutes of usual."),
        )

    hrv_low = _outside_personal_range(hrv, summaries["nightly_hrv_rmssd"], direction="low")
    hr_high = _outside_personal_range(resting, summaries["nightly_resting_hr"], direction="high")
    if hrv_low or hr_high:
        evidence = []
        if hrv_low:
            evidence.append(_ui(
                f"睡眠期间 HRV {_sleep_baseline_text('nightly_hrv_rmssd', hrv)} 低于个人常见范围 {_sleep_baseline_range('nightly_hrv_rmssd', summaries['nightly_hrv_rmssd'])}",
                f"Sleep HRV {_sleep_baseline_text('nightly_hrv_rmssd', hrv)} is below your personal range {_sleep_baseline_range('nightly_hrv_rmssd', summaries['nightly_hrv_rmssd'])}",
            ))
        if hr_high:
            evidence.append(_ui(
                f"夜间静息心率 {_sleep_baseline_text('nightly_resting_hr', resting)} 高于个人常见范围 {_sleep_baseline_range('nightly_resting_hr', summaries['nightly_resting_hr'])}",
                f"Nightly resting heart rate {_sleep_baseline_text('nightly_resting_hr', resting)} is above your personal range {_sleep_baseline_range('nightly_resting_hr', summaries['nightly_resting_hr'])}",
            ))
        return plan(
            "warn",
            _ui("；".join(evidence), "; ".join(evidence)),
            _ui("降低睡前负荷", "Lower the pre-sleep load"),
            _ui("优先安排至少 8 小时睡眠机会；睡前 60 分钟停止高刺激屏幕和工作。", "Prioritize at least 8 hours for sleep; stop stimulating screen use and work 60 minutes before bed."),
            _ui("让白天不过度加码", "Keep daytime load measured"),
            _ui("把训练调整为轻松活动或中低强度，并避免把高强度训练安排在临睡前。", "Choose easy activity or low-to-moderate intensity, and avoid scheduling high-intensity training close to bedtime."),
        )

    if _outside_personal_range(regularity, summaries["sleep_regularity"], direction="low"):
        return plan(
            "warn",
            _ui(f"睡眠规律性 {_sleep_baseline_text('sleep_regularity', regularity)}；个人常见范围 {_sleep_baseline_range('sleep_regularity', summaries['sleep_regularity'])}。", f"Sleep regularity is {_sleep_baseline_text('sleep_regularity', regularity)}; your personal range is {_sleep_baseline_range('sleep_regularity', summaries['sleep_regularity'])}."),
            _ui("守住就寝锚点", "Keep a bedtime anchor"),
            _ui("未来 3 晚尽量在相近时间上床；睡前 60 分钟进入低刺激的固定流程。", "For the next 3 nights, go to bed at a similar time and begin the same low-stimulation wind-down 60 minutes beforehand."),
            _ui("固定起床锚点", "Keep a wake-time anchor"),
            _ui("未来 3 天把起床时间控制在平时±30分钟内；起床后尽早接受自然光并保持日常活动。", "For the next 3 days, keep wake time within 30 minutes of usual; get daylight soon after waking and maintain normal activity."),
        )

    if _outside_personal_range(score, summaries["sleep_score"], direction="low"):
        return plan(
            "warn",
            _ui(f"睡眠评分 {_sleep_baseline_text('sleep_score', score)}；个人常见范围 {_sleep_baseline_range('sleep_score', summaries['sleep_score'])}。", f"Sleep score is {_sleep_baseline_text('sleep_score', score)}; your personal range is {_sleep_baseline_range('sleep_score', summaries['sleep_score'])}."),
            _ui("精简睡前安排", "Simplify the pre-sleep routine"),
            _ui("预留至少 8 小时睡眠机会，并在睡前 60 分钟只安排低刺激的放松活动。", "Allow at least 8 hours for sleep and use only low-stimulation wind-down activities during the final 60 minutes before bed."),
            _ui("减少日间干扰", "Reduce daytime disruption"),
            _ui("白天保持规律进餐和活动，避免把重要工作或高强度训练堆到临睡前。", "Keep meals and activity regular during the day; avoid moving major work or high-intensity training close to bedtime."),
        )

    return plan(
        "good",
        _ui("今日可用睡眠指标均处于个人常见范围。", "Today’s available sleep indicators are within your personal range."),
        _ui("延续既有节律", "Continue the established rhythm"),
        _ui("保持平时的就寝与起床时间，继续预留 7.5–8 小时睡眠机会，并在睡前 60 分钟降低刺激。", "Keep your usual bedtime and wake time, allow 7.5–8 hours for sleep, and reduce stimulation during the final 60 minutes before bed."),
        _ui("用白天巩固节律", "Reinforce the rhythm by day"),
        _ui("起床后尽早接受自然光，白天保持日常活动；避免把小睡或高强度训练安排得过晚。", "Get daylight soon after waking and maintain normal activity; avoid scheduling naps or high-intensity training too late."),
    )


def _render_sleep_guidance(data, detail_baseline_data):
    tone, guidance = _sleep_guidance(data, detail_baseline_data)
    night_title, night_action = guidance["night"]
    html = (
        f'<section class="drc-sleep-guidance" aria-label="{escape(_ui("睡眠建议", "Sleep guidance"))}">'
        f'<article class="drc-sleep-guidance-card {tone}"><div class="drc-sleep-guidance-top"><span class="drc-sleep-guidance-icon" aria-hidden="true">✦</span><span class="drc-sleep-guidance-kicker">{escape(_ui("个性化建议", "Personalized guidance"))}</span></div><h3>{escape(night_title)}</h3><p class="drc-sleep-guidance-copy">{escape(night_action)}</p></article>'
        '</section>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _baseline_card_meta(key, summary, current_value, *, baseline_label=None, difference_suffix="", duration=False):
    """Keep each card self-contained without recreating the full baseline panel."""
    center = summary["center"]
    label = baseline_label or _ui("个人基线", "Personal baseline")
    difference = _difference_with_percent(current_value, center, difference_suffix, duration=duration)
    display_summary = _summary_with_current_period(summary, current_value)
    return _ui(
        f"{label}：{_sleep_baseline_text(key, center)} · 差值：{difference}"
        f"<br>个人常见范围：{_sleep_baseline_range(key, summary)} · {_comparison_text(key, display_summary)}",
        f"{label}: {_sleep_baseline_text(key, center)} · Difference: {difference}"
        f"<br>Personal range: {_sleep_baseline_range(key, summary)} · {_comparison_text(key, display_summary)}",
    )


def _range_state(current, summary, *, higher_is_better=None):
    """Classify a current value against its robust personal range."""
    if current is None:
        return "neutral", _ui("当前数据待同步", "Current data is pending sync")
    lower, upper = summary["lower"], summary["upper"]
    if lower is None or upper is None:
        return "neutral", _ui("基线建立中", "Baseline is being established")
    if lower <= current <= upper:
        return "good", _ui("处于个人正常范围", "Within your normal range")
    if higher_is_better is None:
        return "warn", _ui("超出个人常见范围", "Outside your personal range")
    adverse = current < lower if higher_is_better else current > upper
    return ("bad" if adverse else "warn"), _ui("明显偏离", "Material deviation")


def _sleep_baseline_context(detail_baselines):
    """Summarize the baseline coverage supporting every sleep detail card."""
    labels = (
        ("sleep_score", "domain.sleep.score"),
        ("actual_sleep_duration", "domain.sleep.actual_duration"),
        ("nightly_hrv_rmssd", "domain.sleep.hrv"),
        ("nightly_resting_hr", "domain.sleep.nightly_resting_hr"),
        ("respiration_rate", "domain.sleep.respiration"),
        ("sleep_regularity", None),
    )
    segments = []
    windows = []
    for metric_name, label_key in labels:
        summary = detail_baselines[metric_name]
        valid_days = int(summary["valid_nights"] or 0)
        window_days = len(summary["dates"])
        percent = min(100, round(valid_days / window_days * 100)) if window_days else 0
        maturity = TR(
            "domain.sleep.maturity_days",
            valid=valid_days,
            window=window_days,
            percent=percent,
        )
        label = TR(label_key) if label_key else _ui("睡眠规律性", "Sleep Regularity")
        segments.append(f"{label}：{maturity}")
        windows.append(window_days)
    window_days = max(windows, default=28)
    return " · ".join((*segments, TR("domain.sleep.range_basis", window=window_days)))


def _core_cards(data, history, baselines, key_prefix="sleep", detail_baseline_data=None):
    values = _today_sleep_values(data)
    score = values["score"]
    score_tone, score_status = _status(score)
    actual = values["actual_duration_minutes"]
    hrv = values["hrv"]
    resting = values["resting_hr"]
    respiration = values["respiration"]
    detail_baselines, regularity = detail_baseline_data or _today_detail_baselines(data, history)
    duration_base = detail_baselines["actual_sleep_duration"]["center"]
    hrv_base = detail_baselines["nightly_hrv_rmssd"]["center"]
    hr_base = detail_baselines["nightly_resting_hr"]["center"]
    duration_tone, duration_status = _metric_state(actual, duration_base, True, 4)
    hrv_tone, hrv_status = _metric_state(hrv, hrv_base, True, 5)
    hr_tone, hr_status = _metric_state(resting, hr_base, False, 5)
    respiration_tone, respiration_status = _range_state(
        respiration, detail_baselines["respiration_rate"], higher_is_better=None,
    )
    regularity_tone, regularity_status = _range_state(
        regularity, detail_baselines["sleep_regularity"], higher_is_better=True,
    )
    explanation_context = {
        "actual": actual,
        "hrv": hrv,
        "resting": resting,
        "regularity": regularity,
        "summaries": detail_baselines,
    }
    score_meta = _baseline_card_meta("sleep_score", detail_baselines["sleep_score"], score)
    cards = [
        (_ui("睡眠综合评分", "Sleep Composite Score"), _number(score), score_meta, score_status, score_tone, _card_trend_values(detail_baselines["sleep_score"], score), _sleep_card_explanation("sleep_score", score, detail_baselines["sleep_score"], explanation_context), True),
        (_ui("实际睡眠时长", "Actual Sleep Duration"), _duration_hms(actual), _baseline_card_meta("actual_sleep_duration", detail_baselines["actual_sleep_duration"], actual, duration=True), duration_status, duration_tone, _card_trend_values(detail_baselines["actual_sleep_duration"], actual), _sleep_card_explanation("actual_sleep_duration", actual, detail_baselines["actual_sleep_duration"], explanation_context), False),
        (_ui("睡眠期间 HRV", "Sleep HRV"), _number(hrv," ms"), _baseline_card_meta("nightly_hrv_rmssd", detail_baselines["nightly_hrv_rmssd"], hrv, difference_suffix=" ms", baseline_label=_ui("基线中心", "Baseline center")), hrv_status, hrv_tone, _card_trend_values(detail_baselines["nightly_hrv_rmssd"], hrv), _sleep_card_explanation("nightly_hrv_rmssd", hrv, detail_baselines["nightly_hrv_rmssd"], explanation_context), False),
        (_ui("夜间静息心率", "Nightly Resting Heart Rate"), _number(resting," bpm"), _baseline_card_meta("nightly_resting_hr", detail_baselines["nightly_resting_hr"], resting, difference_suffix=" bpm"), hr_status, hr_tone, _card_trend_values(detail_baselines["nightly_resting_hr"], resting), _sleep_card_explanation("nightly_resting_hr", resting, detail_baselines["nightly_resting_hr"], explanation_context), False),
        (_ui("睡眠期间呼吸速率", "Sleep Respiratory Rate"), _number(respiration, _ui(" 次/分", " breaths/min")), _baseline_card_meta("respiration_rate", detail_baselines["respiration_rate"], respiration), respiration_status, respiration_tone, _card_trend_values(detail_baselines["respiration_rate"], respiration), _sleep_card_explanation("respiration_rate", respiration, detail_baselines["respiration_rate"], explanation_context), False),
        (_ui("睡眠规律性", "Sleep Regularity"), _sleep_baseline_text("sleep_regularity", regularity), _baseline_card_meta("sleep_regularity", detail_baselines["sleep_regularity"], regularity), regularity_status, regularity_tone, _card_trend_values(detail_baselines["sleep_regularity"], regularity), _sleep_card_explanation("sleep_regularity", regularity, detail_baselines["sleep_regularity"], explanation_context), False),
    ]
    cols = st.columns(2)
    for index, (col, card) in enumerate(zip(cols * 3, cards)):
        with col:
            st.markdown(
                _card_html(
                    *card[:5],
                    trend_svg=_trend_svg(card[5], card[4]),
                    explanation=card[6],
                    primary=card[7],
                    metric=True,
                ),
                unsafe_allow_html=True,
            )
    valid = max(
        (int(summary["valid_nights"] or 0) for summary in detail_baselines.values()),
        default=0,
    )
    target = 28
    if valid < target:
        maturity_caption = _ui(f"基线建立中：当前有效数据 {valid} / {target} 天，距离形成可靠基线还需 {target - valid} 天。", f"Baseline is being established: {valid} / {target} valid days; {target - valid} more days are needed.")
        st.caption(maturity_caption)

def _today_sleep_data(data):
    """Show the current Polar sleep payload as a single, factual table."""
    if not data or not data.get("has_observed_data"):
        if data:
            st.info(TR("domain.sleep.today_pending", date=format_date(data["date"], LANGUAGE)))
        else:
            st.info(TR("domain.sleep.empty"))
        return
    values = _today_sleep_values(data)
    fields = (
        ("date", "reports.date"), ("sleep_score", "domain.sleep.score"),
        ("sleep_start_time", "domain.sleep.bedtime"), ("wake_time", "domain.sleep.wake_time"),
        ("total_sleep_duration_minutes", "domain.sleep.total_duration"),
        ("actual_sleep_duration_minutes", "domain.sleep.actual_duration"),
        ("deep_sleep_duration_minutes", "domain.sleep.deep_duration"),
        ("rem_sleep_duration_minutes", "domain.sleep.rem_duration"),
        ("average_sleep_hr_bpm", "domain.sleep.average_hr"),
        ("nightly_hrv_rmssd", "domain.sleep.hrv"),
        ("nightly_resting_hr", "domain.sleep.nightly_resting_hr"),
        ("respiration_rate", "domain.sleep.respiration"),
        ("minimum_sleep_hr_bpm", "domain.sleep.minimum_hr"),
    )
    row = {}
    for field, label in fields:
        value = values["score"] if field == "sleep_score" else _field(data, field)
        if field == "date":
            value = format_date(data["date"], LANGUAGE)
        elif field in ("sleep_start_time", "wake_time"):
            value = time_to_hms(value)
        elif field.endswith("duration_minutes"):
            value = minutes_to_hms(value)
        elif field == "sleep_score" and value not in (None, ""):
            value = format_number(value, LANGUAGE)
        elif value not in (None, ""):
            value = format_number(value, LANGUAGE)
        row[TR(label)] = value if value not in (None, "") else TR("common.no_data")
    centered_dataframe([row])


def _problem_analysis(data, history, baselines):
    st.subheader(TR("domain.sleep.problem_analysis"))
    total = _hours(_field(data, "total_sleep_duration_minutes"))
    deep = _hours(_field(data, "deep_sleep_duration_minutes"))
    hrv = _field(data, "nightly_hrv_rmssd")
    hrv_base = (baselines.get("nightly_hrv_rmssd") or {}).get("median_value")
    bedtime = _sleep_datetime(_field(data, "sleep_start_time"), data["date"])
    checks = []
    if total is None:
        checks.append(("neutral", TR("domain.sleep.issue_duration_no_data")))
    elif total >= 7:
        checks.append(("good", TR("domain.sleep.issue_duration_good")))
    else:
        checks.append(("bad", TR("domain.sleep.issue_duration_bad")))
    if deep is None or total in (None, 0):
        checks.append(("neutral", TR("domain.sleep.issue_deep_no_data")))
    elif deep / total >= 0.15:
        checks.append(("good", TR("domain.sleep.issue_deep_good")))
    else:
        checks.append(("bad", TR("domain.sleep.issue_deep_bad")))
    if bedtime is None:
        checks.append(("neutral", TR("domain.sleep.issue_bedtime_no_data")))
    elif bedtime.hour > 23 or (bedtime.hour == 23 and bedtime.minute >= 30):
        checks.append(("bad", TR("domain.sleep.issue_bedtime_bad")))
    else:
        checks.append(("good", TR("domain.sleep.issue_bedtime_good")))
    if hrv is None or hrv_base in (None, 0):
        checks.append(("neutral", TR("domain.sleep.issue_hrv_no_data")))
    elif hrv >= hrv_base * 0.95:
        checks.append(("good", TR("domain.sleep.issue_hrv_good")))
    else:
        checks.append(("bad", TR("domain.sleep.issue_hrv_bad")))
    for tone, text in checks:
        (st.success if tone == "good" else st.error if tone == "bad" else st.info)(text)


def _card(label, current, baseline, formatter, higher_is_better=True):
    if current is None:
        tone, status = "neutral", TR("domain.sleep.status_no_data")
        value_text, delta_text = TR("common.no_data"), "→"
    else:
        value_text = formatter(current)
        if baseline in (None, 0):
            tone, status, delta_text = "neutral", TR("domain.sleep.status_no_baseline"), "→"
        else:
            delta = (current - baseline) / abs(baseline) * 100
            favorable = delta >= 5 if higher_is_better else delta <= -5
            unfavorable = delta <= -5 if higher_is_better else delta >= 5
            tone = "good" if favorable else "bad" if unfavorable else "warn"
            status = TR("domain.sleep.status_improving" if favorable else "domain.sleep.status_attention" if unfavorable else "domain.sleep.status_stable")
            arrow = "↑" if delta > 1 else "↓" if delta < -1 else "→"
            delta_text = f"{arrow} {delta:+.1f}%"
    html = (
        f'<div class="drc-sleep-card {tone}"><div class="drc-sleep-card-label">{escape(label)}</div>'
        f'<div class="drc-sleep-card-value">{escape(value_text)}</div>'
        f'<div class="drc-sleep-card-delta">{escape(delta_text)}</div>'
        f'<div class="drc-sleep-card-status">{escape(status)} · {TR("domain.sleep.baseline_28d")}: '
        f'{escape(formatter(baseline) if baseline is not None else TR("common.no_data"))}</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _status_cards(data, baselines):
    st.subheader(TR("domain.sleep.core_metrics"))
    current = {
        "score": data.get("sleep_score"),
        "duration": _hours(_field(data, "total_sleep_duration_minutes")),
        "hrv": _field(data, "nightly_hrv_rmssd"),
        "heart_rate": _field(data, "nightly_resting_hr"),
    }
    baseline = {
        "score": (baselines.get("sleep_score") or {}).get("median_value"),
        "duration": (baselines.get("sleep_duration") or {}).get("median_value"),
        "hrv": (baselines.get("nightly_hrv_rmssd") or {}).get("median_value"),
        "heart_rate": (baselines.get("nightly_resting_hr") or {}).get("median_value"),
    }
    cards = (
        ("domain.sleep.composite_score", "score", lambda x: _number(x), True),
        ("domain.sleep.total_duration", "duration", lambda x: _number(x, " h"), True),
        ("domain.sleep.hrv", "hrv", lambda x: _number(x, " ms"), True),
        ("domain.sleep.nightly_resting_hr", "heart_rate", lambda x: _number(x, " bpm"), False),
    )
    columns = st.columns(4)
    for column, (label, key, formatter, higher) in zip(columns, cards):
        with column:
            _card(TR(label), current[key], baseline[key], formatter, higher)


def _component_score(name, data, history, baselines):
    total = _hours(_field(data, "total_sleep_duration_minutes"))
    if name == "duration":
        return None if total is None else min(100, total / 8 * 100)
    if name == "deep":
        value = _hours(_field(data, "deep_sleep_duration_minutes"))
        return None if value is None or not total else min(100, value / total / 0.2 * 100)
    if name == "rem":
        value = _hours(_field(data, "rem_sleep_duration_minutes"))
        return None if value is None or not total else min(100, value / total / 0.2 * 100)
    if name == "hrv":
        value, base = _field(data, "nightly_hrv_rmssd"), (baselines.get("nightly_hrv_rmssd") or {}).get("median_value")
        return None if value is None or not base else min(100, value / base * 100)
    if name == "heart_rate":
        value, base = _field(data, "nightly_resting_hr"), (baselines.get("nightly_resting_hr") or {}).get("median_value")
        return None if value is None or not base else min(100, base / value * 100)
    if name == "respiration":
        value, base = _field(data, "respiration_rate"), (baselines.get("respiration_rate") or {}).get("median_value")
        return None if value is None or not base else min(100, base / value * 100)
    if name == "regularity":
        return SleepRegularityService.calculate_regularity(history, current=data).score
    return None


def _score_composition(data, history, baselines):
    st.subheader(TR("domain.sleep.score_composition"))
    st.caption(TR("domain.sleep.score_composition_note"))
    components = (
        ("domain.sleep.total_duration", "duration"), ("domain.sleep.deep_duration", "deep"),
        ("domain.sleep.rem_duration", "rem"), ("domain.sleep.hrv", "hrv"),
        ("domain.sleep.nightly_resting_hr", "heart_rate"), ("domain.sleep.respiration", "respiration"),
        ("domain.sleep.regularity", "regularity"),
    )
    columns = st.columns(2)
    for index, (label, name) in enumerate(components):
        score = _component_score(name, data, history, baselines)
        with columns[index % 2]:
            st.markdown(f"**{TR(label)}**")
            if score is None:
                st.caption(TR("common.no_data"))
            else:
                st.progress(max(0.0, min(1.0, score / 100)))
                st.caption(TR("domain.sleep.component_status", status=TR("domain.sleep.status_good" if score >= 75 else "domain.sleep.status_attention")))


def _trends(history):
    st.subheader(TR("domain.sleep.trends"))
    items = sorted(history[:14], key=lambda item: item["date"])
    if len(items) < 2:
        st.info(TR("domain.sleep.trends_no_data"))
        return
    dates, duration, hrv, heart_rate = [], [], [], []
    for item in items:
        dates.append(item["date"])
        duration.append(_hours(_field(item, "total_sleep_duration_minutes")))
        hrv.append(_field(item, "nightly_hrv_rmssd"))
        heart_rate.append(_field(item, "nightly_resting_hr"))
    figure = make_subplots(rows=1, cols=3, subplot_titles=[
        TR("domain.sleep.actual_duration"), TR("domain.sleep.hrv"),
        TR("domain.sleep.nightly_resting_hr"),
    ])
    for row, col, values, color in (
        (1, 1, duration, "#3aa675"), (1, 2, hrv, "#9b7bd3"),
        (1, 3, heart_rate, "#e0a02b"),
    ):
        figure.add_trace(go.Scatter(x=dates, y=values, mode="lines+markers", line=dict(color=color, width=3), connectgaps=False, showlegend=False), row=row, col=col)
    figure.update_layout(height=300, margin=dict(l=20, r=20, t=55, b=20), plot_bgcolor="white")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _raw_data(history):
    labels = {
            "sleep_start_time": "domain.sleep.bedtime", "wake_time": "domain.sleep.wake_time",
            "total_sleep_duration_minutes": "domain.sleep.total_duration", "actual_sleep_duration_minutes": "domain.sleep.actual_duration",
            "deep_sleep_duration_minutes": "domain.sleep.deep_duration", "rem_sleep_duration_minutes": "domain.sleep.rem_duration",
            "average_sleep_hr_bpm": "domain.sleep.average_hr", "nightly_hrv_rmssd": "domain.sleep.hrv",
            "nightly_resting_hr": "domain.sleep.nightly_resting_hr",
            "respiration_rate": "domain.sleep.respiration", "minimum_sleep_hr_bpm": "domain.sleep.minimum_hr",
    }
    rows = []
    for item in history:
        row = {TR("reports.date"): format_date(item["date"], LANGUAGE)}
        for field, label in labels.items():
            value = _field(item, field)
            if field in ("sleep_start_time", "wake_time"):
                value = time_to_hms(value)
            elif field.endswith("duration_minutes"):
                value = minutes_to_hms(value)
            row[TR(label)] = value
        rows.append(row)
    if rows:
        # Keep the first screen focused on the latest seven records. Older
        # records remain available by scrolling inside the table.
        centered_dataframe(rows, max_height="28rem")
    else:
        st.info(TR("common.no_data"))


def _historical_sleep_row(item):
    labels = {
        "sleep_start_time": "domain.sleep.bedtime", "wake_time": "domain.sleep.wake_time",
        "total_sleep_duration_minutes": "domain.sleep.total_duration", "actual_sleep_duration_minutes": "domain.sleep.actual_duration",
        "deep_sleep_duration_minutes": "domain.sleep.deep_duration", "rem_sleep_duration_minutes": "domain.sleep.rem_duration",
        "average_sleep_hr_bpm": "domain.sleep.average_hr", "nightly_hrv_rmssd": "domain.sleep.hrv",
        "nightly_resting_hr": "domain.sleep.nightly_resting_hr", "respiration_rate": "domain.sleep.respiration",
        "minimum_sleep_hr_bpm": "domain.sleep.minimum_hr",
    }
    row = {
        TR("reports.date"): format_date(item["date"], LANGUAGE),
        TR("domain.sleep.score"): _number(item.get("sleep_score")),
    }
    for field, label in labels.items():
        value = _field(item, field)
        if field in ("sleep_start_time", "wake_time"):
            value = time_to_hms(value)
        elif field.endswith("duration_minutes"):
            value = minutes_to_hms(value)
        else:
            value = _number(value)
        row[TR(label)] = value
    return row


def _historical_sleep_record_table(history):
    """Keep the historical record table separate and make its rows selectable."""
    title = _ui("历史睡眠记录", "Historical Sleep Records")
    with st.expander(title, expanded=False):
        if not history:
            st.info(TR("common.no_data"))
            return None
        history_dates = [item["date"] for item in history]
        selected_date = st.session_state.get("sleep_history_selected")
        if selected_date not in history_dates:
            selected_date = history_dates[0]
            st.session_state["sleep_history_selected"] = selected_date
        rows = [_historical_sleep_row(item) for item in history]
        headers = list(rows[0].keys()) + [_ui("操作", "Action")]
        widths = [1.0, .75, .95, .95, 1.05, 1.05, 1.05, 1.05, 1.05, 1.0, 1.0, 1.0, 1.0, 1.05]
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
                    _ui("查看", "View"),
                    key=f"sleep_history_view_{item['date']}",
                    use_container_width=True,
                ):
                    st.session_state["sleep_history_selected"] = item["date"]
                    st.session_state["sleep_history_details_visible"] = True
                    st.session_state["sleep_history_details_focus_nonce"] = (
                        st.session_state.get("sleep_history_details_focus_nonce", 0) + 1
                    )
                    selected_date = item["date"]
    return selected_date


@st.fragment
def _render_historical_sleep_interaction(history, persisted_baselines):
    """Rerun only the selected-history area after a table interaction."""
    history_focus_nonce = st.session_state.get("sleep_history_details_focus_nonce", 0)
    last_history_focus_nonce = st.session_state.get("sleep_history_details_last_scrolled_nonce", 0)
    should_focus_history = history_focus_nonce > last_history_focus_nonce
    _historical_sleep_situation(
        history,
        persisted_baselines,
        auto_expand=should_focus_history,
        focus_nonce=history_focus_nonce,
    )
    if should_focus_history:
        st.session_state["sleep_history_details_last_scrolled_nonce"] = history_focus_nonce


def _historical_sleep_situation(history, persisted_baselines, *, auto_expand=False, focus_nonce=0):
    """Show only the selected historical night's data and details."""
    data_title = _ui("历史睡眠数据", "Historical Sleep Data")
    details_title = _ui("历史睡眠详情", "Historical Sleep Details")

    # Historical records are the first child directory of the situation.
    selected_date = _historical_sleep_record_table(history)
    if not st.session_state.get("sleep_history_details_visible", False):
        return

    with st.expander(data_title, expanded=auto_expand):
        selected = next((item for item in history if item["date"] == selected_date), None)
        centered_dataframe([_historical_sleep_row(selected)] if selected else [])

    selected = next((item for item in history if item["date"] == selected_date), None)
    with st.expander(details_title, expanded=auto_expand):
        if not selected:
            st.info(TR("common.no_data"))
        elif not selected.get("has_observed_data"):
            st.info(TR("common.no_data"))
        else:
            # The historical table and its detail view are both Polar-only:
            # unavailable Polar fields must remain unavailable here.
            selected = get_latest_sleep(log_date=selected_date, polar_only=True) or selected
            valid_history = [item for item in history if _is_complete_sleep_record(item)]
            historical_baselines = _synchronized_sleep_baselines(
                valid_history,
                persisted_baselines,
                exclude_date=selected["date"],
            )
            _core_cards(selected, valid_history, historical_baselines, key_prefix=f"history_{selected['date']}")

    if auto_expand:
        # Use the data expander itself as the scroll target. A separate empty
        # anchor would create a visible blank row between the two sections.
        render_interaction_focus(
            components,
            target_expander_label=data_title,
            nonce=focus_nonce,
            # Keep the section header just below Streamlit's fixed toolbar.
            top_offset=80,
        )


def _sleep_baseline_text(key, value):
    if value is None:
        return TR("common.no_data")
    if key == "actual_sleep_duration":
        total_minutes = round(value)
        hours, minutes = divmod(total_minutes, 60)
        return _ui(f"{hours}小时{minutes:02d}分", f"{hours}h {minutes:02d}m")
    if key == "sleep_score":
        return _ui(f"{round(value):.0f}分", f"{round(value):.0f}")
    if key == "nightly_hrv_rmssd":
        return f"{round(value):.0f} ms"
    if key == "nightly_resting_hr":
        return f"{value:.1f} bpm"
    if key == "sleep_regularity":
        return _ui(f"{round(value):.0f}分", f"{round(value):.0f} / 100")
    return _ui(f"{value:.1f}次/分", f"{value:.1f} breaths/min")


def _sleep_baseline_range(key, summary):
    lower, upper = summary["lower"], summary["upper"]
    if lower is None or upper is None:
        return TR("common.no_data")
    return f"{_sleep_baseline_text(key, lower)}—{_sleep_baseline_text(key, upper)}"


def _comparison_text(key, summary):
    difference = summary["difference"]
    if difference is None:
        return _ui("前后周期数据不足", "Not enough data for period comparison")
    if key == "actual_sleep_duration":
        amount = round(abs(difference))
        if amount == 0:
            return _ui("近7天与前7天基本持平", "Last 7 days are level with the previous 7")
        direction = _ui("增加", "higher by") if difference > 0 else _ui("减少", "lower by")
        return _ui(f"近7天较前7天{direction}{amount}分钟", f"Last 7 days are {direction} {amount} min")
    if key == "sleep_score":
        amount = round(abs(difference))
        if amount == 0:
            return _ui("近7天与前7天基本持平", "Last 7 days are level with the previous 7")
        direction = _ui("上升", "up") if difference > 0 else _ui("下降", "down")
        return _ui(f"近7天较前7天{direction}{amount}分", f"Last 7 days are {direction} {amount} points")
    if key == "nightly_hrv_rmssd":
        amount = round(abs(summary["percent_difference"] or 0))
        direction = _ui("上升", "up") if difference > 0 else _ui("下降", "down") if difference < 0 else _ui("持平", "level")
        return _ui(f"近7天较前7天{direction}{amount}%", f"Last 7 days are {direction} {amount}%")
    if key == "nightly_resting_hr":
        amount = abs(difference)
        direction = _ui("上升", "up") if difference > 0 else _ui("下降", "down") if difference < 0 else _ui("持平", "level")
        return _ui(f"近7天较前7天{direction}{amount:.1f} bpm", f"Last 7 days are {direction} {amount:.1f} bpm")
    if key == "sleep_regularity":
        amount = round(abs(difference))
        direction = _ui("上升", "up") if difference > 0 else _ui("下降", "down") if difference < 0 else _ui("持平", "level")
        return _ui(f"近7晚规律性较前7晚{direction}{amount}分", f"Regularity over the last 7 nights is {direction} {amount} points")
    recent_14 = [value for value in summary["series"][-14:] if value is not None]
    stable = len(recent_14) >= 2 and max(recent_14) - min(recent_14) <= 1.0
    return _ui("最近两周整体稳定" if stable else "最近两周波动有所增加", "Stable overall in the last two weeks" if stable else "Variation increased in the last two weeks")


def _baseline_chart(summary, key, current_date=None, current_value=None):
    dates, values = summary["dates"], summary["series"]
    lower, upper, center = summary["lower"], summary["upper"], summary["center"]
    numeric_values = [float(value) for value in values if value is not None]
    scale_values = numeric_values + [value for value in (lower, upper, center, current_value) if value is not None]
    if not dates or not scale_values:
        return f'<div class="drc-baseline-chart-wrap"><div class="drc-sleep-card-meta">{escape(TR("common.no_data"))}</div></div>'
    width, height, left, right, top, bottom = 520, 180, 8, 8, 12, 12
    low, high = min(scale_values), max(scale_values)
    spread = max(high - low, 1.0)
    low -= spread * .1
    high += spread * .1

    def x_at(index):
        return left + index * (width - left - right) / max(1, len(dates) - 1)

    def y_at(value):
        return top + (high - float(value)) / (high - low) * (height - top - bottom)

    def path_for(indices):
        commands, started = [], False
        for index in indices:
            value = values[index]
            if value is None:
                started = False
                continue
            command = "L" if started else "M"
            commands.append(f"{command}{x_at(index):.1f},{y_at(value):.1f}")
            started = True
        return " ".join(commands)

    svg = []
    markers = []

    def marker(css_class, index, value):
        return (
            f'<span class="{css_class}" style="left:{x_at(index) / width * 100:.3f}%;'
            f'top:{y_at(value) / height * 100:.3f}%"></span>'
        )

    if lower is not None and upper is not None:
        svg.append(
            f'<path d="M{x_at(0):.1f},{y_at(upper):.1f} L{x_at(len(dates)-1):.1f},{y_at(upper):.1f} '
            f'L{x_at(len(dates)-1):.1f},{y_at(lower):.1f} L{x_at(0):.1f},{y_at(lower):.1f} Z" '
            'fill="rgba(79,127,191,.14)" />'
        )
    if center is not None:
        svg.append(f'<line x1="{x_at(0):.1f}" y1="{y_at(center):.1f}" x2="{x_at(len(dates)-1):.1f}" y2="{y_at(center):.1f}" stroke="#60718a" stroke-width="1.5" stroke-dasharray="4 3" />')
    valid_indices = [index for index, value in enumerate(values) if value is not None]
    previous_indices, recent_indices = valid_indices[-14:-7], valid_indices[-7:]
    for indices, color, width_value in ((previous_indices, "#a7b0bf", 1.8), (recent_indices, "#3979bd", 2.4)):
        path = path_for(indices)
        if path:
            svg.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{width_value}" stroke-linecap="round" stroke-linejoin="round" />')
            point_class = "drc-baseline-point--previous" if color == "#a7b0bf" else "drc-baseline-point--recent"
            markers.extend(
                marker(f"drc-baseline-point {point_class}", index, values[index])
                for index in indices
            )
    anomalies = set(summary["anomaly_dates"])
    for index, (day, value) in enumerate(zip(dates, values)):
        if value is not None and day in anomalies:
            markers.append(marker("drc-baseline-anomaly", index, value))
    if current_value is not None:
        markers.append(marker("drc-baseline-current", len(dates) - 1, current_value))
    chart = (
        '<div class="drc-sleep-baseline-plot">'
        f'<svg class="drc-sleep-baseline-chart" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" aria-label="{escape(_ui("近28天个人睡眠基线趋势", "28-day personal sleep baseline trend"))}">{"".join(svg)}</svg>'
        f'{"".join(markers)}</div>'
    )
    legend = _ui(
        '<span class="range">个人范围</span><span class="median">基线中位线</span><span>近7天</span><span class="current">当前周期</span>',
        '<span class="range">Personal range</span><span class="median">Baseline median</span><span>Last 7 days</span><span class="current">Current cycle</span>',
    )
    return f'<div class="drc-baseline-chart-wrap">{chart}{BASELINE_LEGEND_OPEN}{legend}{BASELINE_LEGEND_CLOSE}</div>'


def _summary_with_current_period(summary, current_value):
    """Use the current cycle for trend display without changing its baseline."""
    if current_value is None:
        return summary
    historical = [value for value in summary["series"] if value is not None]
    recent_values = [float(current_value), *historical[-6:]]
    previous_values = historical[-13:-6]
    result = dict(summary)
    result.update({
        "recent_average": statistics.mean(recent_values) if recent_values else None,
        "recent_median": statistics.median(recent_values) if recent_values else None,
        "previous_average": statistics.mean(previous_values) if previous_values else None,
        "previous_median": statistics.median(previous_values) if previous_values else None,
    })
    result["difference"] = (
        result["recent_average"] - result["previous_average"]
        if result["recent_average"] is not None and result["previous_average"] is not None else None
    )
    result["percent_difference"] = (
        result["difference"] / abs(result["previous_average"]) * 100
        if result["difference"] is not None and result["previous_average"] not in (None, 0) else None
    )
    return result


def _personal_baseline(data, history):
    target_date = (data or {}).get("date") or date.today().isoformat()
    regularity_points, current_regularity_score = _sleep_regularity_artifacts(history, target_date)
    fields = (
        (_ui("实际睡眠长度", "Actual Sleep Length"), _ui("近28天典型睡眠时长", "Typical sleep duration, last 28 days"), "actual_sleep_duration"),
        (_ui("睡眠评分", "Sleep Score"), _ui("近28天典型睡眠评分", "Typical sleep score, last 28 days"), "sleep_score"),
        (_ui("睡眠期间 HRV", "Sleep HRV"), _ui("睡眠 HRV 个人基线", "Personal sleep HRV baseline"), "nightly_hrv_rmssd"),
        (_ui("夜间静息心率", "Nightly Resting Heart Rate"), _ui("夜间静息心率基线", "Nightly resting HR baseline"), "nightly_resting_hr"),
        (_ui("睡眠期间呼吸速率", "Sleep Respiratory Rate"), _ui("睡眠呼吸频率基线", "Sleep respiratory-rate baseline"), "respiration_rate"),
        (_ui("睡眠规律性", "Sleep Regularity"), _ui("近28天典型规律性评分", "Typical regularity score, last 28 days"), "sleep_regularity"),
    )
    summaries = []
    for title, kicker, key in fields:
        if key == "sleep_regularity":
            points = regularity_points
        else:
            points = []
            for item in history:
                value = _sleep_history_metric(item, key)
                if value in (None, "") or (key == "respiration_rate" and float(value) <= 0):
                    continue
                points.append((item["date"], float(value)))
        summaries.append((title, kicker, key, build_sleep_baseline_summary(points, target_date)))

    st.caption(_ui(
        "基线统计严格排除当前睡眠周期；当前周期会同步显示在卡片和趋势图中。各指标独立计算，缺失日期在图中断开。",
        "Baseline statistics exclude the current sleep cycle; the current cycle is still shown in every card and trend chart. Each metric is calculated independently and missing dates remain disconnected.",
    ))
    for row_start in range(0, len(summaries), 2):
        columns = st.columns(2)
        for column, (title, kicker, key, summary) in zip(columns, summaries[row_start:row_start + 2]):
            if key == "sleep_regularity":
                current_value = current_regularity_score
            else:
                current_value = _sleep_history_metric(data, key)
            display_summary = _summary_with_current_period(summary, current_value)
            values = [value for value in summary["series"] if value is not None]
            if key == "actual_sleep_duration":
                secondary_label = _ui("近7天平均", "Last 7-day average")
                secondary_value = _sleep_baseline_text(key, display_summary["recent_average"])
                exception_label = _ui("不足6小时", "Under 6 hours")
                exception_count = sum(value < 360 for value in values)
            elif key == "sleep_score":
                secondary_label = _ui("近7天平均", "Last 7-day average")
                secondary_value = _sleep_baseline_text(key, summary["recent_average"])
                exception_label = _ui("低于60分", "Below 60")
                exception_count = sum(value < 60 for value in values)
            elif key == "nightly_hrv_rmssd":
                secondary_label = _ui("近7天中位数", "Last 7-day median")
                secondary_value = _sleep_baseline_text(key, display_summary["recent_median"])
                exception_label = _ui("低于个人范围", "Below personal range")
                exception_count = sum(value < summary["lower"] for value in values) if summary["lower"] is not None else 0
            elif key == "nightly_resting_hr":
                secondary_label = _ui("近7天中位数", "Last 7-day median")
                secondary_value = _sleep_baseline_text(key, summary["recent_median"])
                exception_label = _ui("高于个人范围", "Above personal range")
                exception_count = sum(value > summary["upper"] for value in values) if summary["upper"] is not None else 0
            elif key == "respiration_rate":
                secondary_label = _ui("近14天波动", "Last 14-day variation")
                secondary_value = _ui("稳定", "Stable") if "稳定" in _comparison_text(key, display_summary) else _ui("波动增加", "More variable")
                exception_label = _ui("超出个人范围", "Outside personal range")
                exception_count = sum(
                    value < summary["lower"] or value > summary["upper"] for value in values
                ) if summary["lower"] is not None and summary["upper"] is not None else 0
            else:
                secondary_label = _ui("近7晚平均", "Last 7-night average")
                secondary_value = _sleep_baseline_text(key, display_summary["recent_average"])
                exception_label = _ui("低于个人范围", "Below personal range")
                exception_count = sum(
                    value < summary["lower"] for value in values
                ) if summary["lower"] is not None else 0
            trend_text = _comparison_text(key, display_summary)
            with column:
                baseline_card_html = (
                    '<section class="drc-baseline-card">'
                    f'<div class="drc-baseline-card-head"><h3>{escape(title)}</h3></div>'
                    '<div class="drc-baseline-summary">'
                    f'<div class="drc-baseline-kicker">{escape(kicker)}</div>'
                    f'<div class="drc-baseline-main">{escape(_sleep_baseline_text(key, summary["center"]))}</div>'
                    '<div class="drc-baseline-grid">'
                    f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("个人常见范围", "Personal range"))}</div><div class="drc-baseline-item-value">{escape(_sleep_baseline_range(key, summary))}</div></div>'
                    f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(secondary_label)}</div><div class="drc-baseline-item-value">{escape(secondary_value)}</div></div>'
                    f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("趋势", "Trend"))}</div><div class="drc-baseline-item-value">{escape(trend_text)}</div></div>'
                    f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(exception_label)}</div><div class="drc-baseline-item-value">{exception_count} / {summary["valid_nights"]}{escape(_ui("晚", " nights"))}</div></div>'
                    f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("当前周期", "Current cycle"))}</div><div class="drc-baseline-item-value">{escape(_sleep_baseline_text(key, current_value))}</div></div>'
                    f'</div></div>{_baseline_chart(summary, key, target_date, current_value)}</section>'
                )
                st.markdown(baseline_card_html, unsafe_allow_html=True)


def main():
    intro = TR("domain.sleep.intro")
    st.title(TR("domain.sleep.title")); st.caption(intro)
    today_value = date.today().isoformat()
    latest, today_data, history, persisted_baselines = _load_sleep_page_inputs(
        _sleep_database_revision(),
        today_value,
    )
    data = today_data if today_data and today_data.get("has_observed_data") else latest
    valid_history = [item for item in history if _is_complete_sleep_record(item)]
    # The latest observed record remains visible even when some fields are
    # missing; completeness only controls eligibility for baseline statistics.
    detail_data = data if data and data.get("has_observed_data") else None
    baselines = _synchronized_sleep_baselines(
        valid_history,
        persisted_baselines,
        exclude_date=(detail_data or {}).get("date"),
    )

    today_section = _ui("今日睡眠数据", "Today's Sleep Data")
    st.subheader(today_section)
    _today_sleep_data(data)

    st.subheader(TR("domain.sleep.today_details"))
    if detail_data:
        today_detail_baseline_data = _today_detail_baselines(detail_data, valid_history)
        st.caption(_sleep_baseline_context(today_detail_baseline_data[0]))
        _core_cards(
            detail_data,
            valid_history,
            baselines,
            key_prefix="today",
            detail_baseline_data=today_detail_baseline_data,
        )
    elif latest:
        st.info(_ui(
            f"{format_date(latest['date'], LANGUAGE)} 的睡眠数据暂不可用。",
            f"Sleep data for {format_date(latest['date'], LANGUAGE)} is currently unavailable.",
        ))
    else:
        st.info(TR("domain.sleep.empty"))

    _render_historical_sleep_interaction(history, persisted_baselines)

    st.info(TR("domain.sleep.missing_notice"))
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
