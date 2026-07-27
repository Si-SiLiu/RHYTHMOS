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

from src.branding import load_page_icon
from src.dashboard_data import get_latest_local_coach
from src.db import get_current_db_path
from src.demo_sandbox import configure_demo_runtime
from src.domain_dashboard_data import get_domain_baselines, get_latest_sleep, get_sleep_history
from src.exercise_format import hours_to_hms, minutes_to_hms, time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.sleep_regularity import SleepRegularityService
from src.sleep_baseline_view import build_sleep_baseline_summary, build_sleep_regularity_points
from src.ui_tables import centered_dataframe
from src.ui_scroll import render_interaction_focus


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=get_translator(PAGE_LANGUAGE)("domain.sleep.title"),
    page_icon=load_page_icon(), layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "sleep")


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
        get_sleep_history(limit=60),
        get_domain_baselines((
            "sleep_duration", "sleep_score", "nightly_hrv_rmssd",
            "nightly_resting_hr", "respiration_rate",
        )),
    )

SLEEP_CSS = """
<style>
.drc-sleep-card{border:1px solid #d8dee9;border-radius:16px;padding:12px 14px;min-height:148px;background:#fff;box-shadow:0 2px 8px rgba(34,52,84,.06)}
.drc-sleep-card.primary{min-height:250px;height:250px;box-sizing:border-box}.drc-sleep-card h3{margin:0;color:#273248;font-size:.96rem}.drc-sleep-card .drc-sleep-card-value{font-size:2rem;margin:8px 0 2px}.drc-sleep-card.primary .drc-sleep-card-value{font-size:3.45rem}.drc-sleep-card-meta{color:#697386;font-size:.8rem;line-height:1.45;margin-top:6px}.drc-sleep-card-problem{margin-top:10px;font-size:.9rem;font-weight:650;color:#4b5565}.drc-sleep-card.good:before,.drc-sleep-card.warn:before,.drc-sleep-card.bad:before,.drc-sleep-card.neutral:before,.drc-sleep-card.info:before{content:"";display:block;height:4px;border-radius:4px;margin:-12px -14px 10px}
@media (max-width: 900px){.drc-sleep-card.primary{height:auto;min-height:250px}}
.drc-sleep-card.good{border-top:4px solid #3aa675}.drc-sleep-card.warn{border-top:4px solid #e0a02b}.drc-sleep-card.bad{border-top:4px solid #d95c5c}.drc-sleep-card.neutral{border-top:4px solid #8290a5}
.drc-sleep-card-label{font-size:.92rem;color:#697386;font-weight:650}.drc-sleep-card-value{font-size:1.75rem;font-weight:750;color:#273248;margin-top:7px}.drc-sleep-card-delta{font-size:.95rem;font-weight:650;margin-top:5px}.drc-sleep-card-status{font-size:.9rem;color:#697386;margin-top:8px}
.drc-sleep-card.metric{height:250px;box-sizing:border-box}.drc-sleep-card.good .drc-sleep-card-delta{color:#24865c}.drc-sleep-card.warn .drc-sleep-card-delta{color:#aa7415}.drc-sleep-card.bad .drc-sleep-card-delta{color:#b13f3f}.drc-sleep-card.neutral .drc-sleep-card-delta{color:#697386}
.drc-sleep-problem{border-radius:10px;padding:10px 14px;margin:5px 0;font-weight:600}.drc-sleep-problem.good{background:#eaf7f0;color:#24704f}.drc-sleep-problem.bad{background:#fff0f0;color:#a43c3c}.drc-sleep-problem.neutral{background:#f3f5f8;color:#697386}
.drc-baseline-range-label{font-size:.82rem;color:#697386;margin-top:8px}.drc-baseline-range{font-size:1.28rem;line-height:1.2;font-weight:650;color:#273248;margin:4px 0 10px;overflow-wrap:anywhere;word-break:break-word}.drc-baseline-range.compact{font-size:1.08rem;letter-spacing:-.02em}
.drc-baseline-summary{min-height:220px}.drc-baseline-kicker{font-size:.84rem;color:#697386;font-weight:650}.drc-baseline-main{font-size:1.8rem;font-weight:760;color:#273248;margin:4px 0 12px}.drc-baseline-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 16px}.drc-baseline-item{border-top:1px solid #e2e7ef;padding-top:8px}.drc-baseline-item-label{font-size:.78rem;color:#7a8699}.drc-baseline-item-value{font-size:.94rem;color:#273248;font-weight:650;margin-top:3px}
</style>
"""
st.markdown(SLEEP_CSS, unsafe_allow_html=True)


def _number(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _ui(zh, en):
    return zh if LANGUAGE != "en" else en


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


def _trend(values, tone, key):
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return
    figure = go.Figure(go.Scatter(y=values, mode="lines+markers", line=dict(color={"good":"#3aa675","warn":"#e0a02b","bad":"#d95c5c","neutral":"#8290a5"}[tone], width=2), marker=dict(size=4)))
    figure.update_layout(height=48, margin=dict(l=0,r=0,t=2,b=0), xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False}, key=key)


def _card_html(title, value, meta, status, tone, problem=None, primary=False, metric=False):
    extra = f'<div class="drc-sleep-card-problem">{escape(problem)}</div>' if problem else ""
    card_class = f"drc-sleep-card {tone}{' primary' if primary else ''}{' metric' if metric else ''}"
    return f'<div class="{card_class}"><h3>{escape(title)}</h3><div class="drc-sleep-card-value">{escape(value)}</div><div class="drc-sleep-card-status">{escape(status)}</div><div class="drc-sleep-card-meta">{meta}</div>{extra}</div>'


def _core_cards(data, history, baselines, key_prefix="sleep"):
    values = _today_sleep_values(data)
    score = values["score"]
    score_tone, score_status = _status(score)
    actual = values["actual_duration_minutes"]
    hrv = values["hrv"]
    resting = values["resting_hr"]
    duration_base = _actual_sleep_baseline_minutes(history, exclude_date=values["date"])
    score_base = (baselines.get("sleep_score") or {}).get("median_value")
    hrv_base = (baselines.get("nightly_hrv_rmssd") or {}).get("median_value")
    hr_base = (baselines.get("nightly_resting_hr") or {}).get("median_value")
    duration_tone, duration_status = _metric_state(actual, duration_base, True, 4)
    hrv_tone, hrv_status = _metric_state(hrv, hrv_base, True, 5)
    hr_tone, hr_status = _metric_state(resting, hr_base, False, 5)
    issues = []
    if actual is not None and actual < 7 * 60: issues.append(_ui("睡眠时间不足", "Insufficient sleep duration"))
    if hrv is not None and hrv_base and hrv < hrv_base * .95: issues.append(_ui("HRV略低", "HRV is slightly low"))
    problem = (_ui("、", "; ")).join(issues[:2]) or _ui("暂无主要问题", "No major issue detected")
    score_summary = _ui(f"主要问题：{problem}", f"Main observation: {problem}")
    score_meta = _ui(
        f"个人基线：{_number(score_base)} · 差值：{_difference_with_percent(score, score_base)}",
        f"Personal baseline: {_number(score_base)} · Difference: {_difference_with_percent(score, score_base)}",
    )
    cards = [
        (_ui("睡眠综合评分", "Sleep Composite Score"), _number(score), score_meta, score_status, score_tone, [_today_sleep_values(item)["score"] for item in history[:7]], score_summary, True),
        (_ui("实际睡眠时长", "Actual Sleep Duration"), _duration_hms(actual), _ui(f"个人基线：{_duration_hms(duration_base)} · 差值：{_difference_with_percent(actual, duration_base, duration=True)}", f"Personal baseline: {_duration_hms(duration_base)} · Difference: {_difference_with_percent(actual, duration_base, duration=True)}"), duration_status, duration_tone, [_field(x,"actual_sleep_duration_minutes") for x in history[:7]], None, False),
        (_ui("睡眠期间 HRV", "Sleep HRV"), _number(hrv," ms"), _ui(f"基线中心：{_number(hrv_base,' ms')} · 差值：{_difference_with_percent(hrv, hrv_base, ' ms')}", f"Baseline center: {_number(hrv_base,' ms')} · Difference: {_difference_with_percent(hrv, hrv_base, ' ms')}"), hrv_status, hrv_tone, [_field(x,"nightly_hrv_rmssd") for x in history[:7]], None, False),
        (_ui("夜间静息心率", "Nightly Resting Heart Rate"), _number(resting," bpm"), _ui(f"个人基线：{_number(hr_base,' bpm')} · 差值：{_difference_with_percent(resting, hr_base, ' bpm')}", f"Personal baseline: {_number(hr_base,' bpm')} · Difference: {_difference_with_percent(resting, hr_base, ' bpm')}"), hr_status, hr_tone, [_field(x,"nightly_resting_hr") for x in history[:7]], None, False),
    ]
    cols = st.columns(2)
    for index, (col, card) in enumerate(zip(cols * 2, cards)):
        with col:
            st.markdown(_card_html(*card[:5], problem=card[6], primary=card[7], metric=True), unsafe_allow_html=True)
            _trend(card[5], card[4], key=f"{key_prefix}_trend_{index}")
    baseline_records = [v for v in baselines.values() if v]
    valid = max([int(v.get("valid_days") or 0) for v in baseline_records], default=0)
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
    title = "历史睡眠数据" if LANGUAGE != "en" else "Historical Sleep Data"
    st.subheader(title)
    if not history:
        st.info(TR("common.no_data"))
        return None
    history_dates = [item["date"] for item in history]
    selected_date = st.session_state.get("sleep_history_selected")
    if selected_date not in history_dates:
        selected_date = history_dates[0]
        st.session_state["sleep_history_selected"] = selected_date
    rows = [_historical_sleep_row(item) for item in history]
    headers = list(rows[0].keys()) + ["操作" if LANGUAGE != "en" else "Action"]
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
                "查看" if LANGUAGE != "en" else "View",
                key=f"sleep_history_view_{item['date']}",
                use_container_width=True,
            ):
                st.session_state["sleep_history_selected"] = item["date"]
                st.session_state["sleep_history_details_focus_nonce"] = (
                    st.session_state.get("sleep_history_details_focus_nonce", 0) + 1
                )
                selected_date = item["date"]
    return selected_date


@st.fragment
def _render_historical_sleep_interaction(history, persisted_baselines):
    """Rerun only the selected-history area after a table interaction."""
    _render_historical_sleep_interaction(history, persisted_baselines)


def _historical_sleep_situation(history, selected_date, persisted_baselines, *, auto_expand=False, focus_nonce=0):
    """Show only the selected historical night's data and details."""
    situation_title = "历史睡眠情况" if LANGUAGE != "en" else "Historical Sleep Situation"
    data_title = "历史睡眠数据" if LANGUAGE != "en" else "Historical Sleep Data"
    details_title = "历史睡眠详情" if LANGUAGE != "en" else "Historical Sleep Details"
    focus_target_id = "sleep-history-details-focus-target"
    focus_anchor = f'<div id="{focus_target_id}"></div>'
    st.markdown(focus_anchor, unsafe_allow_html=True)
    st.subheader(situation_title)

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
            valid_history = [item for item in history if _is_complete_sleep_record(item)]
            historical_baselines = _synchronized_sleep_baselines(
                valid_history,
                persisted_baselines,
                exclude_date=selected["date"],
            )
            _core_cards(selected, valid_history, historical_baselines, key_prefix=f"history_{selected['date']}")

    if auto_expand:
        render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)


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
    figure = go.Figure()
    if lower is not None and upper is not None:
        figure.add_trace(go.Scatter(
            x=dates, y=[upper] * len(dates), mode="lines", line=dict(width=0),
            hoverinfo="skip", showlegend=False,
        ))
        figure.add_trace(go.Scatter(
            x=dates, y=[lower] * len(dates), mode="lines", line=dict(width=0),
            fill="tonexty", fillcolor="rgba(79,127,191,.14)",
            name=_ui("个人常见范围", "Personal range"), hoverinfo="skip",
        ))
    if center is not None:
        figure.add_trace(go.Scatter(
            x=dates, y=[center] * len(dates), mode="lines",
            line=dict(color="#60718a", width=1.5, dash="dash"),
            name=_ui("基线中位线", "Baseline median"), hoverinfo="skip",
        ))
    valid_indices = [index for index, value in enumerate(values) if value is not None]
    recent_indices = set(valid_indices[-7:])
    previous_indices = set(valid_indices[-14:-7])
    previous = [value if index in previous_indices else None for index, value in enumerate(values)]
    recent = [value if index in recent_indices else None for index, value in enumerate(values)]
    figure.add_trace(go.Scatter(
        x=dates, y=previous, mode="lines+markers", connectgaps=False,
        line=dict(color="#a7b0bf", width=2), marker=dict(size=4),
        name=_ui("前7天", "Previous 7 days"),
    ))
    figure.add_trace(go.Scatter(
        x=dates, y=recent, mode="lines+markers", connectgaps=False,
        line=dict(color="#3979bd", width=2.5), marker=dict(size=5),
        name=_ui("近7天", "Last 7 days"),
    ))
    anomaly_x, anomaly_y = zip(*[
        (day, value) for day, value in zip(dates, values)
        if day in summary["anomaly_dates"]
    ]) if summary["anomaly_dates"] else ([], [])
    figure.add_trace(go.Scatter(
        x=anomaly_x, y=anomaly_y, mode="markers",
        marker=dict(size=8, color="#d95c5c", symbol="circle-open", line=dict(width=2)),
        name=_ui("异常点", "Outlier"),
    ))
    if current_date and current_value is not None:
        figure.add_trace(go.Scatter(
            x=[current_date], y=[current_value], mode="markers",
            marker=dict(size=10, color="#2f9d63", symbol="diamond", line=dict(width=1, color="#ffffff")),
            name=_ui("当前周期", "Current cycle"),
        ))
    figure.update_layout(
        height=210, margin=dict(l=8, r=8, t=18, b=30),
        xaxis=dict(showgrid=False, tickformat="%m-%d", nticks=6),
        yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,.12)", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=10)),
        hovermode="x unified", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displayModeBar": False},
        key=f"sleep_baseline_chart_{key}",
    )


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
            points = build_sleep_regularity_points(history, target_date)
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
                current_value = SleepRegularityService.calculate_regularity(history).score
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
                with st.container(border=True):
                    st.markdown(f"#### {escape(title)}")
                    baseline_card_html = (
                        '<div class="drc-baseline-summary">'
                        f'<div class="drc-baseline-kicker">{escape(kicker)}</div>'
                        f'<div class="drc-baseline-main">{escape(_sleep_baseline_text(key, summary["center"]))}</div>'
                        '<div class="drc-baseline-grid">'
                        f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("个人常见范围", "Personal range"))}</div><div class="drc-baseline-item-value">{escape(_sleep_baseline_range(key, summary))}</div></div>'
                        f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(secondary_label)}</div><div class="drc-baseline-item-value">{escape(secondary_value)}</div></div>'
                        f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("趋势", "Trend"))}</div><div class="drc-baseline-item-value">{escape(trend_text)}</div></div>'
                        f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(exception_label)}</div><div class="drc-baseline-item-value">{exception_count} / {summary["valid_nights"]}{escape(_ui("晚", " nights"))}</div></div>'
                        f'<div class="drc-baseline-item"><div class="drc-baseline-item-label">{escape(_ui("当前周期", "Current cycle"))}</div><div class="drc-baseline-item-value">{escape(_sleep_baseline_text(key, current_value))}</div></div>'
                        '</div></div>'
                    )
                    st.markdown(baseline_card_html, unsafe_allow_html=True)
                    _baseline_chart(summary, key, target_date, current_value)


def main():
    intro = TR("domain.sleep.intro")
    intro = intro.replace("确定性建议", "睡眠建议").replace("deterministic guidance", "sleep guidance")
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

    today_section = "今日睡眠数据" if LANGUAGE != "en" else "Today's Sleep Data"
    st.subheader(today_section)
    _today_sleep_data(data)

    st.subheader(TR("domain.sleep.today_details"))
    if detail_data:
        _core_cards(detail_data, valid_history, baselines, key_prefix="today")
    elif latest:
        st.info(_ui(
            f"{format_date(latest['date'], LANGUAGE)} 的睡眠数据暂不可用。",
            f"Sleep data for {format_date(latest['date'], LANGUAGE)} is currently unavailable.",
        ))
    else:
        st.info(TR("domain.sleep.empty"))

    selected_history_date = _historical_sleep_record_table(history)
    history_focus_nonce = st.session_state.get("sleep_history_details_focus_nonce", 0)
    last_history_focus_nonce = st.session_state.get("sleep_history_details_last_scrolled_nonce", 0)
    should_focus_history = history_focus_nonce > last_history_focus_nonce
    _historical_sleep_situation(
        history,
        selected_history_date,
        persisted_baselines,
        auto_expand=should_focus_history,
        focus_nonce=history_focus_nonce,
    )
    if should_focus_history:
        st.session_state["sleep_history_details_last_scrolled_nonce"] = history_focus_nonce

    st.subheader("个人睡眠基线" if LANGUAGE != "en" else "Personal Sleep Baseline")
    _personal_baseline(detail_data, history)

    st.info(TR("domain.sleep.missing_notice"))
    st.subheader("睡眠建议" if LANGUAGE != "en" else "Sleep Guidance")
    coach = get_latest_local_coach()
    if not coach:
        st.info(TR("local_coach.missing"))
    else:
        priority = coach["sleep_advice"].get("sleep_priority")
        code = {"high": "prioritize_sleep", "elevated": "insufficient_data", "normal": "maintain_schedule"}.get(priority, "insufficient_data")
        st.success(TR(f"local_coach.sleep_advice.{code}"))
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
