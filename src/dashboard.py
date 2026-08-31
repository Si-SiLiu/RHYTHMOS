"""Training section with Polar-authoritative structured exercise details."""

from datetime import date, timedelta
from html import escape
import json
import os
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_latest_local_coach
from src.demo_sandbox import configure_demo_runtime
from src.db import connect
from src.domain_dashboard_data import get_domain_baselines
from src.exercise_format import minutes_to_hms, time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.traditional import traditionalize
from src.i18n.ui import current_language, render_sidebar
from src.training_logging import (
    CUSTOM_EXERCISE, EXERCISE_CATEGORIES, LOAD_UNITS, MEASUREMENT_MODES,
    SET_TYPES, SIDES, copy_exercise, copy_set,
    ensure_polar_session_index,
    get_training_session, list_exercise_catalog,
    list_training_sessions, previous_exercises, save_training_details,
)
from src.training_baseline import get_training_baseline_view
from src.training_plan import (
    SPORT_TYPES, analyze_plan_actual, get_weekly_training_plan,
    plan_day_for_date, prescription_snapshot,
)
from src.training_plan_actual import (
    PLAN_MODULES, OUTDOOR_PLAN_LEGACY_MODULES, OUTDOOR_PLAN_MODULES,
    copy_previous_week_training_content, create_planned_exercise,
    create_planned_session, create_training_cycle, current_cycle_week_segment,
    cycle_end_date_for_weeks, cycle_week_segments,
    delete_planned_exercise, delete_training_cycle,
    get_current_training_cycle, list_planned_sessions,
    list_training_cycles, update_planned_exercise,
    recent_outdoor_action_defaults, recent_planned_action_defaults,
    update_planned_session, update_training_cycle,
)
from src.training_plan_actual_i18n import plan_actual_text
from src.ui.components.training_entry import (
    ENTRY_MODES, EXERTION_PREFERENCES, apply_catalog_defaults,
    copied_set_for_entry, default_load_unit, visible_set_fields,
)
from src.ui_controls import render_manual_input_styles
from src.ui_scroll import render_interaction_focus
from src.ui_tables import centered_dataframe


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.exercise.title")),
    page_icon=load_page_icon(), layout="wide",
)
if os.environ.get("DRC_STREAMLIT_ENTRYPOINT") == "cloud_app.py":
    LANGUAGE, TR = PAGE_LANGUAGE, get_translator(PAGE_LANGUAGE)
else:
    LANGUAGE, TR = render_sidebar(st, "exercise")
render_manual_input_styles(st)


def _ui(zh, en):
    """Return page-local copy in the selected Chinese variant or English."""
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en

TRAINING_CSS = """
<style>
.drc-training-head{display:flex;align-items:center;justify-content:center;text-align:center;font-weight:650;min-height:2.4rem}
div[data-testid="stNumberInput"] button{display:none!important}
div[data-testid="stNumberInput"] input{text-align:center!important;padding-left:0!important;padding-right:0!important;text-indent:0!important;color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important}
div[data-testid="stTextInput"] input{text-align:center!important;color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"]{color:var(--text-color)!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] *{color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value]{flex:1 1 auto!important;width:100%!important;text-align:center!important;padding-left:2rem!important}
.drc-action-input-header{text-align:center;font-weight:650;min-height:1.6rem}
.drc-readonly-action-cell{display:flex;align-items:center;justify-content:center;min-height:2.7rem;padding:.35rem .5rem;border-radius:10px;background:var(--secondary-background-color);color:var(--text-color);text-align:center}
.drc-readonly-development{display:flex;align-items:center;justify-content:center;min-height:2.7rem;padding:.35rem .5rem;border-radius:10px;background:var(--secondary-background-color);color:var(--text-color);text-align:center;font-weight:650}
@media (max-width: 760px){.drc-training-head{min-height:1.8rem;font-size:.9rem}}
</style>
"""
st.markdown(TRAINING_CSS, unsafe_allow_html=True)

TRAINING_PLAN_CSS = """
<style>
.drc-plan-cell{border:1px solid #d9dee7;border-left:4px solid #cbd5e1;border-radius:8px;padding:.35rem .45rem;margin:.15rem 0;min-height:2.4rem;background:#fff;color:#273142;font-size:.82rem}
.drc-plan-module{font-weight:650;color:#526071;font-size:.8rem;padding:.55rem .25rem}
.drc-plan-date{border:1px solid #e2e6ec;border-radius:8px;padding:.4rem .25rem;margin:.15rem 0;text-align:center;color:#273142;background:#fafbfc;font-size:.82rem;line-height:1.45}
.drc-plan-type{color:#788294;font-size:.78rem;margin:.25rem 0 .5rem}
.drc-plan-note{color:#788294;font-size:.78rem}
@media (max-width:760px){.drc-plan-cell{font-size:.76rem;min-height:2rem}.drc-plan-module,.drc-plan-date{font-size:.75rem}}
</style>
"""
st.markdown(TRAINING_PLAN_CSS, unsafe_allow_html=True)

TRAINING_PLAN_ACTUAL_CSS = """
<style>
.drc-plan-actual-title{text-align:center;font-size:1.7rem;font-weight:750;letter-spacing:-.02em;margin:.25rem 0 1rem}
.drc-plan-actual-label{min-height:5.5rem;display:flex;align-items:center;justify-content:center;text-align:center;font-weight:700;padding:.6rem;border:1px solid #d9dee7;background:#fafbfc;color:#273142}
.drc-plan-actual-date{font-size:.95rem;line-height:1.35}.drc-plan-actual-weekday{font-size:.85rem;color:#526071;margin-top:.2rem}
.drc-plan-actual-module{height:12.5rem;min-height:12.5rem;max-height:12.5rem;box-sizing:border-box;color:var(--module-color,#2563eb);font-size:1rem}
.drc-plan-actual-action-name{min-height:3.5rem;display:flex;align-items:center;justify-content:center;text-align:center;padding:.35rem .55rem;border:1px solid #d9dee7;border-radius:.5rem;background:#fafbfc;color:#273142;font-weight:600}
details > summary p,[class*="st-key-plan_actual_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-outdoor_plan_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-plan_actual_cycle_"] [data-baseweb="select"] > div,[class*="st-key-outdoor_plan_cycle_"] [data-baseweb="select"] > div,[class*="st-key-plan_actual_cycle_"] input,[class*="st-key-outdoor_plan_cycle_"] input,.drc-cycle-field-label,.drc-cycle-field-value{font-size:1rem!important;line-height:1.5!important}
[class*="st-key-plan_actual_cycle_"],[class*="st-key-outdoor_plan_cycle_"]{text-align:center!important}
[class*="st-key-plan_actual_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-outdoor_plan_cycle_"] [data-testid="stWidgetLabel"]{display:flex!important;justify-content:center!important;text-align:center!important;color:#31333f!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important;line-height:1.5!important}
[class*="st-key-plan_actual_cycle_"] [data-testid="stWidgetLabel"] p,[class*="st-key-outdoor_plan_cycle_"] [data-testid="stWidgetLabel"] p{width:100%!important;text-align:center!important;color:inherit!important;font-family:inherit!important;font-size:1rem!important;font-weight:600!important;line-height:1.5!important}
[class*="st-key-plan_actual_cycle_week_"] [data-testid="stWidgetLabel"],[class*="st-key-outdoor_plan_cycle_week_"] [data-testid="stWidgetLabel"]{display:none!important}
[class*="st-key-plan_actual_cycle_"] input,[class*="st-key-outdoor_plan_cycle_"] input{text-align:center!important;color:#31333f!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important}
[class*="st-key-plan_actual_cycle_filter"] [data-baseweb="select"] > div,[class*="st-key-outdoor_plan_cycle_filter"] [data-baseweb="select"] > div{justify-content:center!important;text-align:center!important;color:#31333f!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important}
[class*="st-key-plan_actual_cycle_week_"] [data-baseweb="select"] > div,[class*="st-key-outdoor_plan_cycle_week_"] [data-baseweb="select"] > div{justify-content:center!important;text-align:center!important;color:#31333f!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important}
[class*="st-key-plan_actual_cycle_"] input,[class*="st-key-plan_actual_cycle_filter"] [data-baseweb="select"] *,[class*="st-key-plan_actual_cycle_week_"] [data-baseweb="select"] *,[class*="st-key-outdoor_plan_cycle_week_"] [data-baseweb="select"] *{color:#31333f!important;-webkit-text-fill-color:#31333f!important}
[class*="st-key-plan_actual_create_cycle"] button,[class*="st-key-plan_actual_save_cycle_"] button,[class*="st-key-plan_actual_save_actions_"] button,[class*="st-key-plan_actual_inline_type_save_"] button,[class*="st-key-outdoor_plan_save_cycle_"] button,[class*="st-key-outdoor_plan_save_actions_"] button{color:#31333f!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-weight:600!important}
[class*="st-key-plan_actual_save_cycle_"] button,[class*="st-key-plan_actual_save_actions_"] button,[class*="st-key-plan_actual_inline_type_save_"] button,[class*="st-key-outdoor_plan_save_cycle_"] button,[class*="st-key-outdoor_plan_save_actions_"] button{height:2.6rem!important;min-height:2.6rem!important;padding:0 .75rem!important;background:#ff4b4b!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border:0!important;border-radius:8px!important;box-shadow:none!important}
[class*="st-key-plan_actual_save_cycle_"] button:hover,[class*="st-key-plan_actual_save_actions_"] button:hover,[class*="st-key-plan_actual_inline_type_save_"] button:hover,[class*="st-key-outdoor_plan_save_cycle_"] button:hover,[class*="st-key-outdoor_plan_save_actions_"] button:hover{background:#ff3333!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border-color:transparent!important}
.drc-cycle-field-label{text-align:center;color:#31333f;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif;font-size:1rem;font-weight:600;line-height:1.5;margin-bottom:.35rem}
.drc-cycle-field-value{background:#eef1f5;border-radius:8px;padding:.55rem .75rem;color:#31333f;min-height:1.5rem;line-height:1.5rem;text-align:center;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif;font-size:1rem;font-weight:600}
.drc-cycle-section-title{text-align:center;color:#31333f;font-size:1.05rem;font-weight:650;line-height:1.5;margin:1rem 0 .65rem}
[class*="st-key-plan_actual_sets_"] label,[class*="st-key-plan_actual_reps_"] label,[class*="st-key-plan_actual_weight_"] label{justify-content:center!important;text-align:center!important}
[class*="st-key-plan_actual_sets_"] [data-baseweb="input"] > div,[class*="st-key-plan_actual_reps_"] [data-baseweb="input"] > div,[class*="st-key-plan_actual_weight_"] [data-baseweb="input"] > div{background:#fafbfc!important;border:1px solid #d9dee7!important;border-radius:.5rem!important;box-shadow:none!important}
[class*="st-key-plan_actual_sets_"] [data-baseweb="input"] input,[class*="st-key-plan_actual_reps_"] [data-baseweb="input"] input,[class*="st-key-plan_actual_weight_"] [data-baseweb="input"] input{text-align:center!important;color:#31333f!important;-webkit-text-fill-color:#31333f!important;font-weight:600!important}
[class*="st-key-outdoor_plan_sets_"] label,[class*="st-key-outdoor_plan_distance_"] label{justify-content:center!important;text-align:center!important}
[class*="st-key-outdoor_plan_sets_"] [data-baseweb="input"] > div,[class*="st-key-outdoor_plan_distance_"] [data-baseweb="input"] > div{background:#fafbfc!important;border:1px solid #d9dee7!important;border-radius:.5rem!important;box-shadow:none!important}
[class*="st-key-outdoor_plan_sets_"] [data-baseweb="input"] input,[class*="st-key-outdoor_plan_distance_"] [data-baseweb="input"] input{text-align:center!important;color:#31333f!important;-webkit-text-fill-color:#31333f!important;font-weight:600!important}
.drc-plan-action-selection{display:flex;align-items:center;gap:.5rem;margin:.35rem 0 .8rem;padding:.55rem .75rem;border:1px solid #bae6fd;border-radius:.55rem;background:#f0f9ff;color:#075985;font-size:.88rem}.drc-plan-action-selection strong{font-size:1rem}.drc-plan-action-selection span{color:#4b7189}
[class*="st-key-plan_actual_actions_"] [data-baseweb="tag"]{min-height:2rem!important;padding:0 .6rem!important;border:1px solid #38bdf8!important;border-radius:999px!important;background:#e0f2fe!important;color:#075985!important;font-weight:700!important}
[class*="st-key-plan_actual_actions_"] [data-baseweb="tag"] *{color:#075985!important}
[class*="st-key-plan_actual_matrix_cell_filled_"] button{height:12.5rem!important;min-height:12.5rem!important;max-height:12.5rem!important;padding:.55rem .65rem!important;align-items:flex-start!important;justify-content:flex-start!important;overflow-y:auto!important;scrollbar-gutter:stable both-edges!important;white-space:pre-line!important;word-break:break-word!important;line-height:1.45!important;font-size:.82rem!important;text-align:left!important;border-color:#d9dee7!important;background:#fff!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
[class*="st-key-plan_actual_matrix_cell_filled_"] button p{width:100%!important;margin:0!important;text-align:left!important}
[class*="st-key-plan_actual_matrix_cell_filled_"] button:hover{border-color:#8ba6c7!important;background:#f8fbff!important}
[class*="st-key-plan_actual_matrix_cell_filled_"] button:active{transform:scale(.985)}
[class*="st-key-plan_actual_matrix_cell_empty_"] button{height:12.5rem!important;min-height:12.5rem!important;max-height:12.5rem!important;font-size:1rem!important;border-color:#d9dee7!important;background:#fff!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
[class*="st-key-plan_actual_matrix_cell_empty_"] button:hover{border-color:#8ba6c7!important;background:#f8fbff!important}
[class*="st-key-outdoor_plan_matrix_cell_filled_"] button{height:12.5rem!important;min-height:12.5rem!important;max-height:12.5rem!important;padding:.55rem .65rem!important;align-items:flex-start!important;justify-content:flex-start!important;overflow-y:auto!important;scrollbar-gutter:stable both-edges!important;white-space:pre-line!important;word-break:break-word!important;line-height:1.45!important;font-size:.78rem!important;text-align:left!important;border-color:#d9dee7!important;background:#fff!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
[class*="st-key-outdoor_plan_matrix_cell_filled_"] button p{width:100%!important;margin:0!important;text-align:left!important}
[class*="st-key-outdoor_plan_matrix_cell_filled_"] button:hover{border-color:#8ba6c7!important;background:#f8fbff!important}
[class*="st-key-outdoor_plan_matrix_cell_empty_"] button{height:12.5rem!important;min-height:12.5rem!important;max-height:12.5rem!important;font-size:1rem!important;border-color:#d9dee7!important;background:#fff!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
[class*="st-key-outdoor_plan_matrix_cell_empty_"] button:hover{border-color:#8ba6c7!important;background:#f8fbff!important}
[class*="st-key-plan_actual_matrix_type_cell_"] button{min-height:5.5rem!important;white-space:pre-wrap!important;line-height:1.45!important;font-size:.82rem!important;text-align:center!important;border-color:#d9dee7!important;background:#fff!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
[class*="st-key-plan_actual_matrix_type_cell_"] button:hover{border-color:#8ba6c7!important;background:#f8fbff!important}
[class*="st-key-plan_actual_matrix_type_cell_"] button:active{transform:scale(.985)}
@media (prefers-color-scheme: dark){
  .drc-plan-actual-label,.drc-plan-actual-action-name{background:#262730;color:#fafafa;border-color:#3b3f49}
  .drc-plan-actual-weekday{color:#c6cad3}
  [class*="st-key-plan_actual_matrix_cell_filled_"] button,[class*="st-key-plan_actual_matrix_cell_empty_"] button,[class*="st-key-plan_actual_matrix_type_cell_"] button{background:#262730!important;color:#fafafa!important;-webkit-text-fill-color:#fafafa!important;border-color:#3b3f49!important}
  [class*="st-key-plan_actual_matrix_cell_filled_"] button:hover,[class*="st-key-plan_actual_matrix_cell_empty_"] button:hover,[class*="st-key-plan_actual_matrix_type_cell_"] button:hover{background:#30323a!important;border-color:#8ba6c7!important}
  [class*="st-key-outdoor_plan_matrix_cell_filled_"] button,[class*="st-key-outdoor_plan_matrix_cell_empty_"] button{background:#262730!important;color:#fafafa!important;-webkit-text-fill-color:#fafafa!important;border-color:#3b3f49!important}
  [class*="st-key-outdoor_plan_matrix_cell_filled_"] button:hover,[class*="st-key-outdoor_plan_matrix_cell_empty_"] button:hover{background:#30323a!important;border-color:#8ba6c7!important}
  [class*="st-key-plan_actual_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-outdoor_plan_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-plan_actual_cycle_"] input,[class*="st-key-outdoor_plan_cycle_"] input,[class*="st-key-plan_actual_cycle_filter"] [data-baseweb="select"] > div,[class*="st-key-plan_actual_cycle_filter"] [data-baseweb="select"] *,[class*="st-key-plan_actual_cycle_week_"] [data-baseweb="select"] > div,[class*="st-key-outdoor_plan_cycle_week_"] [data-baseweb="select"] > div,[class*="st-key-plan_actual_cycle_week_"] [data-baseweb="select"] *,[class*="st-key-outdoor_plan_cycle_week_"] [data-baseweb="select"] *,[class*="st-key-plan_actual_create_cycle"] button{color:#fafafa!important;-webkit-text-fill-color:#fafafa!important}
  [class*="st-key-plan_actual_save_cycle_"] button,[class*="st-key-plan_actual_save_actions_"] button,[class*="st-key-plan_actual_inline_type_save_"] button,[class*="st-key-outdoor_plan_save_cycle_"] button,[class*="st-key-outdoor_plan_save_actions_"] button{background:#ff4b4b!important;color:#fff!important;-webkit-text-fill-color:#fff!important}
  .drc-cycle-field-label,.drc-cycle-section-title{color:#fafafa}.drc-cycle-field-value{background:#262730;color:#fafafa}
  [class*="st-key-plan_actual_sets_"] [data-baseweb="input"] > div,[class*="st-key-plan_actual_reps_"] [data-baseweb="input"] > div,[class*="st-key-plan_actual_weight_"] [data-baseweb="input"] > div{background:#262730!important;border-color:#3b3f49!important}
  [class*="st-key-plan_actual_sets_"] [data-baseweb="input"] input,[class*="st-key-plan_actual_reps_"] [data-baseweb="input"] input,[class*="st-key-plan_actual_weight_"] [data-baseweb="input"] input{color:#fafafa!important;-webkit-text-fill-color:#fafafa!important}
  [class*="st-key-outdoor_plan_sets_"] [data-baseweb="input"] > div,[class*="st-key-outdoor_plan_distance_"] [data-baseweb="input"] > div{background:#262730!important;border-color:#3b3f49!important}
  [class*="st-key-outdoor_plan_sets_"] [data-baseweb="input"] input,[class*="st-key-outdoor_plan_distance_"] [data-baseweb="input"] input{color:#fafafa!important;-webkit-text-fill-color:#fafafa!important}
}
@media (prefers-reduced-motion: reduce){[class*="st-key-plan_actual_matrix_cell_filled_"] button{transition:none!important}}
</style>
"""
st.markdown(TRAINING_PLAN_ACTUAL_CSS, unsafe_allow_html=True)


def _uuid():
    return str(uuid4())


def _value(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _cell(value):
    return f'<div class="drc-training-head">{escape(str(value))}</div>'


def _baseline(label_key, baseline, suffix="", formatter=None):
    if not baseline or baseline.get("status") == "insufficient_data":
        st.metric(TR(label_key), TR("baseline.insufficient_data")); return
    delta = baseline.get("percent_change")
    display = formatter or (lambda value: _value(value, suffix))
    st.metric(TR(label_key), display(baseline.get("latest_value")), None if delta is None else f"{delta:+.1f}%")
    st.caption(TR("domain.common.baseline_median", value=display(baseline.get("median_value"))))


def _catalog_name(item):
    return item["display_name_zh" if LANGUAGE != "en" else "display_name_en"]


def _session_source(item):
    if item.get("polar_external_id") and item.get("exercises"):
        return TR("training_logging.merged_source")
    if item.get("polar_external_id"):
        return TR("training_logging.polar_synced")
    return TR("training_logging.manual_source")


def _plan_actual_text(key):
    return plan_actual_text(LANGUAGE, key)


PLAN_ACTUAL_MODULE_COLORS = {
    "mobility": "#39a9f4", "core_activation": "#2fd4c5", "isometric_overload": "#e9ab19",
    "explosive": "#67c944", "main_strength": "#ff7c73", "accessory_strength": "#f48db8",
    "small_muscle": "#cf74e6",
}
PLAN_ACTUAL_WEEKDAY_KEYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
PLAN_TRAINING_TYPES = (
    "upper_pull", "lower_push", "upper_push", "lower_pull", "active_recovery",
)
PLAN_TRAINING_TYPE_LABELS = {
    "upper_pull": ("上肢拉力", "Upper-body pull"),
    "lower_push": ("下肢推力", "Lower-body push"),
    "upper_push": ("上肢推力", "Upper-body push"),
    "lower_pull": ("下肢拉力", "Lower-body pull"),
    "active_recovery": ("伤病预防类训练", "Injury-prevention training"),
}
PLAN_MODULE_ACTION_TYPES = {
    "mobility": "关节活动度训练",
    "core_activation": "核心力量激活训练",
    "isometric_overload": "等长超负荷训练",
    "explosive": "爆发性力量训练",
    "main_strength": "整体性力量训练-主项",
    "accessory_strength": "整体性力量训练-副项",
    "small_muscle": "小肌肉群力量训练",
}
OUTDOOR_PLAN_TRAINING_TYPES = (
    "warmup",
    "coordination",
    "double_leg_running_form",
    "single_leg_running_form",
    "acceleration",
)
OUTDOOR_PLAN_TYPE_LABELS = {
    "warmup": ("热身练习", "Warm-up practice"),
    "coordination": ("协调性训练", "Coordination training"),
    "double_leg_running_form": ("双腿跑姿训练", "Double-leg running-form training"),
    "single_leg_running_form": ("单边跑姿训练", "Single-leg running-form training"),
    "acceleration": ("冲刺训练", "Sprint training"),
}
# Keep legacy sessions readable after the outdoor training-type taxonomy changes.
# They are normalized to the new choices when the user edits that day.
OUTDOOR_PLAN_MODULE_ALIASES = dict(zip(OUTDOOR_PLAN_LEGACY_MODULES, OUTDOOR_PLAN_MODULES[:2]))
OUTDOOR_PLAN_TRAINING_TYPE_ALIASES = dict(OUTDOOR_PLAN_MODULE_ALIASES)
OUTDOOR_PLAN_ACTIONS = {
    "warmup": ("慢跑", "全身动态拉伸"),
    "coordination": ("蝎子摆尾", "高踢腿", "胯下击掌", "后退跑", "侧身碎步转髋"),
    "double_leg_running_form": (
        "高重心垫步", "直膝跳", "直腿跑", "小步跑", "小马跳", "a式跳跃", "b式跳跃", "c式跳跃", "扶墙跑",
    ),
    "single_leg_running_form": ("单边下压", "单腿登阶"),
    "acceleration": (
        "趴地起身接起跑", "身体前倾接起跑", "原地小碎步接起跑", "前后左右跳接起跑", "站姿起跑", "跪姿起跑", "蹲距式起跑",
    ),
}
OUTDOOR_PLAN_ACTION_ALIASES = {
    # Keep existing plans readable while migrating the former, overly specific label
    # the next time the user saves that training day.
    "800m慢跑": "慢跑",
}


def _outdoor_plan_type_label(value):
    normalized = OUTDOOR_PLAN_TRAINING_TYPE_ALIASES.get(value, value)
    labels = OUTDOOR_PLAN_TYPE_LABELS.get(normalized, (value, value))
    return labels[1 if LANGUAGE == "en" else 0]


def _outdoor_plan_training_type_key(value):
    normalized = OUTDOOR_PLAN_TRAINING_TYPE_ALIASES.get(value, value)
    return normalized if normalized in OUTDOOR_PLAN_TRAINING_TYPES else OUTDOOR_PLAN_TRAINING_TYPES[0]


def _outdoor_plan_module_key(value):
    return OUTDOOR_PLAN_MODULE_ALIASES.get(value, value)


def _outdoor_plan_action_name(value):
    return OUTDOOR_PLAN_ACTION_ALIASES.get(value, value)


def _recent_first_action_options(options, recent_defaults):
    """Keep familiar actions first while preserving the catalog's default order."""
    return [
        action for _, action in sorted(
            enumerate(dict.fromkeys(options)),
            key=lambda pair: (pair[1] not in recent_defaults, pair[0]),
        )
    ]


def _outdoor_plan_cell_text(exercises):
    if not exercises:
        return "+"
    rows = []
    unique_items = {}
    for item in exercises:
        name = _outdoor_plan_action_name(
            item.get("exercise_display_name") or item.get("exercise_canonical_name")
        )
        if not name:
            continue
        unique_items[name] = item
    for name, item in unique_items.items():
        details = []
        if item.get("target_distance_meters") is not None:
            details.append(f"{item['target_distance_meters']:g}m")
        target_sets = item.get("target_sets")
        if target_sets is None:
            target_sets = item.get("target_reps")
        if target_sets is not None:
            details.append(f"{target_sets}组")
        rows.append(f"• {name}" + (f" · {'×'.join(details)}" if details else ""))
    return "\n".join(rows)


def _cycle_period_label(cycle_name, period_index):
    """Show both the cycle number and its week number explicitly."""
    name = str(cycle_name or "").strip()
    if not name:
        return f"第{period_index}周"
    if name[-1].isdigit():
        return f"{name} · 第{period_index}周"
    return f"{name}{period_index} · 第{period_index}周"


def _selected_cycle_week_segment(cycle_record, *, state_key):
    segments = cycle_week_segments(cycle_record)
    if not segments:
        return None
    options = [segment["index"] for segment in segments]
    current_segment = current_cycle_week_segment(cycle_record)
    default_index = current_segment["index"] if current_segment else options[0]
    selected_index = st.session_state.get(state_key)
    if selected_index not in options:
        selected_index = default_index
        st.session_state[state_key] = selected_index
    return next(segment for segment in segments if segment["index"] == selected_index)


def _cycle_week_selector(cycle_record, *, state_key, container=None):
    """Allow week-level plan browsing, defaulting to the week containing today."""
    segments = cycle_week_segments(cycle_record)
    if not segments:
        return None
    if container is None:
        container = st
    options = [segment["index"] for segment in segments]
    selected_segment = _selected_cycle_week_segment(cycle_record, state_key=state_key)
    chosen_index = container.selectbox(
        "计划周",
        options,
        index=options.index(selected_segment["index"]),
        format_func=lambda index: _cycle_period_label(cycle_record["name"], index),
        key=state_key,
        label_visibility="collapsed",
    )
    return next(segment for segment in segments if segment["index"] == chosen_index)


def _plan_training_type_label(value):
    # Legacy plan rows may contain a sport type from the former editor. Keep
    # that sport taxonomy out of the training-type display.
    if value in SPORT_TYPES:
        value = PLAN_TRAINING_TYPES[0]
    return PLAN_TRAINING_TYPE_LABELS.get(value, (value, value))[1 if LANGUAGE == "en" else 0]


def _plan_actual_matrix_cell_text(exercises):
    if not exercises:
        return "+"
    rows = []
    unique_items = {}
    for item in exercises:
        name = item.get("exercise_display_name") or item.get("exercise_canonical_name")
        if not name:
            continue
        unique_items[name] = item
    for name, item in unique_items.items():
        details = []
        if item.get("target_weight") is not None:
            details.append(f"{item['target_weight']:g}kg")
        if item.get("target_sets") is not None and item.get("target_reps") is not None:
            details.append(f"{item['target_sets']}×{item['target_reps']}")
        rows.append(f"• {name}" + (f" · {' · '.join(details)}" if details else ""))
    return "\n".join(rows)


def _render_training_history_tab(connection, sessions, training_notice=None, selected_cycle=None):
    """Render historical training records in the dedicated History tab."""
    history_training_title = (
        (_ui("历史", "") + TR("domain.exercise.title"))
        if LANGUAGE != "en" else TR("domain.exercise.title")
    )
    selected_history_id = st.session_state.get("training_history_selected")
    if selected_history_id is None and sessions:
        selected_history_id = sessions[0]["id"]
    focus_nonce = st.session_state.get("training_details_focus_nonce", 0)
    last_focus_nonce = st.session_state.get("training_details_last_scrolled_nonce", 0)
    should_focus = focus_nonce > last_focus_nonce
    focus_target_id = f"training-situation-details-{focus_nonce}"
    st.markdown(f'<div id="{focus_target_id}"></div>', unsafe_allow_html=True)
    if should_focus:
        render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)
        st.session_state["training_details_last_scrolled_nonce"] = focus_nonce
    st.subheader(history_training_title)
    _history(connection, sessions)
    if selected_history_id:
        selected_session = get_training_session(connection, selected_history_id)
        if selected_session:
            _details(
                connection,
                selected_session,
                auto_expand=should_focus,
                readonly=selected_session.get("date") < date.today().isoformat(),
            )
            if training_notice:
                st.success(training_notice)
    elif training_notice:
        st.success(training_notice)
def _render_plan_actual_v1(connection, sessions, *, training_notice=None):
    """Render the independent plan matrix and its plan-vs-actual comparison."""
    expansion_state_version = 2
    if st.session_state.get("plan_actual_expansion_state_version") != expansion_state_version:
        st.session_state.pop("plan_actual_open_plan_table", None)
        st.session_state.pop("outdoor_plan_open_plan_table", None)
        st.session_state["plan_actual_expansion_state_version"] = expansion_state_version
    # Bump this when the editor interaction contract changes so a prior
    # session cannot resurrect an editor that was not opened in the current
    # table interaction.
    editor_state_version = 3
    if st.session_state.get("plan_actual_editor_state_version") != editor_state_version:
        for state_prefix in ("plan_actual", "outdoor_plan"):
            for state_suffix in (
                "matrix_date", "matrix_module", "matrix_session_id", "matrix_focus_nonce", "matrix_last_focus_nonce", "editing",
            ):
                st.session_state.pop(f"{state_prefix}_{state_suffix}", None)
        st.session_state["plan_actual_editor_state_version"] = editor_state_version
    text = _plan_actual_text
    # All plan, execution, and historical insights now live in one continuous
    # execution workspace; keep the container invisible rather than showing a
    # redundant one-item tab bar.
    execution_tab = st.container()
    cycles = list_training_cycles(connection)

    with execution_tab:
        save_notice = st.session_state.pop("plan_actual_save_notice", None)
        plan_table_focus_nonce = st.session_state.get("plan_actual_plan_table_focus_nonce", 0)
        plan_table_last_focus_nonce = st.session_state.get("plan_actual_plan_table_last_focus_nonce", 0)
        # Cycle management is an on-demand directory. Do not reopen it from
        # stale editor state after a rerun or after the user returns here.
        strength_cycle_open = False
        strength_cycle_directory = st.expander(
            text("indoor_strength_training_cycle"),
            expanded=strength_cycle_open,
        )
        with strength_cycle_directory:
            cycle_options = [None] + [item["id"] for item in cycles]
            current_cycle = get_current_training_cycle(connection)
            current_cycle_id = current_cycle["id"] if current_cycle else None
            selected_cycle_state = st.session_state.get("plan_actual_cycle_filter")
            if current_cycle_id and selected_cycle_state in (None, ""):
                st.session_state["plan_actual_cycle_filter"] = current_cycle_id
            elif selected_cycle_state not in cycle_options:
                st.session_state["plan_actual_cycle_filter"] = current_cycle_id
            selected_cycle = st.selectbox(
                text("select_cycle"), cycle_options,
                format_func=lambda value: text("no_plans") if value is None else next(
                    item["name"] for item in cycles if item["id"] == value
                ), key="plan_actual_cycle_filter",
            )
            selected_cycle_record = next(
                (item for item in cycles if item["id"] == selected_cycle), None
            )
            if selected_cycle_record:
                edited_name = st.text_input(
                    text("edit_cycle_name"), value=selected_cycle_record["name"],
                    key=f"plan_actual_cycle_name_{selected_cycle}",
                )
                detail_start = date.fromisoformat(selected_cycle_record["start_date"])
                detail_end = date.fromisoformat(selected_cycle_record["end_date"])
                detail_days = (detail_end - detail_start).days + 1
                detail_weeks = detail_days / 7
                detail_fields = st.columns(3, vertical_alignment="top")
                edited_start = detail_fields[0].date_input(
                    text("start_date"), value=detail_start,
                    key=f"plan_actual_cycle_start_{selected_cycle}",
                )
                edited_duration_weeks = detail_fields[1].number_input(
                    text("duration_weeks"), min_value=1, value=int(detail_weeks), step=1,
                    format="%d", key=f"plan_actual_cycle_duration_weeks_{selected_cycle}",
                )
                edited_end = cycle_end_date_for_weeks(edited_start, edited_duration_weeks)
                detail_fields[2].markdown(
                    f"<div class='drc-cycle-field-label'>{escape(text('cycle_end_date'))}</div>",
                    unsafe_allow_html=True,
                )
                detail_fields[2].markdown(
                    f"<div class='drc-cycle-field-value'>{escape(edited_end.strftime('%Y/%m/%d'))}</div>",
                    unsafe_allow_html=True,
                )
                cycle_details_directory = st.expander(
                    text("view_details"),
                    expanded=strength_cycle_open,
                )
            else:
                st.info(text("no_cycle_selected"))

            confirm_cycle_delete = st.checkbox(
                text("confirm_delete_cycle"),
                key=f"plan_actual_confirm_delete_cycle_{selected_cycle or 'none'}",
                disabled=selected_cycle is None,
            )
            show_cycle_creator = st.session_state.get("plan_actual_show_create_cycle", False)
            cycle_action_columns = st.columns(4)
            if cycle_action_columns[0].button(
                text("delete_cycle"), key="plan_actual_delete_cycle",
                disabled=selected_cycle is None or not confirm_cycle_delete,
            ):
                try:
                    delete_training_cycle(connection, selected_cycle)
                    for state_key in (
                        "plan_actual_matrix_date", "plan_actual_matrix_module",
                        "plan_actual_matrix_session_id", "plan_actual_matrix_focus_nonce",
                        "plan_actual_matrix_last_focus_nonce",
                        "plan_actual_editing", "plan_actual_inline_type_date",
                    ):
                        st.session_state.pop(state_key, None)
                    st.session_state["plan_actual_save_notice"] = text("cycle_deleted")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if cycle_action_columns[1].button(
                text("copy_previous_week"), key="plan_actual_copy_previous_week",
                disabled=selected_cycle_record is None,
            ):
                current_period = current_cycle_week_segment(selected_cycle_record)
                if not current_period:
                    st.info(text("no_current_cycle_period"))
                else:
                    copy_result = copy_previous_week_training_content(
                        connection,
                        current_period["matrix_week_start"],
                        cycle_id=selected_cycle,
                    )
                    if copy_result["copied_session_count"]:
                        notice_key = (
                            "previous_week_copy_partial"
                            if copy_result["skipped_date_count"] else "previous_week_copy_success"
                        )
                        st.session_state["plan_actual_save_notice"] = text(notice_key).format(
                            count=copy_result["copied_session_count"],
                            skipped=copy_result["skipped_date_count"],
                        )
                    elif copy_result["source_session_count"]:
                        st.session_state["plan_actual_save_notice"] = text("previous_week_copy_exists")
                    else:
                        st.session_state["plan_actual_save_notice"] = text("no_previous_week_content")
                    st.rerun()
            if not show_cycle_creator:
                if cycle_action_columns[2].button(
                    text("new_cycle"), key="plan_actual_open_cycle_creator"
                ):
                    st.session_state["plan_actual_show_create_cycle"] = True
                    st.rerun()
            if show_cycle_creator:
                st.markdown(
                    f"<div class='drc-cycle-section-title'>{escape(text('new_cycle'))}</div>",
                    unsafe_allow_html=True,
                )
                name = st.text_input(text("cycle_name"), key="plan_actual_cycle_name")
                cycle_fields = st.columns(3)
                start = cycle_fields[0].date_input(
                    text("start_date"), value=date.today(), key="plan_actual_cycle_start"
                )
                duration_weeks = cycle_fields[1].number_input(
                    text("duration_weeks"), min_value=1, value=1, step=1, format="%d",
                    key="plan_actual_cycle_duration_weeks",
                )
                try:
                    end = cycle_end_date_for_weeks(start, duration_weeks)
                    end_label = end.strftime("%Y/%m/%d")
                except ValueError:
                    end = None
                    end_label = "—"
                cycle_fields[2].markdown(
                    f"<div class='drc-cycle-field-label'>{escape(text('end_date'))}</div>",
                    unsafe_allow_html=True,
                )
                cycle_fields[2].markdown(
                    f"<div class='drc-cycle-field-value'>{escape(end_label)}</div>",
                    unsafe_allow_html=True,
                )
                notes = st.text_input(text("cycle_notes"), key="plan_actual_cycle_notes")
                if st.button(text("create_cycle"), key="plan_actual_create_cycle"):
                    try:
                        if end is None:
                            raise ValueError("INVALID_CYCLE_DURATION")
                        create_training_cycle(connection, name, start, end, notes=notes)
                        st.session_state["plan_actual_show_create_cycle"] = False
                        st.success(text("created")); st.rerun()
                    except ValueError as exc:
                        error_key = {
                            "CYCLE_MIN_ONE_WEEK": "minimum_cycle_week",
                            "INVALID_CYCLE_DURATION": "invalid_cycle_duration",
                        }.get(str(exc))
                        st.error(text(error_key) if error_key else str(exc))
            if selected_cycle_record and cycle_action_columns[3].button(
                text("save_changes"), key=f"plan_actual_save_cycle_{selected_cycle}"
            ):
                try:
                    update_training_cycle(
                        connection, selected_cycle, name=edited_name,
                        start_date=edited_start, end_date=edited_end,
                    )
                    st.session_state["plan_actual_save_notice"] = text("cycle_updated")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if not selected_cycle_record:
                cycle_details_directory = strength_cycle_directory
        planned_sessions = (
            list_planned_sessions(connection, cycle_id=selected_cycle)
            if selected_cycle else list_planned_sessions(connection, training_domain="indoor_strength")
        )
        plan_directory = cycle_details_directory
        if plan_table_focus_nonce > plan_table_last_focus_nonce:
            render_interaction_focus(
                components,
                target_expander_label=text("view_details"),
                nonce=plan_table_focus_nonce,
            )
            st.session_state["plan_actual_plan_table_last_focus_nonce"] = plan_table_focus_nonce
        current_period = (
            _cycle_week_selector(
                selected_cycle_record,
                state_key=f"plan_actual_cycle_week_{selected_cycle}",
                container=plan_directory,
            )
            if selected_cycle_record else None
        )
        if current_period:
            week_start = date.fromisoformat(current_period["matrix_week_start"])
        else:
            first_plan_date = min(
                (date.fromisoformat(item["planned_date"]) for item in planned_sessions),
                default=date.today(),
            )
            week_start = first_plan_date - timedelta(days=first_plan_date.weekday())
        week_dates = [week_start + timedelta(days=index) for index in range(7)]
        sessions_by_date = {
            day.isoformat(): [item for item in planned_sessions if item["planned_date"] == day.isoformat()]
            for day in week_dates
        }

        date_header = plan_directory.columns([1.35] + [1] * 7)
        date_header[0].markdown(f"<div class='drc-plan-actual-label'>{escape(text('planned_date'))}</div>", unsafe_allow_html=True)
        for column, day in zip(date_header[1:], week_dates):
            date_label = day.strftime('%Y/%-m/%-d')
            column.markdown(f"<div class='drc-plan-actual-label drc-plan-actual-date'>{date_label}</div>", unsafe_allow_html=True)

        weekday_header = plan_directory.columns([1.35] + [1] * 7)
        weekday_header[0].markdown(f"<div class='drc-plan-actual-label'>{escape(text('time'))}</div>", unsafe_allow_html=True)
        for column, weekday_key in zip(weekday_header[1:], PLAN_ACTUAL_WEEKDAY_KEYS):
            column.markdown(
                f"<div class='drc-plan-actual-label drc-plan-actual-weekday'>{escape(text(weekday_key))}</div>",
                unsafe_allow_html=True,
            )

        types_row = plan_directory.columns([1.35] + [1] * 7)
        types_row[0].markdown(f"<div class='drc-plan-actual-label'>{escape(text('training_type'))}</div>", unsafe_allow_html=True)
        inline_type_date = st.session_state.get("plan_actual_inline_type_date")
        for column, day in zip(types_row[1:], week_dates):
            day_sessions = sessions_by_date[day.isoformat()]
            if inline_type_date == day.isoformat():
                existing_type = day_sessions[0].get("training_type") if day_sessions else PLAN_TRAINING_TYPES[0]
                if existing_type in SPORT_TYPES or existing_type not in PLAN_TRAINING_TYPES:
                    existing_type = PLAN_TRAINING_TYPES[0]
                chosen_type = column.selectbox(
                    text("training_type"), PLAN_TRAINING_TYPES,
                    index=PLAN_TRAINING_TYPES.index(existing_type),
                    format_func=_plan_training_type_label,
                    key=f"plan_actual_inline_type_{day.isoformat()}",
                    label_visibility="collapsed",
                )
                if column.button(text("save_changes"), key=f"plan_actual_inline_type_save_{day.isoformat()}", use_container_width=True):
                    if day_sessions:
                        for session in day_sessions:
                            update_planned_session(connection, session["id"], training_type=chosen_type)
                    else:
                        create_planned_session(
                            connection, day, _plan_training_type_label(chosen_type), chosen_type,
                            cycle_id=selected_cycle,
                        )
                    st.session_state.pop("plan_actual_inline_type_date", None)
                    st.session_state["plan_actual_save_notice"] = text("saved")
                    st.rerun()
            else:
                label = _plan_training_type_label(day_sessions[0]["training_type"]) if day_sessions else "+"
                if column.button(
                    label,
                    key=f"plan_actual_matrix_type_cell_{day.isoformat()}",
                    use_container_width=True,
                ):
                    st.session_state["plan_actual_inline_type_date"] = day.isoformat()
                    st.session_state.pop("plan_actual_matrix_date", None)
                    st.session_state.pop("plan_actual_matrix_module", None)
                    st.session_state.pop("plan_actual_matrix_session_id", None)
                    st.session_state.pop("plan_actual_matrix_focus_nonce", None)
                    st.session_state.pop("plan_actual_matrix_last_focus_nonce", None)
                    st.session_state.pop("plan_actual_editing", None)
                    st.rerun()

        for module_key in PLAN_MODULES:
            row = plan_directory.columns([1.35] + [1] * 7)
            color = PLAN_ACTUAL_MODULE_COLORS[module_key]
            label = escape(
                f"{text('strength_training_prefix')}{text(f'module_{module_key}')}"
            )
            row[0].markdown(
                f"<div class='drc-plan-actual-label drc-plan-actual-module' style='--module-color:{color}'>{label}</div>",
                unsafe_allow_html=True,
            )
            for column, day in zip(row[1:], week_dates):
                day_sessions = sessions_by_date[day.isoformat()]
                exercises = [
                    exercise for session in day_sessions for exercise in session["exercises"]
                    if exercise.get("module_key") == module_key
                ]
                if column.button(
                    _plan_actual_matrix_cell_text(exercises),
                    key=(
                        f"plan_actual_matrix_cell_"
                        f"{'filled' if exercises else 'empty'}_{day.isoformat()}_{module_key}"
                    ),
                    use_container_width=True,
                ):
                    # A day can contain several planned sessions, one for
                    # each strength module. Select the session that owns the
                    # clicked module instead of always taking the day's first
                    # session; otherwise the editor can open with zero
                    # actions even though the matrix card shows actions.
                    module_session = next(
                        (
                            session for session in day_sessions
                            if any(
                                exercise.get("module_key") == module_key
                                for exercise in session["exercises"]
                            )
                        ),
                        None,
                    )
                    st.session_state["plan_actual_matrix_date"] = day.isoformat()
                    st.session_state["plan_actual_matrix_module"] = module_key
                    st.session_state["plan_actual_matrix_session_id"] = (
                        module_session["id"] if module_session else None
                    )
                    st.session_state["plan_actual_editing"] = True
                    st.session_state["plan_actual_matrix_focus_nonce"] = (
                        st.session_state.get("plan_actual_matrix_focus_nonce", 0) + 1
                    )
                    st.rerun()

        selected_date = st.session_state.get("plan_actual_matrix_date")
        selected_module = st.session_state.get("plan_actual_matrix_module")
        if st.session_state.get("plan_actual_editing") and selected_date and selected_module:
            day_sessions = sessions_by_date.get(selected_date, [])
            selected_session_id = st.session_state.get("plan_actual_matrix_session_id")
            selected_session = next(
                (item for item in day_sessions if item["id"] == selected_session_id),
                None,
            )
            if selected_session is None:
                selected_session = next(
                    (
                        item for item in day_sessions
                        if any(
                            exercise.get("module_key") == selected_module
                            for exercise in item["exercises"]
                        )
                    ),
                    None,
                )
            focus_nonce = st.session_state.get("plan_actual_matrix_focus_nonce", 0)
            last_focus_nonce = st.session_state.get("plan_actual_matrix_last_focus_nonce", 0)
            focus_target_id = "plan-actual-edit-focus-target"
            with st.container(border=True):
                st.markdown(f'<div id="{focus_target_id}"></div>', unsafe_allow_html=True)
                if focus_nonce > last_focus_nonce:
                    render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)
                    st.session_state["plan_actual_matrix_last_focus_nonce"] = focus_nonce
                current_type = selected_session["training_type"] if selected_session else PLAN_TRAINING_TYPES[0]
                if current_type in SPORT_TYPES or current_type not in PLAN_TRAINING_TYPES:
                    current_type = PLAN_TRAINING_TYPES[0]

                # The matrix aggregates a module across every session on the
                # selected day. Use that same source in the editor so legacy
                # duplicate session records cannot make the two sides drift.
                module_sessions = [
                    item for item in day_sessions
                    if any(
                        exercise.get("module_key") == selected_module
                        for exercise in item["exercises"]
                    )
                ]
                module_exercises = [
                    exercise
                    for session in module_sessions
                    for exercise in session["exercises"]
                    if exercise.get("module_key") == selected_module
                ]
                recent_defaults = recent_planned_action_defaults(connection, selected_module)
                action_options = _plan_module_action_options(
                    selected_module,
                    PLAN_TRAINING_TYPE_LABELS[current_type][0],
                    [
                        item.get("exercise_display_name") or item.get("exercise_canonical_name")
                        for item in module_exercises
                    ],
                )
                action_options = _recent_first_action_options(action_options, recent_defaults)
                action_option_by_key = {
                    _action_name_key(action): action for action in action_options
                }

                def existing_action_name(exercise):
                    return (
                        exercise.get("exercise_display_name")
                        or exercise.get("exercise_canonical_name")
                        or ""
                    )

                action_picker_key = (
                    f"plan_actual_actions_{selected_session['id']}"
                    if selected_session else f"plan_actual_actions_{selected_date}_{selected_module}"
                )
                action_picker_options_key = f"{action_picker_key}_available_options"
                action_picker_context_key = (
                    f"{selected_date}:{selected_module}:"
                    f"{selected_session['id'] if selected_session else 'new'}:{focus_nonce}"
                )
                action_picker_context_state_key = "plan_actual_action_picker_context"
                action_picker_context_changed = (
                    st.session_state.get(action_picker_context_state_key)
                    != action_picker_context_key
                )
                if action_picker_context_changed or action_picker_key not in st.session_state:
                    st.session_state[action_picker_key] = [
                        action_option_by_key[_action_name_key(name)]
                        for name in dict.fromkeys(
                            existing_action_name(item)
                            for item in module_exercises
                        )
                        if _action_name_key(name) in action_option_by_key
                    ]
                elif st.session_state.get(action_picker_options_key) != action_options:
                    st.session_state[action_picker_key] = [
                        action_option_by_key[_action_name_key(action)]
                        for action in st.session_state[action_picker_key]
                        if _action_name_key(action) in action_option_by_key
                    ]
                # A type switch can reuse the same Streamlit widget key.  In
                # that case filter the value on every render so an action from
                # the previous type cannot remain selected invisibly.
                st.session_state[action_picker_key] = [
                    action_option_by_key[_action_name_key(action)]
                    for action in st.session_state.get(action_picker_key, [])
                    if _action_name_key(action) in action_option_by_key
                ]
                st.session_state[action_picker_context_state_key] = action_picker_context_key
                st.session_state[action_picker_options_key] = list(action_options)
                selected_actions = st.multiselect(
                    text("exercise_multi_name"), action_options, key=action_picker_key,
                    help=text("select_multiple_actions"), placeholder=" ",
                )
                st.markdown(
                    f"<div class='drc-plan-action-selection'><strong>{len(selected_actions)}</strong>"
                    f"{escape(text('selected_actions_count'))}</div>",
                    unsafe_allow_html=True,
                )
                existing_by_name = {
                    _action_name_key(existing_action_name(item)): item
                    for item in module_exercises
                    if _action_name_key(existing_action_name(item))
                }
                for action_name in selected_actions:
                    exercise = existing_by_name.get(_action_name_key(action_name), {})
                    learned = next(
                        (
                            defaults
                            for name, defaults in recent_defaults.items()
                            if _action_name_key(name) == _action_name_key(action_name)
                        ),
                        {},
                    )
                    exercise_key = str(exercise.get("id") or action_name)
                    row = st.columns((2.5, 1, 1, 1), vertical_alignment="center")
                    row[0].markdown(
                        f"<div class='drc-plan-actual-action-name'>{escape(action_name)}</div>",
                        unsafe_allow_html=True,
                    )
                    row[1].number_input(
                        text("sets"), min_value=1,
                        value=int(exercise.get("target_sets") if exercise.get("target_sets") is not None else learned.get("target_sets") or 1), step=1,
                        key=f"plan_actual_sets_{selected_date}_{selected_module}_{exercise_key}",
                    )
                    row[2].number_input(
                        text("reps"), min_value=1,
                        value=int(exercise.get("target_reps") if exercise.get("target_reps") is not None else learned.get("target_reps") or 8), step=1,
                        key=f"plan_actual_reps_{selected_date}_{selected_module}_{exercise_key}",
                    )
                    row[3].number_input(
                        text("weight"), min_value=0.0,
                        value=float(exercise.get("target_weight") if exercise.get("target_weight") is not None else learned.get("target_weight") or 0.0), step=0.5,
                        key=f"plan_actual_weight_{selected_date}_{selected_module}_{exercise_key}",
                    )

                if save_notice:
                    st.success(save_notice)
                if st.button(
                    text("save_changes"), key=f"plan_actual_save_actions_{selected_date}_{selected_module}",
                ):
                    if not selected_actions and not module_exercises:
                        for state_key in (
                            "plan_actual_matrix_date",
                            "plan_actual_matrix_module",
                            "plan_actual_matrix_session_id",
                            "plan_actual_matrix_focus_nonce",
                            "plan_actual_matrix_last_focus_nonce",
                            "plan_actual_editing",
                        ):
                            st.session_state.pop(state_key, None)
                        st.session_state["plan_actual_save_notice"] = text("saved")
                        st.rerun()
                    else:
                        try:
                            session_name = (
                                f"{_plan_training_type_label(current_type)} · "
                                f"{text('strength_training_prefix')}{text(f'module_{selected_module}')}"
                            )
                            if selected_session:
                                session_id = selected_session["id"]
                                update_planned_session(
                                    connection, session_id, session_name=session_name,
                                    training_type=current_type,
                                )
                            else:
                                session_id = create_planned_session(
                                    connection, selected_date, session_name, current_type,
                                    cycle_id=selected_cycle,
                                )
                            selected_action_keys = {
                                _action_name_key(action_name) for action_name in selected_actions
                            }
                            for exercise in module_exercises:
                                name = existing_action_name(exercise)
                                if _action_name_key(name) not in selected_action_keys:
                                    delete_planned_exercise(connection, exercise["id"])
                            for action_name in selected_actions:
                                exercise = existing_by_name.get(_action_name_key(action_name))
                                exercise_key = str(exercise.get("id") or action_name) if exercise else action_name
                                sets = st.session_state[f"plan_actual_sets_{selected_date}_{selected_module}_{exercise_key}"]
                                reps = st.session_state[f"plan_actual_reps_{selected_date}_{selected_module}_{exercise_key}"]
                                weight = st.session_state[f"plan_actual_weight_{selected_date}_{selected_module}_{exercise_key}"]
                                if exercise:
                                    update_planned_exercise(
                                        connection, exercise["id"], exercise_canonical_name=action_name,
                                        exercise_display_name=action_name, target_sets=sets,
                                        target_reps=reps, target_weight=weight,
                                    )
                                else:
                                    create_planned_exercise(
                                        connection, session_id, canonical_name=action_name,
                                        display_name=action_name, target_sets=sets,
                                        target_reps=reps, target_weight=weight,
                                        module_key=selected_module,
                                    )
                            for state_key in (
                                "plan_actual_matrix_date",
                                "plan_actual_matrix_module",
                                "plan_actual_matrix_session_id",
                                "plan_actual_matrix_focus_nonce",
                                "plan_actual_matrix_last_focus_nonce",
                                "plan_actual_editing",
                            ):
                                st.session_state.pop(state_key, None)
                            st.session_state["plan_actual_save_notice"] = text("saved")
                            st.rerun()
                        except (TypeError, ValueError):
                            st.warning(text("invalid_numbers"))
        if save_notice and not (selected_date and selected_module):
            st.success(save_notice)
        _render_outdoor_plan_directory(connection)
        # Show actual training after both plan-cycle directories so users see
        # the active planning context before today's execution data.
        _today_polar_data(sessions)
        _today_training_details(connection, sessions)
        if not sessions:
            st.info(text("no_actual"))

    with execution_tab:
        _render_training_history_tab(connection, sessions, training_notice, selected_cycle)
        _render_training_baseline()
        _render_training_guidance()


def _polar_sport_type(session):
    """Return the Polar-authoritative display name used across training views."""
    return (
        session.get("polar_sport_display")
        or session.get("sport_display")
        or session.get("polar_sport_type")
        or TR("common.no_data")
    )


def _is_strength_training_session(session):
    """Return whether Polar identified this session as strength training."""
    values = (
        session.get("polar_sport_type"),
        session.get("polar_sport_display"),
        session.get("sport_display"),
    )
    for value in values:
        text = str(value or "").strip().casefold()
        if text == "15" or "力量" in text or "strength" in text:
            return True
    return False


def _sport_type_heading():
    return _ui("运动类型", "Sport Type")


def _render_outdoor_plan_directory(connection):
    """Render the independent outdoor running/jumping cycle and weekly plan."""
    text = _plan_actual_text
    domain = "outdoor_running_jumping"
    state_prefix = "outdoor_plan"
    cycles = list_training_cycles(connection, training_domain=domain)

    # Keep the athletics cycle directory consistent with strength: it always
    # starts folded, including after leaving and returning to this page.
    outdoor_cycle_open = False
    outdoor_cycle_directory = st.expander(
        text("outdoor_running_jumping_cycle"),
        expanded=outdoor_cycle_open,
    )
    with outdoor_cycle_directory:
        cycle_options = [None] + [item["id"] for item in cycles]
        current_cycle = get_current_training_cycle(connection, training_domain=domain)
        current_cycle_id = current_cycle["id"] if current_cycle else None
        selected_cycle_state = st.session_state.get(f"{state_prefix}_cycle_filter")
        if current_cycle_id and selected_cycle_state in (None, ""):
            st.session_state[f"{state_prefix}_cycle_filter"] = current_cycle_id
        elif selected_cycle_state not in cycle_options:
            st.session_state[f"{state_prefix}_cycle_filter"] = current_cycle_id
        selected_cycle = st.selectbox(
            text("select_cycle"), cycle_options,
            format_func=lambda value: text("no_plans") if value is None else next(
                item["name"] for item in cycles if item["id"] == value
            ), key=f"{state_prefix}_cycle_filter",
        )
        selected_cycle_record = next(
            (item for item in cycles if item["id"] == selected_cycle), None
        )
        if selected_cycle_record:
            edited_name = st.text_input(
                text("edit_cycle_name"), value=selected_cycle_record["name"],
                key=f"{state_prefix}_cycle_name_{selected_cycle}",
            )
            detail_start = date.fromisoformat(selected_cycle_record["start_date"])
            detail_end = date.fromisoformat(selected_cycle_record["end_date"])
            detail_weeks = ((detail_end - detail_start).days + 1) / 7
            detail_fields = st.columns(3, vertical_alignment="top")
            edited_start = detail_fields[0].date_input(
                text("start_date"), value=detail_start,
                key=f"{state_prefix}_cycle_start_{selected_cycle}",
            )
            edited_duration_weeks = detail_fields[1].number_input(
                text("duration_weeks"), min_value=1, value=int(detail_weeks), step=1,
                format="%d", key=f"{state_prefix}_cycle_duration_weeks_{selected_cycle}",
            )
            edited_end = cycle_end_date_for_weeks(edited_start, edited_duration_weeks)
            detail_fields[2].markdown(
                f"<div class='drc-cycle-field-label'>{escape(text('cycle_end_date'))}</div>",
                unsafe_allow_html=True,
            )
            detail_fields[2].markdown(
                f"<div class='drc-cycle-field-value'>{escape(edited_end.strftime('%Y/%m/%d'))}</div>",
                unsafe_allow_html=True,
            )
            cycle_details_directory = st.expander(
                text("view_details"),
                expanded=outdoor_cycle_open,
            )
        else:
            st.info(text("no_cycle_selected"))

        confirm_cycle_delete = st.checkbox(
            text("confirm_delete_cycle"),
            key=f"{state_prefix}_confirm_delete_cycle_{selected_cycle or 'none'}",
            disabled=selected_cycle is None,
        )
        show_cycle_creator = st.session_state.get(f"{state_prefix}_show_create_cycle", False)
        cycle_action_columns = st.columns(4)
        if cycle_action_columns[0].button(
            text("delete_cycle"), key=f"{state_prefix}_delete_cycle",
            disabled=selected_cycle is None or not confirm_cycle_delete,
        ):
            try:
                delete_training_cycle(connection, selected_cycle)
                for state_key in (
                    f"{state_prefix}_matrix_date", f"{state_prefix}_matrix_module",
                    f"{state_prefix}_matrix_session_id", f"{state_prefix}_matrix_focus_nonce",
                    f"{state_prefix}_matrix_last_focus_nonce",
                    f"{state_prefix}_editing", f"{state_prefix}_inline_type_date",
                ):
                    st.session_state.pop(state_key, None)
                st.session_state[f"{state_prefix}_save_notice"] = text("cycle_deleted")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if cycle_action_columns[1].button(
            text("copy_previous_week"), key=f"{state_prefix}_copy_previous_week",
            disabled=selected_cycle_record is None,
        ):
            current_period = current_cycle_week_segment(selected_cycle_record)
            if not current_period:
                st.info(text("no_current_cycle_period"))
            else:
                copy_result = copy_previous_week_training_content(
                    connection, current_period["matrix_week_start"], cycle_id=selected_cycle,
                )
                if copy_result["copied_session_count"]:
                    notice_key = (
                        "previous_week_copy_partial"
                        if copy_result["skipped_date_count"] else "previous_week_copy_success"
                    )
                    st.session_state[f"{state_prefix}_save_notice"] = text(notice_key).format(
                        count=copy_result["copied_session_count"],
                        skipped=copy_result["skipped_date_count"],
                    )
                elif copy_result["source_session_count"]:
                    st.session_state[f"{state_prefix}_save_notice"] = text("previous_week_copy_exists")
                else:
                    st.session_state[f"{state_prefix}_save_notice"] = text("no_previous_week_content")
                st.rerun()
        if not show_cycle_creator and cycle_action_columns[2].button(
            text("new_cycle"), key=f"{state_prefix}_open_cycle_creator"
        ):
            st.session_state[f"{state_prefix}_show_create_cycle"] = True
            st.rerun()
        if show_cycle_creator:
            st.markdown(
                f"<div class='drc-cycle-section-title'>{escape(text('new_cycle'))}</div>",
                unsafe_allow_html=True,
            )
            name = st.text_input(text("cycle_name"), key=f"{state_prefix}_cycle_name")
            cycle_fields = st.columns(3)
            start = cycle_fields[0].date_input(
                text("start_date"), value=date.today(), key=f"{state_prefix}_cycle_start"
            )
            duration_weeks = cycle_fields[1].number_input(
                text("duration_weeks"), min_value=1, value=1, step=1, format="%d",
                key=f"{state_prefix}_cycle_duration_weeks",
            )
            end = cycle_end_date_for_weeks(start, duration_weeks)
            cycle_fields[2].markdown(
                f"<div class='drc-cycle-field-label'>{escape(text('end_date'))}</div>",
                unsafe_allow_html=True,
            )
            cycle_fields[2].markdown(
                f"<div class='drc-cycle-field-value'>{escape(end.strftime('%Y/%m/%d'))}</div>",
                unsafe_allow_html=True,
            )
            notes = st.text_input(text("cycle_notes"), key=f"{state_prefix}_cycle_notes")
            if st.button(text("create_cycle"), key=f"{state_prefix}_create_cycle"):
                try:
                    create_training_cycle(
                        connection, name, start, end, notes=notes,
                        training_domain=domain,
                    )
                    st.session_state[f"{state_prefix}_show_create_cycle"] = False
                    st.session_state[f"{state_prefix}_save_notice"] = text("created")
                    st.rerun()
                except ValueError as exc:
                    error_key = {
                        "CYCLE_MIN_ONE_WEEK": "minimum_cycle_week",
                        "INVALID_CYCLE_DURATION": "invalid_cycle_duration",
                    }.get(str(exc))
                    st.error(text(error_key) if error_key else str(exc))
        if selected_cycle_record and cycle_action_columns[3].button(
            text("save_changes"), key=f"{state_prefix}_save_cycle_{selected_cycle}"
        ):
            try:
                update_training_cycle(
                    connection, selected_cycle, name=edited_name,
                    start_date=edited_start, end_date=edited_end,
                )
                st.session_state[f"{state_prefix}_save_notice"] = text("cycle_updated")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if not selected_cycle_record:
            cycle_details_directory = outdoor_cycle_directory

    save_notice = st.session_state.pop(f"{state_prefix}_save_notice", None)
    planned_sessions = (
        list_planned_sessions(connection, cycle_id=selected_cycle)
        if selected_cycle else list_planned_sessions(connection, training_domain=domain)
    )
    plan_directory = cycle_details_directory
    outdoor_plan_focus_target_id = f"{state_prefix}-plan-table-target"
    plan_directory.markdown(
        f"<div id='{outdoor_plan_focus_target_id}'></div>",
        unsafe_allow_html=True,
    )
    outdoor_plan_table_focus_nonce = st.session_state.get(
        f"{state_prefix}_plan_table_focus_nonce", 0
    )
    outdoor_plan_table_last_focus_nonce = st.session_state.get(
        f"{state_prefix}_plan_table_last_focus_nonce", 0
    )
    if outdoor_plan_table_focus_nonce > outdoor_plan_table_last_focus_nonce:
        render_interaction_focus(
            components,
            target_id=outdoor_plan_focus_target_id,
            nonce=outdoor_plan_table_focus_nonce,
        )
        st.session_state[f"{state_prefix}_plan_table_last_focus_nonce"] = (
            outdoor_plan_table_focus_nonce
        )
    current_period = (
        _cycle_week_selector(
            selected_cycle_record,
            state_key=f"{state_prefix}_cycle_week_{selected_cycle}",
            container=plan_directory,
        )
        if selected_cycle_record else None
    )
    if current_period:
        week_start = date.fromisoformat(current_period["matrix_week_start"])
    else:
        first_plan_date = min(
            (date.fromisoformat(item["planned_date"]) for item in planned_sessions),
            default=date.today(),
        )
        week_start = first_plan_date - timedelta(days=first_plan_date.weekday())
    week_dates = [week_start + timedelta(days=index) for index in range(7)]
    sessions_by_date = {
        day.isoformat(): [item for item in planned_sessions if item["planned_date"] == day.isoformat()]
        for day in week_dates
    }
    date_header = plan_directory.columns([1.35] + [1] * 7)
    date_header[0].markdown(
        f"<div class='drc-plan-actual-label'>{escape(text('planned_date'))}</div>",
        unsafe_allow_html=True,
    )
    for column, day in zip(date_header[1:], week_dates):
        column.markdown(
            f"<div class='drc-plan-actual-label drc-plan-actual-date'>{day.strftime('%Y/%-m/%-d')}</div>",
            unsafe_allow_html=True,
        )
    weekday_header = plan_directory.columns([1.35] + [1] * 7)
    weekday_header[0].markdown(
        f"<div class='drc-plan-actual-label'>{escape(text('time'))}</div>",
        unsafe_allow_html=True,
    )
    for column, weekday_key in zip(weekday_header[1:], PLAN_ACTUAL_WEEKDAY_KEYS):
        column.markdown(
            f"<div class='drc-plan-actual-label drc-plan-actual-weekday'>{escape(text(weekday_key))}</div>",
            unsafe_allow_html=True,
        )
    for module_key in OUTDOOR_PLAN_MODULES:
        row = plan_directory.columns([1.35] + [1] * 7)
        label = escape(text(f"outdoor_module_{module_key}"))
        row[0].markdown(
            f"<div class='drc-plan-actual-label drc-plan-actual-module'>{label}</div>",
            unsafe_allow_html=True,
        )
        for column, day in zip(row[1:], week_dates):
            day_sessions = sessions_by_date[day.isoformat()]
            exercises = [
                exercise for session in day_sessions for exercise in session["exercises"]
                if _outdoor_plan_module_key(exercise.get("module_key")) == module_key
            ]
            if column.button(
                _outdoor_plan_cell_text(exercises),
                key=(
                    f"{state_prefix}_matrix_cell_"
                    f"{'filled' if exercises else 'empty'}_{day.isoformat()}_{module_key}"
                ),
                use_container_width=True,
            ):
                module_session = next(
                    (
                        session for session in day_sessions
                        if any(
                            _outdoor_plan_module_key(exercise.get("module_key")) == module_key
                            for exercise in session["exercises"]
                        )
                    ),
                    None,
                )
                st.session_state[f"{state_prefix}_matrix_date"] = day.isoformat()
                st.session_state[f"{state_prefix}_matrix_module"] = module_key
                st.session_state[f"{state_prefix}_matrix_session_id"] = module_session["id"] if module_session else None
                st.session_state[f"{state_prefix}_editing"] = True
                st.session_state[f"{state_prefix}_matrix_focus_nonce"] = (
                    st.session_state.get(f"{state_prefix}_matrix_focus_nonce", 0) + 1
                )
                st.rerun()

    selected_date = st.session_state.get(f"{state_prefix}_matrix_date")
    selected_module = st.session_state.get(f"{state_prefix}_matrix_module")
    if st.session_state.get(f"{state_prefix}_editing") and selected_date and selected_module:
        day_sessions = sessions_by_date.get(selected_date, [])
        selected_session_id = st.session_state.get(f"{state_prefix}_matrix_session_id")
        selected_session = next((item for item in day_sessions if item["id"] == selected_session_id), None)
        if selected_session is None:
            selected_session = next(
                (
                    item for item in day_sessions
                    if any(
                        _outdoor_plan_module_key(exercise.get("module_key")) == selected_module
                        for exercise in item["exercises"]
                    )
                ),
                None,
            )
        with st.container(border=True):
            focus_nonce = st.session_state.get(f"{state_prefix}_matrix_focus_nonce", 0)
            last_focus_nonce = st.session_state.get(f"{state_prefix}_matrix_last_focus_nonce", 0)
            focus_target_id = f"{state_prefix}-edit-focus-target"
            st.markdown(f"<div id='{focus_target_id}'></div>", unsafe_allow_html=True)
            if focus_nonce > last_focus_nonce:
                render_interaction_focus(
                    components, target_id=focus_target_id, nonce=focus_nonce, top_offset=96,
                )
                st.session_state[f"{state_prefix}_matrix_last_focus_nonce"] = focus_nonce
            current_type = _outdoor_plan_training_type_key(selected_module)
            # Keep the outdoor editor aligned with its matrix card, which
            # aggregates a module across every session on the selected day.
            module_sessions = [
                item for item in day_sessions
                if any(
                    _outdoor_plan_module_key(exercise.get("module_key")) == selected_module
                    for exercise in item["exercises"]
                )
            ]
            module_exercises = [
                exercise
                for session in module_sessions
                for exercise in session["exercises"]
                if _outdoor_plan_module_key(exercise.get("module_key")) == selected_module
            ]
            recent_defaults = {
                _outdoor_plan_action_name(action_name): defaults
                for action_name, defaults in recent_outdoor_action_defaults(
                    connection, selected_module
                ).items()
            }
            action_options = _recent_first_action_options([
                *[
                    _outdoor_plan_action_name(
                        item.get("exercise_display_name") or item.get("exercise_canonical_name")
                    )
                    for item in module_exercises
                ],
                *OUTDOOR_PLAN_ACTIONS.get(selected_module, ()),
            ], recent_defaults)
            action_picker_key = (
                f"{state_prefix}_actions_{selected_session['id']}"
                if selected_session else f"{state_prefix}_actions_{selected_date}_{selected_module}"
            )
            action_picker_context_key = (
                f"{selected_date}:{selected_module}:"
                f"{selected_session['id'] if selected_session else 'new'}:{focus_nonce}"
            )
            action_picker_context_state_key = f"{state_prefix}_action_picker_context"
            action_picker_context_changed = (
                st.session_state.get(action_picker_context_state_key)
                != action_picker_context_key
            )
            if action_picker_context_changed or action_picker_key not in st.session_state:
                st.session_state[action_picker_key] = [
                    name for name in dict.fromkeys(
                        _outdoor_plan_action_name(
                            item.get("exercise_display_name") or item.get("exercise_canonical_name")
                        )
                        for item in module_exercises
                    ) if name
                ]
            else:
                st.session_state[action_picker_key] = list(dict.fromkeys(
                    _outdoor_plan_action_name(action_name)
                    for action_name in st.session_state[action_picker_key]
                    if _outdoor_plan_action_name(action_name) in action_options
                ))
            st.session_state[action_picker_context_state_key] = action_picker_context_key
            selected_actions = st.multiselect(
                text("exercise_multi_name"), action_options, key=action_picker_key,
                help=text("select_multiple_actions"), placeholder=" ",
            )
            st.markdown(
                f"<div class='drc-plan-action-selection'><strong>{len(selected_actions)}</strong>"
                f"{escape(text('selected_actions_count'))}</div>", unsafe_allow_html=True,
            )
            existing_by_name = {
                _outdoor_plan_action_name(
                    item.get("exercise_display_name") or item.get("exercise_canonical_name")
                ): item
                for item in module_exercises
            }
            for action_name in selected_actions:
                exercise = existing_by_name.get(action_name, {})
                learned = recent_defaults.get(action_name, {})
                exercise_key = str(exercise.get("id") or action_name)
                row = st.columns((2.5, 1, 1), vertical_alignment="center")
                row[0].markdown(
                    f"<div class='drc-plan-actual-action-name'>{escape(action_name)}</div>",
                    unsafe_allow_html=True,
                )
                row[1].number_input(
                    text("sets"), min_value=1,
                    value=int(exercise.get("target_sets") if exercise.get("target_sets") is not None else exercise.get("target_reps") if exercise.get("target_reps") is not None else learned.get("target_sets") or 1), step=1,
                    key=f"{state_prefix}_sets_{selected_date}_{selected_module}_{exercise_key}",
                )
                row[2].number_input(
                    text("distance"), min_value=0.0,
                    value=float(exercise.get("target_distance_meters") if exercise.get("target_distance_meters") is not None else learned.get("target_distance_meters") or 0.0), step=10.0,
                    key=f"{state_prefix}_distance_{selected_date}_{selected_module}_{exercise_key}",
                )
            if save_notice:
                st.success(save_notice)
            if st.button(
                text("save_changes"), key=f"{state_prefix}_save_actions_{selected_date}_{selected_module}",
            ):
                if selected_session is None and selected_cycle is None:
                    st.warning(text("select_cycle_first"))
                elif not selected_actions and not module_exercises:
                    for state_key in (
                        f"{state_prefix}_matrix_date",
                        f"{state_prefix}_matrix_module",
                        f"{state_prefix}_matrix_session_id",
                        f"{state_prefix}_matrix_focus_nonce",
                        f"{state_prefix}_matrix_last_focus_nonce",
                        f"{state_prefix}_editing",
                    ):
                        st.session_state.pop(state_key, None)
                    st.session_state[f"{state_prefix}_save_notice"] = text("saved")
                    st.rerun()
                else:
                    session_name = f"{_outdoor_plan_type_label(current_type)} · {text(f'outdoor_module_{selected_module}') }"
                    if selected_session:
                        session_id = selected_session["id"]
                        update_planned_session(connection, session_id, session_name=session_name, training_type=current_type)
                    else:
                        session_id = create_planned_session(
                            connection, selected_date, session_name, current_type, cycle_id=selected_cycle,
                        )
                    for exercise in module_exercises:
                        name = _outdoor_plan_action_name(
                            exercise.get("exercise_display_name")
                            or exercise.get("exercise_canonical_name")
                        )
                        if name not in selected_actions:
                            delete_planned_exercise(connection, exercise["id"])
                    for action_name in selected_actions:
                        exercise = existing_by_name.get(action_name)
                        exercise_key = str(exercise.get("id") or action_name) if exercise else action_name
                        sets = st.session_state[f"{state_prefix}_sets_{selected_date}_{selected_module}_{exercise_key}"]
                        distance = st.session_state[f"{state_prefix}_distance_{selected_date}_{selected_module}_{exercise_key}"]
                        if exercise:
                            update_planned_exercise(
                                connection, exercise["id"], exercise_canonical_name=action_name,
                                exercise_display_name=action_name, target_sets=sets,
                                target_distance_meters=distance,
                            )
                        else:
                            create_planned_exercise(
                                connection, session_id, canonical_name=action_name,
                                display_name=action_name, target_sets=sets,
                                target_distance=distance,
                                module_key=selected_module,
                            )
                    for state_key in (
                        f"{state_prefix}_matrix_date",
                        f"{state_prefix}_matrix_module",
                        f"{state_prefix}_matrix_session_id",
                        f"{state_prefix}_matrix_focus_nonce",
                        f"{state_prefix}_matrix_last_focus_nonce",
                        f"{state_prefix}_editing",
                    ):
                        st.session_state.pop(state_key, None)
                    st.session_state[f"{state_prefix}_save_notice"] = text("saved")
                    st.rerun()
    if save_notice and not (selected_date and selected_module):
        st.success(save_notice)


def _historical_training_cycles(connection):
    """Render completed or elapsed cycles alongside the training history."""
    today = date.today()
    cycles = [
        cycle for cycle in list_training_cycles(connection, include_archived=True)
        if cycle["status"] in {"completed", "archived"}
        or date.fromisoformat(cycle["end_date"]) < today
    ]
    with st.expander(_ui("历史训练周期", "Training Cycle History"), expanded=False):
        if not cycles:
            st.info(TR("common.no_data"))
            return
        rows = []
        for cycle in cycles:
            start = date.fromisoformat(cycle["start_date"])
            end = date.fromisoformat(cycle["end_date"])
            duration_weeks = (end - start).days / 7 + 1 / 7
            duration_display = (
                str(int(duration_weeks))
                if duration_weeks.is_integer()
                else f"{duration_weeks:.1f}"
            )
            rows.append({
                _ui("周期名称", "Cycle Name"): cycle["name"],
                _ui("开始日期", "Start Date"): format_date(start, LANGUAGE),
                _ui("持续周数", "Duration (weeks)"): duration_display,
                _ui("结束日期", "End Date"): format_date(end, LANGUAGE),
            })
        centered_dataframe(rows)


def _history(connection, sessions):
    _historical_training_cycles(connection)
    with st.expander(TR("history.activity_title"), expanded=False):
        history_view_label = _ui("查看", "View")
        rows = []
        for item in sessions:
            rows.append({
                TR("reports.date"): format_date(item["date"], LANGUAGE),
                TR("training_logging.start_time"): time_to_hms(item.get("start_time")),
                TR("domain.exercise.sport"): _polar_sport_type(item),
                TR("domain.exercise.duration"): minutes_to_hms(
                    item["duration_seconds"] / 60 if item.get("duration_seconds") is not None else None
                ),
                TR("domain.exercise.average_hr"): item.get("average_hr"),
                TR("domain.exercise.maximum_hr"): item.get("max_hr"),
                TR("domain.exercise.calories"): item.get("calories"),
                TR("training_logging.data_source"): _session_source(item),
                TR("domain.exercise.title"): TR("training_logging.view_edit"),
            })
        if rows:
            # Render the table row-by-row so the action cell contains a real
            # Streamlit button rather than plain text in the read-only HTML table.
            headers = list(rows[0].keys())
            widths = [1.0, .9, 1.25, 1.0, .8, .8, .8, 1.0, 1.2]
            # Keep the familiar table layout while limiting the visible viewport
            # to roughly seven rows. Older records remain available by scrolling.
            with st.container(height=430, border=True):
                header_columns = st.columns(widths)
                for column, label in zip(header_columns, headers):
                    header_html = f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>'
                    column.markdown(header_html, unsafe_allow_html=True)
                for item, row in zip(sessions, rows):
                    columns = st.columns(widths, vertical_alignment="center")
                    for column, label in zip(columns[:-1], headers[:-1]):
                        cell_html = f'<div style="text-align:center;">{escape(str(row[label]))}</div>'
                        column.markdown(cell_html, unsafe_allow_html=True)
                    if columns[-1].button(
                        history_view_label,
                        key=f"training_history_view_{item['id']}",
                        use_container_width=True,
                    ):
                        st.session_state["training_history_selected"] = item["id"]
                        st.session_state["training_details_focus_nonce"] = (
                            st.session_state.get("training_details_focus_nonce", 0) + 1
                        )
                        st.rerun()
        else:
            st.info(TR("common.no_data"))


DEVELOPMENT_STRENGTH_OPTIONS = (
    "上肢拉力",
    "下肢推力",
    "上肢推力",
    "下肢拉力",
    "伤病预防类训练",
)
LEGACY_ACTIVE_RECOVERY_TYPE = "主动恢复"
CUSTOM_DEVELOPMENT_STRENGTH_TYPE = "__custom_development_strength_type__"

DEVELOPMENT_STRENGTH_ACTION_NAMES = {
    "上肢拉力": (
        "跪姿胸椎伸展",
        "胸椎向内旋转",
        "胸椎向外旋转",
        "抗屈伸－腹肌轮滚动",
        "抗旋转－哑铃平板划船",
        "抗侧屈－罗马椅杠铃片伸展",
        "超负荷垂直拉",
        "超负荷水平拉",
        "直角杠铃划船",
        "爆发正手引体向上",
        "爆发正手引体向上接单手上摸",
        "爆发单手哑铃划船",
        "爆发反向吊环划船",
        "双手弹力带垂直拉",
        "单手弹力带垂直拉",
        "单手爆发吊环反向划船",
        "正手引体向上",
        "对握引体向上",
        "负重吊环反向划船",
        "小袖抓把高位下拉",
        "小袖抓把宽距坐姿划船",
        "跪姿单臂绳索下拉",
        "单手哑铃划船",
        "Y-T-W伸展",
        "水平旋转－绳索旋转",
        "杠铃手腕正向弯举",
        "杠铃手腕反向弯举",
    ),
    "下肢推力": (
        "单膝跪姿侧向伸展",
        "站姿髋关节弯曲",
        "单膝跪姿前后伸展",
        "根本哈根腿支撑",
        "侧平板腿支撑抬腿",
        "抗屈伸－杠铃负重屈伸",
        "抗侧屈－杠铃负重早安式",
        "抗侧屈－杠铃负重侧屈伸",
        "超负荷半蹲",
        "超负荷中腿拉",
        "速度跳深",
        "杠铃高翻",
        "杠铃挺举高拉",
        "杠铃高翻分腿接杠",
        "杠铃后蹲",
        "杠铃前蹲",
        "杠铃保加利亚蹲",
        "杠铃单腿蹬台阶",
        "杠铃片站姿单侧抬腿",
        "单腿坐姿器械腿屈伸",
        "下至上旋转－杠铃片蹬转上箱",
        "杠铃片单手抛握",
        "杠铃片单手静握",
    ),
    "上肢推力": (
        "跪姿胸椎伸展",
        "胸椎向内旋转",
        "胸椎向外旋转",
        "抗屈伸－杠铃片死虫上举",
        "抗旋转－站姿绳索直臂推",
        "抗侧屈－侧支撑哑铃上提",
        "超负荷垂直推",
        "超负荷水平推",
        "击掌俯卧撑",
        "颈后借力推",
        "弓步单手弹力带推胸",
        "弓步单手哑铃推",
        "爆发杠铃卧推",
        "双手炮筒推肩",
        "偏载哑铃卧推",
        "单手炮筒推肩",
        "杠铃卧推",
        "杠铃实力推",
        "双杠臂屈伸",
        "负重正手俯卧撑",
        "跪姿炮筒推肩",
        "偏载哑铃平板卧推",
        "杠铃片大飞鸟",
        "水平旋转－弹力带旋转",
        "杠铃片手腕弯举",
    ),
    "下肢拉力": (
        "单膝跪姿侧向伸展",
        "站姿髋关节弯曲",
        "单膝跪姿前后伸展",
        "根本哈根腿支撑",
        "侧平板腿支撑抬腿",
        "抗屈伸－杠铃负重屈伸",
        "抗侧屈－杠铃负重早安式",
        "抗侧屈－杠铃负重侧屈伸",
        "超负荷半蹲",
        "超负荷中腿拉",
        "坐姿起跳",
        "杠铃悬垂高翻",
        "杠铃悬垂挺举高拉",
        "杠铃高翻腿接杠",
        "杠铃挺举硬拉",
        "杠铃抓举硬拉",
        "杠铃臀推",
        "杠铃分腿拉",
        "杠铃后退弓箭步",
        "杠铃跪姿伸髋",
        "北欧挺",
        "上至下旋转－弹力带下劈",
        "杠铃杆卷腕",
    ),
    "伤病预防类训练": (
        "跪姿胸椎伸展",
        "胸椎向内旋转",
        "胸椎向外旋转",
        "单膝跪姿侧向伸展",
        "站姿髋关节弯曲",
        "单膝跪姿前后伸展",
        "山羊挺身",
        "反向山羊挺身",
        "悬垂举腿",
        "动态超负荷西班牙蹲",
        "静态超负荷西班牙蹲",
        "双侧哑铃动态分腿蹲",
        "双侧哑铃负重下台阶",
        "坐姿提踵",
        "踝关节背屈",
        "抗旋转－半跪姿绳索下劈",
        "上至下旋转－弓步绳索下劈",
        "抗旋转－半跪姿绳索上砍",
        "下至上旋转－哑铃上砍",
    ),
}

ACTION_NAME_OPTIONS = {
    "关节活动度训练": (
        "跪姿胸椎伸展",
        "胸椎向内旋转",
        "胸椎向外旋转",
        "单膝跪姿侧向伸展",
        "站姿髋关节弯曲",
        "单膝跪姿前后伸展",
        "侧平板腿支撑抬腿",
    ),
    "核心力量激活训练": (
        "抗屈伸-腹肌轮滚动",
        "抗旋转-哑铃平板划船",
        "抗侧屈-罗马椅杠铃片伸展",
        "抗屈伸-杠铃负重屈伸",
        "抗侧屈-杠铃负重早安式",
        "抗侧屈-杠铃负重侧屈伸",
        "抗屈伸-杠铃片死虫上举",
        "抗旋转-站姿绳索直臂推",
        "抗侧屈-侧支撑哑铃上提",
    ),
    "等长超负荷训练": (
        "超负荷垂直拉",
        "超负荷水平拉",
        "超负荷半蹲",
        "超负荷中腿拉",
        "超负荷垂直推",
        "超负荷水平推",
    ),
    "爆发性力量训练": (
        "直角杠铃划船",
        "爆发正手引体向上",
        "爆发单手哑铃划船",
        "爆发反向吊环划船",
        "速度跳深",
        "杠铃高翻",
        "杠铃挺举高拉",
        "杠铃高翻分腿接杠",
        "击掌俯卧撑",
        "颈后借力推",
        "坐姿起跳",
        "杠铃悬垂高翻",
        "杠铃悬垂挺举高拉",
        "杠铃高翻腿接杠",
        "爆发正手引体向上接单手上摸",
        "单手哑铃划船",
        "弓步单手弹力带推胸",
        "弓步单手哑铃推",
    ),
    "整体性力量训练-主项": (
        "正手引体向上",
        "对握引体向上",
        "负重吊环反向划船",
        "小袖抓把高位下拉",
        "小袖抓把宽距坐姿划船",
        "杠铃后蹲",
        "杠铃前蹲",
        "杠铃卧推",
        "杠铃实力推",
        "双杠臂屈伸",
        "负重正手俯卧撑",
        "杠铃挺举硬拉",
        "杠铃抓举硬拉",
        "杠铃臀推",
        "山羊挺身",
        "反向山羊挺身",
        "悬垂举腿",
    ),
    "整体性力量训练-副项": (
        "跪姿单臂绳索下拉",
        "单手哑铃划船",
        "Y-T-W伸展",
        "杠铃保加利亚蹲",
        "杠铃单腿蹬台阶",
        "杠铃片站姿单侧抬腿",
        "单腿坐姿器械腿屈伸",
        "跪姿炮筒推肩",
        "偏载哑铃平板卧推",
        "杠铃片大飞鸟",
        "杠铃分腿拉",
        "杠铃后退弓箭步",
        "杠铃跪姿伸髋",
        "北欧挺",
        "动态超负荷西班牙蹲",
        "静态超负荷西班牙蹲",
        "双侧哑铃动态分腿蹲",
        "双侧哑铃负重下台阶",
        "坐姿提踵",
        "踝关节背屈",
    ),
    "小肌肉群力量训练": (
        "水平旋转-绳索旋转",
        "杠铃手腕正向弯举",
        "杠铃手腕反向弯举",
        "下至上旋转-杠铃片蹬转上箱",
        "杠铃片单手抛握",
        "杠铃片单手静握",
        "水平旋转-弹力带旋转",
        "杠铃片手腕弯举",
        "上至下旋转-弹力带下劈",
        "杠铃杆卷腕",
        "抗旋转-半跪姿绳索下劈",
        "上至下旋转-弓步绳索下劈",
        "抗旋转-半跪姿绳索上砍",
        "下至上旋转-哑铃上砍",
    ),
}


def _action_name_key(name):
    """Compare stored action names while tolerating full-width dashes."""
    return str(name or "").replace("－", "-").replace("—", "-").replace("–", "-").replace(" ", "")


def _plan_module_action_options(module_key, development_type, stored_names=(), learned_defaults=None):
    """Return actions matching both the strength module and development type."""
    action_type = PLAN_MODULE_ACTION_TYPES[module_key]
    allowed_names = DEVELOPMENT_STRENGTH_ACTION_NAMES.get(development_type, ())
    allowed_keys = {_action_name_key(name) for name in allowed_names}
    module_names = [
        name for name in ACTION_NAME_OPTIONS.get(action_type, ())
        if _action_name_key(name) in allowed_keys
    ]
    learned_names = (learned_defaults or {}).keys()
    names = []
    for name in [*stored_names, *learned_names, *module_names]:
        if name and _action_name_key(name) in allowed_keys and name not in names:
            names.append(name)
    return names


def _action_name_options(
    action_type, session_id, stored_names=(), development_type=None
):
    """Return names allowed by the selected development-strength type.

    Standard types deliberately do not merge in the session's remembered
    names.  That state can contain actions selected before the type changed,
    and merging it here makes an upper-push editor display upper-pull actions.
    Only user-created development types may use the reusable catalog and
    remembered custom names.
    """
    saved_key = f"today_action_names_{session_id}_{action_type}"
    saved_names = st.session_state.get(saved_key, [])
    if development_type in DEVELOPMENT_STRENGTH_ACTION_NAMES:
        source_names = list(DEVELOPMENT_STRENGTH_ACTION_NAMES[development_type])
        return list(dict.fromkeys(source_names)), saved_key

    source_names = [*stored_names, *saved_names]
    names = []
    for name in source_names:
        if name and name not in names:
            names.append(name)
    return names, saved_key


def _development_action_rows(rows_by_development, development_type):
    """Return the independent editable action list for one development type."""
    return rows_by_development.setdefault(development_type, [])


def _development_action_match_score(rows, development_type):
    """Count rows that belong to a standard development-strength type."""
    allowed = {
        _action_name_key(name)
        for name in DEVELOPMENT_STRENGTH_ACTION_NAMES.get(development_type, ())
    }
    return sum(
        1 for row in (rows or [])
        if _action_name_key(row.get("name")) in allowed
    )


def _infer_development_type_for_rows(rows, preferred=None):
    """Infer the standard type from stored action names when state is stale."""
    preferred = str(preferred or "").strip()
    scores = {
        development_type: _development_action_match_score(rows, development_type)
        for development_type in DEVELOPMENT_STRENGTH_OPTIONS
    }
    best_score = max(scores.values(), default=0)
    if best_score <= 0:
        return preferred if preferred in scores else None
    if preferred in scores and scores[preferred] == best_score:
        return preferred
    return max(
        DEVELOPMENT_STRENGTH_OPTIONS,
        key=lambda development_type: scores[development_type],
    )


def _normalize_development_action_rows(rows_by_development):
    """Move a clearly misclassified standard-type bucket to its matching type.

    Older sessions could retain the action rows from one type while the type
    selectbox had already changed to another. Normalize only when the best
    matching type is substantially stronger than the current bucket; this
    keeps intentionally custom actions in place.
    """
    normalized = {
        key: list(rows or []) for key, rows in (rows_by_development or {}).items()
    }
    for development_type in DEVELOPMENT_STRENGTH_OPTIONS:
        normalized.setdefault(development_type, [])

    for current_type in DEVELOPMENT_STRENGTH_OPTIONS:
        current_rows = normalized.get(current_type, [])
        if not current_rows:
            continue
        scores = {
            development_type: _development_action_match_score(
                current_rows, development_type
            )
            for development_type in DEVELOPMENT_STRENGTH_OPTIONS
        }
        best_type = max(
            DEVELOPMENT_STRENGTH_OPTIONS,
            key=lambda development_type: scores[development_type],
        )
        current_score = scores[current_type]
        best_score = scores[best_type]
        clearly_misclassified = (
            best_type != current_type
            and best_score > current_score
            and (
                current_score == 0
                or best_score >= max(2, current_score * 2)
            )
        )
        if clearly_misclassified:
            target_rows = normalized.setdefault(best_type, [])
            target_ids = {
                str(row.get("id")) for row in target_rows if row.get("id")
            }
            target_names = {
                _action_name_key(row.get("name"))
                for row in target_rows
                if _action_name_key(row.get("name"))
            }
            for row in current_rows:
                row_id = str(row.get("id")) if row.get("id") else ""
                row_name = _action_name_key(row.get("name"))
                if (row_id and row_id in target_ids) or (
                    row_name and row_name in target_names
                ):
                    continue
                target_rows.append(row)
                if row_id:
                    target_ids.add(row_id)
                if row_name:
                    target_names.add(row_name)
            normalized[current_type] = []
    return normalized


def _add_development_action(rows, row):
    """Add exactly one action to the current development type."""
    rows.append(row)


def _remove_development_action(rows):
    """Remove only the final action from the current development type."""
    if not rows:
        return False
    rows.pop()
    return True


def _recommended_action_name(rows, action_names):
    """Recommend the first catalog action, then the action after the last one."""
    names = [str(name).strip() for name in (action_names or []) if str(name).strip()]
    if not names:
        return ""
    if not rows:
        return names[0]
    previous_name = str(rows[-1].get("name") or "").strip()
    if previous_name in names:
        return names[(names.index(previous_name) + 1) % len(names)]
    return names[0]


def _clone_development_action_rows(rows_by_development):
    """Copy the complete development-type/action model with fresh row ids."""
    return {
        development_type: [
            {
                "id": _uuid(),
                "name": row.get("name") or "",
                "sets": int(row.get("sets") or 1),
                "reps": int(row.get("reps") or 0),
                "load": float(row.get("load") or 0.0),
            }
            for row in rows
        ]
        for development_type, rows in (rows_by_development or {}).items()
    }


def _action_rows_from_training_exercises(exercises, development_type, catalog):
    """Convert legacy structured exercises into the current compact row model."""
    rows = []
    for exercise in exercises or []:
        catalog_item = catalog.get(exercise.get("exercise_catalog_id"))
        name = (
            _catalog_name(catalog_item) if catalog_item else
            exercise.get("custom_exercise_name") or ""
        )
        sets = exercise.get("sets") or []
        first_set = next((item for item in sets if isinstance(item, dict)), {})
        rows.append({
            "id": _uuid(),
            "name": name,
            "sets": max(len(sets), 1),
            "reps": int(first_set.get("reps") or 0),
            "load": float(first_set.get("load_value") or 0.0),
        })
    return rows


def _polar_training_data_row(sessions, *, include_count=True):
    """Build a Polar data row, with the session count only where it is useful."""
    polar = list(sessions or [])
    if not polar:
        return None
    durations = [item["duration_seconds"] for item in polar if item.get("duration_seconds") is not None]
    calories = [item["calories"] for item in polar if item.get("calories") is not None]
    average_hrs = [item["average_hr"] for item in polar if item.get("average_hr") is not None]
    max_hrs = [item["max_hr"] for item in polar if item.get("max_hr") is not None]
    distances = [item["distance_meters"] for item in polar if item.get("distance_meters") is not None]
    start_times = sorted(item.get("start_time") for item in polar if item.get("start_time"))
    no_data = TR("common.no_data")
    data_date = polar[0].get("date") or date.today().isoformat()
    row = {
        TR("training_logging.today_date"): format_date(data_date, LANGUAGE),
        TR("training_logging.start_time"): time_to_hms(start_times[0]) if start_times else no_data,
        TR("training_logging.today_duration"): minutes_to_hms(sum(durations) / 60) if durations else no_data,
        TR("training_logging.today_average_hr"): round(sum(average_hrs) / len(average_hrs)) if average_hrs else no_data,
        TR("training_logging.today_max_hr"): max(max_hrs) if max_hrs else no_data,
        TR("training_logging.today_calories"): sum(calories) if calories else no_data,
        TR("training_logging.today_distance"): sum(distances) if distances else no_data,
    }
    if include_count:
        row = {
            TR("training_logging.today_date"): row[TR("training_logging.today_date")],
            TR("training_logging.today_count"): len(polar),
            **{key: value for key, value in row.items() if key != TR("training_logging.today_date")},
        }
    return row


def _today_polar_data(sessions):
    today = date.today().isoformat()
    st.subheader(TR("training_logging.today_data"))
    polar = [item for item in sessions if item.get("date") == today and item.get("polar_external_id")]
    if not polar:
        st.info(TR("training_logging.today_no_data"))
        return
    row = _polar_training_data_row(polar)
    centered_dataframe([row])


def _seed_plan_exercise(prescription, block):
    catalog_id = prescription.get("exercise_catalog_id")
    mode = "freeform"
    catalog = prescription.get("measurement_mode")
    if catalog:
        mode = catalog
    planned_sets = prescription.get("planned_sets") or []
    sets = []
    for planned in planned_sets:
        item = _set_default()
        item.update({key: planned.get(key) for key in (
            "set_type", "load_value", "load_unit", "reps", "duration_seconds",
            "distance_meters", "rpe", "rir", "rest_seconds", "side",
        ) if key in planned})
        item["completed"] = False
        sets.append(item)
    if not sets:
        sets = [{**_set_default(), "load_unit": "kg", "completed": False}]
    return {
        **_exercise_default(),
        "exercise_catalog_id": catalog_id,
        "custom_exercise_name": prescription.get("custom_exercise_name") or "",
        "measurement_mode": mode,
        "module_key": block["module_key"],
        "training_prescription_id": prescription["id"],
        "planned_sets_json": json.dumps(planned_sets, ensure_ascii=False),
        "sets": sets,
    }


def _render_today_plan_controls(connection, session, *, today_plan, today_day):
    if not today_day:
        return
    st.markdown(f"### {TR('training_plan.today_plan')}：{today_day['day_label']}")
    prescriptions = [
        (block, prescription)
        for block in today_day.get("blocks", [])
        for prescription in block.get("prescriptions", [])
    ]
    editor_key = f"training_plan_editor_active_{session['id']}"
    state_key = f"training_exercise_editor_{session['id']}"
    actual = st.session_state.get(state_key, session.get("exercises") or [])
    completed = sum(
        bool(item.get("completed"))
        for exercise in actual
        for item in exercise.get("sets", [])
    )
    planned = sum(len(item.get("planned_sets", [])) for _, item in prescriptions)
    st.caption(f"{TR('training_plan.planned_sets')}：{planned} · {TR('training_plan.actual_result')}：{completed}")
    if prescriptions:
        for block, prescription in prescriptions:
            name = (
                prescription.get("display_name_zh") if LANGUAGE != "en"
                else prescription.get("display_name_en")
            ) or prescription.get("custom_exercise_name") or TR("common.no_data")
            with st.expander(f"{block['module_label']} · {name}", expanded=False):
                st.caption(f"{TR('training_plan.planned_sets')}：{len(prescription.get('planned_sets', []))}")
                skip_key = f"training_plan_skipped_{session['id']}_{prescription['id']}"
                if st.button(TR("training_plan_action_labels.skip"), key=f"{skip_key}_button"):
                    st.session_state[skip_key] = True
                if st.session_state.get(skip_key):
                    st.caption(TR("training_plan_action_labels.skipped"))
                if st.button(TR("training_plan_actions.copy_plan_sets"), key=f"copy_plan_sets_{session['id']}_{prescription['id']}"):
                    current = list(st.session_state.get(state_key, session.get("exercises") or []))
                    current.append(_seed_plan_exercise(prescription, block))
                    st.session_state[state_key] = current
                    st.session_state[editor_key] = True
                    st.rerun()
    if st.button(TR("training_plan.start_logging"), key=f"start_plan_logging_{session['id']}"):
        current = list(st.session_state.get(state_key, session.get("exercises") or []))
        if not current:
            current = [_seed_plan_exercise(item, block) for block, item in prescriptions]
        st.session_state[state_key] = current
        st.session_state[editor_key] = True
        st.rerun()
    if st.session_state.get(editor_key):
        exercises = _exercise_editor(connection, session)
        save_draft, complete = st.columns(2)
        draft_clicked = save_draft.button(
            TR("training_logging.save_draft"),
            key=f"today_save_draft_{session['id']}",
        )
        complete_clicked = complete.button(
            TR("training_logging.complete_log"),
            key=f"today_complete_{session['id']}",
            type="primary",
        )
        if draft_clicked or complete_clicked:
            try:
                save_training_details(connection, session["id"], {
                    "resolved_sport_type": session.get("resolved_sport_type") or session.get("polar_sport_type"),
                    "status": "completed" if complete_clicked else "draft",
                    "notes": session.get("notes"),
                    "training_program_id": (today_plan.get("program") or {}).get("id"),
                    "training_day_template_id": today_day.get("id"),
                    "prescription_snapshot_json": json.dumps(prescription_snapshot(today_day), ensure_ascii=False),
                }, exercises)
            except Exception as exc:
                # Keep the editor state and unsaved values available after a
                # validation or persistence error; the user can correct and
                # retry without losing the current entry.
                st.error(TR("training_logging.save_failed", message=str(exc)))
            else:
                st.session_state[editor_key] = False
                st.rerun()


def _today_training_details(connection, sessions):
    today = date.today().isoformat()
    polar = [item for item in sessions if item.get("date") == today and item.get("polar_external_id")]
    # Keep today's real Polar details; temporary/manual sessions are not part
    # of this section and should not create the standalone list shown here.
    # Keep the daily records in chronological order so that the numbering
    # remains stable and reflects the order in which the Polar sessions took
    # place, even when several sessions share the same date.
    today_sessions = sorted(
        polar,
        key=lambda item: (
            item.get("start_time") or "23:59:59",
            str(item.get("id") or item.get("uuid") or ""),
        ),
    )
    plan = get_weekly_training_plan(connection, date.today())
    today_day = plan_day_for_date(plan, date.today())
    st.subheader(TR("training_logging.today_details"))
    if not polar:
        st.info(TR("training_logging.today_no_data"))
        return
    if not today_sessions:
        return
    for index, session in enumerate(today_sessions, start=1):
        sport_type = _polar_sport_type(session)
        label = f"{index}. {sport_type}"
        # Keep each session's detailed action section collapsed until the user
        # explicitly opens it, so the daily overview stays compact.
        with st.expander(label, expanded=False):
            # The aggregate Polar fields are already shown in 今日训练数据.
            # Only strength sessions have structured action input and action
            # summaries; other Polar sports keep their Polar-only view.
            if _is_strength_training_session(session):
                with st.container(border=True):
                    st.markdown(f"### {TR('training_logging.exercise_details')}")
                    today_action_rows = _today_action_input_table(connection, session, sessions)
                with st.container(border=True):
                    st.markdown(f"### {TR('training_logging.summary')}")
                    _today_training_summary(session, today_action_rows)


def _compact_action_rows_to_exercises(rows_by_development, catalog):
    """Convert the compact action editor model to the storage payload."""
    catalog_by_name = {
        _catalog_name(item): item
        for item in (catalog or {}).values()
        if _catalog_name(item)
    }
    exercises = []
    sequence_order = 0
    for development_type, rows in (rows_by_development or {}).items():
        for row in rows or []:
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            catalog_item = catalog_by_name.get(name)
            set_count = max(1, int(row.get("sets") or 1))
            exercises.append({
                "uuid": _uuid(),
                "exercise_catalog_id": catalog_item.get("id") if catalog_item else None,
                "custom_exercise_name": None if catalog_item else name,
                "sequence_order": sequence_order,
                "exercise_category": "strength",
                "measurement_mode": "weight_reps",
                "primary_muscle_group": (
                    catalog_item.get("primary_muscle_group") if catalog_item else None
                ),
                "equipment": catalog_item.get("equipment") if catalog_item else None,
                "is_unilateral": bool(catalog_item.get("is_unilateral")) if catalog_item else False,
                "skill_proficiency": None,
                "notes": None,
                "module_key": str(development_type or "").strip() or None,
                "sets": [{
                    "uuid": _uuid(),
                    "set_type": "working",
                    "load_value": float(row.get("load") or 0.0),
                    "load_unit": "kg",
                    "reps": int(row.get("reps") or 0),
                    "duration_seconds": None,
                    "distance_meters": None,
                    "resistance_level": None,
                    "incline_percent": None,
                    "rpe": None,
                    "rir": None,
                    "rest_seconds": None,
                    "side": "not_applicable",
                    "completed": True,
                    "notes": None,
                } for _ in range(set_count)],
            })
            sequence_order += 1
    return exercises


def _today_exercise_details(connection, session):
    """Read-only action detail view used by the daily training section."""
    exercises = session.get("exercises") or []
    if not exercises:
        return

    catalog = {item["id"]: item for item in list_exercise_catalog(connection)}
    field_labels = (
        ("load_value", "load"), ("load_unit", "load_unit"), ("reps", "reps"),
        ("duration_seconds", "duration_seconds"), ("distance_meters", "distance_meters"),
        ("resistance_level", "resistance"), ("incline_percent", "incline"),
        ("rpe", "rpe"), ("rir", "rir"), ("rest_seconds", "rest"),
        ("side", "side"), ("completed", "completed_set"), ("notes", "set_notes"),
    )
    for index, exercise in enumerate(exercises, start=1):
        catalog_item = catalog.get(exercise.get("exercise_catalog_id"))
        name = (
            _catalog_name(catalog_item) if catalog_item else
            exercise.get("custom_exercise_name") or TR("common.no_data")
        )
        sets = exercise.get("sets") or []
        total_reps = sum([
            float(item.get("reps")) for item in sets
            if item.get("reps") not in (None, "")
        ])
        loads = [item.get("load_value") for item in sets if item.get("load_value") not in (None, "")]
        overview = st.columns(4)
        overview[0].metric(TR("training_logging.exercise"), name)
        overview[1].metric(TR("training_logging.total_sets"), len(sets))
        overview[2].metric(TR("training_logging.total_reps"), int(total_reps) if float(total_reps).is_integer() else total_reps)
        overview[3].metric(TR("training_logging.load"), _value(max(loads) if loads else None))
        with st.container(border=True):
            st.markdown(f"#### {index}. {name}")
            meta = st.columns(4)
            meta[0].metric(TR("training_logging.exercise_category"), TR(
                f"training_logging.categories.{exercise.get('exercise_category', 'other')}"
            ))
            meta[1].metric(TR("training_logging.measurement_mode"), TR(
                f"training_logging.modes.{exercise.get('measurement_mode', 'freeform')}"
            ))
            meta[2].metric(TR("training_logging.primary_muscle_group"), exercise.get("primary_muscle_group") or TR("common.no_data"))
            meta[3].metric(TR("training_logging.equipment"), exercise.get("equipment") or TR("common.no_data"))
            if exercise.get("notes"):
                st.caption(f"{TR('training_logging.exercise_notes')}：{exercise['notes']}")

            if not sets:
                st.caption(TR("training_logging.empty_sets"))
                continue
            rows = []
            for set_item in sets:
                row = {
                    TR("training_logging.set"): set_item.get("set_number"),
                    TR("training_logging.set_type"): TR(
                        f"training_logging.set_types.{set_item.get('set_type', 'working')}"
                    ),
                }
                for field, label in field_labels:
                    value = set_item.get(field)
                    if field == "load_unit":
                        value = TR(f"training_logging.load_units.{value or 'none'}")
                    elif field == "side":
                        value = TR(f"training_logging.sides.{value or 'not_applicable'}")
                    elif field == "completed":
                        value = TR("common.yes") if value else TR("common.no")
                    elif value in (None, ""):
                        value = TR("common.no_data")
                    row[TR(f"training_logging.{label}")] = value
                rows.append(row)
            centered_dataframe(rows)


def _today_action_input_table(connection, session, sessions):
    """Render an independent action-type group and its action rows."""
    load_label = f"{TR('training_logging.load')}（{'kg'.upper()}）"
    sets_label = TR("training_logging.total_sets").replace("总", "", 1)
    action_name_label = TR("training_logging.exercise")
    reps_label = TR("training_logging.reps")
    session_id = session["id"]
    repaint_key = f"today_action_v3_repaint_{session_id}"

    # An action callback sets this flag before the body is rendered.  Abort
    # that intermediate interaction run and immediately start one clean run,
    # so removed widgets cannot survive as frontend deltas.
    if st.session_state.pop(repaint_key, False):
        st.rerun()

    catalog = {item["id"]: item for item in list_exercise_catalog(connection)}
    stored_action_names = [
        _catalog_name(item) for item in catalog.values() if _catalog_name(item)
    ]

    def available_action_names(selected_development_type):
        return _action_name_options(
            selected_development_type,
            session_id,
            stored_action_names,
            selected_development_type,
        )

    def new_row(name="", sets=1, reps=0, load=0.0):
        return {
            "id": _uuid(),
            "name": name or "",
            "sets": int(sets or 1),
            "reps": int(reps or 0),
            "load": float(load or 0.0),
        }

    rows_by_development_key = f"today_action_rows_by_development_v3_{session_id}"
    rows_model_key = f"today_action_rows_by_development_version_{session_id}"
    development_type_key = f"today_action_development_type_{session_id}"
    if st.session_state.get(rows_model_key) != 4:
        previous_rows = {}
        model_version = st.session_state.get(rows_model_key)
        if model_version == 3:
            previous_rows = st.session_state.get(rows_by_development_key, {})
        else:
            # Preserve any in-progress legacy rows during the one-time
            # transition. Every development type then owns an entirely
            # separate list, so its + and - controls cannot affect another.
            legacy_groups = st.session_state.get(
                f"today_action_groups_v2_{session_id}", []
            )
            legacy_active_id = st.session_state.get(
                f"today_action_active_group_v2_{session_id}"
            )
            legacy_group = next(
                (
                    group for group in legacy_groups
                    if group.get("id") == legacy_active_id
                ),
                legacy_groups[0] if legacy_groups else None,
            )
            legacy_rows = list(legacy_group.get("rows") or []) if legacy_group else []
            previous_rows = {
                development_type: (
                    legacy_rows
                    if development_type == DEVELOPMENT_STRENGTH_OPTIONS[0]
                    else []
                )
                for development_type in DEVELOPMENT_STRENGTH_OPTIONS
            }

        previous_rows = dict(previous_rows or {})
        legacy_recovery_rows = previous_rows.pop(LEGACY_ACTIVE_RECOVERY_TYPE, [])
        if legacy_recovery_rows:
            previous_rows.setdefault("伤病预防类训练", []).extend(
                legacy_recovery_rows
            )
        for development_type in DEVELOPMENT_STRENGTH_OPTIONS:
            previous_rows.setdefault(development_type, [])

        selected_before = st.session_state.get(development_type_key)
        selected_rows_before = list(previous_rows.get(selected_before, []))
        normalized_rows = _normalize_development_action_rows(previous_rows)
        st.session_state[rows_by_development_key] = normalized_rows

        # If the selected bucket was moved because its action names clearly
        # belong to another type, keep the selector aligned with the rows.
        inferred_type = _infer_development_type_for_rows(
            selected_rows_before, selected_before
        )
        if (
            selected_rows_before
            and inferred_type
            and not normalized_rows.get(selected_before)
            and normalized_rows.get(inferred_type)
        ):
            st.session_state[development_type_key] = inferred_type
        st.session_state[rows_model_key] = 4

    rows_by_development = st.session_state.get(rows_by_development_key, {})
    legacy_recovery_rows = rows_by_development.pop(LEGACY_ACTIVE_RECOVERY_TYPE, [])
    if legacy_recovery_rows:
        rows_by_development.setdefault("伤病预防类训练", []).extend(legacy_recovery_rows)
    for development_type in DEVELOPMENT_STRENGTH_OPTIONS:
        rows_by_development.setdefault(development_type, [])
    # Re-check on every render as well as during the one-time migration.  A
    # hot-reloaded session can already carry the current model version while
    # its action buckets were created by an older run (or accidentally shared
    # the same list).  Normalizing here keeps the selected type and its rows
    # aligned before any widgets are created.
    selected_before = st.session_state.get(development_type_key)
    selected_rows_before = list(rows_by_development.get(selected_before, []))
    normalized_rows = _normalize_development_action_rows(rows_by_development)
    inferred_type = _infer_development_type_for_rows(
        selected_rows_before, selected_before
    )
    if (
        selected_rows_before
        and inferred_type
        and inferred_type != selected_before
        and not normalized_rows.get(selected_before)
        and normalized_rows.get(inferred_type)
    ):
        st.session_state[development_type_key] = inferred_type
    rows_by_development = normalized_rows
    st.session_state[rows_by_development_key] = rows_by_development
    if st.session_state.get(development_type_key) == LEGACY_ACTIVE_RECOVERY_TYPE:
        st.session_state[development_type_key] = "伤病预防类训练"
    legacy_custom_development_type_key = (
        f"today_action_custom_development_type_{session_id}"
    )
    active_custom_development_type_key = (
        f"today_action_active_custom_development_type_{session_id}"
    )
    custom_development_types_key = (
        f"today_action_custom_development_types_{session_id}"
    )
    development_type_label = TR("training_logging.development_strength_type")
    development_type_header = (
        "<div class='drc-action-input-header'>"
        + escape(development_type_label)
        + "</div>"
    )
    st.markdown(development_type_header, unsafe_allow_html=True)
    # Migrate the former sentinel + text-input pair before the replacement
    # selectbox is instantiated.  This keeps a hot-reloaded session usable.
    if st.session_state.get(development_type_key) == CUSTOM_DEVELOPMENT_STRENGTH_TYPE:
        legacy_value = str(
            st.session_state.get(legacy_custom_development_type_key)
            or st.session_state.get(active_custom_development_type_key)
            or ""
        ).strip()
        st.session_state[development_type_key] = (
            legacy_value or DEVELOPMENT_STRENGTH_OPTIONS[0]
        )
    remembered_custom_development_type = str(
        st.session_state.get(active_custom_development_type_key, "")
    ).strip()
    if not remembered_custom_development_type:
        custom_row_types = [
            key for key, rows in rows_by_development.items()
            if key not in DEVELOPMENT_STRENGTH_OPTIONS and rows
        ]
        if custom_row_types:
            remembered_custom_development_type = custom_row_types[-1]
            st.session_state[active_custom_development_type_key] = (
                remembered_custom_development_type
            )
    custom_development_types = []
    for candidate in [
        *st.session_state.get(custom_development_types_key, []),
        remembered_custom_development_type,
        *[
            key for key, rows in rows_by_development.items()
            if key not in DEVELOPMENT_STRENGTH_OPTIONS and rows
        ],
    ]:
        candidate = str(candidate or "").strip()
        if candidate and candidate not in DEVELOPMENT_STRENGTH_OPTIONS and candidate not in custom_development_types:
            custom_development_types.append(candidate)
    st.session_state[custom_development_types_key] = custom_development_types
    development_type_options = [*DEVELOPMENT_STRENGTH_OPTIONS, *custom_development_types]
    development_type_choice = st.selectbox(
        development_type_label,
        development_type_options,
        key=development_type_key,
        label_visibility="collapsed",
        accept_new_options=True,
        placeholder=_ui("选择或输入发展力量类型", "Select or enter development strength type"),
    )
    development_type = str(development_type_choice or "").strip()
    if not development_type:
        development_type = DEVELOPMENT_STRENGTH_OPTIONS[0]
    if development_type not in DEVELOPMENT_STRENGTH_OPTIONS:
        if development_type not in custom_development_types:
            custom_development_types.append(development_type)
            st.session_state[custom_development_types_key] = custom_development_types
        st.session_state[active_custom_development_type_key] = development_type
    active_rows = _development_action_rows(rows_by_development, development_type)

    previous_sessions = sorted(
        (
            item for item in (sessions or [])
            if item.get("id") != session_id
        ),
        key=lambda item: (
            item.get("date") or "",
            item.get("start_time") or "",
            str(item.get("id") or item.get("uuid") or ""),
        ),
        reverse=True,
    )
    template_notice_key = f"today_action_template_notice_{session_id}"

    # Button callbacks run before this script body renders.  Updating the
    # current list there prevents Streamlit from first drawing the old row
    # and then leaving a partial copy of its number inputs behind.
    def current_development_type():
        return development_type or None

    def add_current_action():
        selected_development_type = current_development_type()
        if not selected_development_type:
            return
        current_rows = _development_action_rows(
            st.session_state[rows_by_development_key], selected_development_type
        )
        action_names, _ = available_action_names(selected_development_type)
        _add_development_action(
            current_rows,
            new_row(name=_recommended_action_name(current_rows, action_names)),
        )
        st.session_state[repaint_key] = True

    def remove_current_action():
        selected_development_type = current_development_type()
        if not selected_development_type:
            return
        current_rows = _development_action_rows(
            st.session_state[rows_by_development_key], selected_development_type
        )
        _remove_development_action(current_rows)
        st.session_state[repaint_key] = True

    def copy_previous_training():
        source = next(
            (
                item for item in previous_sessions
                if any(
                    st.session_state.get(
                        f"today_action_rows_by_development_v3_{item.get('id')}", {}
                    ).values()
                )
            ),
            None,
        )
        copied_rows = None
        source_type = None
        if source:
            source_rows_key = f"today_action_rows_by_development_v3_{source['id']}"
            source_rows = st.session_state.get(source_rows_key, {})
            copied_rows = _clone_development_action_rows(source_rows)
            source_type = st.session_state.get(
                f"today_action_development_type_{source['id']}"
            )
        else:
            source = next(
                (item for item in previous_sessions if item.get("exercises")),
                None,
            )
            if source:
                copied_rows = {
                    item: [] for item in DEVELOPMENT_STRENGTH_OPTIONS
                }
                copied_rows[development_type] = _action_rows_from_training_exercises(
                    source.get("exercises"), development_type, catalog
                )
                source_type = development_type

        if copied_rows is None:
            st.session_state[template_notice_key] = TR(
                "training_logging.no_previous_training"
            )
            return

        st.session_state[rows_by_development_key] = copied_rows
        if source_type in DEVELOPMENT_STRENGTH_OPTIONS:
            st.session_state[development_type_key] = source_type
        elif source_type:
            st.session_state[development_type_key] = source_type
            custom_types = list(st.session_state.get(custom_development_types_key, []))
            if source_type not in custom_types:
                custom_types.append(source_type)
            st.session_state[custom_development_types_key] = custom_types
            st.session_state[active_custom_development_type_key] = source_type
        st.session_state[template_notice_key] = TR(
            "training_logging.copied_previous_training"
        )
        st.session_state[repaint_key] = True

    def save_current_template():
        templates = st.session_state.setdefault("today_action_templates_v1", [])
        templates.append({
            "saved_on": date.today().isoformat(),
            "source_session_id": session_id,
            "rows_by_development": _clone_development_action_rows(
                st.session_state[rows_by_development_key]
            ),
        })
        st.session_state[template_notice_key] = TR(
            "training_logging.template_saved"
        )

    headers = (action_name_label, sets_label, reps_label, load_label)
    column_widths = (3.2, .75, .75, .9)
    header_columns = st.columns(column_widths)
    for column, header in zip(header_columns, headers):
        header_html = "<div class='drc-action-input-header'>" + str(header) + "</div>"
        column.markdown(header_html, unsafe_allow_html=True)

    # Keep a stable, explicit slot for every row that has existed during this
    # session.  When an action is removed we clear its slot ourselves instead
    # of relying on Streamlit's dynamic-column reconciliation, which can leave
    # faded reps/load fields and duplicate action controls in the browser.
    slot_counts_key = f"today_action_v3_slot_counts_{session_id}"
    slot_counts = st.session_state.setdefault(slot_counts_key, {})
    slot_count = max(slot_counts.get(development_type, 0), len(active_rows))
    slot_counts[development_type] = slot_count
    row_slots = [st.empty() for _ in range(slot_count)]

    for row_index, row in enumerate(active_rows):
        row_id = row["id"]
        row_container = row_slots[row_index].container()
        row_columns = row_container.columns(column_widths)
        action_names, saved_names_key = available_action_names(development_type)
        if row["name"] == "__custom_action__":
            row["name"] = ""
        # A standard development type is a closed action set.  Replace any
        # stale row that came from another type before constructing the
        # selectbox, otherwise the old action remains visible after switching
        # the development-strength selector.
        if (
            development_type in DEVELOPMENT_STRENGTH_ACTION_NAMES
            and row["name"]
            and _action_name_key(row["name"])
            not in {_action_name_key(name) for name in action_names}
        ):
            row["name"] = ""
        if not row["name"]:
            row["name"] = _recommended_action_name(active_rows[:row_index], action_names)
        name_options = list(action_names)
        if (
            development_type not in DEVELOPMENT_STRENGTH_ACTION_NAMES
            and row["name"]
            and row["name"] not in name_options
        ):
            name_options.append(row["name"])
        if not name_options:
            name_options = [""]
        name_choice_key = f"today_action_v3_name_choice_{session_id}_{row_id}"
        if (
            development_type in DEVELOPMENT_STRENGTH_ACTION_NAMES
            and st.session_state.get(name_choice_key) not in name_options
        ):
            st.session_state[name_choice_key] = row["name"]
        if st.session_state.get(name_choice_key) == "__custom_action__":
            st.session_state[name_choice_key] = (
                row["name"] if row["name"] in name_options else name_options[0]
            )
        selected_name = row_columns[0].selectbox(
            action_name_label, name_options,
            index=(name_options.index(row["name"]) if row["name"] in name_options else 0),
            key=name_choice_key,
            label_visibility="collapsed",
            accept_new_options=(development_type not in DEVELOPMENT_STRENGTH_ACTION_NAMES),
            placeholder=_ui("选择或输入动作名称", "Select or enter exercise name"),
        )
        row["name"] = str(selected_name or "").strip()
        if row["name"] and row["name"] not in action_names:
            saved_names = list(st.session_state.get(saved_names_key, []))
            if row["name"] not in saved_names:
                saved_names.append(row["name"])
                st.session_state[saved_names_key] = saved_names
        row["sets"] = row_columns[1].number_input(
            sets_label, min_value=1, step=1, value=row["sets"],
            key=f"today_action_v3_sets_{session_id}_{row_id}",
            label_visibility="collapsed",
        )
        row["reps"] = row_columns[2].number_input(
            reps_label, min_value=0, step=1, value=row["reps"],
            key=f"today_action_v3_reps_{session_id}_{row_id}",
            label_visibility="collapsed",
        )
        row["load"] = row_columns[3].number_input(
            load_label, min_value=0.0, step=0.5, value=row["load"],
            key=f"today_action_v3_load_{session_id}_{row_id}",
            label_visibility="collapsed",
        )

    for stale_slot in row_slots[len(active_rows):]:
        stale_slot.empty()

    st.session_state[rows_by_development_key] = rows_by_development
    action_count = len(active_rows)
    controls_container = st.container(
        key=f"today_action_v3_controls_{session_id}_{development_type}"
    )
    group_action_controls = controls_container.columns(2)
    group_action_controls[0].button(
        f"{action_name_label.replace('名称', '')}+",
        key=f"today_action_v3_add_{session_id}_{development_type}",
        use_container_width=True,
        on_click=add_current_action,
    )
    group_action_controls[1].button(
        f"{action_name_label.replace('名称', '')}-",
        key=f"today_action_v3_delete_{session_id}_{development_type}",
        use_container_width=True,
        disabled=action_count == 0,
        on_click=remove_current_action,
    )

    template_controls = st.columns(2)
    template_controls[0].button(
        TR("training_logging.copy_previous_training"),
        key=f"today_action_v3_copy_previous_{session_id}",
        use_container_width=True,
        on_click=copy_previous_training,
    )
    template_controls[1].button(
        TR("training_logging.save_template"),
        key=f"today_action_v3_save_template_{session_id}",
        use_container_width=True,
        on_click=save_current_template,
    )
    notice = st.session_state.pop(template_notice_key, None)
    if notice:
        st.success(notice)

    save_notice_key = f"today_action_save_notice_{session_id}"
    if st.button(
        TR("training_logging.save_action_details"),
        key=f"today_action_v3_save_{session_id}",
        type="primary",
        use_container_width=True,
    ):
        try:
            save_training_details(
                connection,
                session_id,
                {
                    "resolved_sport_type": (
                        session.get("resolved_sport_type")
                        or session.get("polar_sport_type")
                    ),
                    "status": "completed",
                    "notes": session.get("notes"),
                },
                _compact_action_rows_to_exercises(rows_by_development, catalog),
            )
            st.session_state[save_notice_key] = TR("training_logging.saved")
            st.rerun()
        except Exception as exc:
            st.error(TR("training_logging.save_failed", message=str(exc)))
    save_notice = st.session_state.pop(save_notice_key, None)
    if save_notice:
        st.success(save_notice)
    return rows_by_development


def _today_action_summary(rows_by_development):
    """Summarize the current, unsaved action rows for one Polar session."""
    rows = [
        row
        for action_rows in (rows_by_development or {}).values()
        for row in action_rows
    ]
    total_sets = sum(int(row.get("sets") or 0) for row in rows)
    total_reps = sum(
        int(row.get("sets") or 0) * int(row.get("reps") or 0)
        for row in rows
    )
    volume_load = sum(
        int(row.get("sets") or 0)
        * int(row.get("reps") or 0)
        * float(row.get("load") or 0.0)
        for row in rows
    )
    development_types = [
        development_type
        for development_type, action_rows in (rows_by_development or {}).items()
        if action_rows
    ]
    return {
        "exercise_count": len(rows),
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_load": volume_load,
        "development_types": "、".join(development_types) or TR("common.no_data"),
    }


def _render_training_summary(session, action_summary):
    """Render the shared Polar plus action summary for daily/history views."""
    polar_values = (
        ("sport_type", _polar_sport_type(session)),
        ("start_time", time_to_hms(session.get("start_time"))),
        (
            "duration",
            minutes_to_hms(session["duration_seconds"] / 60)
            if session.get("duration_seconds") is not None else TR("common.no_data"),
        ),
        ("average_hr", _value(session.get("average_hr"))),
        ("max_hr", _value(session.get("max_hr"))),
        ("calories", _value(session.get("calories"))),
        ("distance", _value(session.get("distance_meters"))),
    )
    action_values = (
        ("exercise_count", action_summary["exercise_count"]),
        ("total_sets", action_summary["total_sets"]),
        ("total_reps", action_summary["total_reps"]),
        ("volume_load", action_summary["volume_load"]),
        ("development_strength_type", action_summary["development_types"]),
    )
    columns = st.columns(3)
    for index, (label, value) in enumerate((*polar_values, *action_values)):
        if isinstance(value, (int, float)):
            display_value = format_number(value, LANGUAGE)
        else:
            display_value = value
        columns[index % 3].metric(TR(f"training_logging.{label}"), display_value)


def _today_training_summary(session, rows_by_development):
    """Show one combined summary of Polar data and the current action rows."""
    _render_training_summary(session, _today_action_summary(rows_by_development))


def _historical_action_summary(session):
    """Convert saved historical exercises to the shared action summary shape."""
    stored_exercises = session.get("exercises") or []
    exercises = _historical_recorded_exercises(session)
    total_sets = 0
    total_reps = 0
    volume_load = 0.0
    development_types = []
    for exercise in exercises:
        sets = exercise.get("sets") or []
        total_sets += len(sets)
        for item in sets:
            reps = item.get("reps")
            reps_value = float(reps) if reps not in (None, "") else 0.0
            total_reps += int(reps_value) if reps_value.is_integer() else reps_value
            load = item.get("load_value")
            if load not in (None, ""):
                volume_load += float(load) * reps_value
        development_type = (
            exercise.get("development_strength_type")
            or exercise.get("development_type")
            or exercise.get("module_key")
        )
        if development_type and development_type not in development_types:
            development_types.append(development_type)

    saved_summary = session.get("summary") or {}
    if not stored_exercises:
        total_sets = saved_summary.get("total_set_count") or 0
        total_reps = saved_summary.get("total_reps") or 0
        volume_load = saved_summary.get("strength_volume_load_kg") or 0
    return {
        "exercise_count": (
            len(exercises) if stored_exercises
            else saved_summary.get("exercise_count") or 0
        ),
        "total_sets": total_sets,
        "total_reps": total_reps,
        "volume_load": volume_load,
        "development_types": "、".join(development_types) or TR("common.no_data"),
    }


def _historical_training_summary(session):
    _render_training_summary(session, _historical_action_summary(session))


def _has_recorded_training_set(set_item):
    """Return whether a persisted set contains actual user-entered data."""
    for field in (
        "load_value", "reps", "duration_seconds", "distance_meters",
        "resistance_level", "incline_percent", "rpe", "rir", "rest_seconds",
    ):
        value = set_item.get(field)
        if value not in (None, "", False, 0, 0.0):
            return True
    return bool(str(set_item.get("notes") or "").strip())


def _historical_recorded_exercises(session):
    """Keep only historical exercises that contain a non-default set."""
    return [
        exercise for exercise in (session.get("exercises") or [])
        if any(
            _has_recorded_training_set(item)
            for item in (exercise.get("sets") or [])
        )
    ]


def _historical_action_rows(session, catalog):
    """Convert persisted exercises to the compact daily action-row shape."""
    grouped = {}
    for exercise in _historical_recorded_exercises(session):
        development_type = (
            exercise.get("development_strength_type")
            or exercise.get("development_type")
            or exercise.get("module_key")
            or TR("common.no_data")
        )
        catalog_item = catalog.get(exercise.get("exercise_catalog_id"))
        name = (
            _catalog_name(catalog_item) if catalog_item else
            exercise.get("custom_exercise_name") or TR("common.no_data")
        )
        sets = exercise.get("sets") or []
        reps = float(sum(
            float(item.get("reps"))
            for item in sets
            if item.get("reps") not in (None, "")
        ))
        loads = [
            float(item.get("load_value"))
            for item in sets
            if item.get("load_value") not in (None, "")
        ]
        grouped.setdefault(str(development_type), []).append({
            "name": name,
            "sets": len(sets),
            "reps": int(reps) if reps.is_integer() else reps,
            "load": max(loads) if loads else None,
        })
    # Older saved records could retain the selected type after the action
    # list had changed.  Apply the same type-to-action normalization used by
    # the editor so read-only history does not show contradictory pairings.
    normalized = _normalize_development_action_rows(grouped)
    return {
        development_type: rows
        for development_type, rows in normalized.items()
        if rows
    }


def _session_header(session):
    st.info(TR("training_logging.readonly_notice") if session["polar_readonly"] else TR("training_logging.manual_notice"))
    row = _polar_training_data_row([session], include_count=False)
    if row:
        centered_dataframe([row])
    st.caption(
        f"{TR('training_logging.data_source')}：{_session_source(session)}　"
        f"{TR('training_logging.sync_status')}："
        f"{TR('training_logging.polar_synced') if session['polar_readonly'] else TR('training_logging.manual_source')}"
    )
    st.caption(f"{_sport_type_heading()}：{_polar_sport_type(session)}")


def _set_default():
    return {
        "uuid": _uuid(), "set_type": "working", "load_value": None,
        "load_unit": "none", "reps": None, "duration_seconds": None,
        "distance_meters": None, "resistance_level": None, "incline_percent": None,
        "rpe": None, "rir": None, "rest_seconds": None,
        "side": "not_applicable", "completed": True, "notes": None,
    }


def _exercise_default():
    return {
        "uuid": _uuid(), "exercise_catalog_id": None, "custom_exercise_name": "",
        "exercise_category": "strength", "measurement_mode": "weight_reps",
        "primary_muscle_group": "", "equipment": "", "is_unilateral": False,
        "skill_proficiency": None, "notes": "", "sets": [{**_set_default(), "load_unit": "kg"}],
        "_catalog_applied_id": None, "_save_to_library": False,
    }


def _editor_state(session):
    key = f"training_exercise_editor_{session['id']}"
    if key not in st.session_state:
        st.session_state[key] = [
            {**copy_exercise(item), "_catalog_applied_id": item.get("exercise_catalog_id"),
             "_save_to_library": False}
            for item in session["exercises"]
        ]
    return key, st.session_state[key]


def _set_field(column, item, field, prefix):
    """Render one applicable field while leaving every hidden value untouched."""
    if field == "set_type":
        item[field] = column.selectbox(
            TR("training_logging.set_type"), SET_TYPES,
            index=SET_TYPES.index(item.get(field, "working")),
            format_func=lambda value: TR(f"training_logging.set_types.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "load_unit":
        item[field] = column.selectbox(
            TR("training_logging.load_unit"), LOAD_UNITS,
            index=LOAD_UNITS.index(item.get(field, "none")) if item.get(field, "none") in LOAD_UNITS else 0,
            format_func=lambda value: TR(f"training_logging.load_units.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "side":
        item[field] = column.selectbox(
            TR("training_logging.side"), SIDES,
            index=SIDES.index(item.get(field, "not_applicable")),
            format_func=lambda value: TR(f"training_logging.sides.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "completed":
        item[field] = column.checkbox(
            TR("training_logging.completed_set"), value=bool(item.get(field, True)),
            key=f"{prefix}_{field}",
        )
    elif field == "notes":
        item[field] = column.text_input(
            TR("training_logging.set_notes"), value=item.get(field) or "",
            key=f"{prefix}_{field}",
        )
    else:
        labels = {
            "load_value": "load", "reps": "reps", "duration_seconds": "duration_seconds",
            "distance_meters": "distance_meters", "resistance_level": "resistance",
            "incline_percent": "incline", "rpe": "rpe", "rir": "rir",
            "rest_seconds": "rest",
        }
        settings = {
            "load_value": (0.0, None, .5), "reps": (0, None, 1),
            "duration_seconds": (0.0, None, 5.0), "distance_meters": (0.0, None, 100.0),
            "resistance_level": (0.0, None, 1.0), "incline_percent": (0.0, None, .5),
            "rpe": (1.0, 10.0, .5), "rir": (0.0, 10.0, 1.0),
            "rest_seconds": (0.0, None, 15.0),
        }
        minimum, maximum, step = settings[field]
        options = {
            "label": TR(f"training_logging.{labels[field]}"), "min_value": minimum,
            "value": item.get(field), "step": step, "key": f"{prefix}_{field}",
        }
        if maximum is not None:
            options["max_value"] = maximum
        if field == "load_value" and item.get("load_unit") in {"bodyweight", "none"}:
            options["disabled"] = True
        item[field] = column.number_input(**options)


def _set_editor(exercise, exercise_index, entry_mode, exertion_preference):
    sets = exercise.setdefault("sets", [])
    mode = exercise["measurement_mode"]
    fields = visible_set_fields(mode, entry_mode, exertion_preference)
    segment_label = "practice_segment" if mode in {"dance_practice", "freeform"} else "set"

    for set_index, item in enumerate(list(sets)):
        prefix = f"training_set_{exercise['uuid']}_{item['uuid']}"
        primary_fields = fields[:4]
        columns = st.columns((.7, *(1 for _ in primary_fields)))
        columns[0].markdown(
            _cell(f"{TR(f'training_logging.{segment_label}')} {set_index + 1}"),
            unsafe_allow_html=True,
        )
        for column, field in zip(columns[1:], primary_fields):
            _set_field(column, item, field, prefix)
        remaining = fields[4:]
        for offset in range(0, len(remaining), 5):
            chunk = remaining[offset:offset + 5]
            extra_columns = st.columns(len(chunk))
            for column, field in zip(extra_columns, chunk):
                _set_field(column, item, field, prefix)

    controls = st.columns((1.1, 1.5, 1.2, 5))
    if controls[0].button(TR("training_logging.add_set"), key=f"set_add_{exercise['uuid']}"):
        new_set = _set_default()
        new_set["load_unit"] = default_load_unit(mode)
        sets.append(new_set); st.rerun()
    if controls[1].button(TR("training_logging.copy_previous_set"), key=f"set_copy_{exercise['uuid']}"):
        source = sets[-1] if sets else {**_set_default(), "load_unit": default_load_unit(mode)}
        sets.append(copied_set_for_entry(source, mode, entry_mode, exertion_preference)); st.rerun()
    with controls[2].popover(TR("training_logging.more_actions"), use_container_width=True):
        batch_count = st.number_input(
            TR("training_logging.batch_count"), min_value=1, max_value=20, value=3,
            key=f"set_batch_count_{exercise['uuid']}",
        )
        if st.button(TR("training_logging.batch_add_sets"), key=f"set_batch_{exercise['uuid']}"):
            source = sets[-1] if sets else {**_set_default(), "load_unit": default_load_unit(mode)}
            sets.extend(
                copied_set_for_entry(source, mode, entry_mode, exertion_preference)
                for _ in range(int(batch_count))
            ); st.rerun()
        if sets:
            delete_index = st.selectbox(
                TR("training_logging.delete_set"), range(len(sets)),
                format_func=lambda value: f"{TR(f'training_logging.{segment_label}')} {value + 1}",
                key=f"set_delete_index_{exercise['uuid']}",
            )
            confirmed = st.checkbox(
                TR("training_logging.confirm_delete_set"), key=f"set_delete_confirm_{exercise['uuid']}"
            )
            if st.button(
                TR("training_logging.delete_set"), disabled=not confirmed,
                key=f"set_delete_{exercise['uuid']}", type="primary",
            ):
                sets.pop(delete_index); st.rerun()
    if not sets:
        st.caption(TR("training_logging.empty_sets"))


def _exercise_editor(connection, session):
    state_key, exercises = _editor_state(session)
    catalog = list_exercise_catalog(connection)
    by_id = {item["id"]: item for item in catalog}
    st.subheader(TR("training_logging.exercise_details"))
    preferences = st.columns(2)
    entry_mode = preferences[0].radio(
        TR("training_logging.entry_mode"), ENTRY_MODES,
        format_func=lambda value: TR(f"training_logging.{value}_mode"), horizontal=True,
        key=f"training_entry_mode_{session['id']}",
    )
    exertion_preference = preferences[1].radio(
        TR("training_logging.exertion_preference"), EXERTION_PREFERENCES,
        format_func=lambda value: TR(f"training_logging.use_{value}"), horizontal=True,
        key=f"training_exertion_preference_{session['id']}",
    )
    st.caption(TR("training_logging.hidden_fields_preserved"))
    if not exercises:
        st.info(TR("training_logging.empty_exercises"))

    for index, exercise in enumerate(list(exercises)):
        with st.container(border=True):
            st.markdown(f"#### {index + 1}. {TR('training_logging.exercise')}")
            choice_options = [CUSTOM_EXERCISE, *(item["id"] for item in catalog)]
            current_choice = exercise.get("exercise_catalog_id") or CUSTOM_EXERCISE
            first, second = st.columns(2)
            choice = first.selectbox(
                TR("training_logging.exercise"), choice_options,
                index=choice_options.index(current_choice) if current_choice in choice_options else 0,
                format_func=lambda value: TR("training_logging.custom_exercise")
                if value == CUSTOM_EXERCISE else _catalog_name(by_id[value]),
                key=f"exercise_choice_{exercise['uuid']}",
            )
            selected = by_id.get(choice)
            previous_catalog_id = exercise.get("_catalog_applied_id")
            if selected and exercise.get("_catalog_applied_id") != selected["id"]:
                exercise.update(apply_catalog_defaults(exercise, selected))
                st.session_state[f"exercise_edit_props_{exercise['uuid']}"] = False
            if not selected:
                if previous_catalog_id is not None:
                    st.session_state[f"exercise_edit_props_{exercise['uuid']}"] = True
                exercise["exercise_catalog_id"] = None
                exercise["_catalog_applied_id"] = None
                exercise["custom_exercise_name"] = first.text_input(
                    TR("training_logging.custom_exercise_name"),
                    value=exercise.get("custom_exercise_name") or "",
                    key=f"exercise_custom_{exercise['uuid']}",
                )
            old_mode = exercise.get("measurement_mode", "weight_reps")
            exercise["measurement_mode"] = second.selectbox(
                TR("training_logging.measurement_mode"), MEASUREMENT_MODES,
                index=MEASUREMENT_MODES.index(old_mode),
                format_func=lambda value: TR(f"training_logging.modes.{value}"),
                key=f"exercise_mode_{exercise['uuid']}",
                disabled=bool(selected),
            )
            if not selected:
                exercise["exercise_category"] = st.selectbox(
                    TR("training_logging.exercise_category"), EXERCISE_CATEGORIES,
                    index=EXERCISE_CATEGORIES.index(exercise.get("exercise_category", "other")),
                    format_func=lambda value: TR(f"training_logging.categories.{value}"),
                    key=f"exercise_category_{exercise['uuid']}",
                )
            if exercise["measurement_mode"] != old_mode:
                st.warning(TR("training_logging.incompatible_fields_preserved"))

            with st.expander(TR("training_logging.view_exercise_information")):
                edit_properties = st.checkbox(
                    TR("training_logging.edit_exercise_properties"),
                    value=not bool(selected), key=f"exercise_edit_props_{exercise['uuid']}",
                )
                if edit_properties:
                    fields = st.columns(4 if selected else 3)
                    offset = 1 if selected else 0
                    if selected:
                        exercise["exercise_category"] = fields[0].selectbox(
                            TR("training_logging.exercise_category"), EXERCISE_CATEGORIES,
                            index=EXERCISE_CATEGORIES.index(exercise.get("exercise_category", "other")),
                            format_func=lambda value: TR(f"training_logging.categories.{value}"),
                            key=f"exercise_category_edit_{exercise['uuid']}",
                        )
                    exercise["primary_muscle_group"] = fields[offset].text_input(
                        TR("training_logging.primary_muscle_group"),
                        value=exercise.get("primary_muscle_group") or "",
                        key=f"exercise_muscle_{exercise['uuid']}",
                    )
                    exercise["equipment"] = fields[offset + 1].text_input(
                        TR("training_logging.equipment"), value=exercise.get("equipment") or "",
                        key=f"exercise_equipment_{exercise['uuid']}",
                    )
                    exercise["is_unilateral"] = fields[offset + 2].checkbox(
                        TR("training_logging.laterality"), value=bool(exercise.get("is_unilateral")),
                        key=f"exercise_unilateral_{exercise['uuid']}",
                    )
                else:
                    info = st.columns(5)
                    values = (
                        ("catalog_category", TR(f"training_logging.categories.{exercise['exercise_category']}")),
                        ("catalog_muscle", exercise.get("primary_muscle_group") or TR("common.no_data")),
                        ("catalog_equipment", exercise.get("equipment") or TR("common.no_data")),
                        ("catalog_laterality", TR("common.yes") if exercise.get("is_unilateral") else TR("common.no")),
                        ("default_load_unit", TR(f"training_logging.load_units.{default_load_unit(exercise['measurement_mode'])}")),
                    )
                    for column, (label, value) in zip(info, values):
                        column.metric(TR(f"training_logging.{label}"), value)
                if not selected:
                    save_choice = st.radio(
                        TR("training_logging.custom_exercise_scope"), ("session_only", "save_to_exercise_library"),
                        format_func=lambda value: TR(f"training_logging.{value}"), horizontal=True,
                        key=f"exercise_scope_{exercise['uuid']}",
                    )
                    exercise["_save_to_library"] = save_choice == "save_to_exercise_library"
                if entry_mode == "simple":
                    exercise["notes"] = st.text_input(
                        TR("training_logging.exercise_notes"), value=exercise.get("notes") or "",
                        key=f"exercise_notes_{exercise['uuid']}",
                    )

            if entry_mode == "advanced" or exercise["exercise_category"] in {"dance", "technique", "rehabilitation"}:
                proficiency, notes = st.columns(2)
                exercise["skill_proficiency"] = proficiency.number_input(
                    TR("training_logging.movement_proficiency"), min_value=1.0, max_value=10.0,
                    value=exercise.get("skill_proficiency"), step=.5,
                    key=f"exercise_proficiency_{exercise['uuid']}",
                    help=TR("training_logging.proficiency_notice"),
                )
                exercise["notes"] = notes.text_input(
                    TR("training_logging.exercise_notes"), value=exercise.get("notes") or "",
                    key=f"exercise_notes_{exercise['uuid']}",
                )

            _set_editor(exercise, index, entry_mode, exertion_preference)
            with st.popover(TR("training_logging.more_actions")):
                if st.button(TR("training_logging.copy_exercise"), key=f"exercise_copy_{exercise['uuid']}"):
                    exercises.insert(index + 1, copy_exercise(exercise)); st.rerun()
                if st.button(TR("training_logging.move_up"), key=f"exercise_up_{exercise['uuid']}", disabled=index == 0):
                    exercises[index - 1], exercises[index] = exercises[index], exercises[index - 1]; st.rerun()
                if st.button(TR("training_logging.move_down"), key=f"exercise_down_{exercise['uuid']}", disabled=index == len(exercises) - 1):
                    exercises[index + 1], exercises[index] = exercises[index], exercises[index + 1]; st.rerun()
                confirmed = st.checkbox(
                    TR("training_logging.confirm_delete_exercise"),
                    key=f"exercise_delete_confirm_{exercise['uuid']}",
                )
                if st.button(
                    TR("training_logging.delete_exercise"), key=f"exercise_delete_{exercise['uuid']}",
                    disabled=not confirmed, type="primary",
                ):
                    exercises.pop(index); st.rerun()

    controls = st.columns((1.2, 1.2, 5))
    if controls[0].button(TR("training_logging.add_exercise"), key=f"exercise_add_{session['id']}"):
        exercises.append(_exercise_default()); st.rerun()
    with controls[1].popover(TR("training_logging.more_actions"), use_container_width=True):
        history = previous_exercises(connection, session["id"])
        if history:
            history_ids = [item["id"] for item in history]
            selected_history = st.selectbox(
                TR("training_logging.history_exercise"), history_ids,
                format_func=lambda value: next(
                    (by_id.get(item.get("exercise_catalog_id"), {}).get(
                        "display_name_zh" if LANGUAGE != "en" else "display_name_en"
                    ) or item.get("custom_exercise_name") or TR("common.no_data"))
                    for item in history if item["id"] == value
                ), key=f"history_exercise_{session['id']}",
            )
            if st.button(TR("training_logging.copy_history_exercise"), key=f"history_copy_{session['id']}"):
                source = next(item for item in history if item["id"] == selected_history)
                exercises.append(copy_exercise(source, reset_completed=True)); st.rerun()
        else:
            st.caption(TR("training_logging.no_history_exercise"))
    st.session_state[state_key] = exercises
    return exercises


def _summary(session, show_title=True):
    summary = session["summary"]
    if show_title:
        st.subheader(TR("training_logging.summary"))
    labels = (
        ("exercise_count", "exercise_count"), ("total_sets", "total_set_count"),
        ("working_sets", "working_set_count"), ("warmup_sets", "warmup_set_count"),
        ("total_reps", "total_reps"), ("volume_load", "strength_volume_load_kg"),
    )
    columns = st.columns(3)
    for index, (label, field) in enumerate(labels):
        value = summary.get(field)
        columns[index % 3].metric(
            TR(f"training_logging.{label}"),
            TR("training_logging.not_calculated") if value is None else format_number(value, LANGUAGE),
        )


def _readonly_training_details(connection, session):
    """Show historical action rows with today's compact read-only layout."""
    catalog = {item["id"]: item for item in list_exercise_catalog(connection)}
    st.subheader(TR("training_logging.exercise_details"))
    grouped = _historical_action_rows(session, catalog)
    if not grouped:
        st.info(TR("training_logging.empty_sets"))
        return
    load_label = f"{TR('training_logging.load')}（KG）"
    headers = (
        TR("training_logging.exercise"),
        TR("training_logging.total_sets").replace("总", "", 1),
        TR("training_logging.reps"),
        load_label,
    )
    for development_type, rows in grouped.items():
        st.markdown(
            "<div class='drc-action-input-header'>"
            + escape(TR("training_logging.development_strength_type"))
            + "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='drc-readonly-development'>"
            + escape(str(development_type))
            + "</div>",
            unsafe_allow_html=True,
        )
        header_columns = st.columns((3.2, .75, .75, .9))
        for column, header in zip(header_columns, headers):
            column.markdown(
                "<div class='drc-action-input-header'>" + escape(str(header)) + "</div>",
                unsafe_allow_html=True,
            )
        for row in rows:
            columns = st.columns((3.2, .75, .75, .9))
            values = (
                row["name"], row["sets"], row["reps"],
                _value(row["load"]) if row["load"] is not None else TR("common.no_data"),
            )
            for column, value in zip(columns, values):
                column.markdown(
                    "<div class='drc-readonly-action-cell'>"
                    + escape(str(value))
                    + "</div>",
                    unsafe_allow_html=True,
                )


def _render_plan_actual_analysis(connection, session):
    plan = get_weekly_training_plan(connection, date.fromisoformat(session["date"]))
    day = plan_day_for_date(plan, date.fromisoformat(session["date"]))
    if not day:
        return
    analysis = analyze_plan_actual(day, session.get("exercises") or [])
    st.markdown(f"### {TR('training_plan.plan_actual')}")
    columns = st.columns(4)
    columns[0].metric(TR("training_plan.exercise_completion"), _value(analysis["exercise_completion_rate"], "%"))
    columns[1].metric(TR("training_plan.set_completion"), _value(analysis["set_completion_rate"], "%"))
    columns[2].metric(TR("training_plan.planned_sets"), analysis["planned_sets"])
    columns[3].metric(TR("training_plan.actual_result"), analysis["completed_sets"])
    regulated = [
        item.get("hprs_snapshot")
        for block in day.get("blocks", [])
        for item in block.get("prescriptions", [])
        if item.get("hprs_snapshot")
    ]
    if regulated:
        with st.expander(TR("training_plan.regulated_plan"), expanded=False):
            st.json(regulated)


def _details(connection, session, *, auto_expand=False, readonly=False):
    historical_data_title = (_ui("历史", "") + TR("training_logging.title")) if LANGUAGE != "en" else TR("training_logging.title")
    historical_details_title = (_ui("历史", "") + TR("training_logging.combined_details")) if LANGUAGE != "en" else TR("training_logging.combined_details")
    with st.expander(historical_data_title, expanded=auto_expand):
        _session_header(session)
        if readonly:
            st.caption(f"{TR('training_logging.notes')}：{session.get('notes') or TR('common.no_data')}")
        else:
            notes = st.text_area(
                TR("training_logging.notes"), value=session.get("notes") or "",
                key=f"training_notes_{session['id']}",
            )

    # Match today's behavior: structured action details and the combined
    # action summary exist only when Polar identified the session as strength
    # training.  Other historical sports keep their Polar data view only.
    if not _is_strength_training_session(session):
        return

    with st.expander(historical_details_title, expanded=auto_expand):
        # The history panel mirrors the compact daily view.  Editing remains
        # available in today's section above; this panel never renders the
        # legacy advanced editor or mutation controls.
        _readonly_training_details(connection, session)
        _historical_training_summary(session)


TRAINING_BASELINE_CSS = """
<style>
.drc-load-card,.drc-load-week{border:1px solid rgba(117,130,148,.18);border-radius:var(--rh-radius-standard);background:rgba(117,130,148,.065);box-shadow:none;color:var(--rh-text)}
.drc-load-card{box-sizing:border-box;min-height:0;padding:1.25rem 1.35rem}.drc-load-card-head{display:flex;align-items:flex-start;justify-content:flex-start;gap:.75rem;flex-wrap:wrap;padding-bottom:.875rem;border-bottom:1px solid var(--rh-border-subtle)}
.drc-load-title{color:var(--rh-text);font-size:1.0625rem;font-weight:600;letter-spacing:-.006em;line-height:1.4}.drc-load-value{color:var(--rh-text);font-size:1.875rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.016em;line-height:1.2;margin:1.125rem 0 0}.drc-load-value.is-empty{font-size:1.4375rem;font-weight:600;letter-spacing:-.01em;margin-top:1.25rem}
.drc-load-evidence{color:var(--rh-text-muted);font-size:.8125rem;line-height:1.55;margin-top:1rem}.drc-load-muted{color:var(--rh-text-muted);font-size:.8125rem;line-height:1.55}.drc-load-status{border-radius:var(--rh-radius-small);background:var(--rh-surface-inset);color:var(--rh-text-secondary);font-size:.8125rem;font-weight:600;line-height:1.3;padding:.3125rem .625rem}.drc-load-status.good{background:var(--rh-status-positive-surface);color:var(--rh-status-positive)}.drc-load-status.info{background:rgba(73,111,153,.12);color:#356da8}.drc-load-status.warn{background:var(--rh-status-caution-surface);color:var(--rh-status-caution)}.drc-load-status.neutral{color:var(--rh-text-secondary)}
.drc-range{position:relative;height:8px;margin:1.15rem 0 .4rem;border-radius:999px;background:linear-gradient(90deg,rgba(117,130,148,.12) 0 20%,rgba(47,125,92,.18) 20% 80%,rgba(117,130,148,.12) 80%)}
.drc-range-bound{position:absolute;top:-.25rem;height:16px;border-left:1px solid var(--rh-text-muted)}.drc-range-marker{position:absolute;top:-.22rem;width:12px;height:12px;margin-left:-6px;border-radius:50%;background:#2e7d52;border:2px solid var(--rh-surface);box-shadow:none}
.drc-load-week{margin-top:1.15rem;padding:1.25rem 1.35rem}.drc-load-week-title{color:var(--rh-text);font-size:1.0625rem;font-weight:600;line-height:1.4}.drc-load-week-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:0;margin-top:1rem;border-top:1px solid var(--rh-border-subtle)}.drc-load-week-item{min-width:0;padding:.875rem 1rem .2rem 0}.drc-load-week-item + .drc-load-week-item{border-left:1px solid var(--rh-border-subtle);padding-left:1rem}.drc-load-week-label{color:var(--rh-text-muted);font-size:.8125rem;font-weight:500;line-height:1.4}.drc-load-week-value{color:var(--rh-text);font-size:1.625rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.016em;line-height:1.25;margin-top:.32rem;overflow-wrap:anywhere}
@media (max-width:720px){.drc-load-card,.drc-load-week{padding:1.1rem}.drc-load-week-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.drc-load-week-item:nth-child(odd){border-left:0;padding-left:0}.drc-load-week-item:nth-child(n+3){border-top:1px solid var(--rh-border-subtle)}}
.drc-calendar{display:grid;grid-template-columns:repeat(14,minmax(28px,1fr));gap:.35rem}.drc-day{height:3.2rem;border:1px solid #d9dee7;border-radius:8px;text-align:center;padding:.3rem;font-size:.72rem;color:#687386}.drc-day.training{background:#cfe8d7;color:#1e6b3d}.drc-day.no_training_yet,.drc-day.confirmed_no_training{background:#f4f5f7}.drc-day.planned_rest{background:#e8eef8;color:#3c6090}.drc-day.missing,.drc-day.not_synced,.drc-day.sync_error{border-style:dashed;background:#fff8e9;color:#9a6b20}.drc-legend{display:flex;flex-wrap:wrap;gap:.8rem;margin-top:.7rem;color:#697386;font-size:.82rem}.drc-legend span:before{content:'';display:inline-block;width:.7rem;height:.7rem;border-radius:3px;background:#cfe8d7;margin-right:.3rem}.drc-legend .missing:before{background:#fff8e9;border:1px dashed #9a6b20}.drc-legend .rest:before{background:#e8eef8}.drc-legend .none:before{background:#f4f5f7}
</style>
"""


def _training_status_label(status):
    return {
        "training_present": "status_training", "no_training_yet": "status_yet",
        "planned_rest": "status_rest", "confirmed_no_training": "status_confirmed",
        "not_synced": "status_waiting", "syncing": "status_syncing", "sync_error": "status_error",
        "missing": "status_missing", "partial": "status_partial", "invalid": "status_invalid",
    }.get(status, "status_waiting")


def _training_value(value, suffix=""):
    return TR("common.no_data") if value is None else f"{format_number(value, LANGUAGE)}{suffix}"


def _training_status_class(status):
    if status == "training_present": return "good"
    if status in {"sync_error", "invalid", "missing"}: return "warn"
    if status in {"partial", "not_synced", "syncing"}: return "info"
    return "neutral"


def _range_bar(item):
    lower, upper, current = item.get("lower_bound"), item.get("upper_bound"), item.get("current_value")
    if current is None or lower is None or upper is None:
        return f"<div class='drc-load-muted'>{escape(TR('training_baseline.range_pending'))}</div>"
    spread = max(float(upper) - float(lower), 1.0)
    low = max(0.0, float(lower) - spread)
    high = max(float(upper) + spread, low + 1.0)
    marker = max(0.0, min(100.0, (float(current) - low) / (high - low) * 100))
    lower_pos = (float(lower) - low) / (high - low) * 100
    upper_pos = (float(upper) - low) / (high - low) * 100
    return (
        f"<div class='drc-range'><span class='drc-range-bound' style='left:{lower_pos:.1f}%'></span>"
        f"<span class='drc-range-bound' style='left:{upper_pos:.1f}%'></span>"
        f"<span class='drc-range-marker' style='left:{marker:.1f}%'></span></div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.low_load'))}　　{escape(TR('training_baseline.typical_range_label'))}　　{escape(TR('training_baseline.high_load'))}</div>"
    )


def _training_metric_card(title, item, suffix=""):
    maturity = item.get("maturity", {})
    comparison = item.get("comparison")
    status = TR({
        "markedly_low": "training_baseline.status_markedly_low", "slightly_low": "training_baseline.status_slightly_low",
        "near_typical": "training_baseline.status_near", "slightly_high": "training_baseline.status_slightly_high",
        "markedly_high": "training_baseline.status_markedly_high", "data_accumulating": "training_baseline.status_accumulating",
    }.get(comparison, "training_baseline.status_accumulating"))
    status_class = "good" if comparison == "near_typical" else "warn" if "markedly" in str(comparison) else "info"
    range_text = (
        f"{_training_value(item.get('lower_bound'))}–{_training_value(item.get('upper_bound'))}{suffix}"
        if item.get("lower_bound") is not None else TR("training_baseline.range_pending")
    )
    pct = item.get("percent_difference")
    pct_text = "—" if pct is None else f"{'↑' if pct > 0 else '↓' if pct < 0 else '→'} {abs(pct):.1f}%"
    window_label = _ui("28天基线", "28-day baseline")
    current_value = item.get("current_value")
    value_class = "drc-load-value is-empty" if current_value is None else "drc-load-value"
    card_html = (
        f"<div class='drc-load-card'><div class='drc-load-card-head'><div class='drc-load-title'>{escape(title)} · {escape(window_label)}</div>"
        f"<div class='drc-load-status {status_class}'>{escape(status)}　{escape(pct_text)}</div></div>"
        f"<div class='{value_class}'>{escape(_training_value(current_value, suffix))}</div>"
        f"<div class='drc-load-evidence'>{escape(TR('training_baseline.baseline'))}：{escape(_training_value(item.get('center'), suffix))}　{escape(TR('training_baseline.typical_range'))}：{escape(range_text)}</div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.baseline_phase'))}：{escape(maturity.get('status','collecting'))} · {escape(TR('training_baseline.valid_days'))}：{maturity.get('valid_days',0)}</div>"
        f"{_range_bar(item)}</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_training_baseline():
    view = get_training_baseline_view()
    baseline_title = TR("training_baseline.title")
    if LANGUAGE != "en":
        baseline_title = _ui("个人训练基线", "Personal Training Baseline")
    st.subheader(baseline_title)
    st.markdown(TRAINING_BASELINE_CSS, unsafe_allow_html=True)
    left, right = st.columns(2)
    with left: _training_metric_card(TR("training_baseline.training_duration"), view["duration_baseline"], traditionalize(" 分钟") if LANGUAGE == "zh-TW" else " 分钟")
    with right: _training_metric_card(TR("training_baseline.training_calories"), view["calorie_baseline"], " kcal")
    st.caption(TR("training_baseline.calorie_note"))
    weekly = view["weekly_load"]
    weekly_values = (
        (TR("training_baseline.training_count"), weekly["session_count"]),
        (TR("training_baseline.cumulative_duration"), _training_value(weekly["duration_minutes"], traditionalize(" 分钟") if LANGUAGE == "zh-TW" else " 分钟")),
        (TR("training_baseline.calories"), _training_value(weekly["calories_kcal"], " kcal")),
        (TR("training_baseline.valid_training_days"), weekly["valid_training_days"]),
        (TR("training_baseline.data_completeness"), f"{weekly['data_completeness']}%"),
    )
    weekly_html = "".join(
        f"<div class='drc-load-week-item'><div class='drc-load-week-label'>{escape(str(label))}</div>"
        f"<div class='drc-load-week-value'>{escape(str(value))}</div></div>"
        for label, value in weekly_values
    )
    st.markdown(
        f"<section class='drc-load-week'><div class='drc-load-week-title'>{escape(TR('training_baseline.recent_week'))}</div>"
        f"<div class='drc-load-week-grid'>{weekly_html}</div></section>",
        unsafe_allow_html=True,
    )
    typical = weekly.get("typical_calories_kcal")
    if typical is not None and weekly.get("calories_kcal") is not None:
        st.caption(TR("training_baseline.relative_week", percent=f"{weekly['calories_kcal'] / typical * 100:.1f}", value=format_number(typical, LANGUAGE)))


def _render_training_guidance():
    st.subheader(_ui("训练建议", "Training Guidance"))
    coach = get_latest_local_coach()
    if not coach:
        st.info(TR("local_coach.missing"))
    else:
        summary = coach.get("training_summary") or {}
        if summary.get("advice"):
            st.info(summary["advice"])
            drivers = "、".join(summary.get("drivers") or [])
            if drivers:
                st.caption(f"{TR('local_coach.comprehensive_basis')}：{drivers}")

        def _card_advice(entry):
            base = entry.get("advice") or TR(
                f"local_coach.training_advice.{entry['status']}"
            )
            combined = summary.get("advice")
            if combined and combined != base:
                return f"{base}\n\n综合调整：{combined}"
            return base

        left, right = st.columns(2)
        with left:
            st.markdown(f"**{TR('local_coach.morning_strength')}**")
            st.write(_card_advice(coach["morning_training"]))
        with right:
            st.markdown(f"**{TR('local_coach.evening_hiphop')}**")
            st.write(_card_advice(coach["evening_training"]))
    st.caption(TR("safety.medical"))


def main():
    intro = TR("domain.exercise.intro")
    intro = intro.replace("确定性建议", "训练建议").replace("deterministic guidance", "training guidance")
    st.title(TR("domain.exercise.title"))
    st.caption(intro)
    training_notice = st.session_state.pop("training_save_notice", None)

    connection = connect()
    try:
        ensure_polar_session_index(connection)
        sessions = list_training_sessions(connection, limit=100)
        _render_plan_actual_v1(connection, sessions, training_notice=training_notice)

    finally:
        connection.close()

if __name__ == "__main__":
    main()
