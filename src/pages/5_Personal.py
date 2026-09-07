"""Personal profile, body status, trends, and local targets."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from src.branding import browser_page_title, load_page_icon
from src.db import connect
from src.demo_sandbox import configure_demo_runtime
from src.i18n import format_date, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.personal_logging.body import weight_trend
from src.personal_logging.storage import create_body_measurement
from src.personal_profile import (
    GENDERS,
    TRAINING_GOALS,
    calculate_age,
    get_personal_goals,
    get_personal_profile,
    latest_body_measurement,
    save_personal_goals,
    save_personal_profile,
)
from src.input_habits import record_input_habit
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("personal_info.title")),
    page_icon=load_page_icon(),
    layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "personal")
render_manual_input_styles(st)

PERSONAL_PAGE_CSS = """
<style>
.personal-page-heading{margin:.1rem 0 2rem;max-width:44rem}
.personal-page-heading h1{margin:0;color:var(--rh-text);font-size:clamp(1.85rem,3vw,2.35rem);font-weight:720;letter-spacing:-.035em;line-height:1.12}
.personal-page-heading p{margin:.6rem 0 0;color:var(--rh-text-muted);font-size:.95rem;line-height:1.65}
.personal-overview-section{margin:0 0 1.25rem;padding:1.1rem 1.15rem 1.15rem;border:1px solid var(--rh-border-subtle);border-radius:var(--rh-radius-emphasis);background:var(--rh-surface-raised);box-shadow:var(--rh-shadow-raised)}
.personal-overview-section-head{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:0 0 .85rem}
.personal-overview-section-title{margin:0;color:var(--rh-text);font-size:1.05rem;font-weight:680;letter-spacing:-.014em;line-height:1.35}
.personal-overview-section-detail{margin:0;color:var(--rh-text-muted);font-size:.78rem;line-height:1.4;text-align:right}
.personal-profile-grid,.personal-body-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.55rem}
.personal-body-grid{grid-template-columns:1.28fr repeat(2,minmax(0,1fr))}
.personal-summary-cell{min-width:0;padding:.75rem .8rem;border-radius:var(--rh-radius-standard);background:var(--rh-surface-inset)}
.personal-summary-cell--primary{background:color-mix(in srgb,var(--rh-surface-inset) 86%,#3f7bb7 14%)}
.personal-summary-label{overflow:hidden;color:var(--rh-text-muted);font-size:.74rem;font-weight:620;letter-spacing:.018em;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.personal-summary-value{overflow:hidden;margin-top:.35rem;color:var(--rh-text);font-size:clamp(1.18rem,1.65vw,1.55rem);font-weight:680;font-variant-numeric:tabular-nums;letter-spacing:-.028em;line-height:1.18;text-overflow:ellipsis;white-space:nowrap}
.personal-body-grid .personal-summary-value{font-size:clamp(1.4rem,2.15vw,1.95rem);letter-spacing:-.034em}
.personal-trend-chip{display:flex;align-items:baseline;justify-content:flex-end;gap:.45rem;min-width:0;color:var(--rh-text-secondary);font-size:.75rem;line-height:1.35;text-align:right}
.personal-trend-chip strong{color:var(--rh-text);font-size:.94rem;font-weight:680;font-variant-numeric:tabular-nums;letter-spacing:-.015em;white-space:nowrap}
.st-key-personal_weight_trend_card{margin:0 0 1.25rem;border:1px solid var(--rh-border-subtle);border-radius:var(--rh-radius-emphasis);background:var(--rh-surface-raised);box-shadow:var(--rh-shadow-raised)}
.st-key-personal_weight_trend_card [data-testid="stVerticalBlockBorderWrapper"]{border:0;background:transparent;box-shadow:none}
.personal-trend-marker{margin:0 0 -.15rem}
@media (prefers-color-scheme:dark){.personal-summary-cell--primary{background:color-mix(in srgb,var(--rh-surface-inset) 84%,#5387bb 16%)}}
@media (max-width:900px){.personal-profile-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.personal-profile-grid .personal-summary-cell:nth-child(n+4){margin-top:.1rem}}
@media (max-width:640px){.personal-page-heading{margin-bottom:1.35rem}.personal-overview-section{padding:.95rem}.personal-overview-section-head{align-items:flex-start;flex-direction:column;gap:.25rem}.personal-overview-section-detail,.personal-trend-chip{text-align:left;justify-content:flex-start}.personal-profile-grid,.personal-body-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.personal-profile-grid .personal-summary-cell:last-child,.personal-body-grid .personal-summary-cell--primary{grid-column:span 2}.personal-summary-cell{padding:.7rem .75rem}}
div[data-testid="stMetric"] {
    align-items: flex-start !important;
    text-align: left;
}
div[data-testid="stMetric"] label,
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    justify-content: flex-start !important;
    text-align: left !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"],
div[data-testid="stMetric"] div[data-testid="stMetricValue"] > div {
    align-self: stretch !important;
    display: flex !important;
    justify-content: flex-start !important;
    margin-left: 0 !important;
    margin-right: auto !important;
    width: 100% !important;
    text-align: left !important;
}
div[data-testid="stForm"] label {
    display: flex !important;
    justify-content: center !important;
    width: 100% !important;
    text-align: center !important;
    transform: none !important;
}
div[data-testid="stForm"] [data-testid="stWidgetLabel"] {
    display: flex !important;
    justify-content: center !important;
    width: 100% !important;
    text-align: center !important;
    transform: translateX(1rem) !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
}
div[data-testid="stForm"] input,
div[data-testid="stForm"] div[data-baseweb="select"] {
    text-align: center !important;
}
div[data-testid="stForm"] div[data-testid="stNumberInput"] input {
    box-sizing: border-box !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    text-indent: 0 !important;
    text-align: center !important;
}
div[data-testid="stForm"] div[data-testid="stNumberInput"] [data-baseweb="input"] {
    display: flex !important;
    justify-content: center !important;
}
div[data-testid="stForm"] div[data-testid="stNumberInput"] [data-baseweb="input"] > div:has(input) {
    flex: 1 1 100% !important;
    width: 100% !important;
}
div[data-testid="stForm"] div[data-baseweb="select"] div[value] {
    flex: 1 1 auto !important;
    width: 100% !important;
    text-align: center !important;
    /* Offset the reserved dropdown-arrow area so the selected text is
       centered relative to the full control, not the remaining space. */
    transform: translateX(0.6875rem) !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
}
div[data-testid="stForm"] div[data-baseweb="select"] > div,
div[data-testid="stForm"] div[data-baseweb="select"] [role="combobox"] {
    justify-content: center !important;
}
/* The profile form is the only personal form with a text input (name). Scope
   this correction to its gender select so other controls keep their layout. */
div[data-testid="stForm"]:has(div[data-testid="stTextInput"])
    div[data-testid="stSelectbox"] [data-testid="stWidgetLabel"] {
    transform: translateX(-0.6875rem) !important;
}
div[data-testid="stForm"]:has(div[data-testid="stTextInput"])
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value] {
    transform: translateX(1.125rem) !important;
}
/* Scope training-goal alignment and typography to the goal form only. */
div[data-testid="stForm"]:has(div[data-testid="stNumberInput"]):has(div[data-testid="stSelectbox"])
    div[data-testid="stSelectbox"] [data-testid="stWidgetLabel"] {
    transform: translateX(-0.5rem) !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
}
div[data-testid="stForm"]:has(div[data-testid="stNumberInput"]):has(div[data-testid="stSelectbox"])
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value] {
    transform: translateX(1.0625rem) !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
}
div[data-testid="stForm"]:has(div[data-testid="stNumberInput"]):has(div[data-testid="stSelectbox"])
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value] * {
    font-size: 1rem !important;
    font-weight: 400 !important;
    line-height: 1.5 !important;
}
div[data-testid="stForm"] div[data-testid="stDateInput"] input {
    text-align: center !important;
}
div[data-testid="stForm"] div[data-testid="stDateInput"] label {
    transform: translateX(0.5625rem) !important;
}
.personal-form-age {
    margin: .8rem 0 1rem;
    text-align: center;
}
.personal-form-age__label {
    color: #31333f;
    font-weight: 600;
}
.personal-form-age__value {
    margin-top: .35rem;
    color: #31333f;
    font-size: 2rem;
    font-weight: 600;
}
</style>
"""
st.markdown(PERSONAL_PAGE_CSS, unsafe_allow_html=True)


def _value(value, suffix=""):
    if value in (None, ""):
        return TR("common.no_data")
    if isinstance(value, float):
        value = f"{value:g}"
    return f"{value}{suffix}"


def _gender_name(code):
    return TR(f"personal_info.genders.{code}")


def _training_goal_name(code):
    return TR(f"personal_info.training_goals.{code}")


def _summary_cell(label, value, *, primary=False):
    primary_class = " personal-summary-cell--primary" if primary else ""
    return (
        f'<div class="personal-summary-cell{primary_class}">'
        f'<div class="personal-summary-label">{escape(str(label))}</div>'
        f'<div class="personal-summary-value">{escape(str(value))}</div>'
        "</div>"
    )


def _overview_section(title, cells, *, detail="", class_name=""):
    detail_markup = (
        f'<p class="personal-overview-section-detail">{escape(str(detail))}</p>'
        if detail
        else ""
    )
    st.markdown(
        f'<section class="personal-overview-section {class_name}">'
        '<header class="personal-overview-section-head">'
        f'<h2 class="personal-overview-section-title">{escape(str(title))}</h2>'
        f"{detail_markup}</header>"
        f"{''.join(cells)}"
        "</section>",
        unsafe_allow_html=True,
    )


def _basic_information(profile):
    age = calculate_age(profile["birth_date"]) if profile else None
    values = (
        ("name", profile.get("name") if profile else None),
        ("gender", _gender_name(profile["gender"]) if profile else None),
        (
            "birthday",
            format_date(profile["birth_date"], LANGUAGE) if profile else None,
        ),
        ("age", _value(age, TR("personal_info.years"))),
        ("height", _value(profile.get("height_cm") if profile else None, " cm")),
    )
    cells = [
        _summary_cell(TR(f"personal_info.{key}"), _value(value))
        for key, value in values
    ]
    _overview_section(
        TR("personal_info.basic"),
        [f'<div class="personal-profile-grid">{"".join(cells)}</div>'],
    )


def _body_status(connection, latest):
    values = (
        ("weight", _value(latest.get("weight_kg") if latest else None, " kg")),
        ("body_fat", _value(latest.get("body_fat_percent") if latest else None, "%")),
        ("waist", _value(latest.get("waist_cm") if latest else None, " cm")),
    )
    body_detail = (
        TR("personal_info.latest_date", date=format_date(latest["date"], LANGUAGE))
        if latest
        else ""
    )
    cells = [
        _summary_cell(TR(f"personal_info.{key}"), value, primary=key == "weight")
        for key, value in values
    ]
    _overview_section(
        TR("personal_info.body_status"),
        [f'<div class="personal-body-grid">{"".join(cells)}</div>'],
        detail=body_detail,
    )

    trend = weight_trend(connection, 28)
    if len(trend) < 2:
        st.info(TR("personal_info.weight_trend_insufficient"))
        return

    date_label = TR("personal_info.trend_date")
    weight_label = TR("personal_info.weight")
    frame = pd.DataFrame([
        {date_label: row["date"], weight_label: row["weight_kg"]}
        for row in trend
    ])
    frame[date_label] = pd.to_datetime(frame[date_label])
    change = trend[-1]["weight_kg"] - trend[0]["weight_kg"]
    trend_header = (
        '<div class="personal-trend-marker">'
        '<header class="personal-overview-section-head">'
        f'<h2 class="personal-overview-section-title">{escape(TR("personal_info.weight_trend_title"))}</h2>'
        '<div class="personal-trend-chip">'
        f'<span>{escape(TR("personal_info.weight_change"))}</span>'
        f"<strong>{change:+.2f} kg</strong>"
        "</div></header></div>"
    )
    chart = (
        alt.Chart(frame)
        .mark_line(color="#2f72c4", strokeWidth=2.5, point=alt.OverlayMarkDef(
            filled=True, fill="#2f72c4", size=38,
        ))
        .encode(
            x=alt.X(
                f"{date_label}:T",
                axis=alt.Axis(title=None, format="%m/%d", labelAngle=0, tickCount=5, grid=False),
            ),
            y=alt.Y(
                f"{weight_label}:Q",
                axis=alt.Axis(title=None, tickCount=4, gridColor="#dfe6ee", gridOpacity=0.8),
                scale=alt.Scale(zero=False, nice=True, padding=12),
            ),
            tooltip=[
                alt.Tooltip(f"{date_label}:T", title=date_label, format="%Y-%m-%d"),
                alt.Tooltip(f"{weight_label}:Q", title=weight_label, format=".2f"),
            ],
        )
        .properties(height=225)
        .configure_view(strokeWidth=0)
        .configure_axis(
            domain=False,
            labelColor="#8792a3",
            labelFontSize=11,
            labelPadding=8,
            tickColor="#dfe6ee",
            tickSize=0,
        )
    )
    with st.container(border=True, key="personal_weight_trend_card"):
        st.markdown(trend_header, unsafe_allow_html=True)
        st.altair_chart(chart, width="stretch")


def _profile_form(profile):
    with st.form("personal_profile_form"):
        left, middle, right = st.columns(3)
        name = left.text_input(TR("personal_info.name"), value=(profile or {}).get("name") or "")
        current_gender = (profile or {}).get("gender") or "prefer_not_to_say"
        gender = middle.selectbox(
            TR("personal_info.gender"),
            GENDERS,
            index=GENDERS.index(current_gender),
            format_func=_gender_name,
        )
        birthday = right.date_input(
            TR("personal_info.birthday"),
            value=date.fromisoformat(profile["birth_date"]) if profile else date(1990, 1, 1),
            max_value=date.today(),
        )
        height = st.number_input(
            TR("personal_info.height"),
            min_value=50.0,
            max_value=300.0,
            value=float(profile["height_cm"]) if profile else 170.0,
            step=0.1,
        )
        st.markdown(
            '<div class="personal-form-age">'
            f'<div class="personal-form-age__label">{TR("personal_info.age")}</div>'
            f'<div class="personal-form-age__value">{_value(calculate_age(birthday), TR("personal_info.years"))}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        submitted = st.form_submit_button(TR("personal_info.save_profile"), type="primary")
    return submitted, {
        "name": name,
        "gender": gender,
        "birth_date": birthday.isoformat(),
        "height_cm": height,
    }


def _body_form(profile, latest):
    with st.form("personal_body_form"):
        body_date = st.date_input(TR("personal_info.measurement_date"), value=date.today())
        left, middle, right = st.columns(3)
        weight = left.number_input(
            TR("personal_info.weight"), min_value=1.0, max_value=500.0,
            value=float(latest["weight_kg"]) if latest else 60.0, step=0.1,
        )
        body_fat = middle.number_input(
            TR("personal_info.body_fat"), min_value=0.0, max_value=100.0,
            value=float(latest["body_fat_percent"]) if latest and latest.get("body_fat_percent") is not None else None,
            step=0.1,
        )
        waist = right.number_input(
            TR("personal_info.waist"), min_value=1.0, max_value=300.0,
            value=float(latest["waist_cm"]) if latest and latest.get("waist_cm") is not None else None,
            step=0.1,
        )
        submitted = st.form_submit_button(TR("personal_info.save_body"), type="primary")
    height = (profile or {}).get("height_cm") or (latest or {}).get("height_cm")
    return submitted, {
        "date": body_date.isoformat(),
        "height_cm": height,
        "weight_kg": weight,
        "body_fat_percent": body_fat,
        "waist_cm": waist,
        "is_primary": True,
    }


def _goal_form(goals):
    current_training_goal = (goals or {}).get("training_goal") or "maintenance"
    training_goal = st.selectbox(
        TR("personal_info.training_goal"),
        TRAINING_GOALS,
        index=TRAINING_GOALS.index(current_training_goal),
        format_func=_training_goal_name,
        key="personal_training_goal_editor",
    )
    with st.form("personal_goal_form"):
        left, middle, right = st.columns(3)
        target_weight = left.number_input(
            TR("personal_info.target_weight"), min_value=1.0, max_value=500.0,
            value=float(goals["target_weight_kg"]) if goals and goals.get("target_weight_kg") is not None else None,
            step=0.1,
        )
        target_body_fat = middle.number_input(
            TR("personal_info.target_body_fat"), min_value=0.1, max_value=100.0,
            value=float(goals["target_body_fat_percent"]) if goals and goals.get("target_body_fat_percent") is not None else None,
            step=0.1,
        )
        target_waist = right.number_input(
            TR("personal_info.target_waist"), min_value=1.0, max_value=300.0,
            value=float(goals["target_waist_cm"]) if goals and goals.get("target_waist_cm") is not None else None,
            step=0.1,
        )
        calorie_adjustment = None
        if training_goal == "fat_loss":
            calorie_adjustment = st.number_input(
                TR("personal_info.daily_calorie_deficit"), min_value=1.0, max_value=2000.0,
                value=float(goals["daily_calorie_adjustment_kcal"])
                if goals and goals.get("training_goal") == "fat_loss"
                and goals.get("daily_calorie_adjustment_kcal") is not None else 350.0,
                step=50.0,
            )
        elif training_goal == "muscle_gain":
            calorie_adjustment = st.number_input(
                TR("personal_info.daily_calorie_surplus"), min_value=1.0, max_value=2000.0,
                value=float(goals["daily_calorie_adjustment_kcal"])
                if goals and goals.get("training_goal") == "muscle_gain"
                and goals.get("daily_calorie_adjustment_kcal") is not None else 250.0,
                step=50.0,
            )
        submitted = st.form_submit_button(TR("personal_info.save_goals"), type="primary")
    return submitted, {
        "training_goal": training_goal,
        "target_weight_kg": target_weight,
        "target_body_fat_percent": target_body_fat,
        "target_waist_cm": target_waist,
        "daily_calorie_adjustment_kcal": calorie_adjustment,
    }


def main():
    st.markdown(
        '<header class="personal-page-heading">'
        f'<h1>{escape(TR("personal_info.title"))}</h1>'
        f'<p>{escape(TR("personal_info.intro"))}</p>'
        "</header>",
        unsafe_allow_html=True,
    )
    save_notice = st.session_state.pop("personal_save_notice", None)
    connection = connect(migrate=False)
    try:
        profile = get_personal_profile(connection)
        latest = latest_body_measurement(connection)
        goals = get_personal_goals(connection)
        _basic_information(profile)
        _body_status(connection, latest)
        st.subheader(TR("personal_info.edit"))

        with st.expander(TR("personal_info.profile_form"), expanded=False):
            profile_submitted, profile_data = _profile_form(profile)
        if profile_submitted:
            try:
                save_personal_profile(connection, profile_data)
                record_input_habit(
                    connection, "personal.profile",
                    fields=("height_cm",),
                    choices={"personal.gender": profile_data.get("gender")},
                    numeric={"personal.height_cm": profile_data.get("height_cm")},
                )
                st.session_state["personal_save_notice"] = TR("personal_info.profile_saved"); st.rerun()
            except ValueError:
                st.error(TR("personal_info.invalid_profile"))

        with st.expander(TR("personal_info.body_form"), expanded=False):
            body_submitted, body_data = _body_form(profile, latest)
        if body_submitted:
            if body_data["height_cm"] is None:
                st.error(TR("personal_info.save_profile_first"))
            else:
                try:
                    create_body_measurement(connection, body_data)
                    record_input_habit(
                        connection, "personal.body",
                        fields=("weight_kg", "body_fat_percent", "waist_cm"),
                        numeric={
                            "personal.weight_kg": body_data.get("weight_kg"),
                            "personal.body_fat_percent": body_data.get("body_fat_percent"),
                            "personal.waist_cm": body_data.get("waist_cm"),
                        },
                    )
                    st.session_state["personal_save_notice"] = TR("personal_info.body_saved"); st.rerun()
                except ValueError:
                    st.error(TR("personal_info.invalid_body"))

        with st.expander(TR("personal_info.goal_form"), expanded=False):
            goals_submitted, goals_data = _goal_form(goals)
        if goals_submitted:
            try:
                save_personal_goals(connection, goals_data)
                record_input_habit(
                    connection, "personal.goals",
                    fields=("target_weight_kg", "target_body_fat_percent", "target_waist_cm"),
                    choices={"personal.training_goal": goals_data.get("training_goal")},
                    numeric={
                        "personal.target_weight_kg": goals_data.get("target_weight_kg"),
                        "personal.target_body_fat_percent": goals_data.get("target_body_fat_percent"),
                        "personal.target_waist_cm": goals_data.get("target_waist_cm"),
                        "personal.daily_calorie_adjustment_kcal": goals_data.get("daily_calorie_adjustment_kcal"),
                    },
                )
                st.session_state["personal_save_notice"] = TR("personal_info.goals_saved"); st.rerun()
            except ValueError:
                st.error(TR("personal_info.invalid_goals"))
        if save_notice:
            st.success(save_notice)
    finally:
        connection.close()
    st.caption(TR("personal_info.local_notice"))
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
