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
from html import escape
from pathlib import Path

import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import connect_readonly, get_data_freshness, get_latest_confidence
from src.demo_sandbox import configure_demo_runtime, is_demo_mode
from src.i18n import format_date, get_translator
from src.i18n.traditional import traditionalize
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


def _ui(zh, en):
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


SYSTEM_PAGE_CSS = """
<style>
.rh-system-intro{max-width:42rem;margin:-.2rem 0 1.5rem;color:var(--rh-text-muted);font-size:.94rem;line-height:1.65}
.rh-system-health{display:grid;grid-template-columns:auto minmax(0,1fr);gap:1rem;align-items:start;margin:0 0 1.75rem;padding:1rem 1.1rem;border:1px solid var(--rh-border-subtle);border-radius:var(--rh-radius-emphasis);background:var(--rh-surface-raised);box-shadow:var(--rh-shadow-raised)}
.rh-system-health-mark{display:flex;align-items:center;justify-content:center;width:2.25rem;height:2.25rem;border-radius:50%;font-size:1rem;font-weight:750;line-height:1}
.rh-system-health--positive .rh-system-health-mark{color:var(--rh-status-positive);background:var(--rh-status-positive-surface);border:1px solid color-mix(in srgb,var(--rh-status-positive) 24%,transparent)}
.rh-system-health--caution .rh-system-health-mark{color:var(--rh-status-caution);background:var(--rh-status-caution-surface);border:1px solid color-mix(in srgb,var(--rh-status-caution) 24%,transparent)}
.rh-system-health--negative .rh-system-health-mark{color:var(--rh-status-negative);background:var(--rh-status-negative-surface);border:1px solid color-mix(in srgb,var(--rh-status-negative) 24%,transparent)}
.rh-system-health-eyebrow{margin:0 0 .2rem;color:var(--rh-text-muted);font-size:.72rem;font-weight:650;letter-spacing:.045em;line-height:1.35}
.rh-system-health-title{margin:0;color:var(--rh-text);font-size:1.05rem;font-weight:680;letter-spacing:-.01em;line-height:1.4}
.rh-system-health-reasons{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.6rem}
.rh-system-health-reason{display:inline-flex;align-items:center;min-height:1.55rem;padding:.08rem .5rem;border-radius:999px;background:var(--rh-surface-inset);color:var(--rh-text-secondary);font-size:.75rem;line-height:1.25}
.rh-system-section{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:1.9rem 0 .7rem}
.rh-system-section h2{margin:0;color:var(--rh-text);font-size:var(--drc-section-title-size);font-weight:700;letter-spacing:-.018em;line-height:1.3}
.rh-system-section p{margin:0;color:var(--rh-text-muted);font-size:.82rem;line-height:1.45;text-align:right}
.rh-system-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem}
.rh-system-grid--versions{grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem}
.rh-system-grid--three{grid-template-columns:repeat(3,minmax(0,1fr))}
.rh-system-card{min-width:0;padding:1rem;border:1px solid #e2e7ee;border-radius:var(--rh-radius-standard);background:#f8fafc;box-shadow:0 1px 2px rgba(27,42,57,.025)}
.rh-system-grid--versions .rh-system-card{padding:.78rem .85rem;background:#fafbfd;box-shadow:none}
.rh-system-card-label{overflow:hidden;color:var(--rh-text-muted);font-size:.72rem;font-weight:620;letter-spacing:.025em;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.rh-system-card-value{overflow:hidden;margin-top:.42rem;color:var(--rh-text);font-size:clamp(1.25rem,1.9vw,1.7rem);font-weight:675;letter-spacing:-.028em;line-height:1.16;text-overflow:ellipsis;white-space:nowrap}
.rh-system-grid--versions .rh-system-card-value{margin-top:.24rem;font-size:1rem;font-weight:620;letter-spacing:-.01em}
.rh-system-card-detail{min-height:1.15rem;margin-top:.48rem;color:var(--rh-text-muted);font-size:.75rem;line-height:1.45}
.rh-system-card--positive{border-color:#c9dfd2}
.rh-system-card--caution{border-color:#e7d4ac}
.rh-system-card--negative{border-color:#e6c2c2}
@media (hover: hover) and (prefers-reduced-motion: no-preference){.rh-system-card{transition:transform 180ms ease-out,box-shadow 180ms ease-out,border-color 180ms ease-out}.rh-system-card:hover{transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.18),0 20px 36px rgba(0,0,0,.14)}}
[class*="st-key-system_sync_action"]{margin-top:1.35rem;padding:1rem 1.1rem!important;border:1px solid var(--rh-border-subtle)!important;border-radius:var(--rh-radius-emphasis)!important;background:var(--rh-surface-raised)!important;box-shadow:var(--rh-shadow-raised)}
[class*="st-key-system_sync_action"] [data-testid="stButton"]{margin:0!important}
[class*="st-key-manual_sync_now"] button{min-height:2.4rem!important;border:1px solid #275c91!important;border-radius:var(--rh-radius-small)!important;background:#275c91!important;color:#fff!important;font-weight:650!important;box-shadow:none!important;transition:transform 140ms ease-out,background-color 140ms ease!important}
[class*="st-key-manual_sync_now"] button:hover{background:#204f80!important;border-color:#204f80!important}
[class*="st-key-manual_sync_now"] button:active{transform:scale(.98)}
@media (prefers-color-scheme:dark){.rh-system-card,.rh-system-grid--versions .rh-system-card{background:rgba(255,255,255,.035);border-color:rgba(185,198,214,.16)}.rh-system-card--positive{border-color:rgba(85,160,116,.38)}.rh-system-card--caution{border-color:rgba(192,145,62,.42)}.rh-system-card--negative{border-color:rgba(190,91,91,.42)}}
@media (max-width:980px){.rh-system-grid,.rh-system-grid--versions,.rh-system-grid--three{grid-template-columns:repeat(2,minmax(0,1fr))}.rh-system-section{align-items:flex-start;flex-direction:column;gap:.2rem}.rh-system-section p{text-align:left}}
@media (max-width:620px){.rh-system-grid,.rh-system-grid--versions,.rh-system-grid--three{grid-template-columns:1fr}.rh-system-health{gap:.75rem;padding:.9rem}.rh-system-card{padding:.9rem}.rh-system-card-value{font-size:1.38rem}}
</style>
"""


def _system_card(label, value, detail="", tone="neutral"):
    tone_class = f" rh-system-card--{tone}" if tone != "neutral" else ""
    return (
        f'<article class="rh-system-card{tone_class}">'
        f'<div class="rh-system-card-label">{escape(str(label))}</div>'
        f'<div class="rh-system-card-value">{escape(str(value))}</div>'
        f'<div class="rh-system-card-detail">{escape(str(detail)) if detail else "&nbsp;"}</div>'
        "</article>"
    )


def _render_system_section(title, description, cards, *, version_grid=False, three_column_grid=False):
    grid_class = " rh-system-grid--versions" if version_grid else " rh-system-grid--three" if three_column_grid else ""
    st.markdown(
        '<div class="rh-system-section">'
        f"<h2>{escape(title)}</h2><p>{escape(description)}</p></div>"
        f'<div class="rh-system-grid{grid_class}">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def _health_reason_copy(reason):
    if reason == "Tests, state files, database access, and data freshness are healthy.":
        return _ui("测试、项目状态、本地数据库与数据新鲜度均正常", "Tests, state files, database access, and data freshness are healthy")
    if reason == "Project state is unavailable.":
        return _ui("项目状态文件不可用", "Project state file is unavailable")
    if reason == "Database is unavailable or unreadable.":
        return _ui("本地数据库不可读", "Local database is unavailable")
    if reason == "Recorded unittest status is invalid or failing.":
        return _ui("测试状态需要处理", "Test status needs attention")
    if reason == "Version source is unavailable.":
        return _ui("版本信息不可用", "Version source is unavailable")
    if reason == "Project state and version source do not match.":
        return _ui("版本信息尚未对齐", "Version sources are not aligned")
    if reason == "Latest data date is missing or invalid.":
        return _ui("最新数据日期不可用", "Latest data date is unavailable")
    if reason.startswith("Latest data is ") and reason.endswith(" days old."):
        days = reason.removeprefix("Latest data is ").removesuffix(" days old.")
        return _ui(f"最新数据已延迟 {days} 天", f"Latest data is {days} days old")
    if reason.endswith(" active P1 issue(s) remain."):
        count = reason.split(" ", 1)[0]
        return _ui(f"仍有 {count} 项 P1 待处理", f"{count} active P1 issues remain")
    if reason.startswith("Last sync completed with ") and reason.endswith(" endpoint warning(s)."):
        count = reason.removeprefix("Last sync completed with ").removesuffix(" endpoint warning(s).")
        return _ui(f"上次同步有 {count} 项端点警告", f"Last sync has {count} endpoint warnings")
    return reason


def _render_system_health(status):
    health = str(status.get("system_health", "warning")).lower()
    tone = {"healthy": "positive", "warning": "caution", "unhealthy": "negative"}.get(health, "caution")
    mark = {"positive": "✓", "caution": "!", "negative": "×"}[tone]
    title = {
        "positive": _ui("本地系统运行正常", "Local system is operating normally"),
        "caution": _ui("系统可用，但有需要关注的状态", "System is available, with items needing attention"),
        "negative": _ui("系统状态需要处理", "System status needs attention"),
    }[tone]
    reasons = status.get("health_reasons") or []
    reason_markup = "".join(
        f'<span class="rh-system-health-reason">{escape(_health_reason_copy(str(reason)))}</span>'
        for reason in reasons[:3]
    )
    st.markdown(
        f'<section class="rh-system-health rh-system-health--{tone}">'
        f'<div class="rh-system-health-mark" aria-hidden="true">{mark}</div>'
        '<div><div class="rh-system-health-eyebrow">'
        f'{escape(TR(f"system_status.{health}"))}</div>'
        f'<p class="rh-system-health-title">{escape(title)}</p>'
        f'<div class="rh-system-health-reasons">{reason_markup}</div></div></section>',
        unsafe_allow_html=True,
    )


def _format_sync_time(value):
    if not value:
        return TR("common.not_run")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
    except ValueError:
        return str(value)


def _scheduler_result_label(value):
    normalized = str(value or "").strip().lower()
    labels = {
        "success": _ui("已完成", "Completed"),
        "succeeded": _ui("已完成", "Completed"),
        "completed": _ui("已完成", "Completed"),
        "failed": _ui("未完成", "Not completed"),
        "failure": _ui("未完成", "Not completed"),
        "running": _ui("正在运行", "Running"),
    }
    return labels.get(normalized, TR("common.not_run") if not normalized else str(value))


def _scheduler_section():
    if is_demo_mode():
        st.subheader(TR("scheduler_ui.title"))
        st.info(_ui(
            "公开体验版使用合成数据，不连接 Polar，也不执行数据同步。",
            "The public demo uses synthetic data and does not connect to Polar or run sync.",
        ))
        return
    loaded = load_scheduler_config()
    config = loaded.config
    scheduler_history = SchedulerHistory()
    daily = get_daily_scheduler_status(config, scheduler_history=scheduler_history)
    agent = get_launch_agent_status()
    if loaded.used_fallback:
        st.warning(TR("scheduler_ui.config_fallback"))
    st.subheader(TR("scheduler_ui.title"))
    st.caption(_ui(
        "睡眠、运动或恢复数据写入后优先同步；每天 12:00、18:00、23:00 固定同步。错过后会在下次打开应用时立即补同步。",
        "Sleep, training, and recovery saves sync first; fixed syncs run at 12:00, 18:00, and 23:00. A missed run catches up when the app next opens.",
    ))
    agent_label = TR(
        "scheduler_ui.installed" if agent.state == "installed"
        else "scheduler_ui.not_installed" if agent.state == "not_installed"
        else "scheduler_ui.abnormal"
    )
    _render_system_section(
        _ui("同步配置", "Sync configuration"),
        _ui("本地定时任务", "Local scheduled task"),
        [
            _system_card(
                TR("scheduler_ui.enabled"),
                TR("scheduler_ui.enabled_value") if config.enabled else TR("scheduler_ui.disabled_value"),
                _ui("自动运行开关", "Automatic run switch"),
                "positive" if config.enabled else "neutral",
            ),
            _system_card(
                _ui("更新频率", "Refresh cadence"), _ui("数据变更优先；12:00、18:00、23:00", "Data-change priority; 12:00, 18:00, 23:00"),
                _ui("睡眠、运动与恢复数据", "Sleep, training, and recovery data"),
            ),
            _system_card(
                TR("scheduler_ui.timezone"), TR("scheduler_ui.system_timezone"),
                _ui("任务使用的系统时区", "System timezone used by the task"),
            ),
            _system_card(
                TR("scheduler_ui.agent"), agent_label,
                _ui("macOS 后台服务", "macOS background service"),
                "positive" if agent.state == "installed" else "caution",
            ),
        ],
    )
    result = _scheduler_result_label(daily.latest_scheduled_result)
    result_tone = "negative" if str(daily.latest_scheduled_result or "").lower() in {"failed", "failure"} else "positive" if str(daily.latest_scheduled_result or "").lower() in {"success", "succeeded", "completed"} else "neutral"
    warnings = daily.latest_scheduled_warning_count
    _render_system_section(
        _ui("最近运行", "Recent run"),
        _ui("结果与下一次计划", "Outcome and next scheduled run"),
        [
            _system_card(
                TR("scheduler_ui.latest"), _format_sync_time(daily.latest_scheduled_at),
                _ui("最近一次后台尝试", "Most recent background attempt"),
            ),
            _system_card(
                TR("scheduler_ui.result"), result,
                _ui(
                    f"今日{'已' if daily.today_synced else '尚未'}同步 · {warnings if warnings is not None else 0} 项端点警告",
                    f"Today {'synced' if daily.today_synced else 'not synced'} · {warnings if warnings is not None else 0} endpoint warnings",
                ),
                result_tone,
            ),
            _system_card(
                TR("scheduler_ui.next"), _format_sync_time(daily.next_scheduled_at),
                _ui("下一次计划执行", "Next scheduled run"),
            ),
        ],
        three_column_grid=True,
    )
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
            st.caption(_ui("固定同步时间：12:00、18:00、23:00。", "Fixed sync times: 12:00, 18:00, 23:00."))
            submitted = st.form_submit_button(TR("scheduler_ui.save_settings"), type="primary")
        if submitted:
            try:
                updated = replace(config, enabled=enabled, prompt_before_catch_up=False)
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
    st.markdown(SYSTEM_PAGE_CSS, unsafe_allow_html=True)
    st.title(TR("domain.system.title"))
    st.markdown(
        f'<p class="rh-system-intro">{escape(TR("domain.system.intro"))}</p>',
        unsafe_allow_html=True,
    )
    save_notice = st.session_state.pop("system_save_notice", None)
    status = load_system_status()
    health = status["system_health"].lower()
    _render_system_health(status)

    versions = (
        ("system_status.app_version", "app_version"),
        ("system_status.recovery_engine", "recovery_engine_version"),
        ("system_status.baseline_engine", "baseline_engine_version"),
        ("system_status.database_schema", "database_schema_version"),
        ("system_status.dashboard_version", "dashboard_version"),
    )
    _render_system_section(
        _ui("版本与架构", "Versions & architecture"),
        _ui("本地运行组件", "Local runtime components"),
        [
            _system_card(TR(label), status.get(key) or TR("common.unavailable"))
            for label, key in versions
        ],
        version_grid=True,
    )

    freshness = get_data_freshness() or {}
    source_lag = freshness.get("source_data_lag_days")
    source_date = format_date(freshness.get("latest_source_data_date"), LANGUAGE)
    aligned = bool(freshness.get("database_aligned_with_source"))
    today_ready = bool(freshness.get("today_source_data_available"))
    _render_system_section(
        TR("domain.system.data_status"),
        _ui("Polar 源与本地数据库", "Polar source and local database"),
        [
            _system_card(
                TR("metrics.source_date"), source_date,
                _ui("当前可用源数据", "Current available source data"),
            ),
            _system_card(
                TR("metrics.source_lag"),
                TR("common.unavailable") if source_lag is None else TR("common.days", count=source_lag),
                _ui("相对最新源记录", "Against the latest source record"),
                "positive" if source_lag == 0 else "caution",
            ),
            _system_card(
                TR("metrics.database_aligned"),
                TR("common.yes") if aligned else TR("common.no"),
                _ui("原始导入与计算状态", "Import and calculation status"),
                "positive" if aligned else "caution",
            ),
            _system_card(
                TR("metrics.today_source"),
                TR("common.ready") if today_ready else TR("common.unavailable"),
                _ui("以 Polar 当前提供为准", "Based on Polar availability"),
                "positive" if today_ready else "neutral",
            ),
        ],
    )

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
    _render_system_section(
        TR("domain.system.quality_status"),
        _ui("本地检查与恢复判断基础", "Local checks and recovery evidence"),
        [
            _system_card(TR(label), value, detail)
            for (label, value, detail) in (
                ("system_status.test_status", quality[0][1], _ui("本地回归测试", "Local regression tests")),
                ("domain.system.integrity", quality[1][1], _ui("只读数据库检查", "Read-only database check")),
                ("confidence.score", quality[2][1], _ui("恢复判断的数据支撑", "Data support for recovery")),
                ("confidence.level", quality[3][1], _ui("根据完整度与基线成熟度", "From completeness and baseline maturity")),
            )
        ],
    )

    last_sync_success = status.get("last_sync_success")
    sync_success_value = (
        TR("common.not_run") if last_sync_success is None
        else TR("common.yes") if last_sync_success else TR("common.no")
    )
    _render_system_section(
        TR("domain.system.sync_status"),
        _ui("按需更新本地数据", "Update local data when needed"),
        [
            _system_card(
                TR("sync.last"), _format_sync_time(status.get("last_sync")),
                _ui("本地时间", "Local time"),
            ),
            _system_card(
                TR("sync.success"), sync_success_value,
                _ui("最近一次同步结果", "Most recent sync result"),
                "positive" if last_sync_success else "caution" if last_sync_success is False else "neutral",
            ),
            _system_card(
                TR("sync.records"),
                status.get("last_sync_records_imported") if status.get("last_sync_records_imported") is not None else TR("common.not_run"),
                _ui("最近一次导入", "Most recent import"),
            ),
            _system_card(
                TR("system_status.cloud_ai_status"),
                TR("common.ready") if status.get("cloud_ai_runtime_ready") else TR("common.blocked"),
                _ui("受独立审批门禁控制", "Controlled by an independent approval gate"),
            ),
        ],
    )
    if is_demo_mode():
        st.info(_ui(
            "公开体验版不执行 Polar 数据同步。",
            "The public demo does not run Polar data synchronization.",
        ))
    else:
        with st.container(key="system_sync_action", border=False):
            copy_column, action_column = st.columns([3.2, 1], vertical_alignment="center")
            with copy_column:
                st.markdown(f"**{_ui('立即更新本地数据', 'Update local data now')}**")
                st.caption(_ui(
                    "手动同步会重新读取 Polar 数据并更新本地计算。",
                    "Manual sync refreshes Polar data and local calculations.",
                ))
            with action_column:
                if st.button(TR("scheduler_ui.sync_now"), key="manual_sync_now", type="primary", use_container_width=True):
                    try:
                        with st.spinner(TR("scheduler_ui.running")):
                            run_triggered_pipeline("manual")
                        st.success(TR("scheduler_ui.sync_finished"))
                        st.rerun()
                    except SchedulerRunError as exc:
                        st.error(TR("scheduler_ui.sync_failed", message=exc.error_code))
    with st.expander(_ui("自动同步设置", "Automatic sync settings"), expanded=False):
        _scheduler_section()
    if save_notice:
        st.success(save_notice)
    st.caption(TR("domain.system.local_only"))


if __name__ == "__main__": main()
