"""Bilingual Streamlit page for local logging and reviewed AI Context export."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date
import json

import pandas as pd
import streamlit as st

from src.ai_context.exporter import export_ai_context
from src.branding import browser_page_title, load_page_icon
from src.db import connect
from src.demo_sandbox import configure_demo_runtime, is_demo_mode
from src.i18n import format_date, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.personal_logging.body import calculate_bmi, weight_trend
from src.personal_logging.config import MEAL_TYPES, SESSION_TYPES
from src.personal_logging.storage import (
    create_batch_sets, create_body_measurement, create_nutrition_log,
    create_workout_session, delete_body_measurement, delete_nutrition_log,
    delete_workout_session, list_body_measurements, list_nutrition_logs,
    list_workout_sessions,
)
from src.personal_logging.summaries import rebuild_daily_summaries
from src.post_save_sync import refresh_local_coach_for_date, start_priority_data_sync
from src.input_habits import (
    bootstrap_input_habits, clear_input_habits, format_input_habit_summary, get_input_habits,
    get_input_habit_defaults, record_input_habit, set_input_habits_enabled,
)
from src.ui_tables import centered_dataframe
from src.ui_controls import render_manual_input_styles


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("personal_logging.title")),
    page_icon=load_page_icon(),
    layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "daily_log")
render_manual_input_styles(st)
st.title(TR("personal_logging.title"))


def _queue_priority_data_sync():
    if is_demo_mode():
        return
    try:
        start_priority_data_sync()
    except RuntimeError:
        # The manual record is durable even if its optional background sync
        # runner is unavailable; the fixed scheduler will reconcile it later.
        return


with connect() as connection:
    bootstrap_input_habits(connection)
    input_habit_defaults = get_input_habit_defaults(connection)
    input_habit_summary = format_input_habit_summary(connection)
if input_habit_summary:
    st.caption(TR("input_habits.summary", summary=input_habit_summary))
with st.expander(TR("input_habits.title"), expanded=False):
    with connect() as connection:
        habit_profile = get_input_habits(connection)
    st.caption(TR("input_habits.description"))
    st.write(TR("input_habits.learned_count", count=habit_profile["event_count"]))
    if habit_profile["enabled"]:
        if st.button(TR("input_habits.disable"), key="disable_input_habits"):
            with connect() as connection:
                set_input_habits_enabled(connection, False)
            st.rerun()
    else:
        if st.button(TR("input_habits.enable"), key="enable_input_habits"):
            with connect() as connection:
                set_input_habits_enabled(connection, True)
            st.rerun()
    if st.button(TR("input_habits.clear"), key="clear_input_habits"):
        with connect() as connection:
            clear_input_habits(connection)
        st.rerun()
selected_date = st.date_input(
    TR("personal_logging.record_date"), date.today(), key="log_date"
).isoformat()
tabs = st.tabs(tuple(TR(key) for key in (
    "personal_logging.body_tab", "personal_logging.nutrition_tab", "personal_logging.strength_tab",
    "personal_logging.other_tab", "personal_logging.summary_tab", "personal_logging.ai_tab",
)))


def optional_number(value):
    return None if value in (None, 0.0) else float(value)


def error_text(exc):
    code = str(exc)
    known = {"WEIGHT_REQUIRED", "HEIGHT_REQUIRED_FOR_FIRST_MEASUREMENT", "FOOD_NAME_REQUIRED", "EXERCISE_NAME_REQUIRED", "INVALID_SET_COUNT", "AI_CONTEXT_SENSITIVE_QUESTION"}
    return TR(f"errors.{code}") if code in known else TR("errors.invalid_value")


def meal_name(code):
    return TR(f"meal_type.{code}")


def session_name(code):
    return TR(f"session_type.{code}")


def display_rows(rows, columns, enum_column=None, enum_formatter=None):
    frame = pd.DataFrame(rows)
    available = [column for column in columns if column in frame.columns]
    frame = frame[available].copy()
    if enum_column in frame.columns and enum_formatter:
        frame[enum_column] = frame[enum_column].map(enum_formatter)
    labels = {
        "date": TR("reports.date"), "height_cm": TR("personal_logging.height"),
        "weight_kg": TR("personal_logging.weight"), "waist_cm": TR("personal_logging.waist"),
        "body_fat_percent": TR("personal_logging.body_fat"), "meal_type": TR("personal_logging.meal_type"),
        "food_name": TR("personal_logging.food"), "amount": TR("personal_logging.amount"),
        "unit": TR("personal_logging.unit"), "calories": TR("personal_logging.calories"),
        "protein_g": TR("personal_logging.protein"), "carbohydrate_g": TR("personal_logging.carbs"),
        "fat_g": TR("personal_logging.fat"), "session_type": TR("personal_logging.session_type"),
        "duration_minutes": TR("personal_logging.duration"), "session_rpe": TR("personal_logging.session_rpe"),
    }
    centered_dataframe(frame.rename(columns=labels))


with tabs[0]:
    with st.form("body_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        height = c1.number_input(TR("personal_logging.height"), min_value=0.0, key="body_height")
        weight = c2.number_input(TR("personal_logging.weight"), min_value=0.0, key="body_weight")
        waist = c3.number_input(TR("personal_logging.waist"), min_value=0.0, key="body_waist")
        fat = c4.number_input(TR("personal_logging.body_fat"), min_value=0.0, max_value=100.0, key="body_fat")
        primary = st.checkbox(TR("personal_logging.primary"), value=True, key="body_primary")
        notes = st.text_area(TR("personal_logging.notes"), key="body_notes")
        if st.form_submit_button(TR("personal_logging.save_body")):
            try:
                with connect() as connection:
                    create_body_measurement(connection, {"date": selected_date, "height_cm": optional_number(height), "weight_kg": optional_number(weight), "waist_cm": optional_number(waist), "body_fat_percent": optional_number(fat), "is_primary": primary, "notes": notes or None})
                    record_input_habit(
                        connection,
                        "daily_log.body",
                        fields=[field for field, value in (
                            ("height_cm", height), ("weight_kg", weight),
                            ("waist_cm", waist), ("body_fat_percent", fat),
                        ) if value not in (None, 0.0)],
                    )
                st.success(TR("personal_logging.body_saved"))
            except (ValueError, RuntimeError) as exc:
                st.error(error_text(exc))
    with connect() as connection:
        body_rows = list_body_measurements(connection, 30)
    if body_rows:
        display_rows(body_rows, ("id", "date", "height_cm", "weight_kg", "waist_cm", "body_fat_percent"))
        latest = body_rows[0]
        st.metric("BMI", calculate_bmi(latest["weight_kg"], latest["height_cm"]) or TR("common.no_data"))
        st.caption(TR("personal_logging.bmi_notice"))
        with st.form("delete_body"):
            record_id = st.selectbox(TR("personal_logging.delete_body_id"), [row["id"] for row in body_rows], key="delete_body_id")
            confirm = st.checkbox(TR("personal_logging.confirm_delete_body"), key="delete_body_confirm")
            if st.form_submit_button(TR("common.delete")) and confirm:
                with connect() as connection: delete_body_measurement(connection, record_id)
                st.success(TR("common.saved"))
    else:
        st.info(TR("personal_logging.body_empty"))

with tabs[1]:
    with st.form("nutrition_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        meal_index = MEAL_TYPES.index(input_habit_defaults["meal_type"]) if input_habit_defaults.get("meal_type") in MEAL_TYPES else 0
        meal_type = c1.selectbox(TR("personal_logging.meal_type"), MEAL_TYPES, index=meal_index, format_func=meal_name, key="nutrition_meal_type")
        food_name = c2.text_input(TR("personal_logging.food"), key="nutrition_food")
        amount = c3.number_input(TR("personal_logging.amount"), min_value=0.0, key="nutrition_amount")
        unit = st.text_input(TR("personal_logging.unit"), key="nutrition_unit")
        nutrient_cols = st.columns(7)
        label_keys = ("calories", "protein", "carbs", "fat", "fiber", "water", "sodium")
        nutrient_values = [column.number_input(TR(f"personal_logging.{key}"), min_value=0.0, key=f"nutrition_{key}") for column, key in zip(nutrient_cols, label_keys)]
        notes = st.text_area(TR("personal_logging.nutrition_notes"), key="nutrition_notes")
        if st.form_submit_button(TR("personal_logging.add_food")):
            keys = ("calories", "protein_g", "carbohydrate_g", "fat_g", "fiber_g", "water_ml", "sodium_mg")
            try:
                with connect() as connection:
                    create_nutrition_log(connection, {"date": selected_date, "meal_type": meal_type, "food_name": food_name, "amount": optional_number(amount), "unit": unit or None, "notes": notes or None, "data_source": "manual", **{key: optional_number(value) for key, value in zip(keys, nutrient_values)}})
                    record_input_habit(
                        connection,
                        "daily_log.nutrition",
                        fields=[key for key, value in zip(keys, nutrient_values) if value not in (None, 0.0)],
                        choices={"nutrition.meal_type": meal_type, "nutrition.unit": unit},
                        numeric={"nutrition.amount": amount},
                    )
                refresh_local_coach_for_date(selected_date)
                st.success(TR("personal_logging.food_saved"))
            except ValueError as exc:
                st.error(error_text(exc))
    with connect() as connection: nutrition_rows = list_nutrition_logs(connection, selected_date)
    if nutrition_rows:
        display_rows(nutrition_rows, ("id", "date", "meal_type", "food_name", "amount", "unit", "calories", "protein_g", "carbohydrate_g", "fat_g"), "meal_type", meal_name)
        with st.form("delete_nutrition"):
            item_id = st.selectbox(TR("personal_logging.delete_food_id"), [row["id"] for row in nutrition_rows], key="delete_nutrition_id")
            confirm = st.checkbox(TR("personal_logging.confirm_delete_food"), key="delete_nutrition_confirm")
            if st.form_submit_button(TR("common.delete")) and confirm:
                with connect() as connection: delete_nutrition_log(connection, item_id)
                refresh_local_coach_for_date(selected_date)
                st.success(TR("common.saved"))
    else: st.info(TR("personal_logging.nutrition_empty"))

with tabs[2]:
    with st.form("strength_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        duration = c1.number_input(TR("personal_logging.duration"), min_value=0.0, value=float(input_habit_defaults.get("training_duration_minutes") or 0.0), key="strength_duration")
        session_rpe = c2.number_input(TR("personal_logging.session_rpe"), min_value=0.0, max_value=10.0, value=float(input_habit_defaults.get("training_session_rpe") or 0.0), key="strength_rpe")
        exercise_name = c3.text_input(TR("personal_logging.exercise"), key="strength_exercise")
        category = c4.text_input(TR("personal_logging.category"), key="strength_category")
        s1, s2, s3 = st.columns(3)
        weight = s1.number_input(TR("personal_logging.weight_kg"), min_value=0.0, key="strength_weight")
        reps = s2.number_input(TR("personal_logging.reps"), min_value=0, step=1, key="strength_reps")
        set_count = s3.number_input(TR("personal_logging.sets"), min_value=1, step=1, key="strength_sets")
        if st.form_submit_button(TR("personal_logging.save_strength")):
            try:
                with connect() as connection:
                    session_id = create_workout_session(connection, {"date": selected_date, "session_type": "strength", "duration_minutes": optional_number(duration), "session_rpe": optional_number(session_rpe)})
                    create_batch_sets(connection, session_id, exercise_name, int(set_count), int(reps), optional_number(weight), exercise_category=category or None)
                    record_input_habit(
                        connection,
                        "daily_log.training",
                        fields=[field for field, value in (
                            ("duration_minutes", duration), ("session_rpe", session_rpe),
                            ("exercise_name", exercise_name), ("weight_kg", weight),
                            ("reps", reps), ("set_count", set_count),
                        ) if value not in (None, "", 0, 0.0)],
                        choices={"training.session_type": "strength"},
                        numeric={"training.duration_minutes": duration, "training.session_rpe": session_rpe},
                    )
                refresh_local_coach_for_date(selected_date)
                _queue_priority_data_sync()
                st.success(TR("personal_logging.strength_saved", sets=set_count))
            except ValueError as exc: st.error(error_text(exc))

with tabs[3]:
    with st.form("other_training_form", clear_on_submit=False):
        other_types = [kind for kind in SESSION_TYPES if kind != "strength"]
        preferred_type = input_habit_defaults.get("training_type")
        type_index = other_types.index(preferred_type) if preferred_type in other_types else 0
        session_type = st.selectbox(TR("personal_logging.session_type"), other_types, index=type_index, format_func=session_name, key="other_session_type")
        c1, c2 = st.columns(2)
        duration = c1.number_input(TR("personal_logging.other_duration"), min_value=0.0, value=float(input_habit_defaults.get("training_duration_minutes") or 0.0), key="other_duration")
        rpe = c2.number_input(TR("personal_logging.session_rpe"), min_value=0.0, max_value=10.0, value=float(input_habit_defaults.get("training_session_rpe") or 0.0), key="other_rpe")
        metadata_text = st.text_area(TR("personal_logging.metadata"), value="{}", key="other_metadata")
        notes = st.text_area(TR("personal_logging.training_notes"), key="other_notes")
        if st.form_submit_button(TR("personal_logging.save_training")):
            try:
                metadata = json.loads(metadata_text)
                with connect() as connection:
                    create_workout_session(connection, {"date": selected_date, "session_type": session_type, "duration_minutes": optional_number(duration), "session_rpe": optional_number(rpe), "metadata": metadata, "notes": notes or None})
                    record_input_habit(
                        connection,
                        "daily_log.training",
                        fields=[field for field, value in (
                            ("duration_minutes", duration), ("session_rpe", rpe),
                            ("metadata", metadata_text), ("notes", notes),
                        ) if value not in (None, "", 0, 0.0, "{}")],
                        choices={"training.session_type": session_type},
                        numeric={"training.duration_minutes": duration, "training.session_rpe": rpe},
                    )
                refresh_local_coach_for_date(selected_date)
                _queue_priority_data_sync()
                st.success(TR("personal_logging.training_saved"))
            except (ValueError, json.JSONDecodeError) as exc: st.error(error_text(exc))
    with connect() as connection: workout_rows = list_workout_sessions(connection, selected_date)
    if workout_rows:
        display_rows(workout_rows, ("id", "date", "session_type", "duration_minutes", "session_rpe"), "session_type", session_name)
        with st.form("delete_workout"):
            workout_id = st.selectbox(TR("personal_logging.delete_training_id"), [row["id"] for row in workout_rows], key="delete_workout_id")
            confirm = st.checkbox(TR("personal_logging.confirm_delete_training"), key="delete_workout_confirm")
            if st.form_submit_button(TR("common.delete")) and confirm:
                with connect() as connection: delete_workout_session(connection, workout_id)
                refresh_local_coach_for_date(selected_date)
                _queue_priority_data_sync()
                st.success(TR("personal_logging.training_deleted"))
    else: st.info(TR("personal_logging.training_empty"))

with tabs[4]:
    with connect() as connection:
        summary = rebuild_daily_summaries(connection, selected_date); trends = weight_trend(connection, 90, selected_date)
    body, nutrition, training = summary["body"], summary["nutrition"], summary["training"]
    for column, (label, value) in zip(st.columns(4), ((TR("personal_logging.weight"), body.get("latest_weight_kg")), (TR("personal_logging.waist"), body.get("waist_cm")), (TR("personal_logging.calories"), nutrition.get("calories")), (TR("reports.manual_sessions"), training.get("session_count")))):
        with column: st.metric(label, value if value is not None else TR("common.no_data"))
    if trends:
        frame = pd.DataFrame(trends).rename(columns={"date": TR("reports.date"), "weight_kg": TR("personal_logging.weight")})
        st.line_chart(frame, x=TR("reports.date"), y=TR("personal_logging.weight"))

with tabs[5]:
    st.warning(TR("ai_context.manual_warning"))
    question_options = tuple(TR(f"ai_context.q{index}") for index in range(1, 9))
    questions = st.multiselect(TR("ai_context.questions"), question_options, key="ai_questions")
    custom_question = st.text_input(TR("ai_context.custom_question"), key="ai_custom_question")
    range_days = st.selectbox(TR("ai_context.range"), (1, 7, 14, 30), index=1, key="ai_range")
    if st.button(TR("ai_context.preview")):
        try:
            with connect() as connection: result = export_ai_context(connection, selected_date, range_days, questions + ([custom_question] if custom_question else []), dry_run=True, language=LANGUAGE)
            st.session_state["ai_context_preview"] = result
        except ValueError as exc: st.error(error_text(exc))
    preview = st.session_state.get("ai_context_preview")
    if preview:
        st.json(preview["payload"])
        confirm = st.checkbox(TR("ai_context.confirm"), key="ai_export_confirm")
        if st.button(TR("ai_context.generate")):
            if not confirm: st.error(TR("ai_context.confirm_first"))
            else:
                with connect() as connection: export_ai_context(connection, selected_date, range_days, questions + ([custom_question] if custom_question else []), dry_run=False, confirmed=True, language=LANGUAGE)
                st.success(TR("ai_context.written"))
