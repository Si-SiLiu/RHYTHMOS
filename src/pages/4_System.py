"""System Information, scheduled-sync status, and explicit catch-up controls."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from dataclasses import replace
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import connect_readonly, get_data_freshness, get_latest_confidence
from src.demo_sandbox import configure_demo_runtime, is_demo_mode
from src.i18n import format_date, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.system_status import load_system_status
from src.scheduler.config import load_scheduler_config, save_scheduler_config
from src.scheduler.history import SchedulerHistory
from src.scheduler.launch_agent import (
    get_launch_agent_status,
    install_launch_agent,
    uninstall_launch_agent,
)
from src.scheduler.runner import SchedulerRunError, run_triggered_pipeline
from src.scheduler.status import evaluate_catch_up, get_daily_scheduler_status
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.system.title")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, TR = render_sidebar(st, "system")
render_manual_input_styles(st)
BASE_DIR = Path(__file__).resolve().parents[2]


def _scheduler_section():
    if is_demo_mode():
        st.subheader(TR("scheduler_ui.title"))
        st.info(
            "公开体验版使用合成数据，不连接 Polar，也不执行数据同步。"
            if LANGUAGE != "en"
            else "The public demo uses synthetic data and does not connect to Polar or run sync."
        )
        return
    loaded = load_scheduler_config()
    config = loaded.config
    scheduler_history = SchedulerHistory()
    daily = get_daily_scheduler_status(config, scheduler_history=scheduler_history)
    agent = get_launch_agent_status()
    if loaded.used_fallback:
        st.warning(TR("scheduler_ui.config_fallback"))
    st.subheader(TR("scheduler_ui.title"))
    st.info(
        "自动同步频率：每隔 2 小时同步一次训练和睡眠数据。"
        if LANGUAGE != "en"
        else "Automatic sync frequency: training and sleep data are synchronized every 2 hours."
    )
    agent_label = TR(
        "scheduler_ui.installed" if agent.state == "installed"
        else "scheduler_ui.not_installed" if agent.state == "not_installed"
        else "scheduler_ui.abnormal"
    )
    cards = (
        ("scheduler_ui.enabled", TR("scheduler_ui.enabled_value") if config.enabled else TR("scheduler_ui.disabled_value")),
        ("scheduler_ui.time", config.sync_time),
        ("scheduler_ui.timezone", TR("scheduler_ui.system_timezone")),
        ("scheduler_ui.agent", agent_label),
    )
    for column, (label, value) in zip(st.columns(4), cards):
        with column: st.metric(TR(label), value)
    status_cards = (
        ("scheduler_ui.latest", daily.latest_scheduled_at or TR("common.not_run")),
        ("scheduler_ui.result", daily.latest_scheduled_result or TR("common.not_run")),
        ("scheduler_ui.warning_count", daily.latest_scheduled_warning_count if daily.latest_scheduled_warning_count is not None else TR("common.not_run")),
        ("scheduler_ui.today", TR("common.yes") if daily.today_synced else TR("common.no")),
        ("scheduler_ui.next", daily.next_scheduled_at or TR("common.unavailable")),
    )
    for column, (label, value) in zip(st.columns(5), status_cards):
        with column: st.metric(TR(label), value)
    if daily.pipeline_running:
        st.info(TR("scheduler_ui.running"))
    st.caption(TR("scheduler_ui.sleep_caveat"))

    catch_up = evaluate_catch_up(config, scheduler_history=scheduler_history)
    if catch_up.should_prompt or (catch_up.eligible and not config.prompt_before_catch_up):
        st.warning(TR("scheduler_ui.missing_today"))
        sync_column, later_column = st.columns(2)
        if sync_column.button(TR("scheduler_ui.sync_now"), type="primary", key="catch_up_now"):
            try:
                run_triggered_pipeline("catch_up")
                st.success(TR("scheduler_ui.sync_finished")); st.rerun()
            except SchedulerRunError as exc:
                st.error(TR("scheduler_ui.sync_failed", message=exc.error_code))
        if later_column.button(TR("scheduler_ui.later"), key="catch_up_later"):
            scheduler_history.defer_catch_up(datetime.now().astimezone())
            st.info(TR("scheduler_ui.deferred")); st.rerun()

    with st.expander(TR("scheduler_ui.settings"), expanded=False):
        with st.form("scheduler_settings_form"):
            enabled = st.checkbox(TR("scheduler_ui.enabled"), value=config.enabled)
            sync_time = st.text_input(TR("scheduler_ui.time"), value=config.sync_time, max_chars=5)
            submitted = st.form_submit_button(TR("scheduler_ui.save_settings"), type="primary")
        if submitted:
            try:
                updated = replace(config, enabled=enabled, sync_time=sync_time)
                save_scheduler_config(updated)
                if updated.enabled:
                    install_launch_agent(BASE_DIR, updated)
                else:
                    uninstall_launch_agent()
                st.session_state["system_save_notice"] = TR("scheduler_ui.saved"); st.rerun()
            except Exception as exc:
                st.error(TR("scheduler_ui.sync_failed", message=str(exc)))
        left, right = st.columns(2)
        if left.button(TR("scheduler_ui.install"), key="install_launch_agent"):
            try:
                install_launch_agent(BASE_DIR, config)
                st.session_state["system_save_notice"] = TR("scheduler_ui.saved"); st.rerun()
            except Exception as exc:
                st.error(TR("scheduler_ui.sync_failed", message=str(exc)))
        if right.button(TR("scheduler_ui.uninstall"), key="uninstall_launch_agent"):
            try:
                uninstall_launch_agent()
                st.session_state["system_save_notice"] = TR("scheduler_ui.saved"); st.rerun()
            except Exception as exc:
                st.error(TR("scheduler_ui.sync_failed", message=str(exc)))


def main():
    st.title(TR("domain.system.title")); st.caption(TR("domain.system.intro"))
    save_notice = st.session_state.pop("system_save_notice", None)
    status = load_system_status()
    health = status["system_health"].lower()
    {"healthy": st.success, "warning": st.warning, "unhealthy": st.error}[health](TR(f"system_status.{health}"))
    versions = (
        ("system_status.app_version", "app_version"),
        ("system_status.recovery_engine", "recovery_engine_version"),
        ("system_status.baseline_engine", "baseline_engine_version"),
        ("system_status.database_schema", "database_schema_version"),
        ("system_status.dashboard_version", "dashboard_version"),
    )
    for column, (label, key) in zip(st.columns(5), versions):
        with column: st.metric(TR(label), status.get(key) or TR("common.unavailable"))

    st.subheader(TR("domain.system.data_status"))
    freshness = get_data_freshness() or {}
    cards = (
        ("metrics.source_date", format_date(freshness.get("latest_source_data_date"), LANGUAGE)),
        ("metrics.source_lag", TR("common.unavailable") if freshness.get("source_data_lag_days") is None else TR("common.days", count=freshness["source_data_lag_days"])),
        ("metrics.database_aligned", TR("common.yes") if freshness.get("database_aligned_with_source") else TR("common.no")),
        ("metrics.today_source", TR("common.ready") if freshness.get("today_source_data_available") else TR("common.unavailable")),
    )
    for column, (label, value) in zip(st.columns(4), cards):
        with column: st.metric(TR(label), value)

    st.subheader(TR("domain.system.quality_status"))
    confidence = get_latest_confidence()
    connection = connect_readonly()
    try: integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally: connection.close()
    test_value = TR("common.unavailable") if status.get("test_total") is None else f"{status.get('test_passed')} / {status.get('test_total')}"
    confidence_level = confidence.get("confidence_level") if confidence else None
    confidence_label = (
        TR(f"confidence.{confidence_level}")
        if confidence_level in {"high", "moderate", "low", "insufficient"}
        else TR("common.no_data")
    )
    quality = (
        ("system_status.test_status", test_value),
        ("domain.system.integrity", TR("common.ready") if integrity == "ok" else integrity),
        ("confidence.score", confidence.get("confidence_score") if confidence else TR("common.no_data")),
        ("confidence.level", confidence_label),
    )
    for column, (label, value) in zip(st.columns(4), quality):
        with column: st.metric(TR(label), value)

    st.subheader(TR("domain.system.sync_status"))
    sync = (
        ("sync.last", status.get("last_sync") or TR("common.not_run")),
        ("sync.success", TR("common.not_run") if status.get("last_sync_success") is None else TR("common.yes") if status["last_sync_success"] else TR("common.no")),
        ("sync.records", status.get("last_sync_records_imported") if status.get("last_sync_records_imported") is not None else TR("common.not_run")),
        ("system_status.cloud_ai_status", TR("common.ready") if status.get("cloud_ai_runtime_ready") else TR("common.blocked")),
    )
    for column, (label, value) in zip(st.columns(4), sync):
        with column: st.metric(TR(label), value)
    if is_demo_mode():
        st.info(
            "公开体验版不执行 Polar 数据同步。"
            if LANGUAGE != "en"
            else "The public demo does not run Polar data synchronization."
        )
    elif st.button(TR("scheduler_ui.sync_now"), key="manual_sync_now", type="primary"):
        try:
            with st.spinner(TR("scheduler_ui.running")):
                run_triggered_pipeline("manual")
            st.success(TR("scheduler_ui.sync_finished"))
            st.rerun()
        except SchedulerRunError as exc:
            st.error(TR("scheduler_ui.sync_failed", message=exc.error_code))
    _scheduler_section()
    if save_notice:
        st.success(save_notice)
    st.caption(TR("domain.system.local_only"))


if __name__ == "__main__": main()
