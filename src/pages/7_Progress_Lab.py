"""Read-only training progress view."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
from src.pages._bootstrap import ensure_project_root
ensure_project_root()
import streamlit as st
from src.branding import browser_page_title, load_page_icon
from src.cognitive_training import get_control_speed_trends, get_training_history
from src.i18n import get_translator
from src.i18n.ui import current_language, render_sidebar

language = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(language)("navigation.progress_lab")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, _ = render_sidebar(st, "progress_lab")

def ui(zh, en):
    return zh if LANGUAGE != "en" else en

st.title(ui("Progress Lab｜训练进展", "Progress Lab"))
st.caption(ui("趋势只比较相同训练方案、模式和相近难度；不同难度的原始反应速度不直接比较。", "Trends compare like-for-like plans, modes, and nearby difficulty; raw reaction times across difficulty levels are not compared directly."))
history = get_training_history(28)
general_history = [row for row in history if row.get("training_plan") != "cognitive_control_speed"]
if not history:
    st.info(ui("最近 28 天暂无训练记录。", "No training records in the last 28 days."))
elif general_history:
    st.dataframe(general_history, use_container_width=True, hide_index=True)
    st.caption(ui("快速模式和标准模式在数据层分别保存；设备上下文用于解释屏幕尺寸和输入设备差异。", "Quick and standard modes are stored separately; device context helps explain screen and input-device differences."))

control_trends = get_control_speed_trends(28)
if control_trends:
    st.subheader(ui("认知控制与处理速度", "Cognitive Control & Processing Speed"))
    mode = st.selectbox(ui("模式（不混合比较）", "Mode (kept separate)"), ["quick", "standard"], key="control_speed_trend_mode")
    rows = [row for row in control_trends if row["session_mode"] == mode]
    protocols = sorted({row["protocol_version"] for row in rows})
    protocol = st.selectbox(ui("协议", "Protocol"), protocols, key="control_speed_protocol") if protocols else None
    rows = [row for row in rows if row["protocol_version"] == protocol]
    difficulties = sorted({row["difficulty_config_hash"] for row in rows})
    difficulty = st.selectbox(ui("难度配置", "Difficulty configuration"), difficulties, key="control_speed_difficulty") if difficulties else None
    rows = [row for row in rows if row["difficulty_config_hash"] == difficulty]
    devices = sorted({row["device_class"] for row in rows})
    device = st.selectbox(ui("设备类别", "Device class"), devices, key="control_speed_device") if devices else None
    rows = [row for row in rows if row["device_class"] == device]
    methods = sorted({row["input_method"] for row in rows})
    method = st.selectbox(ui("输入方式", "Input method"), methods, key="control_speed_input") if methods else None
    rows = [row for row in rows if row["input_method"] == method]
    show_all = st.checkbox(ui("查看全部历史记录（不可直接比较）", "Show all history (not directly comparable)"), value=False)
    if show_all:
        rows = [row for row in control_trends if row["session_mode"] == mode]
        st.warning(ui("当前视图混合了不同协议、难度或设备条件，不可直接解释为训练趋势。", "This view mixes protocol, difficulty, or device conditions and is not directly comparable."))
    if rows:
        display = []
        for row in rows:
            metrics = row["metrics"]
            display.append({
                ui("日期", "Date"): row["started_at"][:10], ui("任务", "Task"): row["task_type"],
                ui("协议", "Protocol"): row["protocol_version"], ui("难度", "Difficulty"): row["difficulty_end"],
                ui("难度配置", "Difficulty config"): row["difficulty_config_hash"], ui("设备", "Device"): row["device_class"],
                ui("输入", "Input"): row["input_method"],
                ui("准确率", "Accuracy"): row["accuracy"], ui("中位反应时间", "Median RT"): row["median_rt_ms"],
                ui("关键指标", "Key metric"): metrics.get("interference_cost_ms", metrics.get("switch_cost_ms", metrics.get("correct_per_minute"))),
            })
        st.dataframe(display, use_container_width=True, hide_index=True)
        if not show_all and len(rows) < 3:
            st.info(ui("当前数据不足以形成稳定趋势。", "Current data are insufficient for a stable trend."))
    else:
        st.info(ui("当前数据不足以形成稳定趋势。", "Current data are insufficient for a stable trend."))
