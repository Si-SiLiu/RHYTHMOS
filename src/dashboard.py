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
    MODULE_COLORS, WEEKDAY_KEYS, create_training_day_template,
    analyze_plan_actual, create_training_prescription,
    create_training_program, delete_training_prescription,
    get_or_create_training_block, get_weekly_training_plan,
    plan_day_for_date, prescription_snapshot,
    update_training_day_sport_type,
)
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

TRAINING_CSS = """
<style>
.drc-training-head{display:flex;align-items:center;justify-content:center;text-align:center;font-weight:650;min-height:2.4rem}
div[data-testid="stExpander"] summary p{font-size:1.5rem!important;font-weight:650!important}
div[data-testid="stNumberInput"] button{display:none!important}
div[data-testid="stNumberInput"] input{text-align:center!important;padding-left:0!important;padding-right:0!important;text-indent:0!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
div[data-testid="stTextInput"] input{text-align:center!important;color:#273142!important;-webkit-text-fill-color:#273142!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"]{color:#273142!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] *{color:#273142!important;-webkit-text-fill-color:#273142!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value]{flex:1 1 auto!important;width:100%!important;text-align:center!important;padding-left:2rem!important}
.drc-action-input-header{text-align:center;font-weight:650;min-height:1.6rem}
.drc-readonly-action-cell{display:flex;align-items:center;justify-content:center;min-height:2.7rem;padding:.35rem .5rem;border-radius:10px;background:#f0f2f6;color:#273142;text-align:center}
.drc-readonly-development{display:flex;align-items:center;justify-content:center;min-height:2.7rem;padding:.35rem .5rem;border-radius:10px;background:#f0f2f6;color:#273142;text-align:center;font-weight:650}
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
    return "运动类型" if LANGUAGE != "en" else "Sport Type"


def _history(sessions):
    st.subheader(TR("history.activity_title"))
    history_view_label = "查看" if LANGUAGE != "en" else "View"
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


def _create_week_plan(connection):
    program_id = create_training_program(connection, TR("training_plan.title"))
    labels = {
        "mon": "周一", "tue": "周二", "wed": "周三", "thu": "周四",
        "fri": "周五", "sat": "周六", "sun": "周日",
    } if LANGUAGE != "en" else {
        "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
        "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
    }
    for index, day_key in enumerate(WEEKDAY_KEYS, start=1):
        create_training_day_template(connection, program_id, day_key, labels[day_key], sequence_order=index)
    return program_id


def _plan_cell_text(block):
    if not block:
        return TR("common.none")
    names = []
    for item in block.get("prescriptions", [])[:2]:
        names.append(
            (item.get("display_name_zh") if LANGUAGE != "en" else item.get("display_name_en"))
            or item.get("custom_exercise_name")
            or TR("common.no_data")
        )
    remaining = len(block.get("prescriptions", [])) - len(names)
    return "、".join(names) + (f" +{remaining}{TR('training_plan.more_actions')}" if remaining > 0 else "")


SPORT_TYPE_LABELS = {
    "performance_dance": "表演舞",
    "indoor_strength": "室内力量训练",
    "track_field": "田径运动",
}

ACTION_TYPE_OPTIONS = (
    "关节活动度训练",
    "核心力量激活训练",
    "等长超负荷训练",
    "爆发性力量训练",
    "整体性力量训练-主项",
    "整体性力量训练-副项",
    "小肌肉群力量训练",
)

DEVELOPMENT_STRENGTH_OPTIONS = (
    "上肢拉力",
    "下肢推力",
    "上肢推力",
    "下肢拉力",
    "主动恢复",
)
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
        "单手哑铃划船",
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
        "杠铃臀推",
        "杠铃分腿拉",
        "杠铃后退弓箭步",
        "杠铃跪姿伸髋",
        "北欧挺",
        "上至下旋转－弹力带下劈",
        "杠铃杆卷腕",
    ),
    "主动恢复": (
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
        "杠铃臀推",
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


def _action_name_options(
    action_type, session_id, stored_names=(), development_type=None
):
    """Return all reusable names, including names already stored by the user."""
    # Standard development types keep their strict action whitelist.  A
    # custom development type falls back to the exercise catalog.  In both
    # cases the selectbox below also accepts a new value directly, matching
    # the nutrition food editor without a second custom-name widget.
    development_names = list(DEVELOPMENT_STRENGTH_ACTION_NAMES.get(development_type, ()))
    saved_key = f"today_action_names_{session_id}_{action_type}"
    saved_names = st.session_state.get(saved_key, [])
    source_names = development_names or list(stored_names)
    names = []
    for name in [*source_names, *saved_names]:
        if name and name not in names:
            names.append(name)
    return names, saved_key


def _development_action_rows(rows_by_development, development_type):
    """Return the independent editable action list for one development type."""
    return rows_by_development.setdefault(development_type, [])


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


def _day_actions(day, sport_type):
    blocks = day.get("blocks", []) if sport_type == "indoor_strength" else [
        block for block in day.get("blocks", []) if block.get("module_key") == "daily_plan"
    ]
    return [
        (block, prescription)
        for block in blocks
        for prescription in block.get("prescriptions", [])
    ]


def _render_daily_plan_inputs(connection, days, day_dates, sport_type):
    date_row = st.columns(len(days) + 1)
    date_row[0].markdown(f"**{TR('training_plan.date')}**")
    for day_index, (column, day) in enumerate(zip(date_row[1:], days), start=1):
        day_date = day_dates.get(day["day_key"])
        day_date_label = format_date(day_date.isoformat(), LANGUAGE) if day_date else "—"
        column.markdown(
            f"**{day_index}**  \n{escape(day_date_label)}  \n{escape(day['day_label'])}"
        )
        current_type = day.get("sport_type") or "indoor_strength"
        selected_type = column.selectbox(
            TR("training_plan.sport_type"),
            list(SPORT_TYPE_LABELS),
            index=list(SPORT_TYPE_LABELS).index(current_type) if current_type in SPORT_TYPE_LABELS else 1,
            format_func=lambda value: SPORT_TYPE_LABELS[value],
            key=f"training_plan_day_type_{sport_type}_{day['id']}",
        )
        if selected_type != current_type:
            update_training_day_sport_type(connection, day["id"], selected_type)
            st.rerun()
        actions = _day_actions(day, selected_type)
        if actions:
            names = []
            for _, prescription in actions[:2]:
                names.append(
                    prescription.get("display_name_zh")
                    or prescription.get("custom_exercise_name")
                    or prescription.get("prescription_name")
                    or "未命名动作"
                )
            summary = "、".join(names)
            if len(actions) > 2:
                summary += f" +{len(actions) - 2}个动作"
            column.caption(summary)
        else:
            column.caption(TR("training_plan.no_actions"))
        if column.button(
            TR("training_plan.create_action"),
            key=f"training_plan_day_note_save_{sport_type}_{day['id']}",
            use_container_width=True,
        ):
            st.session_state["training_plan_selected_day"] = day["id"]
            st.session_state["training_plan_add_prescription_day"] = day["id"]
            st.rerun()


def _render_day_action_editor(connection, day):
    sport_type = day.get("sport_type") or "indoor_strength"
    st.markdown(f"#### {day['day_label']} · {SPORT_TYPE_LABELS.get(sport_type, sport_type)}")
    st.caption(TR("training_plan.action_summary"))
    actions = _day_actions(day, sport_type)
    if actions:
        header = st.columns([3, 1, 1, 1, 3, 1])
        for cell, label in zip(header, (
            TR("training_plan.action_name"), TR("training_plan.set_count"),
            TR("training_plan.reps"), TR("training_plan.load_kg"),
            TR("training_plan.notes"), TR("training_plan.delete_action"),
        )):
            cell.caption(label)
        for block, prescription in actions:
            planned = prescription.get("planned_sets") or []
            first_set = planned[0] if planned else {}
            name = (
                prescription.get("display_name_zh")
                or prescription.get("custom_exercise_name")
                or prescription.get("prescription_name")
                or "未命名动作"
            )
            row = st.columns([3, 1, 1, 1, 3, 1])
            row[0].markdown(f"**{escape(name)}**  \n{escape(block['module_label'])}")
            row[1].write(len(planned) or "—")
            row[2].write(first_set.get("reps") or "—")
            row[3].write(first_set.get("load_value") if first_set.get("load_value") is not None else "—")
            row[4].write(prescription.get("target_notes") or "—")
            if row[5].button(TR("training_plan.delete_action"), key=f"training_plan_delete_{prescription['id']}"):
                delete_training_prescription(connection, prescription["id"])
                st.rerun()
    else:
        st.info(TR("training_plan.no_actions_add"))

    module_labels = {
        "mobility": "灵活性", "core_activation": "核心激活",
        "isometric_overload": "等长超负荷", "explosive": "爆发力",
        "main_strength": "主力量", "accessory_strength": "辅助力量",
        "small_muscle": "小肌群",
    }
    with st.form(f"training_plan_action_form_{day['id']}"):
        if sport_type == "indoor_strength":
            module_key = st.selectbox(TR("training_plan.module"), list(module_labels), format_func=lambda value: module_labels[value])
        else:
            module_key = "daily_plan"
            st.caption(f"{TR('training_plan.sport_type_prefix')}：{SPORT_TYPE_LABELS.get(sport_type, sport_type)}")
        name = st.text_input(TR("training_plan.action_name"), placeholder=TR("training_plan.action_name"))
        fields = st.columns(4)
        set_count = fields[0].number_input(TR("training_plan.set_count"), min_value=1, max_value=30, value=3, step=1)
        reps = fields[1].number_input(TR("training_plan.reps"), min_value=1, max_value=200, value=8, step=1)
        load_value = fields[2].number_input(TR("training_plan.load_kg"), min_value=0.0, max_value=1000.0, value=0.0, step=0.5)
        notes = fields[3].text_input(TR("training_plan.notes"), placeholder=TR("training_plan.notes"))
        if st.form_submit_button(TR("training_plan.add_action")):
            if not name.strip():
                st.warning(TR("training_plan.enter_action_name"))
            else:
                module_label = module_labels.get(module_key, SPORT_TYPE_LABELS.get(sport_type, "当日动作"))
                block_id = get_or_create_training_block(
                    connection, day["id"], module_key, module_label,
                )
                planned_sets = [
                    {"set_type": "working", "load_value": float(load_value), "load_unit": "kg", "reps": int(reps)}
                    for _ in range(int(set_count))
                ]
                create_training_prescription(
                    connection, block_id,
                    custom_exercise_name=name.strip(), prescription_name=name.strip(),
                    sequence_order=99, planned_sets=planned_sets, target_notes=notes.strip() or None,
                )
                st.rerun()


def _render_weekly_training_plan(connection):
    with st.expander(TR("training_plan.title"), expanded=False):
        plan = get_weekly_training_plan(connection)
        if not plan["program"]:
            st.info(TR("training_plan.empty"))
            if st.button(TR("training_plan.create_week"), key="training_plan_create_week"):
                with connection:
                    _create_week_plan(connection)
                st.rerun()
            return

        st.caption(f"{TR('training_plan.program')}：{plan['program']['name']}")
        days = plan["days"]
        monday = date.today() - timedelta(days=date.today().weekday())
        day_dates = {
            day_key: monday + timedelta(days=index)
            for index, day_key in enumerate(WEEKDAY_KEYS)
        }
        blocks_by_module = {}
        for day in days:
            if (day.get("sport_type") or "indoor_strength") != "indoor_strength":
                continue
            for block in day["blocks"]:
                if block.get("module_key") == "daily_plan":
                    continue
                blocks_by_module.setdefault(block["module_key"], {})[day["day_key"]] = block

        with st.expander(SPORT_TYPE_LABELS["indoor_strength"], expanded=True):
            st.caption(TR("training_plan.current_matrix_input"))
            _render_daily_plan_inputs(connection, days, day_dates, "indoor_strength")
            if not blocks_by_module:
                st.info(TR("training_plan.no_prescriptions"))
                selected_day_id = st.session_state.get("training_plan_selected_day")
                selected_day = next((day for day in days if day["id"] == selected_day_id), None)
                if (
                    selected_day
                    and (selected_day.get("sport_type") or "indoor_strength") == "indoor_strength"
                    and st.session_state.get("training_plan_add_prescription_day") == selected_day["id"]
                ):
                    _render_day_action_editor(connection, selected_day)
            else:
                for module_key, by_day in blocks_by_module.items():
                    row = st.columns(len(days) + 1)
                    module_html = f"<div class='drc-plan-module'>{escape(by_day[next(iter(by_day))]['module_label'])}</div>"
                    row[0].markdown(module_html, unsafe_allow_html=True)
                    for column, day in zip(row[1:], days):
                        block = by_day.get(day["day_key"])
                        if block:
                            label = _plan_cell_text(block)
                            if column.button(label, key=f"training_plan_cell_{day['id']}_{module_key}", use_container_width=True):
                                st.session_state["training_plan_selected_day"] = day["id"]
                                st.rerun()
                        else:
                            column.markdown(TR("common.no_data"))

                selected_day_id = st.session_state.get("training_plan_selected_day")
                selected_day = next((day for day in days if day["id"] == selected_day_id), None)
                if (
                    selected_day
                    and (selected_day.get("sport_type") or "indoor_strength") == "indoor_strength"
                    and st.session_state.get("training_plan_add_prescription_day") == selected_day["id"]
                ):
                    _render_day_action_editor(connection, selected_day)

        for sport_type, sport_label in SPORT_TYPE_LABELS.items():
            if sport_type == "indoor_strength":
                continue
            selected_day_id = st.session_state.get("training_plan_selected_day")
            selected_day = next((day for day in days if day["id"] == selected_day_id), None)
            show_editor = bool(
                selected_day
                and (selected_day.get("sport_type") or "indoor_strength") == sport_type
                and st.session_state.get("training_plan_add_prescription_day") == selected_day["id"]
            )
            with st.expander(sport_label, expanded=show_editor):
                _render_daily_plan_inputs(connection, days, day_dates, sport_type)
                if show_editor:
                    _render_day_action_editor(connection, selected_day)


def _polar_training_data_row(sessions):
    """Build the shared Polar data row used by daily and historical views."""
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
    return {
        TR("training_logging.today_date"): format_date(data_date, LANGUAGE),
        TR("training_logging.today_count"): len(polar),
        TR("training_logging.start_time"): time_to_hms(start_times[0]) if start_times else no_data,
        TR("training_logging.today_duration"): minutes_to_hms(sum(durations) / 60) if durations else no_data,
        TR("training_logging.today_average_hr"): round(sum(average_hrs) / len(average_hrs)) if average_hrs else no_data,
        TR("training_logging.today_max_hr"): max(max_hrs) if max_hrs else no_data,
        TR("training_logging.today_calories"): sum(calories) if calories else no_data,
        TR("training_logging.today_distance"): sum(distances) if distances else no_data,
    }


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
        if save_draft.button(TR("training_logging.save_draft"), key=f"today_save_draft_{session['id']}") or complete.button(TR("training_logging.complete_log"), key=f"today_complete_{session['id']}", type="primary"):
            save_training_details(connection, session["id"], {
                "resolved_sport_type": session.get("resolved_sport_type") or session.get("polar_sport_type"),
                "status": "completed", "notes": session.get("notes"),
                "training_program_id": (today_plan.get("program") or {}).get("id"),
                "training_day_template_id": today_day.get("id"),
                "prescription_snapshot_json": json.dumps(prescription_snapshot(today_day), ensure_ascii=False),
            }, exercises)
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
        with st.expander(label, expanded=True):
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
    if st.session_state.get(rows_model_key) != 3:
        # Preserve any in-progress legacy rows in the first type during the
        # one-time transition.  Every development type then owns an entirely
        # separate list, so its + and - controls cannot change another type.
        legacy_rows = []
        legacy_groups = st.session_state.get(f"today_action_groups_v2_{session_id}", [])
        legacy_active_id = st.session_state.get(
            f"today_action_active_group_v2_{session_id}"
        )
        legacy_group = next(
            (group for group in legacy_groups if group.get("id") == legacy_active_id),
            legacy_groups[0] if legacy_groups else None,
        )
        if legacy_group:
            legacy_rows = list(legacy_group.get("rows") or [])
        st.session_state[rows_by_development_key] = {
            development_type: (
                legacy_rows if development_type == DEVELOPMENT_STRENGTH_OPTIONS[0]
                else []
            )
            for development_type in DEVELOPMENT_STRENGTH_OPTIONS
        }
        st.session_state[rows_model_key] = 3

    rows_by_development = st.session_state.get(rows_by_development_key, {})
    for development_type in DEVELOPMENT_STRENGTH_OPTIONS:
        rows_by_development.setdefault(development_type, [])
    st.session_state[rows_by_development_key] = rows_by_development
    development_type_key = f"today_action_development_type_{session_id}"
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
        placeholder=(
            "选择或输入发展力量类型"
            if LANGUAGE != "en" else
            "Select or enter development strength type"
        ),
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
        if not row["name"]:
            row["name"] = _recommended_action_name(active_rows[:row_index], action_names)
        name_options = list(action_names)
        if row["name"] and row["name"] not in name_options:
            name_options.append(row["name"])
        if not name_options:
            name_options = [""]
        name_choice_key = f"today_action_v3_name_choice_{session_id}_{row_id}"
        if st.session_state.get(name_choice_key) == "__custom_action__":
            st.session_state[name_choice_key] = (
                row["name"] if row["name"] in name_options else name_options[0]
            )
        selected_name = row_columns[0].selectbox(
            action_name_label, name_options,
            index=(name_options.index(row["name"]) if row["name"] in name_options else 0),
            key=name_choice_key,
            label_visibility="collapsed",
            accept_new_options=True,
            placeholder=(
                "选择或输入动作名称"
                if LANGUAGE != "en" else
                "Select or enter exercise name"
            ),
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
    return grouped


def _session_header(session):
    st.info(TR("training_logging.readonly_notice") if session["polar_readonly"] else TR("training_logging.manual_notice"))
    row = _polar_training_data_row([session])
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
    historical_data_title = ("历史" + TR("training_logging.title")) if LANGUAGE != "en" else TR("training_logging.title")
    historical_details_title = ("历史" + TR("training_logging.combined_details")) if LANGUAGE != "en" else TR("training_logging.combined_details")
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
.drc-load-card{border:1px solid #d9dee7;border-radius:14px;padding:1rem 1.1rem;background:linear-gradient(145deg,#fff,#f7f9fc);min-height:11rem}
.drc-load-title{font-size:1.1rem;font-weight:700;color:#273142}.drc-load-value{font-size:2rem;font-weight:750;color:#222b3a;margin:.35rem 0}
.drc-load-muted{color:#788294;font-size:.88rem}.drc-load-status{font-weight:650;margin-top:.45rem}.drc-load-status.good{color:#1d7a46}.drc-load-status.info{color:#356da8}.drc-load-status.warn{color:#b66a19}.drc-load-status.neutral{color:#697386}
.drc-range{position:relative;height:12px;margin:1.2rem .2rem .4rem;border-radius:999px;background:linear-gradient(90deg,#edf0f4 0 20%,#dcefe2 20% 80%,#edf0f4 80%)}
.drc-range-bound{position:absolute;top:-.35rem;height:26px;border-left:2px solid #6f7885}.drc-range-marker{position:absolute;top:-.25rem;width:20px;height:20px;margin-left:-10px;border-radius:50%;background:#2e7d52;border:3px solid white;box-shadow:0 1px 5px #718096}
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
    window_label = "28天基线" if LANGUAGE != "en" else "28-day baseline"
    card_html = (
        f"<div class='drc-load-card'><div class='drc-load-title'>{escape(title)} · {escape(window_label)}</div>"
        f"<div class='drc-load-value'>{escape(_training_value(item.get('current_value'), suffix))}</div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.baseline'))}：{escape(_training_value(item.get('center'), suffix))}　{escape(TR('training_baseline.typical_range'))}：{escape(range_text)}</div>"
        f"<div class='drc-load-status {status_class}'>{escape(status)}　{escape(pct_text)}</div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.baseline_phase'))}：{escape(maturity.get('status','collecting'))} · {escape(TR('training_baseline.valid_days'))}：{maturity.get('valid_days',0)}</div>"
        f"{_range_bar(item)}</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_training_baseline():
    view = get_training_baseline_view()
    baseline_title = TR("training_baseline.title")
    if LANGUAGE != "en":
        baseline_title = "个人训练基线"
    st.subheader(baseline_title)
    st.markdown(TRAINING_BASELINE_CSS, unsafe_allow_html=True)
    left, right = st.columns(2)
    with left: _training_metric_card(TR("training_baseline.training_duration"), view["duration_baseline"], " 分钟")
    with right: _training_metric_card(TR("training_baseline.training_calories"), view["calorie_baseline"], " kcal")
    st.caption(TR("training_baseline.calorie_note"))
    with st.container(border=True):
        st.markdown(f"### {TR('training_baseline.recent_week')}")
        weekly = view["weekly_load"]
        cols = st.columns(5)
        for column, (label, value) in zip(cols, ((TR("training_baseline.training_count"), weekly["session_count"]), (TR("training_baseline.cumulative_duration"), _training_value(weekly["duration_minutes"], " 分钟")), (TR("training_baseline.calories"), _training_value(weekly["calories_kcal"], " kcal")), (TR("training_baseline.valid_training_days"), weekly["valid_training_days"]), (TR("training_baseline.data_completeness"), f"{weekly['data_completeness']}%"))):
            column.metric(label, value)
        typical = weekly.get("typical_calories_kcal")
        if typical is not None and weekly.get("calories_kcal") is not None:
            st.caption(TR("training_baseline.relative_week", percent=f"{weekly['calories_kcal'] / typical * 100:.1f}", value=format_number(typical, LANGUAGE)))


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
        _today_polar_data(sessions)
        _today_training_details(connection, sessions)
        _history(sessions)
        selected_history_id = st.session_state.get("training_history_selected")
        if selected_history_id is None and sessions:
            selected_history_id = sessions[0]["id"]
        if selected_history_id:
            selected_session = get_training_session(connection, selected_history_id)
            if selected_session:
                focus_nonce = st.session_state.get("training_details_focus_nonce", 0)
                last_focus_nonce = st.session_state.get("training_details_last_scrolled_nonce", 0)
                should_focus = focus_nonce > last_focus_nonce
                # Keep both historical detail expanders collapsed by default;
                # only the click that created this new focus request opens them.
                auto_expand = should_focus
                focus_target_id = f"training-situation-details-{focus_nonce}"
                focus_anchor = f'<div id="{focus_target_id}"></div>'
                st.markdown(focus_anchor, unsafe_allow_html=True)
                if should_focus:
                    render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)
                    st.session_state["training_details_last_scrolled_nonce"] = focus_nonce
                history_training_title = ("历史" + TR("domain.exercise.title")) if LANGUAGE != "en" else TR("domain.exercise.title")
                st.subheader(history_training_title)
                historical_readonly = selected_session.get("date") < date.today().isoformat()
                _details(
                    connection,
                    selected_session,
                    auto_expand=auto_expand,
                    readonly=historical_readonly,
                )
                if training_notice:
                    st.success(training_notice)
        elif training_notice:
            st.success(training_notice)
    finally:
        connection.close()

    _render_training_baseline()

    st.subheader("训练建议" if LANGUAGE != "en" else "Training Guidance")
    coach = get_latest_local_coach()
    if not coach: st.info(TR("local_coach.missing"))
    else:
        left, right = st.columns(2)
        with left:
            st.markdown(f"**{TR('local_coach.morning_strength')}**")
            st.write(TR(f"local_coach.training_advice.{coach['morning_training']['status']}"))
        with right:
            st.markdown(f"**{TR('local_coach.evening_hiphop')}**")
            st.write(TR(f"local_coach.training_advice.{coach['evening_training']['status']}"))
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
