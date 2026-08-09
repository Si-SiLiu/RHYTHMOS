"""Training Studio: browser-based cognitive practice, isolated from daily checks."""
import sqlite3
import sys
import uuid
from datetime import date
from html import escape
from pathlib import Path

root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from src.pages._bootstrap import ensure_project_root
ensure_project_root()

import streamlit as st
import streamlit.components.v1 as components
from src.branding import browser_page_title, load_page_icon
from src.cognitive_component import render_training
from src.cognitive_control_history_view import (
    comparable_records,
    derived_metric,
    display_difficulty,
    display_mode,
    display_percent,
    display_response_time,
    history_rows,
    summary as control_summary,
)
from src.cognitive_history_view import get_training_task_history
from src.cognitive_training import PLANS, get_control_speed_trends, get_training_history, recommendation, save_training_session
from src.demo_sandbox import configure_demo_runtime
from src.i18n import get_translator
from src.i18n.ui import current_language, render_sidebar
from src.i18n.traditional import traditionalize
from src.neural_readiness import get_daily_result
from src.performance_planner import (
    PlannerConflictError,
    PlannerNotFoundError,
    link_checkpoint_run,
)
from src.ui_scroll import render_interaction_focus

configure_demo_runtime(st)
language = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(language)("navigation.training_studio")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, _ = render_sidebar(st, "training_studio")
TR = get_translator(LANGUAGE)

# A page navigation back into Training Studio starts a fresh local flow. Keep
# state during component-driven reruns, but never resume a previous run after
# visiting another page.
if st.session_state.get("drc_previous_page") != "training_studio":
    for key in list(st.session_state):
        if key.startswith("cognitive_"):
            del st.session_state[key]

planner_checkpoint_context = st.session_state.pop(
    "planner_cognitive_checkpoint_context", None
)
if planner_checkpoint_context:
    st.session_state["cognitive_checkpoint_context"] = planner_checkpoint_context
    st.session_state["cognitive_selected_plan"] = "focus_alertness"
    st.session_state["cognitive_selected_mode"] = "quick"
    st.session_state["cognitive_run_id"] = uuid.uuid4().hex
    st.session_state["cognitive_phase"] = "running"

def ui(zh, en):
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


def reset_training_flow():
    """Clear only the current Training Studio run; keep saved history intact."""
    for key in list(st.session_state):
        if key.startswith("cognitive_"):
            del st.session_state[key]
    st.session_state["cognitive_phase"] = "select"


def general_history_rows(records):
    """Keep daily training history useful without exposing storage columns."""
    plan_keys = {
        "focus_alertness": "plan_focus_alertness",
        "working_memory": "plan_working_memory",
        "cognitive_control_speed": "plan_cognitive_control_speed",
    }
    rows = []
    for record in records:
        complete = bool(record.get("completed_session_count")) and record.get("average_accuracy") is not None
        rows.append({
            TR("cognitive_progress.date"): record.get("date") or TR("cognitive_progress.missing"),
            TR("cognitive_progress.test"): TR(f"cognitive_progress.{plan_keys.get(record.get('training_plan'), 'unknown')}") if record.get("training_plan") in plan_keys else TR("cognitive_progress.missing"),
            TR("cognitive_progress.completed_sessions"): TR(
                "cognitive_progress.completed_sessions_value",
                value=record.get("completed_session_count") or 0,
            ),
            TR("cognitive_progress.accuracy"): display_percent(record.get("average_accuracy"), LANGUAGE),
            TR("cognitive_progress.median_response_time"): display_response_time(record.get("median_rt_ms"), LANGUAGE),
            TR("cognitive_progress.difficulty"): display_difficulty(record.get("highest_difficulty"), LANGUAGE),
            TR("cognitive_progress.data_status"): TR(
                "cognitive_progress.data_complete" if complete else "cognitive_progress.data_incomplete"
            ),
        })
    return rows


def general_record_rows(records):
    """Compact record list for the top-level history section."""
    plan_keys = {
        "focus_alertness": "plan_focus_alertness",
        "working_memory": "plan_working_memory",
        "cognitive_control_speed": "plan_cognitive_control_speed",
    }
    return [{
        TR("cognitive_progress.date"): record.get("date") or TR("cognitive_progress.missing"),
        TR("cognitive_progress.test"): TR(f"cognitive_progress.{plan_keys[record['training_plan']]}"),
        TR("cognitive_progress.completed_sessions"): TR(
            "cognitive_progress.completed_sessions_value",
            value=record.get("completed_session_count") or 0,
        ),
        TR("cognitive_progress.data_status"): TR(
            "cognitive_progress.data_complete"
            if record.get("completed_session_count")
            else "cognitive_progress.data_incomplete"
        ),
    } for record in records if record.get("training_plan") in plan_keys]


def render_cognitive_record_table(records):
    """Selectable historical records, matching the shared View interaction."""
    rows = general_record_rows(records)
    if not rows:
        st.info(ui("最近 28 天暂无训练记录。", "No training records in the last 28 days."))
        return None
    record_keys = [f"{record.get('date')}|{record.get('training_plan')}" for record in records]
    selected_key = st.session_state.get("cognitive_history_selected")
    if selected_key not in record_keys:
        selected_key = record_keys[0]
        st.session_state["cognitive_history_selected"] = selected_key
    headers = list(rows[0]) + [TR("cognitive_progress.action")]
    widths = [1.2, 2.1, 1.25, 1.2, .7]
    with st.container(height=430, border=True):
        header_columns = st.columns(widths)
        for column, label in zip(header_columns, headers):
            column.markdown(
                f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>',
                unsafe_allow_html=True,
            )
        for record, row, record_key in zip(records, rows, record_keys):
            columns = st.columns(widths, vertical_alignment="center")
            for column, label in zip(columns[:-1], headers[:-1]):
                column.markdown(
                    f'<div style="text-align:center;">{escape(str(row[label]))}</div>',
                    unsafe_allow_html=True,
                )
            if columns[-1].button(
                TR("cognitive_progress.view"),
                key=f"cognitive_history_view_{record_key}",
                use_container_width=True,
            ):
                st.session_state["cognitive_history_selected"] = record_key
                st.session_state["cognitive_history_detail_plan"] = record["training_plan"]
                st.session_state["cognitive_history_focus_nonce"] = (
                    st.session_state.get("cognitive_history_focus_nonce", 0) + 1
                )
                st.rerun()
    return next((record for record, record_key in zip(records, record_keys) if record_key == selected_key), None)


def render_control_history(show_heading=True):
    """Display Cognitive Control history without exposing comparison internals."""
    if show_heading:
        st.subheader(TR("cognitive_control_history.title"))
    test_types = tuple(PLANS["cognitive_control_speed"])
    selected_test = st.selectbox(
        TR("cognitive_control_history.test_selector"),
        test_types,
        format_func=lambda value: TR(f"cognitive_control_history.test_{value}"),
        key="control_history_test_type",
    )
    days = st.radio(
        TR("cognitive_control_history.trend_title"),
        (7, 14, 30),
        format_func=lambda value: TR(f"cognitive_control_history.days_{value}"),
        horizontal=True,
        key="control_history_days",
        label_visibility="collapsed",
    )
    records = [
        record for record in get_control_speed_trends(days)
        if record.get("task_type") == selected_test
    ]
    result = control_summary(records, LANGUAGE)
    if result is None:
        st.info(TR("cognitive_control_history.trend_empty"))
        return

    st.markdown(f"#### {result['test']} · {result['mode']}")
    metrics = st.columns(5)
    metrics[0].metric(TR("cognitive_control_history.accuracy"), result["accuracy"])
    metrics[1].metric(TR("cognitive_control_history.median_response_time"), result["reaction_time"])
    metrics[2].metric(TR("cognitive_control_history.difficulty"), result["difficulty"])
    metrics[3].metric(TR("cognitive_control_history.valid_records"), result["valid_records"])
    metrics[4].metric(TR("cognitive_control_history.trend_status"), result["trend_status"])
    metric = derived_metric(result["latest"], LANGUAGE)
    if metric:
        st.caption(f"{metric['label']}: {metric['value']}")
        st.caption(metric["explanation"])

    st.markdown(f"#### {TR('cognitive_control_history.trend_title')}")
    comparable, _ = comparable_records(records)
    if len(comparable) < 3:
        st.info(TR("cognitive_control_history.trend_empty"))
    else:
        st.dataframe(history_rows(comparable, LANGUAGE), use_container_width=True, hide_index=True)


def render_plan_task_history(plan):
    """Render task-level history for Focus & Alertness or Working Memory."""
    test_types = tuple(PLANS[plan])
    selected_test = st.selectbox(
        TR("cognitive_control_history.test_selector"),
        test_types,
        format_func=lambda value: TR(f"cognitive_control_history.test_{value}"),
        key=f"cognitive_history_{plan}_test",
    )
    days = st.radio(
        TR("cognitive_control_history.trend_title"),
        (7, 14, 30),
        format_func=lambda value: TR(f"cognitive_control_history.days_{value}"),
        horizontal=True,
        key=f"cognitive_history_{plan}_days",
        label_visibility="collapsed",
    )
    records = [
        record for record in get_training_task_history(plan, days)
        if record.get("task_type") == selected_test
    ]
    result = control_summary(records, LANGUAGE)
    if result is None:
        st.info(TR("cognitive_progress.no_plan_history"))
        return
    st.markdown(f"#### {result['test']} · {result['mode']}")
    metrics = st.columns(5)
    metrics[0].metric(TR("cognitive_control_history.accuracy"), result["accuracy"])
    metrics[1].metric(TR("cognitive_control_history.median_response_time"), result["reaction_time"])
    metrics[2].metric(TR("cognitive_control_history.difficulty"), result["difficulty"])
    metrics[3].metric(TR("cognitive_control_history.valid_records"), result["valid_records"])
    metrics[4].metric(TR("cognitive_control_history.trend_status"), result["trend_status"])
    st.markdown(f"#### {TR('cognitive_control_history.trend_title')}")
    comparable, _ = comparable_records(records)
    if len(comparable) < 3:
        st.info(TR("cognitive_control_history.trend_empty"))
    else:
        st.dataframe(history_rows(comparable, LANGUAGE), use_container_width=True, hide_index=True)


def render_plan_history_detail(plan, records):
    """Render the same task-level detail surface for the non-control plans."""
    render_plan_task_history(plan)


def today_task_history(target_date):
    """Collect today's persisted task results without changing stored data."""
    records = []
    for plan in PLANS:
        records.extend(
            record for record in get_training_task_history(plan, 30)
            if str(record.get("started_at") or "")[:10] == target_date
        )
    return sorted(records, key=lambda record: str(record.get("started_at") or ""), reverse=True)


st.title(ui("认知训练", "Cognitive Training"))
st.caption(ui("通过短时、结构化的认知任务，训练专注、警觉、工作记忆、认知控制与处理速度。训练成绩反映任务内表现和长期练习趋势，不代表智力水平或医学诊断。", "Short, structured cognitive tasks for focus, alertness, working memory, cognitive control, and processing speed. Results describe task performance and practice trends, not intelligence or medical diagnosis."))
with st.container(border=True):
    st.markdown(ui("**Daily Neural Check**：固定协议、固定难度，用于状态检测并进入个人基线。\n\n**认知训练**：可自适应难度、可以积分和升级，用于认知练习，结果只进入训练档案，不直接影响神经准备度或恢复评分。", "**Daily Neural Check**: fixed protocol and difficulty for state assessment and baseline.\n\n**Cognitive Training**: adaptive practice with points and levels; results stay in the training record and do not change Neural Readiness or Recovery scores."))

history = get_training_history(28)
today = date.today().isoformat()
today_history = [record for record in history if record.get("date") == today]
today_tasks = today_task_history(today)
st.subheader(TR("cognitive_progress.today_data"))
if today_history:
    st.dataframe(general_history_rows(today_history), use_container_width=True, hide_index=True)
else:
    st.info(TR("cognitive_progress.no_today_data"))
st.subheader(TR("cognitive_progress.today_details"))
if today_tasks:
    st.dataframe(history_rows(today_tasks, LANGUAGE), use_container_width=True, hide_index=True)
else:
    st.info(TR("cognitive_progress.no_today_details"))
try:
    neural = get_daily_result()
except Exception:
    neural = None
recommendation_data = recommendation(neural, history)
st.subheader(ui("今日推荐", "Today's recommendation"))
st.info(recommendation_data["reason"])

phase = st.session_state.get("cognitive_phase", "select")
if phase == "select":
    st.subheader(ui("训练方案", "Training plans"))
    plans = {"focus_alertness": ui("Focus & Alertness｜专注与警觉", "Focus & Alertness"), "working_memory": ui("Working Memory｜工作记忆", "Working Memory"), "cognitive_control_speed": ui("Cognitive Control & Processing Speed｜认知控制与处理速度", "Cognitive Control & Processing Speed")}
    selected = st.radio(ui("选择训练方案", "Choose a training plan"), list(plans), format_func=lambda key: plans[key], key="cognitive_selected_plan")
    if selected == "cognitive_control_speed":
        st.caption(ui("通过干扰抑制、规则切换和符号匹配任务，练习在复杂信息中保持准确、灵活和高效的反应。", "Practice interference control, flexible rule switching, and efficient symbol processing through structured cognitive tasks."))
    mode = st.radio(ui("训练时长", "Session length"), ["standard", "quick"], format_func=lambda value: ui("标准训练（约 6–8 分钟）", "Standard (about 6–8 min)") if value == "standard" else ui("快速训练（约 3–4 分钟）", "Quick (about 3–4 min)"), horizontal=True, key="cognitive_selected_mode")
    if st.button(ui("开始训练", "Start training"), type="primary"):
        st.session_state["cognitive_run_id"] = uuid.uuid4().hex
        st.session_state["cognitive_phase"] = "running"
        st.rerun()
    st.caption(ui("训练前完成 Daily Neural Check 更利于固定时间比较；训练后建议休息，不建议无限重复。", "Complete Daily Neural Check before training when possible for consistent comparisons. Rest after a session; avoid endless repetition."))

    st.divider()
    st.subheader(TR("cognitive_progress.section_title"))
    st.caption(ui("趋势只比较相同训练方案、模式和相近难度；不同难度的原始反应速度不直接比较。", "Trends compare like-for-like plans, modes, and nearby difficulty; raw reaction times across difficulty levels are not compared directly."))
    plan_order = ("focus_alertness", "working_memory", "cognitive_control_speed")
    focus_nonce = st.session_state.get("cognitive_history_focus_nonce", 0)
    last_focus_nonce = st.session_state.get("cognitive_history_last_focus_nonce", 0)
    auto_expand = focus_nonce > last_focus_nonce
    focus_target_id = "cognitive-history-details-focus-target"
    st.markdown(f'<div id="{focus_target_id}"></div>', unsafe_allow_html=True)
    with st.expander(TR("cognitive_progress.records"), expanded=False):
        selected_record = render_cognitive_record_table(history)
    with st.expander(TR("cognitive_progress.all_history"), expanded=auto_expand):
        if history:
            if selected_record:
                st.caption(TR("cognitive_progress.selected_data"))
                st.dataframe(general_history_rows([selected_record]), use_container_width=True, hide_index=True)
            st.caption(TR("cognitive_progress.all_history_caption"))
            for plan in plan_order:
                plan_rows = [row for row in history if row.get("training_plan") == plan]
                if not plan_rows:
                    continue
                st.markdown(f"#### {TR(f'cognitive_progress.plan_{plan}')}")
                st.dataframe(general_history_rows(plan_rows), use_container_width=True, hide_index=True)
        else:
            st.info(ui("最近 28 天暂无训练记录。", "No training records in the last 28 days."))
    with st.expander(TR("cognitive_progress.details"), expanded=auto_expand):
        detail_plans = ("focus_alertness", "working_memory", "cognitive_control_speed")
        selected_detail_plan = st.radio(
            TR("cognitive_progress.detail_type"),
            detail_plans,
            format_func=lambda value: TR(f"cognitive_progress.plan_{value}"),
            horizontal=False,
            key="cognitive_history_detail_plan",
        )
        if selected_detail_plan == "cognitive_control_speed":
            render_control_history(show_heading=False)
        else:
            render_plan_history_detail(selected_detail_plan, history)
    if auto_expand:
        st.session_state["cognitive_history_last_focus_nonce"] = focus_nonce
        render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)
elif phase == "running":
    plan = st.session_state.get("cognitive_selected_plan", "focus_alertness")
    mode = st.session_state.get("cognitive_selected_mode", "standard")
    if st.session_state.get("cognitive_checkpoint_context"):
        st.caption(ui("本次为计划建议的任务前认知检查。", "This is a suggested before-task cognitive check."))
    action_left, action_right = st.columns([1, 5])
    if action_left.button(ui("重新测试", "Retest"), key="cognitive_retest_running"):
        reset_training_flow()
        st.rerun()
    action_right.caption(ui("重新测试会清空本次尚未保存的数据，并回到训练方案选择。", "Retest clears this unsaved run and returns to training-plan selection."))
    response = render_training(run_id=st.session_state["cognitive_run_id"], training_plan=plan, session_mode=mode, task_types=PLANS[plan])
    if response:
        try:
            saved = save_training_session(response)
        except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
            st.error(ui(f"保存失败：{exc}", f"Save failed: {exc}"))
        else:
            checkpoint_context = st.session_state.get("cognitive_checkpoint_context")
            if saved.get("completed") and checkpoint_context:
                try:
                    linked = link_checkpoint_run(
                        checkpoint_context["checkpoint_id"],
                        saved["session_id"],
                    )
                except (PlannerConflictError, PlannerNotFoundError, sqlite3.Error) as exc:
                    st.error(ui(f"检查关联失败：{exc}", f"Checkpoint link failed: {exc}"))
                    st.stop()
                saved["checkpoint_id"] = linked["checkpoint_id"]
            st.session_state["cognitive_saved"] = saved
            st.session_state["cognitive_phase"] = "summary"
            st.rerun()
elif phase == "summary":
    saved = st.session_state.get("cognitive_saved", {})
    st.subheader(ui("训练总结", "Training summary"))
    if saved.get("interrupted"):
        st.warning(ui("本次训练被中断，已保存原始记录，但不计入个人最佳成绩。", "This session was interrupted. Raw data is saved but excluded from personal bests."))
    task_labels = {
        "focus_target": ui("目标专注", "Target Focus"),
        "focus_gonogo": ui("反应抑制", "Go / No-Go"),
        "focus_visual_search": ui("视觉搜索", "Visual Search"),
        "memory_grid": ui("记忆棋盘", "Memory Grid"),
        "sequence_memory": ui("工作记忆", "Working Memory"),
        "nback_lite": ui("轻量 N-back", "N-back Lite"),
        "stroop_control": ui("斯特鲁普控制", "Stroop Control"),
        "task_switching": ui("任务切换", "Task Switching"),
        "symbol_match": ui("符号匹配", "Symbol Match"),
    }
    tasks = saved.get("tasks", [])
    st.caption(ui("以下为本次连续完成的三项正式训练数据。", "Results from the three formal tasks completed in this session."))
    cols = st.columns(len(tasks) or 1)
    for col, task in zip(cols, tasks):
        with col:
            col.metric(task_labels.get(task["task_type"], task["task_type"]), "—" if task.get("accuracy") is None else f"{task['accuracy']*100:.0f}%", ui("正确率", "Accuracy"))
            st.caption(ui(f"难度 {task.get('difficulty_start')} → {task.get('difficulty_end')}", f"Difficulty {task.get('difficulty_start')} → {task.get('difficulty_end')}"))
            st.caption(ui(
                f"正确 {task.get('correct_count', 0)} / {task.get('total_trials', 0)} · 中位反应 {task.get('median_rt_ms') if task.get('median_rt_ms') is not None else '—'} ms",
                f"Correct {task.get('correct_count', 0)} / {task.get('total_trials', 0)} · Median RT {task.get('median_rt_ms') if task.get('median_rt_ms') is not None else '—'} ms",
            ))
            if task.get("task_type") == "focus_gonogo":
                metrics = task.get("metrics") or {}
                go_total = metrics.get("go_trial_count") or 1
                st.caption(ui(f"GO 正确率：{(metrics.get('correct_go_count') or 0) / go_total * 100:.0f}% · NO-GO 抑制正确率：{(metrics.get('inhibition_accuracy') or 0) * 100:.0f}%", f"GO accuracy: {(metrics.get('correct_go_count') or 0) / go_total * 100:.0f}% · NO-GO inhibition: {(metrics.get('inhibition_accuracy') or 0) * 100:.0f}%"))
                st.caption(ui(f"GO 遗漏：{metrics.get('omission_count') or 0} · NO-GO 误触：{metrics.get('commission_error_count') or 0}", f"GO omissions: {metrics.get('omission_count') or 0} · NO-GO commissions: {metrics.get('commission_error_count') or 0}"))
            if task.get("task_type") in {"stroop_control", "task_switching", "symbol_match"}:
                metrics = task.get("metrics") or {}
                key = {"stroop_control": "interference_cost_ms", "task_switching": "switch_cost_ms", "symbol_match": "correct_per_minute"}[task["task_type"]]
                st.caption(ui(f"关键指标：{metrics.get(key) if metrics.get(key) is not None else '样本不足'}", f"Key metric: {metrics.get(key) if metrics.get(key) is not None else 'insufficient data'}"))
    st.info(ui("本次结果用于观察任务内表现和练习趋势；当前数据不足以判断长期变化。建议现在休息片刻。", "This result describes task performance and practice trends; it is not enough to judge long-term change. Consider resting now."))
    action_left, action_right = st.columns(2)
    if action_left.button(ui("重新测试", "Retest"), type="primary"):
        reset_training_flow()
        st.rerun()
    if action_right.button(ui("再看训练方案", "Back to training plans")):
        reset_training_flow()
        st.rerun()
