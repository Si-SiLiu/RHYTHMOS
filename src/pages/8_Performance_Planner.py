"""Performance Planner: local daily planning and deterministic adaptations."""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, time
from pathlib import Path


root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from src.pages._bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.demo_sandbox import configure_demo_runtime
from src.i18n import format_datetime, format_number, format_percent, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.neural_fatigue_service import compute_current_result
from src.neural_readiness import calculate_work_impact, get_daily_result, get_work_phase_results
from src.performance_planner import (
    ADAPTIVE_RECOVERY_TITLE,
    BLOCK_STATUSES,
    BLOCK_TYPES,
    CHECKPOINT_TRIGGERS,
    CHECKPOINT_TYPES,
    DEMAND_LEVELS,
    PLAN_STATUSES,
    PRIORITY_LEVELS,
    PlannerConflictError,
    PlannerNotFoundError,
    PlannerValidationError,
    acknowledge_recommendation,
    add_block,
    apply_recommendation,
    build_daily_cognitive_check_suggestions,
    create_checkpoint,
    create_plan,
    delete_block,
    delete_checkpoint,
    delete_plan,
    dismiss_suggested_cognitive_checkpoint,
    ensure_suggested_cognitive_checkpoint,
    generate_recommendations,
    get_plan_for_date,
    get_timeline_summary,
    get_block_defaults,
    link_checkpoint_run,
    list_blocks,
    list_checkpoints,
    list_recommendations,
    reorder_blocks,
    transition_block,
    update_block,
    update_checkpoint_status,
    update_plan,
)

PLANNER_OPERATION_ERRORS = (
    PlannerConflictError,
    PlannerNotFoundError,
    PlannerValidationError,
)


configure_demo_runtime(st)
page_language = current_language(st.session_state)
page_translator = get_translator(page_language)
st.set_page_config(
    page_title=browser_page_title(
        page_translator("navigation.performance_planner")
    ),
    page_icon=load_page_icon(),
    layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "performance_planner")

PLANNER_STYLE = """
<style>
.pp-hero{padding:.3rem 0 1rem}
.pp-subtitle{font-size:1.22rem;font-weight:650;opacity:.78}
.pp-block{border-left:.35rem solid #4f8bf9;padding:.35rem .8rem;margin:.2rem 0}
.pp-block small{opacity:.72}
div[data-testid="stMetric"]{min-width:0}
div[data-testid="stExpander"]:has(.pp-add-block-marker) label{text-align:center;justify-content:center;width:100%}
div[data-testid="stExpander"]:has(.pp-add-block-marker) [data-baseweb="input"] input,
div[data-testid="stExpander"]:has(.pp-add-block-marker) [data-baseweb="textarea"] textarea{text-align:center!important}
/* Streamlit selectboxes use a separate value container from their native input.
   Center that container while keeping the disclosure icon anchored at the right. */
div[data-testid="stExpander"]:has(.pp-add-block-marker) [data-baseweb="select"]>div{position:relative}
div[data-testid="stExpander"]:has(.pp-add-block-marker) [data-baseweb="select"]>div>div:first-child{
  position:absolute!important;inset:0;display:flex!important;
  align-items:center;justify-content:center!important;text-align:center!important
}
div[data-testid="stExpander"]:has(.pp-add-block-marker) [data-baseweb="select"]>div>div:first-child *{
  text-align:center!important
}
@media(max-width:600px){
  .pp-subtitle{font-size:1.05rem}
  .pp-block{padding-left:.55rem}
  div[data-testid="stHorizontalBlock"]{flex-wrap:wrap}
}
</style>
"""
st.markdown(PLANNER_STYLE, unsafe_allow_html=True)


def _flash(key: str) -> None:
    st.session_state["performance_planner_flash"] = key
    st.rerun()


def _show_flash() -> None:
    key = st.session_state.pop("performance_planner_flash", None)
    if key:
        st.success(TR(key))
    error_key = st.session_state.pop("performance_planner_error", None)
    if error_key:
        st.error(TR(error_key))


def _error(exc: Exception) -> None:
    if isinstance(exc, PlannerConflictError):
        key = (
            "performance_planner.overlap_error"
            if "overlap" in str(exc)
            else "performance_planner.run_conflict"
        )
    elif isinstance(exc, PlannerNotFoundError):
        key = (
            "performance_planner.run_not_found"
            if "cognitive run" in str(exc)
            else "performance_planner.not_found_error"
        )
    elif isinstance(exc, PlannerValidationError):
        key = (
            "performance_planner.time_error"
            if "planned_end" in str(exc)
            else "performance_planner.input_error"
        )
    else:
        key = "performance_planner.unexpected_error"
    st.session_state["performance_planner_error"] = key
    st.rerun()


def _label(group: str, value: str) -> str:
    return TR(f"performance_planner.{group}.{value}")


def _combine(day: date, selected_time: time) -> datetime:
    return datetime.combine(day, selected_time)


def _local_timezone_name() -> str:
    """Return the computer's configured IANA timezone."""
    localtime = Path("/etc/localtime")
    try:
        resolved = localtime.resolve()
        marker = "/zoneinfo/"
        resolved_text = str(resolved)
        if marker in resolved_text:
            return resolved_text.split(marker, 1)[1]
    except OSError:
        pass
    return datetime.now().astimezone().tzinfo.key if getattr(
        datetime.now().astimezone().tzinfo, "key", None
    ) else "UTC"


def _block_title(block: dict) -> str:
    if block["title"] == ADAPTIVE_RECOVERY_TITLE:
        return TR("performance_planner.adaptive_recovery")
    return block["title"]


ADD_BLOCK_WIDGET_KEYS = (
    "pp_add_block_title",
    "pp_add_block_type",
    "pp_add_start_time",
    "pp_add_end_time",
    "pp_add_priority",
    "pp_add_cognitive_demand",
    "pp_add_physical_demand",
    "pp_add_context",
    "pp_add_notes",
)
ADD_BLOCK_ADVANCED_FIELDS = ("priority", "cognitive_demand", "physical_demand")
ADD_BLOCK_MARKER = '<span class="pp-add-block-marker"></span>'


def _initialise_add_block_state() -> None:
    if st.session_state.pop("pp_add_reset", False):
        for key in ADD_BLOCK_WIDGET_KEYS:
            st.session_state.pop(key, None)
        st.session_state.pop("pp_add_advanced_touched", None)
    block_type = st.session_state.setdefault("pp_add_block_type", BLOCK_TYPES[0])
    defaults = get_block_defaults(block_type)
    st.session_state.setdefault("pp_add_block_title", "")
    st.session_state.setdefault("pp_add_start_time", time(9, 0))
    st.session_state.setdefault("pp_add_end_time", time(10, 0))
    touched = st.session_state.setdefault("pp_add_advanced_touched", {})
    for field in ADD_BLOCK_ADVANCED_FIELDS:
        st.session_state.setdefault(f"pp_add_{field}", defaults[field])
        touched.setdefault(field, False)


def _mark_add_block_advanced_touched(field: str) -> None:
    st.session_state.setdefault("pp_add_advanced_touched", {})[field] = True


def _apply_add_block_type_defaults() -> None:
    block_type = st.session_state["pp_add_block_type"]
    defaults = get_block_defaults(block_type)
    touched = st.session_state.setdefault("pp_add_advanced_touched", {})
    for field in ADD_BLOCK_ADVANCED_FIELDS:
        if not touched.get(field, False):
            st.session_state[f"pp_add_{field}"] = defaults[field]


def _open_neural_readiness() -> None:
    st.switch_page("pages/3_Neural_Readiness.py")


def _neural_fatigue_band(score: float) -> str:
    if score < 34:
        return "low"
    if score < 67:
        return "moderate"
    return "high"


def _render_neural_fatigue_status(selected_date: date) -> None:
    st.subheader(TR("performance_planner.neural_fatigue_section"))
    st.caption(TR("performance_planner.neural_fatigue_boundary"))
    try:
        view = compute_current_result(target_date=selected_date)
    except (sqlite3.Error, ValueError):
        st.warning(TR("performance_planner.neural_fatigue_unavailable"))
        return

    result = view["result"]
    if result.status != "available" or result.burden_score is None:
        st.warning(TR("performance_planner.neural_fatigue_insufficient"))
        return

    band = _neural_fatigue_band(result.burden_score)
    metrics = st.columns(4)
    metrics[0].metric(
        TR("performance_planner.neural_fatigue_burden"),
        format_number(result.burden_score, LANGUAGE),
    )
    metrics[1].metric(
        TR("performance_planner.neural_fatigue_level"),
        TR(f"performance_planner.neural_fatigue_{band}"),
    )
    metrics[2].metric(
        TR("performance_planner.neural_fatigue_confidence"),
        format_percent(result.confidence * 100, LANGUAGE),
    )
    metrics[3].metric(
        TR("performance_planner.neural_fatigue_components"),
        format_number(len(result.available_components), LANGUAGE),
    )
    if view["latest_observation"] is not None:
        st.caption(
            TR("performance_planner.neural_fatigue_latest")
            + ": "
            + format_datetime(view["latest_observation"], LANGUAGE)
        )


def _render_neural_readiness_summary(selected_date: date) -> None:
    """Show the current readiness state as the input to today's plan."""
    st.subheader(TR("performance_planner.neural_readiness_section"))
    st.caption(TR("performance_planner.neural_readiness_hint"))
    result = get_daily_result(selected_date.isoformat())
    if not result:
        st.info(TR("performance_planner.neural_readiness_missing"))
        if st.button(
            TR("performance_planner.complete_neural_readiness"),
            key="performance_planner_start_neural_readiness",
            type="primary",
            width="content",
        ):
            _open_neural_readiness()
        return

    metrics = st.columns(4)
    metrics[0].metric(
        TR("performance_planner.neural_median_rt"),
        f"{format_number(result.get('median_rt_ms'), LANGUAGE)} ms",
    )
    metrics[1].metric(
        TR("performance_planner.neural_stability"),
        format_number(result.get("rt_coefficient_of_variation"), LANGUAGE),
    )
    metrics[2].metric(
        TR("performance_planner.neural_baseline"),
        TR(f"performance_planner.neural_baseline_{result.get('baseline_status', 'insufficient')}"),
    )
    metrics[3].metric(
        TR("performance_planner.neural_confidence"),
        TR(f"performance_planner.neural_confidence_{result.get('confidence_level', 'unavailable')}"),
    )
    st.caption(TR("performance_planner.neural_readiness_plan_link"))
    if st.button(
        TR("performance_planner.retest_neural_readiness"),
        key="performance_planner_retest_neural_readiness",
        type="primary",
        width="content",
    ):
        _open_neural_readiness()
    impact = calculate_work_impact(get_work_phase_results(selected_date.isoformat()))
    if impact:
        st.caption(TR("performance_planner.work_impact_section"))
        impact_columns = st.columns(3)
        impact_columns[0].metric(
            TR("performance_planner.work_rt_change"),
            "—" if impact["median_rt_delta_ms"] is None else f"{impact['median_rt_delta_ms']:+.0f} ms",
        )
        impact_columns[1].metric(
            TR("performance_planner.work_fatigue_change"),
            f"{impact['mental_fatigue_delta']:+d}",
        )
        impact_columns[2].metric(
            TR("performance_planner.work_impact_level"),
            TR(f"performance_planner.work_impact_{impact['level']}"),
        )


def _block_by_id(blocks: list[dict], block_id: str | None) -> dict | None:
    return next((block for block in blocks if block["block_id"] == block_id), None)


def _start_suggested_cognitive_check(plan_id: str, related_block_id: str) -> None:
    checkpoint = ensure_suggested_cognitive_checkpoint(plan_id, related_block_id)
    st.session_state["planner_cognitive_checkpoint_context"] = {
        "checkpoint_id": checkpoint["checkpoint_id"],
        "plan_id": checkpoint["plan_id"],
        "related_block_id": checkpoint["related_block_id"],
        "trigger_type": checkpoint["trigger_type"],
    }
    st.switch_page("pages/6_Training_Studio.py")


def _render_cognitive_check_suggestions(plan_id: str) -> None:
    st.subheader(TR("performance_planner.cognitive_check_suggestions"))
    suggestions = build_daily_cognitive_check_suggestions(plan_id)
    if not suggestions:
        st.caption(TR("performance_planner.no_cognitive_check_suggestions"))
        return
    for suggestion in suggestions:
        with st.container(border=True):
            st.markdown(f"**{TR('performance_planner.cognitive_check_suggestion')}**")
            st.write(suggestion["block_title"])
            suggested_at = datetime.fromisoformat(suggestion["scheduled_at"])
            st.caption(TR("performance_planner.before_task", time=suggested_at.strftime("%H:%M")))
            st.caption(TR("performance_planner.cognitive_check_suggestion_hint"))
            actions = st.columns(2)
            if actions[0].button(
                TR("performance_planner.start_cognitive_check"),
                key=f"pp_start_cognitive_{suggestion['suggestion_id']}",
                type="primary",
            ):
                try:
                    _start_suggested_cognitive_check(
                        plan_id,
                        suggestion["related_block_id"],
                    )
                except PLANNER_OPERATION_ERRORS as exc:
                    _error(exc)
            if actions[1].button(
                TR("performance_planner.skip_cognitive_check"),
                key=f"pp_skip_cognitive_{suggestion['suggestion_id']}",
            ):
                try:
                    dismiss_suggested_cognitive_checkpoint(
                        plan_id,
                        suggestion["related_block_id"],
                    )
                except PLANNER_OPERATION_ERRORS as exc:
                    _error(exc)
                else:
                    _flash("performance_planner.cognitive_check_skipped")


st.title(TR("performance_planner.title"))
st.subheader(TR("performance_planner.subtitle"))
st.caption(TR("performance_planner.intro"))
st.info(TR("performance_planner.local_notice"))
_show_flash()

selected_date = st.date_input(
    TR("performance_planner.plan_date"),
    value=date.today(),
    key="performance_planner_date",
)

_render_neural_readiness_summary(selected_date)
_render_neural_fatigue_status(selected_date)
plan = get_plan_for_date(selected_date)

if plan is None:
    st.info(TR("performance_planner.no_plan"))
    with st.form("performance_planner_create"):
        st.subheader(TR("performance_planner.new_plan"))
        new_title = st.text_input(
            TR("performance_planner.plan_title"),
            value=TR("performance_planner.default_plan_title"),
        )
        new_timezone = st.text_input(
            TR("performance_planner.timezone"),
            value=_local_timezone_name(),
        )
        submitted = st.form_submit_button(
            TR("performance_planner.create"),
            type="primary",
        )
        if submitted:
            try:
                create_plan(selected_date, new_title, new_timezone)
            except PLANNER_OPERATION_ERRORS as exc:
                _error(exc)
            else:
                _flash("performance_planner.plan_saved")
    st.stop()

blocks = list_blocks(plan["plan_id"])
checkpoints = list_checkpoints(plan["plan_id"])
summary = get_timeline_summary(plan["plan_id"])
current_block = _block_by_id(blocks, summary["current_block_id"])
next_block = _block_by_id(blocks, summary["next_block_id"])

metric_columns = st.columns(4)
metric_columns[0].metric(
    TR("performance_planner.completion"),
    f"{summary['completion_percent']:.0f}%",
)
metric_columns[1].metric(
    TR("performance_planner.completed_blocks"),
    f"{summary['completed_block_count']}/{summary['total_block_count']}",
)
metric_columns[2].metric(
    TR("performance_planner.high_demand"),
    TR("performance_planner.minutes_value", value=summary["high_cognitive_minutes"]),
)
metric_columns[3].metric(
    TR("performance_planner.recovery_minutes"),
    TR("performance_planner.minutes_value", value=summary["recovery_minutes"]),
)

status_columns = st.columns(3)
status_columns[0].caption(TR("performance_planner.current_block"))
status_columns[0].write(
    _block_title(current_block)
    if current_block
    else TR("performance_planner.none_scheduled")
)
status_columns[1].caption(TR("performance_planner.next_block"))
status_columns[1].write(
    _block_title(next_block)
    if next_block
    else TR("performance_planner.none_scheduled")
)
status_columns[2].caption(TR("performance_planner.continuous_work"))
status_columns[2].write(
    TR(
        "performance_planner.minutes_value",
        value=summary["continuous_work_minutes"],
    )
)
st.progress(min(1.0, summary["completion_percent"] / 100))

schedule_tab, checkpoint_tab, recommendation_tab, settings_tab = st.tabs(
    [
        TR("performance_planner.schedule"),
        TR("performance_planner.checkpoints"),
        TR("performance_planner.recommendations_tab"),
        TR("performance_planner.settings"),
    ]
)

with schedule_tab:
    with st.expander(TR("performance_planner.add_block"), expanded=not blocks):
        _initialise_add_block_state()
        st.markdown(ADD_BLOCK_MARKER, unsafe_allow_html=True)
        block_title = st.text_input(
            TR("performance_planner.block_title"),
            key="pp_add_block_title",
        )
        first_row = st.columns(3)
        block_type = first_row[0].selectbox(
            TR("performance_planner.block_type"),
            BLOCK_TYPES,
            format_func=lambda value: _label("types", value),
            key="pp_add_block_type",
            on_change=_apply_add_block_type_defaults,
        )
        start_time = first_row[1].time_input(
            TR("performance_planner.start"),
            key="pp_add_start_time",
        )
        end_time = first_row[2].time_input(
            TR("performance_planner.end"),
            key="pp_add_end_time",
        )
        with st.expander(TR("performance_planner.more_options"), expanded=False):
            second_row = st.columns(3)
            priority = second_row[0].selectbox(
                TR("performance_planner.priority"),
                PRIORITY_LEVELS,
                format_func=lambda value: _label("priority_values", value),
                key="pp_add_priority",
                on_change=_mark_add_block_advanced_touched,
                args=("priority",),
            )
            cognitive_demand = second_row[1].selectbox(
                TR("performance_planner.cognitive_demand"),
                DEMAND_LEVELS,
                format_func=lambda value: _label("demand", value),
                key="pp_add_cognitive_demand",
                on_change=_mark_add_block_advanced_touched,
                args=("cognitive_demand",),
            )
            physical_demand = second_row[2].selectbox(
                TR("performance_planner.physical_demand"),
                DEMAND_LEVELS,
                format_func=lambda value: _label("demand", value),
                key="pp_add_physical_demand",
                on_change=_mark_add_block_advanced_touched,
                args=("physical_demand",),
            )
            context = st.text_input(
                TR("performance_planner.context"),
                key="pp_add_context",
            )
            notes = st.text_area(
                TR("performance_planner.notes"),
                key="pp_add_notes",
            )
        add_submitted = st.button(
            TR("performance_planner.add"),
            type="primary",
            key="pp_add_block_submit",
        )
        if add_submitted:
            try:
                add_block(
                    plan["plan_id"],
                    block_title,
                    block_type,
                    _combine(selected_date, start_time),
                    _combine(selected_date, end_time),
                    priority=priority,
                    cognitive_demand=cognitive_demand,
                    physical_demand=physical_demand,
                    context=context,
                    notes=notes,
                )
            except PLANNER_OPERATION_ERRORS as exc:
                _error(exc)
            else:
                st.session_state["pp_add_reset"] = True
                _flash("performance_planner.block_added")

    if not blocks:
        st.info(TR("performance_planner.empty_schedule"))

    for index, block in enumerate(blocks):
        block_start = datetime.fromisoformat(block["planned_start"])
        block_end = datetime.fromisoformat(block["planned_end"])
        with st.container(border=True):
            display_columns = st.columns([1.2, 3.5, 1.4])
            display_columns[0].markdown(
                TR(
                    "performance_planner.block_time",
                    start=block_start.strftime("%H:%M"),
                    end=block_end.strftime("%H:%M"),
                )
            )
            display_columns[1].write(_block_title(block))
            display_columns[1].caption(
                f"{_label('types', block['block_type'])} · "
                f"{TR('performance_planner.cognitive_demand')}: "
                f"{_label('demand', block['cognitive_demand'])}"
            )
            display_columns[2].write(
                _label("status_values", block["status"])
            )

            action_columns = st.columns(6)
            transitions = (
                ("in_progress", "mark_in_progress"),
                ("completed", "mark_completed"),
                ("skipped", "mark_skipped"),
                ("postponed", "mark_postponed"),
            )
            for action_column, (target_status, label_key) in zip(
                action_columns[:4],
                transitions,
            ):
                if action_column.button(
                    TR(f"performance_planner.{label_key}"),
                    key=f"pp_status_{block['block_id']}_{target_status}",
                    disabled=block["status"] == target_status,
                    use_container_width=True,
                ):
                    try:
                        transition_block(block["block_id"], target_status)
                    except PLANNER_OPERATION_ERRORS as exc:
                        _error(exc)
                    else:
                        _flash("performance_planner.block_saved")
            if action_columns[4].button(
                TR("performance_planner.move_up"),
                key=f"pp_up_{block['block_id']}",
                disabled=index == 0,
                use_container_width=True,
            ):
                ordered = [item["block_id"] for item in blocks]
                ordered[index - 1], ordered[index] = ordered[index], ordered[index - 1]
                reorder_blocks(plan["plan_id"], ordered)
                st.rerun()
            if action_columns[5].button(
                TR("performance_planner.move_down"),
                key=f"pp_down_{block['block_id']}",
                disabled=index == len(blocks) - 1,
                use_container_width=True,
            ):
                ordered = [item["block_id"] for item in blocks]
                ordered[index + 1], ordered[index] = ordered[index], ordered[index + 1]
                reorder_blocks(plan["plan_id"], ordered)
                st.rerun()

            with st.expander(TR("performance_planner.edit")):
                with st.form(f"pp_edit_{block['block_id']}"):
                    edit_title = st.text_input(
                        TR("performance_planner.block_title"),
                        value=_block_title(block),
                    )
                    edit_row = st.columns(3)
                    edit_type = edit_row[0].selectbox(
                        TR("performance_planner.block_type"),
                        BLOCK_TYPES,
                        index=BLOCK_TYPES.index(block["block_type"]),
                        format_func=lambda value: _label("types", value),
                        key=f"pp_type_{block['block_id']}",
                    )
                    edit_start = edit_row[1].time_input(
                        TR("performance_planner.start"),
                        value=block_start.time(),
                        key=f"pp_start_{block['block_id']}",
                    )
                    edit_end = edit_row[2].time_input(
                        TR("performance_planner.end"),
                        value=block_end.time(),
                        key=f"pp_end_{block['block_id']}",
                    )
                    demand_row = st.columns(3)
                    edit_priority = demand_row[0].selectbox(
                        TR("performance_planner.priority"),
                        PRIORITY_LEVELS,
                        index=PRIORITY_LEVELS.index(block["priority"]),
                        format_func=lambda value: _label("priority_values", value),
                        key=f"pp_priority_{block['block_id']}",
                    )
                    edit_cognitive = demand_row[1].selectbox(
                        TR("performance_planner.cognitive_demand"),
                        DEMAND_LEVELS,
                        index=DEMAND_LEVELS.index(block["cognitive_demand"]),
                        format_func=lambda value: _label("demand", value),
                        key=f"pp_cognitive_{block['block_id']}",
                    )
                    edit_physical = demand_row[2].selectbox(
                        TR("performance_planner.physical_demand"),
                        DEMAND_LEVELS,
                        index=DEMAND_LEVELS.index(block["physical_demand"]),
                        format_func=lambda value: _label("demand", value),
                        key=f"pp_physical_{block['block_id']}",
                    )
                    edit_context = st.text_input(
                        TR("performance_planner.context"),
                        value=block["context"] or "",
                        key=f"pp_context_{block['block_id']}",
                    )
                    edit_notes = st.text_area(
                        TR("performance_planner.notes"),
                        value=block["notes"] or "",
                        key=f"pp_notes_{block['block_id']}",
                    )
                    if st.form_submit_button(TR("performance_planner.save")):
                        try:
                            update_block(
                                block["block_id"],
                                title=edit_title,
                                block_type=edit_type,
                                planned_start=_combine(selected_date, edit_start),
                                planned_end=_combine(selected_date, edit_end),
                                priority=edit_priority,
                                cognitive_demand=edit_cognitive,
                                physical_demand=edit_physical,
                                context=edit_context,
                                notes=edit_notes,
                            )
                        except PLANNER_OPERATION_ERRORS as exc:
                            _error(exc)
                        else:
                            _flash("performance_planner.block_saved")
                delete_confirmed = st.checkbox(
                    TR("performance_planner.confirm_delete"),
                    key=f"pp_delete_confirm_{block['block_id']}",
                )
                if st.button(
                    TR("performance_planner.delete"),
                    key=f"pp_delete_{block['block_id']}",
                    disabled=not delete_confirmed,
                ):
                    delete_block(block["block_id"])
                    _flash("performance_planner.block_deleted")

with checkpoint_tab:
    _render_cognitive_check_suggestions(plan["plan_id"])
    with st.expander(TR("performance_planner.advanced_research_settings"), expanded=False):
        with st.expander(TR("performance_planner.add_checkpoint_manually"), expanded=False):
            with st.form("performance_planner_add_checkpoint"):
                checkpoint_row = st.columns(3)
                checkpoint_type = checkpoint_row[0].selectbox(
                    TR("performance_planner.checkpoint_type"),
                    CHECKPOINT_TYPES,
                    format_func=lambda value: _label("checkpoint_types", value),
                )
                trigger_type = checkpoint_row[1].selectbox(
                    TR("performance_planner.trigger_type"),
                    CHECKPOINT_TRIGGERS,
                    format_func=lambda value: _label("triggers", value),
                )
                checkpoint_time = checkpoint_row[2].time_input(
                    TR("performance_planner.scheduled_at"),
                    value=time(12, 0),
                )
                block_options = [None, *[block["block_id"] for block in blocks]]
                related_block_id = st.selectbox(
                    TR("performance_planner.related_block"),
                    block_options,
                    format_func=lambda value: (
                        TR("performance_planner.no_related_block")
                        if value is None
                        else _block_title(_block_by_id(blocks, value))
                    ),
                )
                if st.form_submit_button(TR("performance_planner.add"), type="primary"):
                    try:
                        create_checkpoint(
                            plan["plan_id"], checkpoint_type,
                            _combine(selected_date, checkpoint_time), trigger_type,
                            related_block_id=related_block_id,
                        )
                    except PLANNER_OPERATION_ERRORS as exc:
                        _error(exc)
                    else:
                        _flash("performance_planner.checkpoint_added")

        with st.expander(TR("performance_planner.technical_details"), expanded=False):
            if not checkpoints:
                st.info(TR("performance_planner.checkpoint_empty"))
            for checkpoint in checkpoints:
                with st.container(border=True):
                    checkpoint_columns = st.columns([2.5, 2, 1.2])
                    checkpoint_columns[0].write(_label("checkpoint_types", checkpoint["checkpoint_type"]))
                    checkpoint_columns[1].write(datetime.fromisoformat(checkpoint["scheduled_at"]).strftime("%H:%M"))
                    checkpoint_columns[2].write(_label("status_values", checkpoint["status"]))
                    with st.form(f"pp_link_{checkpoint['checkpoint_id']}"):
                        run_id = st.text_input(
                            TR("performance_planner.run_id"),
                            value=checkpoint["cognitive_run_id"] or "",
                            disabled=checkpoint["cognitive_run_id"] is not None,
                        )
                        if st.form_submit_button(
                            TR("performance_planner.link_run"),
                            disabled=checkpoint["cognitive_run_id"] is not None,
                        ):
                            try:
                                link_checkpoint_run(checkpoint["checkpoint_id"], run_id)
                            except PLANNER_OPERATION_ERRORS as exc:
                                _error(exc)
                            else:
                                _flash("performance_planner.run_linked")
                    checkpoint_actions = st.columns(2)
                    if checkpoint_actions[0].button(
                        TR("performance_planner.mark_skipped"),
                        key=f"pp_checkpoint_skip_{checkpoint['checkpoint_id']}",
                        disabled=checkpoint["status"] != "pending",
                    ):
                        update_checkpoint_status(checkpoint["checkpoint_id"], "skipped")
                        st.rerun()
                    confirmation_key = f"pp_checkpoint_delete_pending_{checkpoint['checkpoint_id']}"
                    if st.session_state.get(confirmation_key):
                        st.warning(TR("performance_planner.checkpoint_delete_notice"))
                        confirmation_actions = st.columns(2)
                        if confirmation_actions[0].button(
                            TR("performance_planner.checkpoint_delete_confirm"),
                            key=f"pp_checkpoint_delete_confirm_{checkpoint['checkpoint_id']}",
                        ):
                            delete_checkpoint(checkpoint["checkpoint_id"])
                            st.session_state.pop(confirmation_key, None)
                            _flash("performance_planner.checkpoint_deleted")
                        if confirmation_actions[1].button(
                            TR("performance_planner.checkpoint_delete_cancel"),
                            key=f"pp_checkpoint_delete_cancel_{checkpoint['checkpoint_id']}",
                        ):
                            st.session_state.pop(confirmation_key, None)
                            st.rerun()
                    elif checkpoint_actions[1].button(
                        TR("performance_planner.delete"),
                        key=f"pp_checkpoint_delete_{checkpoint['checkpoint_id']}",
                    ):
                        st.session_state[confirmation_key] = True
                        st.rerun()

with recommendation_tab:
    st.caption(TR("performance_planner.generate_hint"))
    st.warning(TR("performance_planner.no_auto_change"))
    if st.button(
        TR("performance_planner.generate"),
        type="primary",
        key="pp_generate",
    ):
        try:
            generate_recommendations(plan["plan_id"])
        except PLANNER_OPERATION_ERRORS as exc:
            _error(exc)
        else:
            st.rerun()
    recommendations = list_recommendations(plan["plan_id"], latest_only=True)
    if not recommendations:
        st.info(TR("performance_planner.no_recommendations"))
    for recommendation in recommendations:
        with st.container(border=True):
            heading_columns = st.columns([3, 1, 1])
            heading_columns[0].subheader(TR(recommendation["title_key"]))
            heading_columns[1].caption(TR("performance_planner.severity"))
            heading_columns[1].write(
                _label("severity_values", recommendation["severity"])
            )
            heading_columns[2].caption(TR("performance_planner.data_sufficiency"))
            heading_columns[2].write(
                _label("sufficiency", recommendation["data_sufficiency"])
            )
            st.write(TR(recommendation["message_key"]))
            st.caption(TR("performance_planner.rationale"))
            st.caption(
                _label("rationales", recommendation["rationale"])
            )
            action_columns = st.columns(2)
            if action_columns[0].button(
                TR("performance_planner.acknowledge"),
                key=f"pp_ack_{recommendation['recommendation_id']}",
                disabled=recommendation["acknowledged_at"] is not None,
            ):
                acknowledge_recommendation(recommendation["recommendation_id"])
                _flash("performance_planner.acknowledged")
            confirmed = action_columns[1].checkbox(
                TR("performance_planner.apply_confirm"),
                key=f"pp_confirm_{recommendation['recommendation_id']}",
            )
            if action_columns[1].button(
                TR("performance_planner.apply"),
                key=f"pp_apply_{recommendation['recommendation_id']}",
                disabled=(
                    not confirmed
                    or recommendation["applied_at"] is not None
                ),
            ):
                try:
                    apply_recommendation(
                        recommendation["recommendation_id"],
                        confirmed=confirmed,
                    )
                except PLANNER_OPERATION_ERRORS as exc:
                    _error(exc)
                else:
                    _flash("performance_planner.applied")

with settings_tab:
    with st.form("performance_planner_settings"):
        settings_title = st.text_input(
            TR("performance_planner.plan_title"),
            value=plan["title"],
        )
        settings_timezone = st.text_input(
            TR("performance_planner.timezone"),
            value=plan["timezone"],
        )
        settings_status = st.selectbox(
            TR("performance_planner.status"),
            PLAN_STATUSES,
            index=PLAN_STATUSES.index(plan["status"]),
            format_func=lambda value: _label("status_values", value),
        )
        if st.form_submit_button(
            TR("performance_planner.save"),
            type="primary",
        ):
            try:
                update_plan(
                    plan["plan_id"],
                    title=settings_title,
                    timezone=settings_timezone,
                    status=settings_status,
                )
            except PLANNER_OPERATION_ERRORS as exc:
                _error(exc)
            else:
                _flash("performance_planner.plan_saved")
    plan_delete_confirmed = st.checkbox(
        TR("performance_planner.confirm_delete"),
        key="pp_plan_delete_confirm",
    )
    if st.button(
        TR("performance_planner.delete"),
        key="pp_plan_delete",
        disabled=not plan_delete_confirmed,
    ):
        delete_plan(plan["plan_id"])
        _flash("performance_planner.plan_deleted")
