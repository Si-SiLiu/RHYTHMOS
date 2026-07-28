"""Training Studio: browser-based cognitive practice, isolated from daily checks."""
import sys
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from src.pages._bootstrap import ensure_project_root
ensure_project_root()

import streamlit as st
from src.branding import browser_page_title, load_page_icon
from src.cognitive_component import render_training
from src.cognitive_training import PLANS, get_training_history, recommendation, save_training_session
from src.demo_sandbox import configure_demo_runtime
from src.i18n import get_translator
from src.i18n.ui import current_language, render_sidebar
from src.neural_readiness import get_daily_result

configure_demo_runtime(st)
language = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(language)("navigation.training_studio")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, _ = render_sidebar(st, "training_studio")

# A page navigation back into Training Studio starts a fresh local flow. Keep
# state during component-driven reruns, but never resume a previous run after
# visiting another page.
if st.session_state.get("drc_previous_page") != "training_studio":
    for key in list(st.session_state):
        if key.startswith("cognitive_"):
            del st.session_state[key]

def ui(zh, en):
    return zh if LANGUAGE != "en" else en


def reset_training_flow():
    """Clear only the current Training Studio run; keep saved history intact."""
    for key in list(st.session_state):
        if key.startswith("cognitive_"):
            del st.session_state[key]
    st.session_state["cognitive_phase"] = "select"

st.title(ui("Training Studio｜认知训练室", "Training Studio"))
st.caption(ui("通过短时、结构化的认知任务，训练专注、警觉、工作记忆、认知控制与处理速度。训练成绩反映任务内表现和长期练习趋势，不代表智力水平或医学诊断。", "Short, structured cognitive tasks for focus, alertness, working memory, cognitive control, and processing speed. Results describe task performance and practice trends, not intelligence or medical diagnosis."))
with st.container(border=True):
    st.markdown(ui("**Daily Neural Check**：固定协议、固定难度，用于状态检测并进入个人基线。\n\n**Training Studio**：可自适应难度、可以积分和升级，用于认知练习，结果只进入训练档案，不直接影响神经准备度或恢复评分。", "**Daily Neural Check**: fixed protocol and difficulty for state assessment and baseline.\n\n**Training Studio**: adaptive practice with points and levels; results stay in the training record and do not change Neural Readiness or Recovery scores."))

history = get_training_history(28)
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
elif phase == "running":
    plan = st.session_state.get("cognitive_selected_plan", "focus_alertness")
    mode = st.session_state.get("cognitive_selected_mode", "standard")
    action_left, action_right = st.columns([1, 5])
    if action_left.button(ui("重新测试", "Retest"), key="cognitive_retest_running"):
        reset_training_flow()
        st.rerun()
    action_right.caption(ui("重新测试会清空本次尚未保存的数据，并回到训练方案选择。", "Retest clears this unsaved run and returns to training-plan selection."))
    response = render_training(run_id=st.session_state["cognitive_run_id"], training_plan=plan, session_mode=mode, task_types=PLANS[plan])
    if response:
        try:
            saved = save_training_session(response)
        except (ValueError, KeyError, OSError) as exc:
            st.error(ui(f"保存失败：{exc}", f"Save failed: {exc}"))
        else:
            st.session_state["cognitive_saved"] = saved
            st.session_state["cognitive_phase"] = "summary"
            st.rerun()
elif phase == "summary":
    saved = st.session_state.get("cognitive_saved", {})
    st.subheader(ui("训练总结", "Training summary"))
    if saved.get("interrupted"):
        st.warning(ui("本次训练被中断，已保存原始记录，但不计入个人最佳成绩。", "This session was interrupted. Raw data is saved but excluded from personal bests."))
    tasks = saved.get("tasks", [])
    cols = st.columns(len(tasks) or 1)
    for col, task in zip(cols, tasks):
        with col:
            col.metric(task["task_type"], "—" if task.get("accuracy") is None else f"{task['accuracy']*100:.0f}%")
            st.caption(ui(f"难度 {task.get('difficulty_start')} → {task.get('difficulty_end')}", f"Difficulty {task.get('difficulty_start')} → {task.get('difficulty_end')}"))
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
