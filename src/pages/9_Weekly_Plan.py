"""Weekly user-intent plan, kept separate from daily execution records."""

from datetime import date, datetime, time, timedelta
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.demo_sandbox import configure_demo_runtime
from src.i18n import get_translator
from src.i18n.ui import current_language, render_sidebar
from src.user_plan import (
    PLAN_CATEGORIES,
    WEEKDAY_KEYS,
    compare_week_plan,
    copy_plan_items,
    create_plan_item,
    create_week_plan,
    delete_plan_item,
    event_color_key,
    get_week_plan,
    group_plan_items_for_display,
    list_plan_items,
    merge_plan_slots,
    update_plan_item,
    week_start,
)
from src.ui_scroll import render_interaction_focus


configure_demo_runtime(st)
LANGUAGE = current_language(st.session_state)
TR = get_translator(LANGUAGE)
st.set_page_config(
    page_title=browser_page_title(TR("weekly_plan.title")),
    page_icon=load_page_icon(),
    layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "weekly_plan")

WEEKDAY_LABEL_KEYS = tuple(f"weekly_plan.weekdays.{key}" for key in WEEKDAY_KEYS)
WEEKLY_PLAN_GRID_MARKER = '<span class="weekly-plan-grid-marker"></span>'
WEEKLY_PLAN_ENTRY_MARKER_PREFIX = '<span class="weekly-plan-entry-marker weekly-plan-entry-marker-'
WEEKLY_PLAN_ENTRY_MARKER_SUFFIX = '"></span>'
WEEKLY_PLAN_ADD_ANCHOR = '<div id="weekly-plan-add-item-anchor"></div>'
WEEKLY_PLAN_EDIT_ANCHOR = '<div id="weekly-plan-edit-item-anchor"></div>'
WEEKLY_PLAN_ADD_MARKER = '<span class="weekly-plan-add-marker"></span>'
WEEKLY_PLAN_EDIT_MARKER = '<span class="weekly-plan-edit-marker"></span>'
DEFAULT_PLAN_SLOTS = (
    ("06:00", "08:00"),
    ("08:00", "10:00"),
    ("10:00", "12:00"),
    ("12:00", "14:00"),
    ("14:00", "16:00"),
    ("16:00", "18:00"),
    ("18:00", "20:00"),
    ("20:00", "22:00"),
    ("22:00", "23:00"),
)

PLAN_CSS = """
<style>
/* Day palette: quiet, low-saturation category cards with dark readable type. */
:root{
--weekly-plan-grid-strong:#9aa3af;
--weekly-plan-grid:#aeb7c2;
--weekly-plan-meta:#3d4754;
--weekly-plan-empty:#748091;
--weekly-plan-card-text:#1d1d1f;
--weekly-plan-card-hover:rgba(29,29,31,.16);
--weekly-plan-work:#fdecec;
--weekly-plan-study:#eaf2fd;
--weekly-plan-training:#e8f6ed;
--weekly-plan-meal:#fff6de;
--weekly-plan-recovery:#eaf7f8;
--weekly-plan-personal:#f8ecf5;
--weekly-plan-other:#f1f2f4;
--weekly-plan-event-blue:#eaf2fd;
--weekly-plan-event-green:#e8f6ed;
--weekly-plan-event-amber:#fff3dc;
--weekly-plan-event-rose:#fbeaec;
--weekly-plan-event-purple:#f3ebf8;
--weekly-plan-event-teal:#e5f4f3;
--weekly-plan-event-slate:#eef1f5;
--weekly-plan-event-coral:#fcece6;
}
/* Night palette: preserve category meaning without placing white text on
   luminous pastel cards. Each surface is deliberately darkened first. */
@media (prefers-color-scheme: dark){
:root{
--weekly-plan-grid-strong:#747f8d;
--weekly-plan-grid:#56606d;
--weekly-plan-meta:#dde3eb;
--weekly-plan-empty:#9ba7b6;
--weekly-plan-card-text:#f5f7fa;
--weekly-plan-card-hover:rgba(245,247,250,.28);
--weekly-plan-work:#572f3b;
--weekly-plan-study:#213d5e;
--weekly-plan-training:#1d4938;
--weekly-plan-meal:#4d3c18;
--weekly-plan-recovery:#19464a;
--weekly-plan-personal:#482b42;
--weekly-plan-other:#363a42;
--weekly-plan-event-blue:#213d5e;
--weekly-plan-event-green:#1d4938;
--weekly-plan-event-amber:#4d3c18;
--weekly-plan-event-rose:#572f3b;
--weekly-plan-event-purple:#482b42;
--weekly-plan-event-teal:#19464a;
--weekly-plan-event-slate:#363a42;
--weekly-plan-event-coral:#5a352c;
}
}
.weekly-plan-table{border:1px solid rgba(117,130,148,.24);border-radius:14px;overflow:hidden}
.weekly-plan-table-title{display:flex;align-items:center;justify-content:center;min-height:3.35rem;text-align:center;font-size:1.12rem;font-weight:700;padding:.35rem .75rem;border-bottom:0}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker){border:1.5px solid var(--weekly-plan-grid-strong);border-radius:12px;overflow:hidden;gap:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) > div[data-testid="stElementContainer"]:has(.weekly-plan-table-title){padding:0!important;margin:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stHorizontalBlock"]{gap:0!important;margin:0!important;border-top:1px solid var(--weekly-plan-grid)}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]{min-height:4.1rem;padding:0!important;border-right:1px solid var(--weekly-plan-grid);display:flex;align-items:center;justify-content:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]>div{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) [data-testid="stMarkdownContainer"]{height:100%;margin:0!important;display:flex;align-items:center;justify-content:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) .weekly-plan-header-cell,
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) .weekly-plan-time{height:100%;display:flex;align-items:center;justify-content:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:last-child{border-right:0}
.weekly-plan-header-cell{width:100%;padding:.2rem;text-align:center;font-weight:700}
.weekly-plan-time{width:100%;color:var(--weekly-plan-meta);font-size:.78rem;white-space:nowrap;text-align:center}
.weekly-plan-entry{border-radius:9px;padding:.35rem .25rem;margin:-.05rem 0;font-size:.78rem;line-height:1.35;text-align:center}
.weekly-plan-entry small{display:block;opacity:.72;margin-top:.15rem}
.weekly-plan-legend{display:flex;gap:.55rem;flex-wrap:wrap;margin:.6rem 0}
.weekly-plan-legend span{font-size:.76rem;padding:.22rem .55rem;border-radius:999px;color:var(--weekly-plan-card-text)}
.weekly-plan-legend-work{background:var(--weekly-plan-work)}
.weekly-plan-legend-study{background:var(--weekly-plan-study)}
.weekly-plan-legend-training{background:var(--weekly-plan-training)}
.weekly-plan-legend-meal{background:var(--weekly-plan-meal)}
.weekly-plan-legend-recovery{background:var(--weekly-plan-recovery)}
.weekly-plan-legend-personal{background:var(--weekly-plan-personal)}
.weekly-plan-legend-other{background:var(--weekly-plan-other)}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) [data-testid="stButton"] button{min-height:3.5rem;border-radius:0;border:0;background:transparent;color:var(--weekly-plan-empty);font-size:.9rem}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) [data-testid="stButton"] button:hover{background:rgba(117,130,148,.10);color:var(--text-color)}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stElementContainer"]:has(.weekly-plan-entry-marker){display:none!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker) [data-testid="stButton"] button{min-height:3.5rem;border:0;border-radius:9px;background:var(--weekly-plan-entry-color,#dbeafe);color:var(--weekly-plan-card-text);-webkit-text-fill-color:var(--weekly-plan-card-text);font-size:.78rem;line-height:1.35;white-space:pre-wrap;padding:.35rem .25rem;transform:scale(.82);transform-origin:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker) [data-testid="stButton"] button:hover{filter:brightness(.97);box-shadow:0 0 0 2px var(--weekly-plan-card-hover)}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-blue) [data-testid="stButton"] button{background:var(--weekly-plan-event-blue)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-green) [data-testid="stButton"] button{background:var(--weekly-plan-event-green)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-amber) [data-testid="stButton"] button{background:var(--weekly-plan-event-amber)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-rose) [data-testid="stButton"] button{background:var(--weekly-plan-event-rose)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-purple) [data-testid="stButton"] button{background:var(--weekly-plan-event-purple)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-teal) [data-testid="stButton"] button{background:var(--weekly-plan-event-teal)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-slate) [data-testid="stButton"] button{background:var(--weekly-plan-event-slate)!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .weekly-plan-grid-marker) div[data-testid="stColumn"]:has(.weekly-plan-entry-marker-event-coral) [data-testid="stButton"] button{background:var(--weekly-plan-event-coral)!important}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-testid="stElementContainer"]:has(.weekly-plan-add-marker),
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-testid="stElementContainer"]:has(.weekly-plan-edit-marker){display:none!important}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) label,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) label{text-align:center;justify-content:center;width:100%}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-baseweb="input"] input,
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-baseweb="textarea"] textarea,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-baseweb="input"] input,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-baseweb="textarea"] textarea{text-align:center!important}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-baseweb="select"]>div,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-baseweb="select"]>div{position:relative}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-baseweb="select"]>div>div:first-child,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-baseweb="select"]>div>div:first-child{position:absolute!important;inset:0;display:flex!important;align-items:center;justify-content:center!important;text-align:center!important}
div[data-testid="stExpander"]:has(.weekly-plan-add-marker) [data-baseweb="select"]>div>div:first-child *,
div[data-testid="stExpander"]:has(.weekly-plan-edit-marker) [data-baseweb="select"]>div>div:first-child *{text-align:center!important}
@media(max-width:760px){.weekly-plan-table{overflow-x:auto}.weekly-plan-header,.weekly-plan-row{min-width:760px}.weekly-plan-entry{font-size:.7rem}}
</style>
"""
st.markdown(PLAN_CSS, unsafe_allow_html=True)


def _timezone_name() -> str:
    tzinfo = datetime.now().astimezone().tzinfo
    return getattr(tzinfo, "key", None) or "UTC"


def _category_label(category: str) -> str:
    return TR(f"weekly_plan.categories.{category}")


def _weekday_label(index: int) -> str:
    return TR(WEEKDAY_LABEL_KEYS[index])


def _status_label(status: str) -> str:
    return TR(f"weekly_plan.status.{status}")


def _time_text(value: time | str) -> str:
    """Return the editable HH:MM representation used by the plan form."""
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return str(value).strip()[:5]


def _parse_time_text(value: str, field: str) -> time:
    """Parse a manually entered HH:MM value before it reaches the model."""
    try:
        return time.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must use HH:MM") from exc


def _render_matrix(items: list[dict]) -> None:
    # Keep the full weekly canvas visible even before the user has filled it.
    # User-defined intervals are added without losing the reference rows.
    display_items = group_plan_items_for_display(items)
    slots = merge_plan_slots(DEFAULT_PLAN_SLOTS, display_items)

    with st.container():
        st.markdown(WEEKLY_PLAN_GRID_MARKER, unsafe_allow_html=True)
        st.markdown(
            f"<div class='weekly-plan-table-title'>{escape(TR('weekly_plan.title'))}</div>",
            unsafe_allow_html=True,
        )
        header = st.columns([1.05] + [1] * 7)
        header[0].markdown(
            f"<div class='weekly-plan-header-cell'>{escape(TR('weekly_plan.time'))}</div>",
            unsafe_allow_html=True,
        )
        for index, column in enumerate(header[1:]):
            column.markdown(
                f"<div class='weekly-plan-header-cell'>{escape(_weekday_label(index))}</div>",
                unsafe_allow_html=True,
            )

        for start, end in slots:
            row = st.columns([1.05] + [1] * 7)
            row[0].markdown(
                f"<div class='weekly-plan-time'>{escape(start)}–{escape(end)}</div>",
                unsafe_allow_html=True,
            )
            for weekday, column in enumerate(row[1:]):
                cells = [
                    item for item in display_items
                    if item["weekday"] == weekday
                    and item["start_time"] == start
                    and item["end_time"] == end
                ]
                if not cells:
                    if column.button(
                        TR("weekly_plan.empty_slot"),
                        key=f"weekly_plan_slot_{weekday}_{start}_{end}",
                        use_container_width=True,
                    ):
                        st.session_state["weekly_plan_cell_prefill"] = {
                            "weekday": weekday,
                            "start_time": time.fromisoformat(start),
                            "end_time": time.fromisoformat(end),
                        }
                        st.session_state["weekly_plan_add_focus_nonce"] = (
                            st.session_state.get("weekly_plan_add_focus_nonce", 0) + 1
                        )
                        st.session_state["weekly_plan_add_form_expanded"] = True
                        st.rerun()
                    continue
                for item in cells:
                    color_key = event_color_key(item["title"])
                    column.markdown(
                        f"{WEEKLY_PLAN_ENTRY_MARKER_PREFIX}event-{color_key}{WEEKLY_PLAN_ENTRY_MARKER_SUFFIX}",
                        unsafe_allow_html=True,
                    )
                    label = "\n".join(
                        part for part in [item["title"], *item.get("detail_titles", [])]
                        if part
                    )
                    if column.button(
                        label,
                        key=f"weekly_plan_item_{item['item_id']}",
                        use_container_width=True,
                    ):
                        st.session_state["weekly_plan_selected_item_id"] = item["item_id"]
                        st.session_state["weekly_plan_edit_focus_nonce"] = (
                            st.session_state.get("weekly_plan_edit_focus_nonce", 0) + 1
                        )
                        st.rerun()

    legend = "".join(
        f"<span class='weekly-plan-legend-{category}'>{escape(_category_label(category))}</span>"
        for category in PLAN_CATEGORIES
    )
    st.markdown(f"<div class='weekly-plan-legend'>{legend}</div>", unsafe_allow_html=True)


def _render_add_form(plan: dict, items: list[dict]) -> None:
    expanded = st.session_state.pop("weekly_plan_add_form_expanded", False)
    prefill = st.session_state.pop("weekly_plan_cell_prefill", None)
    if prefill:
        st.session_state["weekly_plan_form_weekday"] = prefill["weekday"]
        st.session_state["weekly_plan_form_start"] = _time_text(prefill["start_time"])
        st.session_state["weekly_plan_form_end"] = _time_text(prefill["end_time"])
    st.session_state.setdefault("weekly_plan_form_weekday", 0)
    st.session_state.setdefault("weekly_plan_form_category", PLAN_CATEGORIES[0])
    st.session_state.setdefault("weekly_plan_form_start", "09:00")
    st.session_state.setdefault("weekly_plan_form_end", "11:00")
    # Keep the high-frequency input surface open after each successful add.
    with st.expander(TR("weekly_plan.add_item"), expanded=expanded):
        st.markdown(WEEKLY_PLAN_ADD_MARKER, unsafe_allow_html=True)
        st.caption(TR("weekly_plan.slot_hint"))
        with st.form("weekly_plan_add_item"):
            first_row = st.columns(4)
            weekday = first_row[0].selectbox(
                TR("weekly_plan.weekday"), range(7),
                format_func=_weekday_label,
                key="weekly_plan_form_weekday",
            )
            category = first_row[1].selectbox(
                TR("weekly_plan.category"), PLAN_CATEGORIES,
                format_func=_category_label,
                key="weekly_plan_form_category",
            )
            start_text = first_row[2].text_input(
                TR("weekly_plan.start"), key="weekly_plan_form_start",
                max_chars=5, placeholder="HH:MM",
            )
            end_text = first_row[3].text_input(
                TR("weekly_plan.end"), key="weekly_plan_form_end",
                max_chars=5, placeholder="HH:MM",
            )
            title = st.text_input(TR("weekly_plan.item_title"))
            notes = st.text_input(TR("weekly_plan.notes"))
            if st.form_submit_button(TR("weekly_plan.add"), type="primary"):
                try:
                    start_time = _parse_time_text(start_text, "start_time")
                    end_time = _parse_time_text(end_text, "end_time")
                    create_plan_item(
                        plan["plan_id"], weekday, title, start_time, end_time, category,
                        notes=notes,
                    )
                except ValueError as exc:
                    st.error(TR("weekly_plan.invalid_item") + f"：{exc}")
                else:
                    st.session_state["weekly_plan_notice"] = "weekly_plan.item_added"
                    st.session_state["weekly_plan_add_form_expanded"] = True
                    st.rerun()


def _render_edit_form(plan: dict, items: list[dict], *, expanded: bool = False) -> None:
    selected_id = st.session_state.get("weekly_plan_selected_item_id")
    item = next(
        (candidate for candidate in items if candidate["item_id"] == selected_id),
        None,
    ) if selected_id else None
    if selected_id and item is None:
        st.session_state.pop("weekly_plan_selected_item_id", None)

    with st.expander(TR("weekly_plan.edit_item"), expanded=expanded and item is not None):
        st.markdown(WEEKLY_PLAN_EDIT_MARKER, unsafe_allow_html=True)
        if item is None:
            st.info(TR("weekly_plan.select_item_to_edit"))
            return

        prefix = f"weekly_plan_edit_{selected_id}"
        st.session_state.setdefault(f"{prefix}_weekday", item["weekday"])
        st.session_state.setdefault(f"{prefix}_category", item["category"])
        st.session_state.setdefault(f"{prefix}_start", _time_text(item["start_time"]))
        st.session_state.setdefault(f"{prefix}_end", _time_text(item["end_time"]))
        st.session_state.setdefault(f"{prefix}_title", item["title"])
        st.session_state.setdefault(f"{prefix}_notes", item.get("notes") or "")

        with st.form(f"{prefix}_form"):
            first_row = st.columns(4)
            weekday = first_row[0].selectbox(
                TR("weekly_plan.weekday"), range(7), format_func=_weekday_label,
                key=f"{prefix}_weekday",
            )
            category = first_row[1].selectbox(
                TR("weekly_plan.category"), PLAN_CATEGORIES, format_func=_category_label,
                key=f"{prefix}_category",
            )
            start_text = first_row[2].text_input(
                TR("weekly_plan.start"), key=f"{prefix}_start",
                max_chars=5, placeholder="HH:MM",
            )
            end_text = first_row[3].text_input(
                TR("weekly_plan.end"), key=f"{prefix}_end",
                max_chars=5, placeholder="HH:MM",
            )
            title = st.text_input(TR("weekly_plan.item_title"), key=f"{prefix}_title")
            notes = st.text_input(TR("weekly_plan.notes"), key=f"{prefix}_notes")
            save, delete = st.columns(2)
            save_clicked = save.form_submit_button(TR("weekly_plan.save_changes"), type="primary")
            delete_clicked = delete.form_submit_button(TR("weekly_plan.delete"))
            if delete_clicked:
                delete_plan_item(selected_id)
                st.session_state.pop("weekly_plan_selected_item_id", None)
                st.session_state["weekly_plan_notice"] = "weekly_plan.item_deleted"
                st.rerun()
            if save_clicked:
                try:
                    start_time = _parse_time_text(start_text, "start_time")
                    end_time = _parse_time_text(end_text, "end_time")
                    update_plan_item(
                        selected_id, weekday, title, start_time, end_time, category,
                        notes=notes,
                    )
                except ValueError as exc:
                    st.error(TR("weekly_plan.invalid_item") + f"：{exc}")
                else:
                    st.session_state.pop("weekly_plan_selected_item_id", None)
                    st.session_state["weekly_plan_notice"] = "weekly_plan.item_updated"
                    st.rerun()


def _render_copy_previous_week(plan: dict, monday: date) -> None:
    previous_plan = get_week_plan(monday - timedelta(days=7))
    copy_clicked = st.button(
        TR("weekly_plan.copy_previous"),
        disabled=previous_plan is None,
        key="weekly_plan_copy_previous",
    )
    if previous_plan is None:
        st.caption(TR("weekly_plan.no_previous_plan"))
        return
    if copy_clicked:
        try:
            copied = copy_plan_items(previous_plan["plan_id"], plan["plan_id"])
        except ValueError as exc:
            st.error(TR("weekly_plan.copy_error") + f"：{exc}")
        else:
            st.session_state["weekly_plan_notice"] = (
                "weekly_plan.copy_success", copied,
            )
            st.rerun()


def _render_comparison(plan: dict) -> None:
    rows = compare_week_plan(plan["plan_id"])
    completed = sum(row["actual_status"] == "completed" for row in rows)
    recorded = sum(row["actual_status"] != "unrecorded" for row in rows)
    st.subheader(TR("weekly_plan.comparison"))
    st.caption(TR("weekly_plan.comparison_hint"))
    metrics = st.columns(3)
    metrics[0].metric(TR("weekly_plan.planned_count"), len(rows))
    metrics[1].metric(TR("weekly_plan.recorded_count"), recorded)
    metrics[2].metric(TR("weekly_plan.completed_count"), completed)
    if not rows:
        st.info(TR("weekly_plan.empty_comparison"))
        return
    display_rows = [
        {
            TR("weekly_plan.date"): row["plan_date"],
            TR("weekly_plan.weekday"): _weekday_label(row["weekday"]),
            TR("weekly_plan.planned"): f"{row['start_time']}–{row['end_time']} · {row['title']}",
            TR("weekly_plan.actual"): row["actual_title"] or TR("weekly_plan.no_actual"),
            TR("weekly_plan.status_label"): _status_label(row["actual_status"]),
        }
        for row in rows
    ]
    st.dataframe(display_rows, hide_index=True, use_container_width=True)


st.title(TR("weekly_plan.title"))
st.caption(TR("weekly_plan.intro"))

selected_date = st.date_input(
    TR("weekly_plan.week"),
    value=st.session_state.get("weekly_plan_selected_date", date.today()),
    key="weekly_plan_selected_date",
)
monday = week_start(selected_date)
st.caption(TR("weekly_plan.week_range", start=monday.isoformat(), end=(monday + timedelta(days=6)).isoformat()))

plan = get_week_plan(monday)
if plan is None:
    title = st.text_input(TR("weekly_plan.plan_title"), value=TR("weekly_plan.default_title"))
    if st.button(TR("weekly_plan.create"), type="primary"):
        try:
            create_week_plan(monday, title, _timezone_name())
        except ValueError as exc:
            st.error(TR("weekly_plan.create_error") + f"：{exc}")
        else:
            st.rerun()
    st.info(TR("weekly_plan.not_created"))
else:
    notice = st.session_state.pop("weekly_plan_notice", None)
    if notice:
        if isinstance(notice, tuple):
            st.success(TR(notice[0], count=notice[1]))
        else:
            st.success(TR(notice))
    items = list_plan_items(plan["plan_id"])
    _render_matrix(items)
    focus_nonce = st.session_state.pop("weekly_plan_add_focus_nonce", None)
    st.markdown(WEEKLY_PLAN_ADD_ANCHOR, unsafe_allow_html=True)
    if focus_nonce is not None:
        render_interaction_focus(
            components,
            target_id="weekly-plan-add-item-anchor",
            nonce=focus_nonce,
        )
    _render_copy_previous_week(plan, monday)
    edit_focus_nonce = st.session_state.pop("weekly_plan_edit_focus_nonce", None)
    st.markdown(WEEKLY_PLAN_EDIT_ANCHOR, unsafe_allow_html=True)
    if edit_focus_nonce is not None:
        render_interaction_focus(
            components,
            target_id="weekly-plan-edit-item-anchor",
            nonce=edit_focus_nonce,
        )
    _render_edit_form(plan, items, expanded=edit_focus_nonce is not None)
    _render_add_form(plan, items)
    _render_comparison(plan)
