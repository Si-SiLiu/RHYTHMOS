"""Read-only bilingual Kubios advanced metrics and trends."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

import pandas as pd
import plotly.express as px
import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_kubios_advanced_metrics
from src.demo_sandbox import configure_demo_runtime
from src.i18n import format_date, get_translator
from src.i18n.ui import current_language, render_sidebar


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("kubios_metrics.advanced_title")), page_icon=load_page_icon(), layout="wide")
LANGUAGE, TR = render_sidebar(st, "kubios_advanced")

GROUPS = {
    "time_domain": (("mean_rr", "mean_rr_ms", "ms"), ("rmssd", "rmssd_ms", "ms"), ("sdnn", "sdnn_ms", "ms")),
    "nonlinear": (("sd1", "poincare_sd1_ms", "ms"), ("sd2", "poincare_sd2_ms", "ms")),
    "frequency": (("lf_power", "lf_power_ms2", "ms²"), ("hf_power", "hf_power_ms2", "ms²"), ("lf_nu", "lf_power_nu", "%"), ("hf_nu", "hf_power_nu", "%"), ("lf_hf", "lf_hf_ratio", "")),
    "autonomic": (("readiness", "readiness_percent", "%"), ("pns", "pns_index", ""), ("sns", "sns_index", ""), ("stress", "stress_index", ""), ("respiration", "respiratory_rate_bpm", "breaths/min"), ("physiological_age", "physiological_age", "years"), ("quality", "measurement_quality", ""), ("mood", "mood_code", "")),
}


def show_group(title, metrics, latest):
    st.subheader(TR(f"kubios_metrics.group.{title}"))
    columns = st.columns(min(len(metrics), 4))
    for index, (key, field, unit) in enumerate(metrics):
        with columns[index % len(columns)]:
            value = latest.get(field)
            st.metric(TR(f"kubios_metrics.{key}.name"), TR("common.no_data") if value in (None, "") else f"{value:g} {unit}" if isinstance(value, (int,float)) else str(value))
            st.caption(TR(f"kubios_metrics.{key}.description"))


def main():
    st.title(TR("kubios_metrics.advanced_title")); st.warning(TR("kubios_metrics.trend_only"))
    rows = get_kubios_advanced_metrics()
    if not rows: st.info(TR("common.no_data")); return
    latest = rows[0]; st.caption(TR("kubios_metrics.source_caption", date=format_date(latest["date"], LANGUAGE), source=latest["source_type"]))
    for title, metrics in GROUPS.items(): show_group(title, metrics, latest)
    st.subheader(TR("kubios_metrics.group.trends"))
    window = st.selectbox(
        TR("kubios_metrics.trend_window"), (7, 14, 28), index=2,
        format_func=lambda value: TR("kubios_metrics.trend_days", count=value),
    )
    frame = pd.DataFrame(reversed(rows[:window]))
    available = [name for name in ("rmssd_ms","mean_hr_bpm","readiness_percent","pns_index","sns_index") if frame[name].notna().any()]
    if available:
        figure=px.line(frame,x="date",y=available,markers=True)
        st.plotly_chart(figure,width="stretch")
    else: st.info(TR("common.no_data"))
    st.info(TR("kubios_metrics.frequency.safety")); st.caption(TR("safety.medical"))


if __name__ == "__main__": main()
