"""Personal profile, body status, trends, and local targets."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date

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


def _basic_information(profile):
    st.subheader(TR("personal_info.basic"))
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
    for column, (key, value) in zip(st.columns(len(values)), values):
        column.metric(TR(f"personal_info.{key}"), _value(value))


def _body_status(connection, latest):
    st.subheader(TR("personal_info.body_status"))
    if latest:
        st.caption(TR("personal_info.latest_date", date=format_date(latest["date"], LANGUAGE)))
    values = (
        ("weight", _value(latest.get("weight_kg") if latest else None, " kg")),
        ("body_fat", _value(latest.get("body_fat_percent") if latest else None, "%")),
        ("waist", _value(latest.get("waist_cm") if latest else None, " cm")),
    )
    for column, (key, value) in zip(st.columns(3), values):
        column.metric(TR(f"personal_info.{key}"), value)

    st.markdown(TR("personal_info.weight_trend_title"))
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
    st.line_chart(frame, x=date_label, y=weight_label, height=260)
    change = trend[-1]["weight_kg"] - trend[0]["weight_kg"]
    st.metric(TR("personal_info.weight_change"), f"{change:+.2f} kg")


def _profile_form(profile):
    with st.form("personal_profile_form"):
        st.markdown(TR("personal_info.profile_form"))
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
        st.markdown(TR("personal_info.body_form"))
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
    with st.form("personal_goal_form"):
        st.markdown(TR("personal_info.goal_form"))
        current_training_goal = (goals or {}).get("training_goal") or "maintenance"
        training_goal = st.selectbox(
            TR("personal_info.training_goal"),
            TRAINING_GOALS,
            index=TRAINING_GOALS.index(current_training_goal),
            format_func=_training_goal_name,
        )
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
        submitted = st.form_submit_button(TR("personal_info.save_goals"), type="primary")
    return submitted, {
        "training_goal": training_goal,
        "target_weight_kg": target_weight,
        "target_body_fat_percent": target_body_fat,
        "target_waist_cm": target_waist,
    }


def main():
    st.title(TR("personal_info.title"))
    st.caption(TR("personal_info.intro"))
    save_notice = st.session_state.pop("personal_save_notice", None)
    connection = connect(migrate=False)
    try:
        profile = get_personal_profile(connection)
        latest = latest_body_measurement(connection)
        goals = get_personal_goals(connection)
        _basic_information(profile)
        _body_status(connection, latest)
        st.subheader(TR("personal_info.edit"))

        profile_submitted, profile_data = _profile_form(profile)
        if profile_submitted:
            try:
                save_personal_profile(connection, profile_data)
                st.session_state["personal_save_notice"] = TR("personal_info.profile_saved"); st.rerun()
            except ValueError:
                st.error(TR("personal_info.invalid_profile"))

        body_submitted, body_data = _body_form(profile, latest)
        if body_submitted:
            if body_data["height_cm"] is None:
                st.error(TR("personal_info.save_profile_first"))
            else:
                try:
                    create_body_measurement(connection, body_data)
                    st.session_state["personal_save_notice"] = TR("personal_info.body_saved"); st.rerun()
                except ValueError:
                    st.error(TR("personal_info.invalid_body"))

        goals_submitted, goals_data = _goal_form(goals)
        if goals_submitted:
            try:
                save_personal_goals(connection, goals_data)
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
