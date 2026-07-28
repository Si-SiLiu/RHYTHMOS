"""Neural Readiness MVP: subjective state + browser-timed PVT-B."""

import sys
import uuid
from datetime import date
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.i18n import format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.neural_readiness import (CALIBRATION_PROTOCOL_VERSION, DAILY_SHORT_PROTOCOL_VERSION,
                                  get_condition_preferences, get_daily_result,
                                  save_assessment, save_condition_preferences)
from src.pvt_component import render_pvt


configure_language = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(configure_language)("navigation.neural")),
    page_icon=load_page_icon(), layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "neural")


def _ui(zh, en):
    return zh if LANGUAGE != "en" else en


def _reset_flow():
    for key in tuple(st.session_state):
        if key.startswith("neural_") and key != "neural_practice_completed_once":
            del st.session_state[key]


def _start_new_test():
    """Discard only the in-progress UI state and begin a fresh assessment flow."""
    _reset_flow()
    st.session_state["neural_retake"] = True
    st.session_state["neural_phase"] = "instructions"


def _show_result(result):
    st.subheader(_ui("当日结果与个人基线", "Today and personal baseline"))
    if not result:
        st.info(_ui("今日尚未完成神经准备度评估。", "No Neural Readiness assessment has been completed today."))
        return
    if result.get("interrupted"):
        st.warning(_ui("本次测试受到干扰，已保存原始记录，但不会纳入个人基线。", "This run was interrupted. Its raw data is saved but excluded from your baseline."))
    first, second, third, fourth = st.columns(4)
    first.metric(_ui("中位反应时间", "Median RT"), _ui(f"{format_number(result.get('median_rt_ms'), LANGUAGE)} ms", f"{format_number(result.get('median_rt_ms'), LANGUAGE)} ms"))
    second.metric(_ui("最慢 20% 反应", "Slowest 20% RT"), _ui(f"{format_number(result.get('slowest_20pct_rt_ms'), LANGUAGE)} ms", f"{format_number(result.get('slowest_20pct_rt_ms'), LANGUAGE)} ms"))
    third.metric(_ui("反应稳定性（CV）", "Response stability (CV)"), format_number(result.get("rt_coefficient_of_variation"), LANGUAGE))
    fourth.metric(_ui("错误起始", "False starts"), result.get("false_start_count"))
    baseline_labels = {
        "insufficient": _ui("数据不足，暂不判断", "Insufficient data; no interpretation yet"),
        "building": _ui("基线建立中", "Baseline building"),
        "within_baseline": _ui("接近个人基线", "Within personal baseline"),
        "slower_than_baseline": _ui("反应较个人基线慢", "Slower than personal baseline"),
        "faster_than_baseline": _ui("反应较个人基线快", "Faster than personal baseline"),
    }
    confidence_labels = {
        "high": _ui("较高", "High"), "moderate": _ui("中等", "Moderate"),
        "low": _ui("较低", "Low"), "unavailable": _ui("不可评估", "Unavailable"),
    }
    deviations = result.get("baseline_deviations", {})
    rt = deviations.get("median_rt_ms", {})
    left, right = st.columns(2)
    left.metric(
        _ui("个人基线", "Personal baseline"),
        baseline_labels.get(result.get("baseline_status"), result.get("baseline_status")),
        _ui(f"{result.get('baseline_sample_count', 0)} 个有效日", f"{result.get('baseline_sample_count', 0)} valid days"),
    )
    right.metric(_ui("数据置信度", "Data confidence"), confidence_labels.get(result.get("confidence_level"), result.get("confidence_level")))
    if rt.get("baseline_median") is not None:
        st.caption(_ui(
            f"中位反应时间个人中位基线：{format_number(rt['baseline_median'], LANGUAGE)} ms；今日偏离 {format_number(rt.get('absolute_delta'), LANGUAGE)} ms。",
            f"Median RT baseline: {format_number(rt['baseline_median'], LANGUAGE)} ms; today's deviation: {format_number(rt.get('absolute_delta'), LANGUAGE)} ms.",
        ))
    sleep = [
        (_ui("睡眠分数", "Sleep score"), result.get("sleep_score")),
        (_ui("夜间 HRV", "Nightly HRV"), result.get("nightly_hrv_rmssd")),
        (_ui("晨间 RMSSD", "Morning RMSSD"), result.get("morning_rmssd")),
    ]
    available = [f"{label}: {format_number(value, LANGUAGE)}" for label, value in sleep if value is not None]
    st.caption((_ui("已融合当日数据：", "Integrated daily data: ") + " · ".join(available)) if available else _ui("当日尚无可融合的睡眠或 HRV 数据。", "No same-day sleep or HRV data is available to integrate."))
    st.caption(_ui("结果用于个人纵向观察，不构成医疗诊断，也不直接测量中枢神经系统疲劳。", "Results support personal longitudinal observation; they are not medical diagnosis and do not directly measure central nervous system fatigue."))


st.title(_ui("Neural Readiness｜神经准备度", "Neural Readiness"))
st.caption(_ui("预计约 3—4 分钟", "Estimated total time: 3–4 minutes"))
st.caption(_ui(
    "该测试用于评估警觉性、反应稳定性及其相对个人基线的变化，不属于医疗诊断，也不能直接测量中枢神经系统疲劳。",
    "This test evaluates alertness, response stability, and change relative to your personal baseline. It is not medical diagnosis and cannot directly measure central nervous system fatigue.",
))

today = date.today().isoformat()
existing = get_daily_result(today)
if existing and not st.session_state.get("neural_retake"):
    _show_result(existing)
    if st.button(_ui("重新测试", "Retest"), key="neural_retake_button", type="primary"):
        _start_new_test(); st.rerun()
    if st.button(_ui("进行深度校准（约 3 分钟）", "Run deep calibration (about 3 minutes)")):
        _start_new_test(); st.session_state["neural_test_mode"] = "weekly_calibration"; st.rerun()
    st.stop()

phase = st.session_state.get("neural_phase", "instructions")
if phase == "instructions":
    st.subheader(_ui("1. 测试条件确认", "1. Test conditions"))
    if "neural_condition_defaults" not in st.session_state:
        st.session_state["neural_condition_defaults"] = get_condition_preferences()
    defaults = st.session_state["neural_condition_defaults"]
    with st.form("neural_conditions"):
        st.caption(_ui("已按你的上次选择预填。", "Pre-filled from your previous choices."))
        quick_ready = st.form_submit_button(_ui("一键确认以上四项", "Confirm all four"))
        quiet = st.checkbox(_ui("当前环境较安静", "My environment is reasonably quiet"), value=defaults["quiet"])
        dominant = st.checkbox(_ui("我会使用惯用手操作", "I will use my dominant hand"), value=defaults["dominant"])
        stay = st.checkbox(_ui("测试过程中不会切换页面", "I will not change page during the test"), value=defaults["stay"])
        device_ok = st.checkbox(_ui("当前设备和浏览器运行正常", "My device and browser are working normally"), value=defaults["device_ok"])
        st.caption(_ui("以下项目仅记录，不阻止测试：", "The following are recorded but do not block testing:"))
        caffeine = st.checkbox(_ui("过去 2 小时摄入过咖啡因", "Caffeine in the last 2 hours"))
        exercise = st.checkbox(_ui("过去 2 小时进行过训练", "Exercise in the last 2 hours"))
        illness = st.checkbox(_ui("存在明显不适或疾病症状", "Noticeable discomfort or illness symptoms"))
        interrupted = st.checkbox(_ui("测试可能受到外部干扰", "The test may be externally disrupted"))
        calibration = st.checkbox(_ui("进行深度校准（约3分钟）", "Use deep calibration (about 3 minutes)"))
        continue_pressed = st.form_submit_button(_ui("继续填写量表", "Continue to scales"), type="primary")
    if quick_ready:
        st.session_state["neural_condition_defaults"] = {"quiet": True, "dominant": True, "stay": True, "device_ok": True}
        st.rerun()
    if continue_pressed:
        remembered = {"quiet": quiet, "dominant": dominant, "stay": stay, "device_ok": device_ok}
        save_condition_preferences(remembered)
        st.session_state["neural_condition_defaults"] = remembered
        st.session_state["neural_context"] = {"caffeine_last_2h": caffeine, "exercise_last_2h": exercise, "illness_or_discomfort": illness, "interrupted": interrupted}
        st.session_state["neural_test_mode"] = "weekly_calibration" if calibration else "daily_short"
        st.session_state["neural_phase"] = "scales"; st.rerun()

elif phase == "scales":
    st.subheader(_ui("2. 主观状态量表", "2. Subjective state scales"))
    with st.form("neural_subjective_state_form"):
        mental_fatigue = st.slider(_ui("脑力疲劳：0＝完全没有脑力疲劳；10＝极度脑力疲劳", "Mental fatigue: 0 = none; 10 = extreme"), 0, 10, 5)
        mental_clarity = st.slider(_ui("思维清晰度：0＝思维非常模糊；10＝思维非常清晰", "Mental clarity: 0 = very foggy; 10 = very clear"), 0, 10, 5)
        task_motivation = st.slider(_ui("困难任务动力：0＝完全不愿处理；10＝非常愿意处理", "Task motivation: 0 = not willing; 10 = very willing"), 0, 10, 5)
        physical_heaviness = st.slider(_ui("身体沉重感：0＝身体轻快；10＝非常沉重或迟钝", "Physical heaviness: 0 = light; 10 = very heavy or sluggish"), 0, 10, 5)
        submitted = st.form_submit_button(_ui("进入练习模式", "Start practice mode"), type="primary")
    if submitted:
        st.session_state["neural_scale_values"] = {"mental_fatigue": mental_fatigue, "mental_clarity": mental_clarity, "task_motivation": task_motivation, "physical_heaviness": physical_heaviness}
        st.session_state["neural_practice_id"] = uuid.uuid4().hex
        st.session_state["neural_phase"] = "practice"; st.rerun()

elif phase == "practice":
    st.subheader(_ui("3. 练习模式", "3. Practice mode"))
    st.caption(_ui("等待目标出现后点击。完成 5 次正确反应后自动进入正式测试；支持鼠标、触摸和空格键，练习不会保存为正式记录。", "Wait for the target, then respond. After 5 correct responses, formal testing starts automatically. Mouse, touch, and Space are supported; practice is not saved."))
    if st.button(_ui("跳过练习，开始警觉性反应", "Skip practice and start Alertness Probe")):
        st.session_state["neural_assessment_id"] = uuid.uuid4().hex
        st.session_state["neural_phase"] = "formal"
        st.rerun()
    practice_done = st.session_state.get("neural_practice_done", False)
    practice = None if practice_done else render_pvt(run_id=st.session_state["neural_practice_id"], duration_seconds=20, practice=True)
    if practice and not practice_done:
        st.session_state["neural_practice_result"] = practice
        st.session_state["neural_practice_done"] = True
        if practice.get("practice_skipped"):
            st.session_state["neural_assessment_id"] = uuid.uuid4().hex
            st.session_state["neural_phase"] = "formal"
        elif practice.get("practice_ready"):
            st.session_state["neural_assessment_id"] = uuid.uuid4().hex
            st.session_state["neural_phase"] = "formal"
        st.rerun()
    if st.session_state.get("neural_practice_done"):
        practice_result = st.session_state.get("neural_practice_result") or {}
        if practice_result.get("practice_ready"):
            st.session_state["neural_practice_completed_once"] = True
            st.success(_ui("练习完成，正在进入正式测试。", "Practice complete; entering the formal test."))
        else:
            st.warning(_ui("练习未完成，请完成 5 次正确反应或选择跳过练习。", "Practice was not completed. Finish 5 correct responses or skip practice."))
            if st.button(_ui("再练一次", "Practice again"), type="primary"):
                st.session_state["neural_practice_id"] = uuid.uuid4().hex
                st.session_state["neural_practice_done"] = False
                st.session_state["neural_practice_result"] = None
                st.rerun()

elif phase == "formal":
    calibration = st.session_state.get("neural_test_mode") == "weekly_calibration"
    mode = "weekly_calibration" if calibration else "daily_short"
    duration = 180 if calibration else 60
    protocol = CALIBRATION_PROTOCOL_VERSION if calibration else DAILY_SHORT_PROTOCOL_VERSION
    st.subheader(_ui("4. Calibration PVT｜警觉性校准测试（180 秒）", "4. Calibration PVT (180 seconds)") if calibration else _ui("4. Alertness Probe｜警觉性反应（约 1 分钟）", "4. Alertness Probe (about 1 minute)"))
    st.caption(_ui("这是一项约1分钟的简短警觉性任务，用于观察反应速度、反应稳定性和提前操作情况，并与个人历史状态比较。短版主要用于个人趋势观察，不能替代标准实验室 PVT，也不能单独判断中枢神经疲劳或医疗风险。", "This brief task observes response speed, stability, and early responses against your own history. It supports personal trends only and is not a laboratory PVT or medical assessment.") if not calibration else _ui("该模式持续约3分钟，提供更多试次以观察持续警觉性和后半程变化。建议在安静、无明显干扰的环境完成。", "This mode lasts about 3 minutes and provides more trials for sustained-alertness and time-on-task trends."))
    action_left, action_right = st.columns([1, 5])
    if action_left.button(_ui("重新测试", "Retest"), key="neural_retest_formal"):
        _start_new_test()
        st.rerun()
    action_right.caption(_ui("重新测试会清空本次尚未保存的数据，并回到测试条件确认。", "Retest clears this unsaved run and returns to test-condition confirmation."))
    response = render_pvt(run_id=st.session_state["neural_assessment_id"], duration_seconds=duration, protocol_version=protocol)
    if response:
        context = st.session_state["neural_context"]
        payload = {
            "id": st.session_state["neural_assessment_id"], "assessment_date": today,
            "timezone": response.get("device_context", {}).get("timezone") or "UTC",
            "protocol_version": protocol, "test_mode": mode, "baseline_group": mode,
            "duration_seconds": duration, "started_at": response["started_at"],
            "completed_at": response["completed_at"], "trials": response.get("trials", []),
            "device_context": response.get("device_context", {}),
            **context, **st.session_state["neural_scale_values"],
            "interrupted": bool(context.get("interrupted")) or bool(response.get("interrupted")),
            "valid_for_baseline": not context.get("interrupted") and not response.get("interrupted"),
        }
        try:
            save_assessment(payload)
        except (ValueError, OSError) as exc:
            st.error(_ui(f"保存失败：{exc}", f"Save failed: {exc}"))
        else:
            st.session_state["neural_phase"] = "complete"; st.rerun()

else:
    _show_result(get_daily_result(today))
    if st.button(_ui("重新测试", "Retest"), type="primary"):
        _start_new_test(); st.rerun()
