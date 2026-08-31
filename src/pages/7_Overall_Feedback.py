"""Cross-domain daily feedback, grounded in locally stored RHYTHMOS data."""

import csv
import io
import sys
import sqlite3
from datetime import date, timedelta
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from html import escape

import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.ai_feedback import AIFeedbackError, generate_feedback_for_date
from src.dashboard_data import (
    connect_readonly,
    get_day_metrics,
    get_kubios_advanced_metrics,
    get_latest_ai_feedback,
    get_latest_local_coach,
)
from src.db import get_current_db_path
from src.demo_sandbox import configure_demo_runtime
from src.domain_dashboard_data import (
    get_latest_recovery,
    get_latest_sleep,
)
from src.exercise_format import minutes_to_hms, time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.traditional import traditionalize
from src.i18n.ui import current_language, render_sidebar
from src.nutrition_logging import list_meal_records
from src.nutrition_logging.feedback import NutritionFeedbackService
from src.recovery_metrics_table import recovery_metrics_table_row
from src.training_logging import list_training_sessions
from src.ui_controls import render_manual_input_styles
from src.ui_tables import centered_dataframe


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("navigation.feedback")),
    page_icon=load_page_icon(),
    layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "feedback")
render_manual_input_styles(st)


def _ui(zh: str, en: str) -> str:
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


def _value(value, suffix="") -> str:
    if value in (None, ""):
        return TR("common.no_data")
    return f"{format_number(value, LANGUAGE)}{suffix}"


def _completion(value) -> str:
    if value in (None, ""):
        return TR("common.no_data")
    percent = float(value) * 100 if float(value) <= 1 else float(value)
    return f"{format_number(percent, LANGUAGE)}%"


def _card(title: str, value: str, detail: str, *, status="neutral") -> None:
    st.markdown(
        "<section class='rh-feedback-card rh-feedback-card--%s'>"
        "<div class='rh-feedback-card-title'>%s</div>"
        "<div class='rh-feedback-card-value'>%s</div>"
        "<div class='rh-feedback-card-detail'>%s</div>"
        "</section>" % (status, escape(title), escape(value), escape(detail)),
        unsafe_allow_html=True,
    )


def _advice_card(title: str, advice: str, *, status="neutral") -> None:
    st.markdown(
        "<section class='rh-feedback-advice rh-feedback-advice--%s'>"
        "<div class='rh-feedback-advice-title'>%s</div>"
        "<p>%s</p>"
        "</section>" % (status, escape(title), escape(advice)),
        unsafe_allow_html=True,
    )


def _domain_card(title: str, commentary: str, suggestion: str, *, status="neutral") -> None:
    st.markdown(
        "<section class='rh-feedback-advice rh-feedback-domain rh-feedback-domain--%s'>"
        "<div class='rh-feedback-advice-title'>%s</div>"
        "<p>%s</p><p class='rh-feedback-domain-suggestion'>%s</p>"
        "</section>" % (status, escape(title), escape(commentary), escape(suggestion)),
        unsafe_allow_html=True,
    )


def _domain_label(domain: str) -> str:
    return {
        "sleep": _ui("睡眠", "Sleep"),
        "recovery": _ui("恢复", "Recovery"),
        "training": _ui("训练", "Training"),
        "nutrition": _ui("营养", "Nutrition"),
    }.get(domain, domain)


FEEDBACK_CSS = """
<style>
.rh-feedback-card,.rh-feedback-advice{box-sizing:border-box;border:1px solid var(--rh-border-subtle);border-radius:var(--rh-radius-standard);background:var(--rh-surface-inset);color:var(--rh-text)}
.rh-feedback-card{min-height:10.75rem;padding:1.15rem 1.2rem}.rh-feedback-card-title,.rh-feedback-advice-title{color:var(--rh-text-secondary);font-size:.875rem;font-weight:600;line-height:1.4}.rh-feedback-card-value{margin-top:1.15rem;color:var(--rh-text);font-size:2.05rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.02em;line-height:1.1}.rh-feedback-card-detail{margin-top:.8rem;color:var(--rh-text-muted);font-size:.8125rem;line-height:1.5}.rh-feedback-card--positive{border-color:var(--rh-status-positive-surface)}.rh-feedback-card--caution{border-color:var(--rh-status-caution-surface)}.rh-feedback-card--negative{border-color:var(--rh-status-negative-surface)}
.rh-feedback-summary{border-left:3px solid var(--rh-accent,#3979bd);border-radius:0 var(--rh-radius-standard) var(--rh-radius-standard) 0;background:var(--rh-surface-inset);padding:1rem 1.15rem;margin:.25rem 0 1.5rem}.rh-feedback-summary-label{color:var(--rh-text-secondary);font-size:.8125rem;font-weight:600}.rh-feedback-summary p{margin:.45rem 0 0;color:var(--rh-text);font-size:1rem;line-height:1.65}
.rh-feedback-advice{min-height:10.5rem;padding:1.05rem 1.15rem;margin-bottom:1rem}.rh-feedback-advice p{margin:.8rem 0 0;color:var(--rh-text);font-size:.9375rem;line-height:1.62}.rh-feedback-advice--positive{border-color:var(--rh-status-positive-surface)}.rh-feedback-advice--caution{border-color:var(--rh-status-caution-surface)}.rh-feedback-advice--negative{border-color:var(--rh-status-negative-surface)}
.rh-feedback-domain{min-height:12.5rem;padding:1.05rem 1.15rem;margin-bottom:1rem}.rh-feedback-domain p{margin:.75rem 0 0;color:var(--rh-text);font-size:.9375rem;line-height:1.62}.rh-feedback-domain-suggestion{color:var(--rh-text-secondary)!important;font-size:.875rem!important}.rh-feedback-domain--positive{border-color:var(--rh-status-positive-surface)}.rh-feedback-domain--caution{border-color:var(--rh-status-caution-surface)}.rh-feedback-domain--neutral,.rh-feedback-domain--insufficient{border-color:var(--rh-border-subtle)}
[class*="st-key-feedback_history_toggle"] button{justify-content:flex-start!important;text-align:left!important;padding:.25rem .75rem!important}[class*="st-key-feedback_history_toggle"] button>div{width:100%!important;justify-content:flex-start!important}[class*="st-key-feedback_history_toggle"] button>div>span[data-has-shortcut]{display:flex!important;align-items:center!important;justify-content:flex-start!important;width:100%!important;gap:.45rem!important}[class*="st-key-feedback_history_toggle"] button>div>span[data-has-shortcut]>[data-testid="stMarkdownContainer"]{width:auto!important;margin:0!important;text-align:left!important}[class*="st-key-feedback_history_toggle"] button p{margin:0!important;text-align:left!important;font-weight:600!important;line-height:1.4!important}
@media (max-width:760px){.rh-feedback-card{min-height:0;margin-bottom:.75rem}.rh-feedback-card-value{font-size:1.8rem}.rh-feedback-advice{min-height:0}}
</style>
"""


def _status_for_recovery(recovery) -> str:
    score = (recovery or {}).get("recovery_score")
    if score is None:
        return "neutral"
    return "positive" if score >= 75 else "caution" if score >= 50 else "negative"


def _status_for_sleep(sleep) -> str:
    score = (sleep or {}).get("sleep_score")
    if score is None:
        return "neutral"
    return "positive" if score >= 75 else "caution" if score >= 50 else "negative"


def _render_codex_feedback(feedback: dict) -> None:
    st.subheader(_ui("Codex 综合反馈", "Codex comprehensive feedback"))
    st.markdown(
        "<section class='rh-feedback-summary'><div class='rh-feedback-summary-label'>%s</div><p>%s</p></section>"
        % (
            escape(_ui("综合评论", "Overall comment")),
            escape(str(feedback.get("summary") or TR("common.no_data"))),
        ),
        unsafe_allow_html=True,
    )
    st.markdown("##### " + _ui("四维反馈与今日行动", "Four-domain feedback and today's actions"))
    st.caption(_ui(
        "每个维度先说明当前判断，再给出今天可执行的建议。",
        "Each domain pairs its current assessment with an action for today.",
    ))
    items = {str(item.get("domain")): item for item in feedback.get("domain_feedback") or []}
    columns = st.columns(2)
    for index, domain in enumerate(("recovery", "sleep", "training", "nutrition")):
        item = items.get(domain) or {}
        with columns[index % 2]:
            _domain_card(
                _domain_label(domain),
                str(item.get("commentary") or _ui("暂无足够数据形成个体化说明。", "Not enough data for an individualized explanation.")),
                _ui("今日行动：", "Today's action: ") + str(
                    item.get("suggestion") or _ui("继续记录后再查看。", "Continue logging and review again.")
                ),
                status=str(item.get("status") or "insufficient"),
            )
    limitations = feedback.get("limitations") or []
    if limitations:
        st.warning(_ui("Codex 数据局限：", "Codex data limitations: ") + " ".join(map(str, limitations)))
def _today_nutrition_snapshot(today_value: str) -> dict:
    """Use the same meal records and day rollup as the Nutrition page."""
    connection = connect_readonly()
    try:
        records = list_meal_records(connection, limit=200)
        summary = NutritionFeedbackService(records, today_value, LANGUAGE).today_summary()
        food_count = summary.get("food_count") or 0
        summary["data_completeness"] = (
            round((summary.get("identified_food_count") or 0) / food_count, 4)
            if food_count else None
        )
        return {
            "date": today_value,
            "summary": summary,
            "energy": _nutrition_energy_values(records, today_value),
        }
    except sqlite3.Error:
        # A partial or pre-migration database should leave this card empty,
        # matching the Nutrition page's no-data state rather than guessing.
        return {"date": today_value, "summary": {}}
    finally:
        connection.close()


def _nutrition_energy_values(records: list[dict], day: str) -> dict:
    """Mirror the Today's Nutrition Data energy-balance calculation exactly."""
    metrics = get_day_metrics(day) or {}
    # Missing calories are unknown, not zero.  Do not turn an empty intake
    # into an artificial calorie gap just because expenditure is available.
    intake_values = []
    for record in records:
        if record.get("date") != day:
            continue
        value = (record.get("summary") or {}).get("calories_kcal")
        if value in (None, ""):
            continue
        try:
            intake_values.append(float(value))
        except (TypeError, ValueError):
            continue
    intake = sum(intake_values) if intake_values else None
    total_expenditure = metrics.get("calories")
    active_expenditure = metrics.get("active_calories")
    try:
        resting_expenditure = (
            float(total_expenditure) - float(active_expenditure)
            if total_expenditure not in (None, "") and active_expenditure not in (None, "")
            else None
        )
    except (TypeError, ValueError):
        resting_expenditure = None
    if resting_expenditure is not None and resting_expenditure < 0:
        resting_expenditure = None
    try:
        calorie_balance = (
            float(total_expenditure) - intake
            if total_expenditure not in (None, "") and intake is not None
            else None
        )
    except (TypeError, ValueError):
        calorie_balance = None
    return {
        "intake": intake,
        "training_calories": metrics.get("training_calories"),
        "resting_expenditure": resting_expenditure,
        "active_expenditure": active_expenditure,
        "total_expenditure": total_expenditure,
        "calorie_surplus": (
            "N/A" if intake is None
            else f"{abs(calorie_balance):.2f}"
            if calorie_balance is not None and calorie_balance < 0 else "—"
        ),
        "calorie_gap": (
            "N/A" if intake is None
            else f"{calorie_balance:.2f}"
            if calorie_balance is not None and calorie_balance > 0 else "—"
        ),
    }


@st.cache_data(show_spinner=False, ttl=30)
def _available_feedback_dates(*, before_date: str) -> list[str]:
    """Return past dates that contain at least one feedback data source."""
    connection = connect_readonly()
    try:
        rows = connection.execute(
            """SELECT DISTINCT log_date FROM (
                   SELECT date AS log_date FROM daily_recovery_metrics
                    WHERE sleep_duration IS NOT NULL OR sleep_score IS NOT NULL
                       OR nightly_hrv_rmssd IS NOT NULL OR nightly_resting_hr IS NOT NULL
                       OR respiration_rate IS NOT NULL OR morning_rmssd IS NOT NULL
                       OR morning_mean_hr IS NOT NULL
                   UNION SELECT date FROM polar_sleep_raw
                   UNION SELECT date FROM polar_nightly_recharge_raw
                   UNION SELECT sleep_date FROM manual_sleep_logs
                   UNION SELECT date FROM kubios_morning_hrv_raw
                   UNION SELECT date FROM manual_recovery_logs
                   UNION SELECT date FROM polar_training_sessions_raw
                   UNION SELECT date FROM manual_activity_sessions
                    WHERE start_time IS NOT NULL OR end_time IS NOT NULL
                       OR duration_minutes IS NOT NULL OR activity_type IS NOT NULL
                       OR activity_name IS NOT NULL OR average_hr_bpm IS NOT NULL
                       OR max_hr_bpm IS NOT NULL OR calories_kcal IS NOT NULL
                   UNION SELECT date FROM meal_records
                    WHERE deleted_at IS NULL AND status = 'completed'
               ) WHERE log_date IS NOT NULL AND log_date < ?
               ORDER BY log_date DESC""",
            (before_date,),
        ).fetchall()
        return [str(row[0]) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _training_data_for_date(log_date: str) -> dict | None:
    """Use the exact Polar-session projection displayed by Today's Training Data."""
    connection = connect_readonly()
    try:
        sessions = list_training_sessions(connection, limit=100)
        polar_sessions = [
            item for item in sessions
            if item.get("date") == log_date and item.get("polar_external_id")
        ]
    except sqlite3.Error:
        return None
    finally:
        connection.close()

    if not polar_sessions:
        return None
    durations = [item["duration_seconds"] for item in polar_sessions if item.get("duration_seconds") is not None]
    calories = [item["calories"] for item in polar_sessions if item.get("calories") is not None]
    average_hrs = [item["average_hr"] for item in polar_sessions if item.get("average_hr") is not None]
    maximum_hrs = [item["max_hr"] for item in polar_sessions if item.get("max_hr") is not None]
    distances = [item["distance_meters"] for item in polar_sessions if item.get("distance_meters") is not None]
    start_times = sorted(item.get("start_time") for item in polar_sessions if item.get("start_time"))
    sports = [
        str(item.get("sport_display") or item.get("polar_sport_display") or "")
        for item in polar_sessions
    ]
    return {
        "date": log_date,
        "sessions": polar_sessions,
        "sports": list(dict.fromkeys(sport for sport in sports if sport)),
        "start_time": start_times[0] if start_times else None,
        "duration_minutes": sum(durations) / 60 if durations else None,
        "average_hr_bpm": round(sum(average_hrs) / len(average_hrs)) if average_hrs else None,
        "maximum_hr_bpm": max(maximum_hrs) if maximum_hrs else None,
        "calories": sum(calories) if calories else None,
        "distance_meters": sum(distances) if distances else None,
    }


def _resolved_value(data: dict | None, field_name: str):
    """Return a source-resolved domain value without duplicating page logic."""
    return ((data or {}).get("resolved_fields") or {}).get(field_name, {}).get("value")


def _table_value(value, formatter=None) -> str:
    if value in (None, ""):
        return TR("common.no_data")
    return formatter(value) if formatter else _value(value)


def _today_feedback_tables(today_value: str, *, sleep: dict | None,
                           nutrition: dict, recovery: dict | None,
                           training: dict | None, recovery_metrics: dict | None = None,
                           include_date: bool = True) -> list[tuple[str, str, list[str], list[dict]]]:
    """Build one compact horizontal table for each data domain."""
    def table(title, filename_part, columns):
        headers = [label for label, _ in columns]
        return title, filename_part, headers, [{label: value for label, value in columns}]

    def date_column(value: str) -> tuple[tuple[str, str], ...]:
        return ((_ui("日期", "Date"), format_date(value, LANGUAGE)),) if include_date else ()

    sleep_date = (sleep or {}).get("date") if (sleep or {}).get("has_observed_data") else today_value
    sleep_table = table(_ui("睡眠数据", "Sleep data"), "sleep", date_column(sleep_date) + (
        (TR("domain.sleep.score"), _table_value((sleep or {}).get("sleep_score"))),
        (TR("domain.sleep.bedtime"), _table_value(_resolved_value(sleep, "sleep_start_time"), time_to_hms)),
        (TR("domain.sleep.wake_time"), _table_value(_resolved_value(sleep, "wake_time"), time_to_hms)),
        (TR("domain.sleep.total_duration"), _table_value(_resolved_value(sleep, "total_sleep_duration_minutes"), minutes_to_hms)),
        (TR("domain.sleep.actual_duration"), _table_value(_resolved_value(sleep, "actual_sleep_duration_minutes"), minutes_to_hms)),
        (TR("domain.sleep.deep_duration"), _table_value(_resolved_value(sleep, "deep_sleep_duration_minutes"), minutes_to_hms)),
        (TR("domain.sleep.rem_duration"), _table_value(_resolved_value(sleep, "rem_sleep_duration_minutes"), minutes_to_hms)),
        (TR("domain.sleep.average_hr"), _table_value(_resolved_value(sleep, "average_sleep_hr_bpm"))),
        (TR("domain.sleep.hrv"), _table_value(_resolved_value(sleep, "nightly_hrv_rmssd"))),
        (TR("domain.sleep.nightly_resting_hr"), _table_value(_resolved_value(sleep, "nightly_resting_hr"))),
        (TR("domain.sleep.respiration"), _table_value(_resolved_value(sleep, "respiration_rate"))),
        (TR("domain.sleep.minimum_hr"), _table_value(_resolved_value(sleep, "minimum_sleep_hr_bpm"))),
    ))

    nutrition_energy = nutrition.get("energy") or {}
    nutrition_table = table(_ui("营养数据", "Nutrition data"), "nutrition", date_column(nutrition.get("date") or today_value) + (
        (_ui("摄入热量总值（kcal）", "Total Intake (kcal)"), _table_value(nutrition_energy.get("intake"))),
        (_ui("运动消耗（kcal）", "Training Expenditure (kcal)"), _table_value(nutrition_energy.get("training_calories"))),
        (_ui("静息消耗估计（kcal）", "Estimated Resting Expenditure (kcal)"), _table_value(nutrition_energy.get("resting_expenditure"))),
        (_ui("活动消耗（kcal）", "Active Expenditure (kcal)"), _table_value(nutrition_energy.get("active_expenditure"))),
        (_ui("总消耗（kcal）", "Total Expenditure (kcal)"), _table_value(nutrition_energy.get("total_expenditure"))),
        (_ui("热量盈余（kcal）", "Calorie Surplus (kcal)"), nutrition_energy.get("calorie_surplus") or "—"),
        (_ui("热量缺口（kcal）", "Calorie Gap (kcal)"), nutrition_energy.get("calorie_gap") or "—"),
    ))

    advanced = recovery_metrics or {}

    def advanced_value(name, fallback=None):
        value = advanced.get(name)
        return fallback if value in (None, "") else value

    recovery_row = recovery_metrics_table_row(
        (recovery or {}).get("date") or today_value,
        {
            "morning_rmssd": advanced_value("rmssd_ms", (recovery or {}).get("morning_rmssd")),
            "morning_mean_hr": advanced_value("mean_hr_bpm", (recovery or {}).get("morning_mean_hr")),
            "pns_index": advanced_value("pns_index"),
            "sns_index": advanced_value("sns_index"),
            "physiological_age": advanced_value("physiological_age"),
            "mean_rr_ms": advanced_value("mean_rr_ms"),
            "sdnn_ms": advanced_value("sdnn_ms"),
            "poincare_sd1_ms": advanced_value("poincare_sd1_ms"),
            "poincare_sd2_ms": advanced_value("poincare_sd2_ms"),
            "stress_index": advanced_value("stress_index", (recovery or {}).get("stress_index")),
            "respiratory_rate": advanced_value("respiratory_rate_bpm", (recovery or {}).get("respiratory_rate")),
            "lf_power_ms2": advanced_value("lf_power_ms2"),
            "hf_power_ms2": advanced_value("hf_power_ms2"),
            "lf_power_nu": advanced_value("lf_power_nu"),
            "hf_power_nu": advanced_value("hf_power_nu"),
            "lf_hf_ratio": advanced_value("lf_hf_ratio"),
            "measurement_quality": advanced_value("measurement_quality", (recovery or {}).get("measurement_quality")),
        },
        tr=TR, language=LANGUAGE, format_date=format_date, ui=_ui,
    )
    recovery_table = (
        _ui("恢复数据", "Recovery data"), "recovery",
        list(recovery_row), [recovery_row],
    )

    training_sessions = (training or {}).get("sessions") or []
    training_table = table(_ui("训练数据", "Training data"), "training", date_column((training or {}).get("date") or today_value) + (
        (TR("training_logging.today_count"), _table_value(len(training_sessions) if training_sessions else None)),
        (TR("training_logging.start_time"), _table_value((training or {}).get("start_time"), time_to_hms)),
        (TR("training_logging.today_duration"), _table_value((training or {}).get("duration_minutes"), minutes_to_hms)),
        (TR("training_logging.today_average_hr"), _table_value((training or {}).get("average_hr_bpm"))),
        (TR("training_logging.today_max_hr"), _table_value((training or {}).get("maximum_hr_bpm"))),
        (TR("training_logging.today_calories"), _table_value((training or {}).get("calories"))),
        (TR("training_logging.today_distance"), _table_value((training or {}).get("distance_meters"))),
    ))
    return [sleep_table, nutrition_table, recovery_table, training_table]


def _feedback_csv(headers: list[str], rows: list[dict]) -> bytes:
    """Export exactly the visible rows with a BOM for spreadsheet compatibility."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


@st.cache_data(show_spinner=False, ttl=30)
def _feedback_tables_for_date(log_date: str, *, today_value: str) -> list[tuple[str, str, list[str], list[dict]]]:
    """Load all four domains for one date using their page-aligned sources."""
    sleep = get_latest_sleep(log_date=log_date)
    return _today_feedback_tables(
        log_date,
        sleep=sleep,
        nutrition=_today_nutrition_snapshot(log_date),
        recovery=get_latest_recovery(log_date=log_date),
        training=_training_data_for_date(log_date),
        recovery_metrics=(get_kubios_advanced_metrics(limit=1, date_value=log_date) or [{}])[0],
    )


@st.cache_data(show_spinner=False, ttl=30)
def _range_feedback_export(
    days: int,
    *,
    today_value: str,
    selected_types: set[str],
) -> tuple[list[str], list[dict]]:
    """Build one CSV payload for the latest calendar range, including today."""
    end = date.fromisoformat(today_value)
    start = end - timedelta(days=days - 1)
    available_dates = set(_available_feedback_dates(
        before_date=(end + timedelta(days=1)).isoformat(),
    ))
    range_tables = []
    for offset in range(days):
        log_date = (start + timedelta(days=offset)).isoformat()
        if log_date == today_value or log_date in available_dates:
            range_tables.extend(_feedback_tables_for_date(log_date, today_value=today_value))
    return _combined_feedback_export(range_tables, selected_types)


def _combined_feedback_export(tables: list[tuple[str, str, list[str], list[dict]]],
                              selected_types: set[str]) -> tuple[list[str], list[dict]]:
    """Return one rectangular CSV payload for all or selected horizontal tables."""
    category_header = _ui("数据类别", "Data category")
    headers = [category_header]
    rows = []
    for title, filename_part, table_headers, table_rows in tables:
        if filename_part not in selected_types:
            continue
        for header in table_headers:
            if header not in headers:
                headers.append(header)
        for table_row in table_rows:
            rows.append({category_header: title, **table_row})
    return headers, rows


def _render_feedback_tables(tables: list[tuple[str, str, list[str], list[dict]]]) -> None:
    """Display each domain as one centered, horizontal table in a shared panel."""
    with st.container(border=True):
        for title, _, table_headers, domain_rows in tables:
            st.markdown(f"#### {title}")
            centered_dataframe(
                [{header: row.get(header) for header in table_headers} for row in domain_rows],
                max_height="12rem",
            )


def _feedback_database_revision():
    """Invalidate the cross-domain snapshot only after a real SQLite change."""
    revision = []
    db_path = get_current_db_path()
    for path in (db_path, db_path.with_name(f"{db_path.name}-wal")):
        try:
            stat = path.stat()
            revision.append((str(path), stat.st_mtime_ns, stat.st_size))
        except FileNotFoundError:
            revision.append((str(path), None, None))
    return tuple(revision)


@st.cache_data(show_spinner=False, max_entries=8)
def _load_feedback_page_inputs(database_revision, today_value, language):
    """Reuse the five primary summaries while navigating between pages."""
    del database_revision
    del language  # Nutrition feedback uses the page language via module state.
    recovery = get_latest_recovery(log_date=today_value)
    # Comprehensive feedback is a same-day report: unlike a history card, it
    # never substitutes an older sleep session for today's missing record.
    sleep = get_latest_sleep(log_date=today_value)
    return (
        recovery,
        sleep,
        _training_data_for_date(today_value),
        _today_nutrition_snapshot(today_value),
        get_latest_local_coach(),
        get_latest_ai_feedback(analysis_date=today_value),
        (get_kubios_advanced_metrics(limit=1, date_value=today_value) or [{}])[0],
    )


def main() -> None:
    today_value = date.today().isoformat()
    # This is a same-day report. Each card and table uses today's date only;
    # a domain with no completed record remains empty rather than borrowing a
    # prior day's data.
    recovery, sleep, today_training, nutrition, coach, ai_feedback, kubios_measurement = _load_feedback_page_inputs(
        _feedback_database_revision(),
        today_value,
        LANGUAGE,
    )

    st.title(TR("navigation.feedback"))
    st.caption(_ui(
        "将最近的恢复、睡眠、训练和营养记录放在一起，帮助你确定今天最值得优先处理的事。",
        "Bring recent recovery, sleep, training, and nutrition records together to identify today's clearest priority.",
    ))
    st.markdown(FEEDBACK_CSS, unsafe_allow_html=True)

    summary = (coach or {}).get("training_summary") or {}
    active_ai_feedback = ai_feedback if ai_feedback and not ai_feedback.get("is_stale") else None

    cards = st.columns(4)
    with cards[0]:
        _card(
            _ui("恢复", "Recovery"),
            _value((recovery or {}).get("recovery_score")),
            _ui("目标日期：", "Target date: ") + format_date((recovery or {}).get("date"), LANGUAGE),
            status=_status_for_recovery(recovery),
        )
    with cards[1]:
        _card(
            _ui("睡眠评分", "Sleep score"),
            _value((sleep or {}).get("sleep_score")),
            _ui("目标日期：", "Target date: ") + format_date(today_value, LANGUAGE),
            status=_status_for_sleep(sleep),
        )
    with cards[2]:
        duration = (today_training or {}).get("duration_minutes")
        _card(
            _ui("今日训练", "Today's training"),
            minutes_to_hms(duration) if duration not in (None, "") else TR("common.no_data"),
            _ui("目标日期：", "Target date: ") + format_date(today_value, LANGUAGE),
        )
    with cards[3]:
        _card(
            _ui("营养记录完整度", "Nutrition completeness"),
            _completion((nutrition.get("summary") or {}).get("data_completeness")),
            _ui("今日记录：", "Today's record: ") + format_date(nutrition.get("date"), LANGUAGE),
        )

    if st.button(
        _ui("生成 Codex 综合反馈", "Generate Codex feedback"),
        key=f"generate_codex_feedback_{today_value}",
        type="primary",
    ):
        with st.spinner(_ui("Codex 正在分析今日综合数据…", "Codex is analyzing today's data…")):
            try:
                generate_feedback_for_date(today_value, language=LANGUAGE)
            except AIFeedbackError as exc:
                st.warning(str(exc))
            else:
                st.rerun()

    if ai_feedback and ai_feedback.get("is_stale"):
        st.info(_ui(
            "此前的 Codex 综合反馈使用旧数据或旧反馈格式，已暂停显示。请重新生成后查看最新的四维反馈；当前本地规则判断仍有效。",
            "The earlier Codex feedback uses outdated data or format and is hidden. Generate it again to view the latest four-domain feedback; the local-rule judgment remains available.",
        ))
    if active_ai_feedback:
        _render_codex_feedback(active_ai_feedback)
    elif summary.get("advice"):
        st.markdown(
            "<section class='rh-feedback-summary'><div class='rh-feedback-summary-label'>%s</div><p>%s</p></section>"
            % (
                escape(_ui("本地规则综合判断（依据：", "Local-rule overall direction (based on: ")
                       + format_date(coach.get("date"), LANGUAGE) + ")"),
                escape(summary["advice"]),
            ),
            unsafe_allow_html=True,
        )
    else:
        st.info(_ui(
            "尚未生成综合建议。继续同步或记录恢复、睡眠、训练和营养数据后，这里会显示基于本地规则的反馈。",
            "No overall direction is available yet. Continue syncing or logging recovery, sleep, training, and nutrition data to see locally generated feedback here.",
        ))

    local_limitations = (coach or {}).get("data_limitations") or []
    if local_limitations and not active_ai_feedback:
        st.warning(_ui("数据局限：", "Data limitations: ") + " ".join(map(str, local_limitations)))
    if coach and coach.get("is_historical") and not active_ai_feedback:
        st.warning(_ui(
            "当前建议来自较早的数据，请结合今天的实际状态谨慎调整。",
            "The current feedback is based on older data; adjust cautiously using today's real-time state.",
        ))
    with st.expander(
        _ui("今日综合数据反馈", "Today's comprehensive data feedback"),
        expanded=False,
    ):
        st.caption(_ui(
            "睡眠、营养、恢复和训练分别展示，并与各页面的当日数据使用相同数据源；当天尚无记录的字段会显示暂无数据。",
            "Sleep, nutrition, recovery, and training are shown separately using the same sources as their respective Today views. Fields without a record for today show no data.",
        ))
        tables = _today_feedback_tables(
            today_value,
            sleep=sleep,
            nutrition=nutrition,
            recovery=recovery,
            training=today_training,
            recovery_metrics=kubios_measurement,
        )
        _render_feedback_tables(tables)

        export_options = {filename_part: title for title, filename_part, _, _ in tables}
        export_scope = st.radio(
            _ui("导出范围", "Export scope"),
            ("all", "selected"),
            format_func=lambda value: _ui("全部数据", "All data") if value == "all" else _ui("选择数据", "Select data"),
            horizontal=True,
            key="feedback_export_scope",
        )
        selected_types = set(export_options)
        if export_scope == "selected":
            selected_types = set(st.multiselect(
                _ui("选择数据类型", "Select data types"),
                list(export_options),
                format_func=lambda value: export_options[value],
                default=list(export_options),
                key="feedback_export_types",
            ))
        export_headers, export_rows = _combined_feedback_export(tables, selected_types)
        st.download_button(
            _ui("导出数据 CSV", "Export data as CSV"),
            data=_feedback_csv(export_headers, export_rows),
            file_name=f"rhythmos_feedback_{today_value}.csv",
            mime="text/csv;charset=utf-8",
            key=f"feedback_csv_{today_value}",
            disabled=not selected_types,
            on_click="ignore",
        )

    history_open = bool(st.session_state.get("feedback_history_open", False))
    history_label = _ui(
        "历史综合数据反馈",
        "Historical comprehensive data feedback",
    )
    if st.button(
        history_label,
        key="feedback_history_toggle",
        width="stretch",
        icon=":material/keyboard_arrow_down:" if history_open else ":material/keyboard_arrow_right:",
    ):
        st.session_state["feedback_history_open"] = not history_open
        st.rerun()
    if history_open:
        history_dates = _available_feedback_dates(before_date=today_value)
        if not history_dates:
            st.caption(_ui(
                "暂无历史数据。后续记录或同步的数据会自动出现在这里。",
                "No historical data is available yet. Future records and synced data will appear here automatically.",
            ))
        else:
            selected_history_date = st.selectbox(
                _ui("选择日期", "Select date"),
                history_dates,
                format_func=lambda value: format_date(value, LANGUAGE),
                key="historical_feedback_date",
            )
            historical_tables = _feedback_tables_for_date(
                selected_history_date,
                today_value=today_value,
            )
            _render_feedback_tables(historical_tables)
            historical_export_options = {
                filename_part: title
                for title, filename_part, _, _ in historical_tables
            }
            historical_export_scope = st.radio(
                _ui("导出范围", "Export scope"),
                ("all", "selected"),
                format_func=lambda value: (
                    _ui("全部数据", "All data")
                    if value == "all" else _ui("选择数据", "Select data")
                ),
                horizontal=True,
                key="historical_feedback_export_scope",
            )
            historical_selected_types = set(historical_export_options)
            if historical_export_scope == "selected":
                historical_selected_types = set(st.multiselect(
                    _ui("选择数据类型", "Select data types"),
                    list(historical_export_options),
                    format_func=lambda value: historical_export_options[value],
                    default=list(historical_export_options),
                    key="historical_feedback_export_types",
                ))
            historical_headers, historical_rows = _combined_feedback_export(
                historical_tables,
                historical_selected_types,
            )
            st.download_button(
                _ui("导出历史数据 CSV", "Export historical data as CSV"),
                data=_feedback_csv(historical_headers, historical_rows),
                file_name=f"rhythmos_historical_feedback_{selected_history_date}.csv",
                mime="text/csv;charset=utf-8",
                key=f"historical_feedback_csv_{selected_history_date}",
                disabled=not historical_selected_types,
                on_click="ignore",
            )
            st.caption(_ui(
                "快捷导出包含今天在内的最近 7 天或 28 天；会沿用上方选择的数据类型。",
                "Quick exports include today and the most recent 7 or 28 calendar days, using the data types selected above.",
            ))
            range_export_columns = st.columns(2)
            for column, days, zh_label, en_label in (
                (range_export_columns[0], 7, "导出过去一周 CSV", "Export past 7 days as CSV"),
                (range_export_columns[1], 28, "导出过去4周 CSV", "Export past 4 weeks as CSV"),
            ):
                with column:
                    range_headers, range_rows = _range_feedback_export(
                        days,
                        today_value=today_value,
                        selected_types=historical_selected_types,
                    )
                    st.download_button(
                        _ui(zh_label, en_label),
                        data=_feedback_csv(range_headers, range_rows),
                        file_name=f"rhythmos_feedback_{days}d_{today_value}.csv",
                        mime="text/csv;charset=utf-8",
                        key=f"historical_feedback_csv_{days}d_{today_value}",
                        disabled=not historical_selected_types,
                        on_click="ignore",
                    )


if __name__ == "__main__":
    main()
