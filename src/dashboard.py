"""Training section with Polar-authoritative structured exercise details."""

from datetime import date, datetime, time
from html import escape
import os
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from src.branding import brand_icon_path, load_page_icon
from src.dashboard_data import get_latest_local_coach
from src.demo_sandbox import configure_demo_runtime
from src.db import connect
from src.domain_dashboard_data import get_domain_baselines
from src.exercise_format import minutes_to_hms, time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.training_logging import (
    CUSTOM_EXERCISE, EXERCISE_CATEGORIES, LOAD_UNITS, MEASUREMENT_MODES,
    SET_TYPES, SIDES, copy_exercise, copy_set,
    create_custom_exercise_catalog, ensure_polar_session_index,
    get_training_session, list_exercise_catalog,
    list_training_sessions, previous_exercises, save_training_details,
    soft_delete_training_session,
)
from src.training_baseline import get_training_baseline_view
from src.ui.components.training_entry import (
    ENTRY_MODES, EXERTION_PREFERENCES, apply_catalog_defaults,
    copied_set_for_entry, default_load_unit, visible_set_fields,
)
from src.ui_controls import render_manual_input_styles
from src.ui_scroll import render_interaction_focus
from src.ui_tables import centered_dataframe


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=get_translator(PAGE_LANGUAGE)("domain.exercise.title"),
    page_icon=load_page_icon(), layout="wide",
)
if os.environ.get("DRC_STREAMLIT_ENTRYPOINT") == "cloud_app.py":
    LANGUAGE, TR = PAGE_LANGUAGE, get_translator(PAGE_LANGUAGE)
else:
    LANGUAGE, TR = render_sidebar(st, "exercise")
render_manual_input_styles(st)

TRAINING_CSS = """
<style>
.drc-training-head{display:flex;align-items:center;justify-content:center;text-align:center;font-weight:650;min-height:2.4rem}
div[data-testid="stExpander"] summary p{font-size:1.5rem!important;font-weight:650!important}
div[data-testid="stNumberInput"] input,div[data-testid="stTextInput"] input{text-align:center!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value]{flex:1 1 auto!important;width:100%!important;text-align:center!important;padding-left:2rem!important}
@media (max-width: 760px){.drc-training-head{min-height:1.8rem;font-size:.9rem}}
</style>
"""
st.markdown(TRAINING_CSS, unsafe_allow_html=True)


def _uuid():
    return str(uuid4())


def _value(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _cell(value):
    return f'<div class="drc-training-head">{escape(str(value))}</div>'


def _baseline(label_key, baseline, suffix="", formatter=None):
    if not baseline or baseline.get("status") == "insufficient_data":
        st.metric(TR(label_key), TR("baseline.insufficient_data")); return
    delta = baseline.get("percent_change")
    display = formatter or (lambda value: _value(value, suffix))
    st.metric(TR(label_key), display(baseline.get("latest_value")), None if delta is None else f"{delta:+.1f}%")
    st.caption(TR("domain.common.baseline_median", value=display(baseline.get("median_value"))))


def _catalog_name(item):
    return item["display_name_zh" if LANGUAGE != "en" else "display_name_en"]


def _session_source(item):
    if item.get("polar_external_id") and item.get("exercises"):
        return TR("training_logging.merged_source")
    if item.get("polar_external_id"):
        return TR("training_logging.polar_synced")
    return TR("training_logging.manual_source")


def _history(sessions):
    st.subheader(TR("history.activity_title"))
    history_view_label = "查看" if LANGUAGE != "en" else "View"
    rows = []
    for item in sessions:
        rows.append({
            TR("reports.date"): format_date(item["date"], LANGUAGE),
            TR("training_logging.start_time"): time_to_hms(item.get("start_time")),
            TR("domain.exercise.sport"): item.get("sport_display") or TR("common.no_data"),
            TR("domain.exercise.duration"): minutes_to_hms(
                item["duration_seconds"] / 60 if item.get("duration_seconds") is not None else None
            ),
            TR("domain.exercise.average_hr"): item.get("average_hr"),
            TR("domain.exercise.maximum_hr"): item.get("max_hr"),
            TR("domain.exercise.calories"): item.get("calories"),
            TR("training_logging.data_source"): _session_source(item),
            TR("domain.exercise.title"): TR("training_logging.view_edit"),
        })
    if rows:
        # Render the table row-by-row so the action cell contains a real
        # Streamlit button rather than plain text in the read-only HTML table.
        headers = list(rows[0].keys())
        widths = [1.0, .9, 1.25, 1.0, .8, .8, .8, 1.0, 1.2]
        # Keep the familiar table layout while limiting the visible viewport
        # to roughly seven rows. Older records remain available by scrolling.
        with st.container(height=430, border=True):
            header_columns = st.columns(widths)
            for column, label in zip(header_columns, headers):
                header_html = f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>'
                column.markdown(header_html, unsafe_allow_html=True)
            for item, row in zip(sessions, rows):
                columns = st.columns(widths, vertical_alignment="center")
                for column, label in zip(columns[:-1], headers[:-1]):
                    cell_html = f'<div style="text-align:center;">{escape(str(row[label]))}</div>'
                    column.markdown(cell_html, unsafe_allow_html=True)
                if columns[-1].button(
                    history_view_label,
                    key=f"training_history_view_{item['id']}",
                    use_container_width=True,
                ):
                    st.session_state["training_history_selected"] = item["id"]
                    st.session_state["training_details_focus_nonce"] = (
                        st.session_state.get("training_details_focus_nonce", 0) + 1
                    )
                    st.rerun()
    else:
        st.info(TR("common.no_data"))


def _today_polar_data(sessions):
    today = date.today().isoformat()
    st.subheader(TR("training_logging.today_data"))
    polar = [item for item in sessions if item.get("date") == today and item.get("polar_external_id")]
    if not polar:
        st.info(TR("training_logging.today_no_data"))
        return
    durations = [item["duration_seconds"] for item in polar if item.get("duration_seconds") is not None]
    calories = [item["calories"] for item in polar if item.get("calories") is not None]
    average_hrs = [item["average_hr"] for item in polar if item.get("average_hr") is not None]
    max_hrs = [item["max_hr"] for item in polar if item.get("max_hr") is not None]
    distances = [item["distance_meters"] for item in polar if item.get("distance_meters") is not None]
    row = {
        TR("training_logging.today_date"): format_date(today, LANGUAGE),
        TR("training_logging.today_count"): len(polar),
    }
    if durations:
        row[TR("training_logging.today_duration")] = minutes_to_hms(sum(durations) / 60)
    if calories:
        row[TR("training_logging.today_calories")] = sum(calories)
    if average_hrs:
        row[TR("training_logging.today_average_hr")] = round(sum(average_hrs) / len(average_hrs))
    if max_hrs:
        row[TR("training_logging.today_max_hr")] = max(max_hrs)
    if distances:
        row[TR("training_logging.today_distance")] = sum(distances)
    centered_dataframe([row])


def _today_training_details(connection, sessions):
    today = date.today().isoformat()
    polar = [item for item in sessions if item.get("date") == today and item.get("polar_external_id")]
    st.subheader(TR("training_logging.today_details"))
    if not polar:
        st.info(TR("training_logging.today_no_data"))
        return
    for index, session in enumerate(polar, start=1):
        label = (
            f"{index}. {format_date(today, LANGUAGE)} · "
            f"{time_to_hms(session.get('start_time'))} · "
            f"{session.get('sport_display') or TR('common.no_data')}"
        )
        with st.expander(label, expanded=False):
            # The aggregate Polar fields are already shown in 今日训练数据.
            # Keep this section focused on the structured training log only.
            with st.container(border=True):
                st.markdown(f"### {TR('training_logging.exercise_details')}")
                _today_exercise_details(connection, session)
            with st.container(border=True):
                st.markdown(f"### {TR('training_logging.summary')}")
                _summary(session, show_title=False)


def _today_exercise_details(connection, session):
    """Read-only action detail view used by the daily training section."""
    exercises = session.get("exercises") or []
    if not exercises:
        st.info(TR("training_logging.empty_exercises"))
        return

    catalog = {item["id"]: item for item in list_exercise_catalog(connection)}
    field_labels = (
        ("load_value", "load"), ("load_unit", "load_unit"), ("reps", "reps"),
        ("duration_seconds", "duration_seconds"), ("distance_meters", "distance_meters"),
        ("resistance_level", "resistance"), ("incline_percent", "incline"),
        ("rpe", "rpe"), ("rir", "rir"), ("rest_seconds", "rest"),
        ("side", "side"), ("completed", "completed_set"), ("notes", "set_notes"),
    )
    for index, exercise in enumerate(exercises, start=1):
        catalog_item = catalog.get(exercise.get("exercise_catalog_id"))
        name = (
            _catalog_name(catalog_item) if catalog_item else
            exercise.get("custom_exercise_name") or TR("common.no_data")
        )
        with st.container(border=True):
            st.markdown(f"#### {index}. {name}")
            meta = st.columns(4)
            meta[0].metric(TR("training_logging.exercise_category"), TR(
                f"training_logging.categories.{exercise.get('exercise_category', 'other')}"
            ))
            meta[1].metric(TR("training_logging.measurement_mode"), TR(
                f"training_logging.modes.{exercise.get('measurement_mode', 'freeform')}"
            ))
            meta[2].metric(TR("training_logging.primary_muscle_group"), exercise.get("primary_muscle_group") or TR("common.no_data"))
            meta[3].metric(TR("training_logging.equipment"), exercise.get("equipment") or TR("common.no_data"))
            if exercise.get("notes"):
                st.caption(f"{TR('training_logging.exercise_notes')}：{exercise['notes']}")

            sets = exercise.get("sets") or []
            if not sets:
                st.caption(TR("training_logging.empty_sets"))
                continue
            rows = []
            for set_item in sets:
                row = {
                    TR("training_logging.set"): set_item.get("set_number"),
                    TR("training_logging.set_type"): TR(
                        f"training_logging.set_types.{set_item.get('set_type', 'working')}"
                    ),
                }
                for field, label in field_labels:
                    value = set_item.get(field)
                    if field == "load_unit":
                        value = TR(f"training_logging.load_units.{value or 'none'}")
                    elif field == "side":
                        value = TR(f"training_logging.sides.{value or 'not_applicable'}")
                    elif field == "completed":
                        value = TR("common.yes") if value else TR("common.no")
                    elif value in (None, ""):
                        value = TR("common.no_data")
                    row[TR(f"training_logging.{label}")] = value
                rows.append(row)
            centered_dataframe(rows)


def _session_header(session):
    st.info(TR("training_logging.readonly_notice") if session["polar_readonly"] else TR("training_logging.manual_notice"))
    columns = st.columns(5)
    columns[0].metric(TR("training_logging.date"), format_date(session["date"], LANGUAGE))
    columns[1].metric(TR("training_logging.start_time"), time_to_hms(session.get("start_time")))
    columns[2].metric(
        TR("training_logging.duration"),
        minutes_to_hms(session["duration_seconds"] / 60) if session.get("duration_seconds") is not None else TR("common.no_data"),
    )
    columns[3].metric(TR("training_logging.average_hr"), _value(session.get("average_hr")))
    columns[4].metric(TR("training_logging.max_hr"), _value(session.get("max_hr")))
    columns = st.columns(4)
    columns[0].metric(TR("training_logging.calories"), _value(session.get("calories")))
    columns[1].metric(TR("training_logging.distance"), _value(session.get("distance_meters")))
    columns[2].metric(TR("training_logging.data_source"), _session_source(session))
    columns[3].metric(
        TR("training_logging.sync_status"),
        TR("training_logging.polar_synced") if session["polar_readonly"] else TR("training_logging.manual_source"),
    )
    if session.get("polar_sport_display"):
        st.caption(f"{TR('training_logging.polar_sport_type')}：{session['polar_sport_display']}")


def _set_default():
    return {
        "uuid": _uuid(), "set_type": "working", "load_value": None,
        "load_unit": "none", "reps": None, "duration_seconds": None,
        "distance_meters": None, "resistance_level": None, "incline_percent": None,
        "rpe": None, "rir": None, "rest_seconds": None,
        "side": "not_applicable", "completed": True, "notes": None,
    }


def _exercise_default():
    return {
        "uuid": _uuid(), "exercise_catalog_id": None, "custom_exercise_name": "",
        "exercise_category": "strength", "measurement_mode": "weight_reps",
        "primary_muscle_group": "", "equipment": "", "is_unilateral": False,
        "skill_proficiency": None, "notes": "", "sets": [{**_set_default(), "load_unit": "kg"}],
        "_catalog_applied_id": None, "_save_to_library": False,
    }


def _editor_state(session):
    key = f"training_exercise_editor_{session['id']}"
    if key not in st.session_state:
        st.session_state[key] = [
            {**copy_exercise(item), "_catalog_applied_id": item.get("exercise_catalog_id"),
             "_save_to_library": False}
            for item in session["exercises"]
        ]
    return key, st.session_state[key]


def _set_field(column, item, field, prefix):
    """Render one applicable field while leaving every hidden value untouched."""
    if field == "set_type":
        item[field] = column.selectbox(
            TR("training_logging.set_type"), SET_TYPES,
            index=SET_TYPES.index(item.get(field, "working")),
            format_func=lambda value: TR(f"training_logging.set_types.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "load_unit":
        item[field] = column.selectbox(
            TR("training_logging.load_unit"), LOAD_UNITS,
            index=LOAD_UNITS.index(item.get(field, "none")) if item.get(field, "none") in LOAD_UNITS else 0,
            format_func=lambda value: TR(f"training_logging.load_units.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "side":
        item[field] = column.selectbox(
            TR("training_logging.side"), SIDES,
            index=SIDES.index(item.get(field, "not_applicable")),
            format_func=lambda value: TR(f"training_logging.sides.{value}"),
            key=f"{prefix}_{field}",
        )
    elif field == "completed":
        item[field] = column.checkbox(
            TR("training_logging.completed_set"), value=bool(item.get(field, True)),
            key=f"{prefix}_{field}",
        )
    elif field == "notes":
        item[field] = column.text_input(
            TR("training_logging.set_notes"), value=item.get(field) or "",
            key=f"{prefix}_{field}",
        )
    else:
        labels = {
            "load_value": "load", "reps": "reps", "duration_seconds": "duration_seconds",
            "distance_meters": "distance_meters", "resistance_level": "resistance",
            "incline_percent": "incline", "rpe": "rpe", "rir": "rir",
            "rest_seconds": "rest",
        }
        settings = {
            "load_value": (0.0, None, .5), "reps": (0, None, 1),
            "duration_seconds": (0.0, None, 5.0), "distance_meters": (0.0, None, 100.0),
            "resistance_level": (0.0, None, 1.0), "incline_percent": (0.0, None, .5),
            "rpe": (1.0, 10.0, .5), "rir": (0.0, 10.0, 1.0),
            "rest_seconds": (0.0, None, 15.0),
        }
        minimum, maximum, step = settings[field]
        options = {
            "label": TR(f"training_logging.{labels[field]}"), "min_value": minimum,
            "value": item.get(field), "step": step, "key": f"{prefix}_{field}",
        }
        if maximum is not None:
            options["max_value"] = maximum
        if field == "load_value" and item.get("load_unit") in {"bodyweight", "none"}:
            options["disabled"] = True
        item[field] = column.number_input(**options)


def _set_editor(exercise, exercise_index, entry_mode, exertion_preference):
    sets = exercise.setdefault("sets", [])
    mode = exercise["measurement_mode"]
    fields = visible_set_fields(mode, entry_mode, exertion_preference)
    segment_label = "practice_segment" if mode in {"dance_practice", "freeform"} else "set"

    for set_index, item in enumerate(list(sets)):
        prefix = f"training_set_{exercise['uuid']}_{item['uuid']}"
        primary_fields = fields[:4]
        columns = st.columns((.7, *(1 for _ in primary_fields)))
        columns[0].markdown(
            _cell(f"{TR(f'training_logging.{segment_label}')} {set_index + 1}"),
            unsafe_allow_html=True,
        )
        for column, field in zip(columns[1:], primary_fields):
            _set_field(column, item, field, prefix)
        remaining = fields[4:]
        for offset in range(0, len(remaining), 5):
            chunk = remaining[offset:offset + 5]
            extra_columns = st.columns(len(chunk))
            for column, field in zip(extra_columns, chunk):
                _set_field(column, item, field, prefix)

    controls = st.columns((1.1, 1.5, 1.2, 5))
    if controls[0].button(TR("training_logging.add_set"), key=f"set_add_{exercise['uuid']}"):
        new_set = _set_default()
        new_set["load_unit"] = default_load_unit(mode)
        sets.append(new_set); st.rerun()
    if controls[1].button(TR("training_logging.copy_previous_set"), key=f"set_copy_{exercise['uuid']}"):
        source = sets[-1] if sets else {**_set_default(), "load_unit": default_load_unit(mode)}
        sets.append(copied_set_for_entry(source, mode, entry_mode, exertion_preference)); st.rerun()
    with controls[2].popover(TR("training_logging.more_actions"), use_container_width=True):
        batch_count = st.number_input(
            TR("training_logging.batch_count"), min_value=1, max_value=20, value=3,
            key=f"set_batch_count_{exercise['uuid']}",
        )
        if st.button(TR("training_logging.batch_add_sets"), key=f"set_batch_{exercise['uuid']}"):
            source = sets[-1] if sets else {**_set_default(), "load_unit": default_load_unit(mode)}
            sets.extend(
                copied_set_for_entry(source, mode, entry_mode, exertion_preference)
                for _ in range(int(batch_count))
            ); st.rerun()
        if sets:
            delete_index = st.selectbox(
                TR("training_logging.delete_set"), range(len(sets)),
                format_func=lambda value: f"{TR(f'training_logging.{segment_label}')} {value + 1}",
                key=f"set_delete_index_{exercise['uuid']}",
            )
            confirmed = st.checkbox(
                TR("training_logging.confirm_delete_set"), key=f"set_delete_confirm_{exercise['uuid']}"
            )
            if st.button(
                TR("training_logging.delete_set"), disabled=not confirmed,
                key=f"set_delete_{exercise['uuid']}", type="primary",
            ):
                sets.pop(delete_index); st.rerun()
    if not sets:
        st.caption(TR("training_logging.empty_sets"))


def _exercise_editor(connection, session):
    state_key, exercises = _editor_state(session)
    catalog = list_exercise_catalog(connection)
    by_id = {item["id"]: item for item in catalog}
    st.subheader(TR("training_logging.exercise_details"))
    preferences = st.columns(2)
    entry_mode = preferences[0].radio(
        TR("training_logging.entry_mode"), ENTRY_MODES,
        format_func=lambda value: TR(f"training_logging.{value}_mode"), horizontal=True,
        key=f"training_entry_mode_{session['id']}",
    )
    exertion_preference = preferences[1].radio(
        TR("training_logging.exertion_preference"), EXERTION_PREFERENCES,
        format_func=lambda value: TR(f"training_logging.use_{value}"), horizontal=True,
        key=f"training_exertion_preference_{session['id']}",
    )
    st.caption(TR("training_logging.hidden_fields_preserved"))
    if not exercises:
        st.info(TR("training_logging.empty_exercises"))

    for index, exercise in enumerate(list(exercises)):
        with st.container(border=True):
            st.markdown(f"#### {index + 1}. {TR('training_logging.exercise')}")
            choice_options = [CUSTOM_EXERCISE, *(item["id"] for item in catalog)]
            current_choice = exercise.get("exercise_catalog_id") or CUSTOM_EXERCISE
            first, second = st.columns(2)
            choice = first.selectbox(
                TR("training_logging.exercise"), choice_options,
                index=choice_options.index(current_choice) if current_choice in choice_options else 0,
                format_func=lambda value: TR("training_logging.custom_exercise")
                if value == CUSTOM_EXERCISE else _catalog_name(by_id[value]),
                key=f"exercise_choice_{exercise['uuid']}",
            )
            selected = by_id.get(choice)
            previous_catalog_id = exercise.get("_catalog_applied_id")
            if selected and exercise.get("_catalog_applied_id") != selected["id"]:
                exercise.update(apply_catalog_defaults(exercise, selected))
                st.session_state[f"exercise_edit_props_{exercise['uuid']}"] = False
            if not selected:
                if previous_catalog_id is not None:
                    st.session_state[f"exercise_edit_props_{exercise['uuid']}"] = True
                exercise["exercise_catalog_id"] = None
                exercise["_catalog_applied_id"] = None
                exercise["custom_exercise_name"] = first.text_input(
                    TR("training_logging.custom_exercise_name"),
                    value=exercise.get("custom_exercise_name") or "",
                    key=f"exercise_custom_{exercise['uuid']}",
                )
            old_mode = exercise.get("measurement_mode", "weight_reps")
            exercise["measurement_mode"] = second.selectbox(
                TR("training_logging.measurement_mode"), MEASUREMENT_MODES,
                index=MEASUREMENT_MODES.index(old_mode),
                format_func=lambda value: TR(f"training_logging.modes.{value}"),
                key=f"exercise_mode_{exercise['uuid']}",
                disabled=bool(selected),
            )
            if not selected:
                exercise["exercise_category"] = st.selectbox(
                    TR("training_logging.exercise_category"), EXERCISE_CATEGORIES,
                    index=EXERCISE_CATEGORIES.index(exercise.get("exercise_category", "other")),
                    format_func=lambda value: TR(f"training_logging.categories.{value}"),
                    key=f"exercise_category_{exercise['uuid']}",
                )
            if exercise["measurement_mode"] != old_mode:
                st.warning(TR("training_logging.incompatible_fields_preserved"))

            with st.expander(TR("training_logging.view_exercise_information")):
                edit_properties = st.checkbox(
                    TR("training_logging.edit_exercise_properties"),
                    value=not bool(selected), key=f"exercise_edit_props_{exercise['uuid']}",
                )
                if edit_properties:
                    fields = st.columns(4 if selected else 3)
                    offset = 1 if selected else 0
                    if selected:
                        exercise["exercise_category"] = fields[0].selectbox(
                            TR("training_logging.exercise_category"), EXERCISE_CATEGORIES,
                            index=EXERCISE_CATEGORIES.index(exercise.get("exercise_category", "other")),
                            format_func=lambda value: TR(f"training_logging.categories.{value}"),
                            key=f"exercise_category_edit_{exercise['uuid']}",
                        )
                    exercise["primary_muscle_group"] = fields[offset].text_input(
                        TR("training_logging.primary_muscle_group"),
                        value=exercise.get("primary_muscle_group") or "",
                        key=f"exercise_muscle_{exercise['uuid']}",
                    )
                    exercise["equipment"] = fields[offset + 1].text_input(
                        TR("training_logging.equipment"), value=exercise.get("equipment") or "",
                        key=f"exercise_equipment_{exercise['uuid']}",
                    )
                    exercise["is_unilateral"] = fields[offset + 2].checkbox(
                        TR("training_logging.laterality"), value=bool(exercise.get("is_unilateral")),
                        key=f"exercise_unilateral_{exercise['uuid']}",
                    )
                else:
                    info = st.columns(5)
                    values = (
                        ("catalog_category", TR(f"training_logging.categories.{exercise['exercise_category']}")),
                        ("catalog_muscle", exercise.get("primary_muscle_group") or TR("common.no_data")),
                        ("catalog_equipment", exercise.get("equipment") or TR("common.no_data")),
                        ("catalog_laterality", TR("common.yes") if exercise.get("is_unilateral") else TR("common.no")),
                        ("default_load_unit", TR(f"training_logging.load_units.{default_load_unit(exercise['measurement_mode'])}")),
                    )
                    for column, (label, value) in zip(info, values):
                        column.metric(TR(f"training_logging.{label}"), value)
                if not selected:
                    save_choice = st.radio(
                        TR("training_logging.custom_exercise_scope"), ("session_only", "save_to_exercise_library"),
                        format_func=lambda value: TR(f"training_logging.{value}"), horizontal=True,
                        key=f"exercise_scope_{exercise['uuid']}",
                    )
                    exercise["_save_to_library"] = save_choice == "save_to_exercise_library"
                if entry_mode == "simple":
                    exercise["notes"] = st.text_input(
                        TR("training_logging.exercise_notes"), value=exercise.get("notes") or "",
                        key=f"exercise_notes_{exercise['uuid']}",
                    )

            if entry_mode == "advanced" or exercise["exercise_category"] in {"dance", "technique", "rehabilitation"}:
                proficiency, notes = st.columns(2)
                exercise["skill_proficiency"] = proficiency.number_input(
                    TR("training_logging.movement_proficiency"), min_value=1.0, max_value=10.0,
                    value=exercise.get("skill_proficiency"), step=.5,
                    key=f"exercise_proficiency_{exercise['uuid']}",
                    help=TR("training_logging.proficiency_notice"),
                )
                exercise["notes"] = notes.text_input(
                    TR("training_logging.exercise_notes"), value=exercise.get("notes") or "",
                    key=f"exercise_notes_{exercise['uuid']}",
                )

            _set_editor(exercise, index, entry_mode, exertion_preference)
            with st.popover(TR("training_logging.more_actions")):
                if st.button(TR("training_logging.copy_exercise"), key=f"exercise_copy_{exercise['uuid']}"):
                    exercises.insert(index + 1, copy_exercise(exercise)); st.rerun()
                if st.button(TR("training_logging.move_up"), key=f"exercise_up_{exercise['uuid']}", disabled=index == 0):
                    exercises[index - 1], exercises[index] = exercises[index], exercises[index - 1]; st.rerun()
                if st.button(TR("training_logging.move_down"), key=f"exercise_down_{exercise['uuid']}", disabled=index == len(exercises) - 1):
                    exercises[index + 1], exercises[index] = exercises[index], exercises[index + 1]; st.rerun()
                confirmed = st.checkbox(
                    TR("training_logging.confirm_delete_exercise"),
                    key=f"exercise_delete_confirm_{exercise['uuid']}",
                )
                if st.button(
                    TR("training_logging.delete_exercise"), key=f"exercise_delete_{exercise['uuid']}",
                    disabled=not confirmed, type="primary",
                ):
                    exercises.pop(index); st.rerun()

    controls = st.columns((1.2, 1.2, 5))
    if controls[0].button(TR("training_logging.add_exercise"), key=f"exercise_add_{session['id']}"):
        exercises.append(_exercise_default()); st.rerun()
    with controls[1].popover(TR("training_logging.more_actions"), use_container_width=True):
        history = previous_exercises(connection, session["id"])
        if history:
            history_ids = [item["id"] for item in history]
            selected_history = st.selectbox(
                TR("training_logging.history_exercise"), history_ids,
                format_func=lambda value: next(
                    (by_id.get(item.get("exercise_catalog_id"), {}).get(
                        "display_name_zh" if LANGUAGE != "en" else "display_name_en"
                    ) or item.get("custom_exercise_name") or TR("common.no_data"))
                    for item in history if item["id"] == value
                ), key=f"history_exercise_{session['id']}",
            )
            if st.button(TR("training_logging.copy_history_exercise"), key=f"history_copy_{session['id']}"):
                source = next(item for item in history if item["id"] == selected_history)
                exercises.append(copy_exercise(source, reset_completed=True)); st.rerun()
        else:
            st.caption(TR("training_logging.no_history_exercise"))
    st.session_state[state_key] = exercises
    return exercises


def _summary(session, show_title=True):
    summary = session["summary"]
    if show_title:
        st.subheader(TR("training_logging.summary"))
    labels = (
        ("exercise_count", "exercise_count"), ("total_sets", "total_set_count"),
        ("working_sets", "working_set_count"), ("warmup_sets", "warmup_set_count"),
        ("total_reps", "total_reps"), ("volume_load", "strength_volume_load_kg"),
        ("average_rpe", "average_rpe"), ("max_rpe", "max_rpe"),
        ("total_rest", "total_rest_seconds"),
    )
    columns = st.columns(3)
    for index, (label, field) in enumerate(labels):
        value = summary.get(field)
        columns[index % 3].metric(
            TR(f"training_logging.{label}"),
            TR("training_logging.not_calculated") if value is None else format_number(value, LANGUAGE),
        )
    groups = summary.get("muscle_group_set_counts") or {}
    st.caption(
        f"{TR('training_logging.muscle_group_sets')}：" +
        (" · ".join(f"{name} {count}" for name, count in groups.items()) or TR("common.no_data"))
    )


def _details(connection, session, *, auto_expand=False):
    historical_data_title = ("历史" + TR("training_logging.title")) if LANGUAGE != "en" else TR("training_logging.title")
    historical_details_title = ("历史" + TR("training_logging.combined_details")) if LANGUAGE != "en" else TR("training_logging.combined_details")
    with st.expander(historical_data_title, expanded=auto_expand):
        _session_header(session)
        left, right = st.columns(2)
        resolved_sport = left.text_input(
            TR("training_logging.resolved_sport_type"),
            value=session.get("sport_display") or session.get("resolved_sport_type") or "",
            key=f"resolved_sport_{session['id']}",
        )
        if session["resolved_sport_type_source"] == "manual_override":
            left.caption(TR("training_logging.user_override"))
        notes = right.text_area(
            TR("training_logging.notes"), value=session.get("notes") or "",
            key=f"training_notes_{session['id']}",
        )
    with st.expander(historical_details_title, expanded=auto_expand):
        exercises = _exercise_editor(connection, session)
        save_draft, complete = st.columns(2)
        draft_clicked = save_draft.button(TR("training_logging.save_draft"), type="secondary")
        complete_clicked = complete.button(TR("training_logging.complete_log"), type="primary")
        if draft_clicked or complete_clicked:
            try:
                with connection:
                    for exercise in exercises:
                        if exercise.get("_save_to_library") and not exercise.get("exercise_catalog_id"):
                            catalog_id = create_custom_exercise_catalog(connection, exercise)
                            exercise["exercise_catalog_id"] = catalog_id
                            exercise["_catalog_applied_id"] = catalog_id
                    save_training_details(connection, session["id"], {
                        "resolved_sport_type": resolved_sport,
                        "status": "draft" if draft_clicked else "completed", "notes": notes,
                    }, exercises)
                st.session_state["training_save_notice"] = TR("training_logging.saved")
                st.rerun()
            except Exception as exc:
                st.error(TR("training_logging.save_failed", message=str(exc)))
        refreshed = get_training_session(connection, session["id"])
        _summary(refreshed)
        confirmed = st.checkbox(
            TR("training_logging.delete_confirm"), key=f"training_delete_confirm_{session['id']}"
        )
        if st.button(TR("training_logging.soft_delete"), disabled=not confirmed):
            soft_delete_training_session(connection, session["id"])
            st.session_state["training_session_selector"] = 0
            st.success(TR("training_logging.deleted")); st.rerun()


TRAINING_BASELINE_CSS = """
<style>
.drc-load-card{border:1px solid #d9dee7;border-radius:14px;padding:1rem 1.1rem;background:linear-gradient(145deg,#fff,#f7f9fc);min-height:11rem}
.drc-load-title{font-size:1.1rem;font-weight:700;color:#273142}.drc-load-value{font-size:2rem;font-weight:750;color:#222b3a;margin:.35rem 0}
.drc-load-muted{color:#788294;font-size:.88rem}.drc-load-status{font-weight:650;margin-top:.45rem}.drc-load-status.good{color:#1d7a46}.drc-load-status.info{color:#356da8}.drc-load-status.warn{color:#b66a19}.drc-load-status.neutral{color:#697386}
.drc-range{position:relative;height:12px;margin:1.2rem .2rem .4rem;border-radius:999px;background:linear-gradient(90deg,#edf0f4 0 20%,#dcefe2 20% 80%,#edf0f4 80%)}
.drc-range-bound{position:absolute;top:-.35rem;height:26px;border-left:2px solid #6f7885}.drc-range-marker{position:absolute;top:-.25rem;width:20px;height:20px;margin-left:-10px;border-radius:50%;background:#2e7d52;border:3px solid white;box-shadow:0 1px 5px #718096}
.drc-calendar{display:grid;grid-template-columns:repeat(14,minmax(28px,1fr));gap:.35rem}.drc-day{height:3.2rem;border:1px solid #d9dee7;border-radius:8px;text-align:center;padding:.3rem;font-size:.72rem;color:#687386}.drc-day.training{background:#cfe8d7;color:#1e6b3d}.drc-day.no_training_yet,.drc-day.confirmed_no_training{background:#f4f5f7}.drc-day.planned_rest{background:#e8eef8;color:#3c6090}.drc-day.missing,.drc-day.not_synced,.drc-day.sync_error{border-style:dashed;background:#fff8e9;color:#9a6b20}.drc-legend{display:flex;flex-wrap:wrap;gap:.8rem;margin-top:.7rem;color:#697386;font-size:.82rem}.drc-legend span:before{content:'';display:inline-block;width:.7rem;height:.7rem;border-radius:3px;background:#cfe8d7;margin-right:.3rem}.drc-legend .missing:before{background:#fff8e9;border:1px dashed #9a6b20}.drc-legend .rest:before{background:#e8eef8}.drc-legend .none:before{background:#f4f5f7}
</style>
"""


def _training_status_label(status):
    return {
        "training_present": "status_training", "no_training_yet": "status_yet",
        "planned_rest": "status_rest", "confirmed_no_training": "status_confirmed",
        "not_synced": "status_waiting", "syncing": "status_syncing", "sync_error": "status_error",
        "missing": "status_missing", "partial": "status_partial", "invalid": "status_invalid",
    }.get(status, "status_waiting")


def _training_value(value, suffix=""):
    return TR("common.no_data") if value is None else f"{format_number(value, LANGUAGE)}{suffix}"


def _training_status_class(status):
    if status == "training_present": return "good"
    if status in {"sync_error", "invalid", "missing"}: return "warn"
    if status in {"partial", "not_synced", "syncing"}: return "info"
    return "neutral"


def _range_bar(item):
    lower, upper, current = item.get("lower_bound"), item.get("upper_bound"), item.get("current_value")
    if current is None or lower is None or upper is None:
        return f"<div class='drc-load-muted'>{escape(TR('training_baseline.range_pending'))}</div>"
    spread = max(float(upper) - float(lower), 1.0)
    low = max(0.0, float(lower) - spread)
    high = max(float(upper) + spread, low + 1.0)
    marker = max(0.0, min(100.0, (float(current) - low) / (high - low) * 100))
    lower_pos = (float(lower) - low) / (high - low) * 100
    upper_pos = (float(upper) - low) / (high - low) * 100
    return (
        f"<div class='drc-range'><span class='drc-range-bound' style='left:{lower_pos:.1f}%'></span>"
        f"<span class='drc-range-bound' style='left:{upper_pos:.1f}%'></span>"
        f"<span class='drc-range-marker' style='left:{marker:.1f}%'></span></div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.low_load'))}　　{escape(TR('training_baseline.typical_range_label'))}　　{escape(TR('training_baseline.high_load'))}</div>"
    )


def _training_metric_card(title, item, suffix=""):
    maturity = item.get("maturity", {})
    comparison = item.get("comparison")
    status = TR({
        "markedly_low": "training_baseline.status_markedly_low", "slightly_low": "training_baseline.status_slightly_low",
        "near_typical": "training_baseline.status_near", "slightly_high": "training_baseline.status_slightly_high",
        "markedly_high": "training_baseline.status_markedly_high", "data_accumulating": "training_baseline.status_accumulating",
    }.get(comparison, "training_baseline.status_accumulating"))
    status_class = "good" if comparison == "near_typical" else "warn" if "markedly" in str(comparison) else "info"
    range_text = (
        f"{_training_value(item.get('lower_bound'))}–{_training_value(item.get('upper_bound'))}{suffix}"
        if item.get("lower_bound") is not None else TR("training_baseline.range_pending")
    )
    pct = item.get("percent_difference")
    pct_text = "—" if pct is None else f"{'↑' if pct > 0 else '↓' if pct < 0 else '→'} {abs(pct):.1f}%"
    window_label = "28天基线" if LANGUAGE != "en" else "28-day baseline"
    card_html = (
        f"<div class='drc-load-card'><div class='drc-load-title'>{escape(title)} · {escape(window_label)}</div>"
        f"<div class='drc-load-value'>{escape(_training_value(item.get('current_value'), suffix))}</div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.baseline'))}：{escape(_training_value(item.get('center'), suffix))}　{escape(TR('training_baseline.typical_range'))}：{escape(range_text)}</div>"
        f"<div class='drc-load-status {status_class}'>{escape(status)}　{escape(pct_text)}</div>"
        f"<div class='drc-load-muted'>{escape(TR('training_baseline.baseline_phase'))}：{escape(maturity.get('status','collecting'))} · {escape(TR('training_baseline.valid_days'))}：{maturity.get('valid_days',0)}</div>"
        f"{_range_bar(item)}</div>"
    )
    st.markdown(card_html, unsafe_allow_html=True)


def _render_training_baseline():
    view = get_training_baseline_view()
    baseline_title = TR("training_baseline.title")
    if LANGUAGE != "en":
        baseline_title = "个人训练基线"
    st.subheader(baseline_title)
    st.markdown(TRAINING_BASELINE_CSS, unsafe_allow_html=True)
    left, right = st.columns(2)
    with left: _training_metric_card(TR("training_baseline.training_duration"), view["duration_baseline"], " 分钟")
    with right: _training_metric_card(TR("training_baseline.training_calories"), view["calorie_baseline"], " kcal")
    st.caption(TR("training_baseline.calorie_note"))
    with st.container(border=True):
        st.markdown(f"### {TR('training_baseline.recent_week')}")
        weekly = view["weekly_load"]
        cols = st.columns(5)
        for column, (label, value) in zip(cols, ((TR("training_baseline.training_count"), weekly["session_count"]), (TR("training_baseline.cumulative_duration"), _training_value(weekly["duration_minutes"], " 分钟")), (TR("training_baseline.calories"), _training_value(weekly["calories_kcal"], " kcal")), (TR("training_baseline.valid_training_days"), weekly["valid_training_days"]), (TR("training_baseline.data_completeness"), f"{weekly['data_completeness']}%"))):
            column.metric(label, value)
        typical = weekly.get("typical_calories_kcal")
        if typical is not None and weekly.get("calories_kcal") is not None:
            st.caption(TR("training_baseline.relative_week", percent=f"{weekly['calories_kcal'] / typical * 100:.1f}", value=format_number(typical, LANGUAGE)))


def main():
    icon, title = st.columns([1, 8], vertical_alignment="center")
    with icon:
        path = brand_icon_path()
        if path: st.image(str(path), width=88)
    with title:
        intro = TR("domain.exercise.intro")
        intro = intro.replace("确定性建议", "训练建议").replace("deterministic guidance", "training guidance")
        st.title(TR("domain.exercise.title")); st.caption(intro)
        training_notice = st.session_state.pop("training_save_notice", None)

    connection = connect(migrate=False)
    try:
        ensure_polar_session_index(connection)
        sessions = list_training_sessions(connection, limit=100)
        _today_polar_data(sessions)
        _today_training_details(connection, sessions)
        _history(sessions)
        selected_history_id = st.session_state.get("training_history_selected")
        if selected_history_id is None and sessions:
            selected_history_id = sessions[0]["id"]
        if selected_history_id:
            selected_session = get_training_session(connection, selected_history_id)
            if selected_session:
                focus_nonce = st.session_state.get("training_details_focus_nonce", 0)
                last_focus_nonce = st.session_state.get("training_details_last_scrolled_nonce", 0)
                should_focus = focus_nonce > last_focus_nonce
                # Keep both historical detail expanders collapsed by default;
                # only the click that created this new focus request opens them.
                auto_expand = should_focus
                focus_target_id = f"training-situation-details-{focus_nonce}"
                focus_anchor = f'<div id="{focus_target_id}"></div>'
                st.markdown(focus_anchor, unsafe_allow_html=True)
                if should_focus:
                    render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)
                    st.session_state["training_details_last_scrolled_nonce"] = focus_nonce
                history_training_title = ("历史" + TR("domain.exercise.title")) if LANGUAGE != "en" else TR("domain.exercise.title")
                st.subheader(history_training_title)
                _details(connection, selected_session, auto_expand=auto_expand)
                if training_notice:
                    st.success(training_notice)
        elif training_notice:
            st.success(training_notice)
    finally:
        connection.close()

    _render_training_baseline()

    st.subheader("训练建议" if LANGUAGE != "en" else "Training Guidance")
    coach = get_latest_local_coach()
    if not coach: st.info(TR("local_coach.missing"))
    else:
        left, right = st.columns(2)
        with left:
            st.markdown(f"**{TR('local_coach.morning_strength')}**")
            st.write(TR(f"local_coach.training_advice.{coach['morning_training']['status']}"))
        with right:
            st.markdown(f"**{TR('local_coach.evening_hiphop')}**")
            st.write(TR(f"local_coach.training_advice.{coach['evening_training']['status']}"))
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
