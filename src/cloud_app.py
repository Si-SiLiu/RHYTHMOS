"""Streamlit Community Cloud entry point for the public, synthetic-data demo."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Streamlit Community Cloud may execute this file with ``src`` as the script
# directory rather than the repository root as the import base. Add the
# project root dynamically so both Cloud and local launches resolve ``src``.
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()


os.environ["DRC_DEMO_MODE"] = "1"
os.environ["DRC_STREAMLIT_ENTRYPOINT"] = "cloud_app.py"

import streamlit as st  # noqa: E402
from src.branding import BRAND_NAME, POSITIONING_LINES, TAGLINE_LINES, browser_page_title  # noqa: E402
from src.demo_sandbox import configure_demo_runtime  # noqa: E402

configure_demo_runtime(st)

st.set_page_config(
    page_title=browser_page_title("Demo"),
    layout="wide",
    initial_sidebar_state="expanded",
)

st.caption(f"{BRAND_NAME}  ·  {' / '.join(POSITIONING_LINES)}")
st.caption(" / ".join(TAGLINE_LINES))
st.info("这是匿名体验沙盒。你在本标签页输入的数据只用于当前体验，不会与其他访问者共享。刷新页面、关闭标签页或应用重启后，数据可能被清除。请勿输入真实姓名、Polar 账号或敏感健康信息。")
st.markdown("反馈入口：请在此处替换为你的问卷链接（Google Form / Tally / 飞书表单）。")

from src import dashboard as training_dashboard  # noqa: E402

training_dashboard.LANGUAGE, training_dashboard.TR = training_dashboard.render_sidebar(st, "exercise")
training_dashboard.main()
