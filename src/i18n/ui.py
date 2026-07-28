"""Shared Streamlit language preference and localized navigation helpers."""

from collections.abc import MutableMapping
import os

from .locale import SUPPORTED_LANGUAGES, normalize_language
from .storage import load_language_preference, save_language_preference
from .translator import get_translator
from ..branding import BRAND_NAME, POSITIONING_LINES
from ..demo_sandbox import is_demo_mode, reset_demo_sandbox
from ..ui_controls import render_app_shell_styles


SESSION_LANGUAGE_KEY = "ui_language"
LANGUAGE_SELECTOR_KEY = "ui_language_selector"


def current_language(session_state: MutableMapping[str, object]) -> str:
    # The preference file is the cross-page source of truth. Streamlit widget
    # state can be page-scoped, so it must not be the authority here.
    language = load_language_preference()
    session_state[SESSION_LANGUAGE_KEY] = language
    return language


def render_sidebar(st, active_page: str) -> tuple[str, object]:
    render_app_shell_styles(st)
    # Track page transitions so forms can distinguish a normal Streamlit
    # rerun from returning to a page after visiting another section.
    st.session_state["drc_previous_page"] = st.session_state.get("drc_active_page")
    st.session_state["drc_active_page"] = active_page
    # Streamlit's column alignment centers cells but not the semantic header
    # layer, so explicitly center both. This also improves screen-reader table
    # consistency while the visible Glide grid keeps the same alignment.
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value],
        [data-testid="stSidebar"] div[data-testid="stSelectbox"] div[data-baseweb="select"] input {
            text-align: left !important;
            padding-left: 1rem !important;
        }
        [data-testid="stDataFrame"] th[role="columnheader"],
        [data-testid="stDataEditor"] th[role="columnheader"],
        [data-testid="stDataFrame"] td[role="gridcell"],
        [data-testid="stDataEditor"] td[role="gridcell"] {
            text-align: center !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    language = current_language(st.session_state)
    translator = get_translator(language)

    st.sidebar.markdown(f"### {BRAND_NAME}")
    st.sidebar.caption("  \n".join(POSITIONING_LINES))

    # Keep the widget state separate from the global language state. This
    # avoids Streamlit's page-navigation reset of a widget-keyed preference.
    if st.session_state.get(LANGUAGE_SELECTOR_KEY) != language:
        st.session_state[LANGUAGE_SELECTOR_KEY] = language

    def persist_language() -> None:
        selected = normalize_language(st.session_state[LANGUAGE_SELECTOR_KEY])
        save_language_preference(selected)
        st.session_state[SESSION_LANGUAGE_KEY] = selected

    st.sidebar.selectbox(
        translator("settings.language"),
        tuple(SUPPORTED_LANGUAGES),
        format_func=lambda code: SUPPORTED_LANGUAGES[code].native_name,
        key=LANGUAGE_SELECTOR_KEY,
        on_change=persist_language,
    )
    if is_demo_mode():
        sandbox_id = st.session_state.get("drc_demo_sandbox_id", "")
        if sandbox_id:
            st.sidebar.caption(f"Sandbox: {sandbox_id[:8]}")
        if st.sidebar.button("重置我的沙盒", key="drc_reset_sandbox"):
            st.session_state["drc_reset_pending"] = True
        if st.session_state.get("drc_reset_pending"):
            st.sidebar.warning("确定要删除当前沙盒并重新开始吗？")
            confirm, cancel = st.sidebar.columns(2)
            if confirm.button("确认重置", key="drc_confirm_reset"):
                reset_demo_sandbox(st)
                st.session_state.pop("drc_reset_pending", None)
                st.rerun()
            if cancel.button("取消", key="drc_cancel_reset"):
                st.session_state.pop("drc_reset_pending", None)
                st.rerun()
    language = current_language(st.session_state)
    translator = get_translator(language)
    main_page = os.environ.get("DRC_STREAMLIT_ENTRYPOINT", "dashboard.py")
    st.sidebar.page_link(
        main_page,
        label=translator("navigation.exercise"),
        icon="🏃",
        disabled=active_page == "exercise",
    )
    st.sidebar.page_link(
        "pages/1_Sleep.py",
        label=translator("navigation.sleep"),
        icon="🌙",
        disabled=active_page == "sleep",
    )
    st.sidebar.page_link(
        "pages/2_Recovery.py",
        label=translator("navigation.recovery"),
        icon="❤️",
        disabled=active_page == "recovery",
    )
    st.sidebar.page_link(
        "pages/3_Neural_Readiness.py",
        label=translator("navigation.neural"),
        icon="⚡",
        disabled=active_page == "neural",
    )
    st.sidebar.page_link(
        "pages/6_Training_Studio.py",
        label=translator("navigation.training_studio"),
        icon="🧠",
        disabled=active_page == "training_studio",
    )
    st.sidebar.page_link(
        "pages/7_Progress_Lab.py",
        label=translator("navigation.progress_lab"),
        icon="📈",
        disabled=active_page == "progress_lab",
    )
    st.sidebar.page_link(
        "pages/3_Nutrition.py",
        label=translator("navigation.nutrition"),
        icon="🥗",
        disabled=active_page == "nutrition",
    )
    st.sidebar.page_link(
        "pages/5_Personal.py",
        label=translator("navigation.personal"),
        icon="👤",
        disabled=active_page == "personal",
    )
    st.sidebar.page_link(
        "pages/4_System.py",
        label=translator("navigation.system"),
        icon="⚙️",
        disabled=active_page == "system",
    )
    return language, translator
