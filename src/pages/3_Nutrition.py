"""Simple food-level nutrition logging with structured local services."""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date, datetime, time, timedelta
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_day_metrics
from src.db import connect
from src.demo_sandbox import configure_demo_runtime
from src.exercise_format import time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.nutrition_logging import (
    FOOD_COUNT_UNITS, FOOD_UNITS, MEAL_TYPES,
    SUPPLEMENT_UNITS, allowed_food_units,
    copy_meal_record,
    create_meal_record, favorite_foods, find_meal_id, find_previous_meal_id,
    find_yesterday_meal_id, food_catalog_by_id, food_unit_label_key,
    get_meal_record, list_food_catalog, list_meal_records,
    meal_time_warning, predict_meal_time, recent_foods, save_meal_record,
    summarize_supplements,
    unit_label_key,
)
from src.nutrition_logging.nutrition_baseline import calculate_personal_nutrition_baseline
from src.nutrition_logging.feedback import (
    METRICS, NutritionFeedbackService, load_nutrition_target_snapshot,
    load_nutrition_targets, recommended_nutrition_targets, save_nutrition_target_snapshot,
    save_nutrition_targets, summarize_draft_food_items,
)
from src.supplements import calculate_intake_ingredients, favorite_products, list_products, recent_products
from src.ui_tables import centered_dataframe
from src.ui_controls import render_manual_input_styles
from src.ui_scroll import render_interaction_focus


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.nutrition.title")),
    page_icon=load_page_icon(), layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "nutrition")
render_manual_input_styles(st)


def _nutrition_number(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _ui(zh, en):
    return zh if LANGUAGE != "en" else en


def _render_html(markup, container=None):
    target = st if container is None else container
    target.markdown(markup, unsafe_allow_html=True)


FEEDBACK_METRIC_LABELS = {
    "calories_kcal": ("热量", "Calories", "kcal"),
    "protein_g": ("蛋白质", "Protein", "g"),
    "carbohydrate_g": ("碳水化合物", "Carbohydrate", "g"),
    "fat_g": ("脂肪", "Fat", "g"),
    "fiber_g": ("膳食纤维", "Fibre", "g"),
    "water_ml": ("水分", "Water", "ml"),
}


def _feedback_metric_label(metric):
    zh, en, _ = FEEDBACK_METRIC_LABELS[metric]
    return _ui(zh, en)


def _nutrition_target_metric_label(metric):
    """Give goal inputs an unambiguous unit without changing card titles."""
    unit = FEEDBACK_METRIC_LABELS[metric][2]
    display_unit = "mL" if unit == "ml" else unit
    return f"{_feedback_metric_label(metric)}（{display_unit}）" if LANGUAGE != "en" else f"{_feedback_metric_label(metric)} ({display_unit})"


def _feedback_value(metric, value):
    if value is None:
        return _ui("数据不足", "Insufficient data")
    if metric == "calories_kcal":
        return f"{round(float(value))} kcal"
    if metric == "water_ml":
        amount = float(value)
        return f"{amount / 1000:.1f} L" if amount >= 1000 else f"{amount:.0f} mL"
    return f"{float(value):.1f} g"


def _render_nutrition_targets(connection):
    """Render the first, compact target editor used by the category cards."""
    st.subheader(_ui("1. 营养目标", "1. Nutrition Targets"))
    st.caption(_ui(
        "设置每日目标范围；只填写最低目标也可以。留空表示尚未设置。",
        "Set daily target ranges. A minimum alone is supported; leave a metric blank to keep it unset.",
    ))
    saved_targets = load_nutrition_targets(connection)
    action_left, action_right, _ = st.columns((1.25, 1.6, 4.15))
    if action_left.button(_ui("复制昨天营养目标", "Copy Yesterday's Targets")):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        yesterday_targets = load_nutrition_target_snapshot(connection, yesterday)
        if not yesterday_targets:
            st.info(_ui("昨天没有已保存的营养目标。", "No saved nutrition targets were found for yesterday."))
        else:
            for metric, (lower, upper) in yesterday_targets.items():
                st.session_state[f"nutrition_target_min_{metric}"] = lower
                st.session_state[f"nutrition_target_max_{metric}"] = upper
            st.rerun()
    if action_right.button(_ui("应用个人推荐目标", "Apply Personal Recommendations")):
        recommendations = recommended_nutrition_targets(connection)
        if not recommendations:
            st.info(_ui("请先在个人信息中填写体重；完整填写身高、生日和体重目标后可获得热量推荐。", "Add a body weight in Personal Information first; height, birthday, and a weight goal enable a calorie recommendation."))
        else:
            for metric, values in recommendations.items():
                lower, upper = values
                if lower is not None:
                    st.session_state[f"nutrition_target_min_{metric}"] = lower
                    st.session_state[f"nutrition_target_max_{metric}"] = upper
            st.rerun()
    target_values = {}
    for row_metrics in (METRICS[:3], METRICS[3:]):
        columns = st.columns(3)
        for column, metric in zip(columns, row_metrics):
            lower, upper = saved_targets.get(metric, (None, None))
            with column:
                _render_html(
                    f'<div class="drc-nutrition-target-heading">{escape(_nutrition_target_metric_label(metric))}</div>'
                )
                target_values[metric] = (
                    st.number_input(
                        _ui("最低目标", "Minimum"), min_value=0.0, value=lower,
                        step=1.0, key=f"nutrition_target_min_{metric}",
                    ),
                    st.number_input(
                        _ui("最高目标（可选）", "Maximum (optional)"), min_value=0.0, value=upper,
                        step=1.0, key=f"nutrition_target_max_{metric}",
                    ),
                )
    if st.button(_ui("保存营养目标", "Save Nutrition Targets"), type="primary"):
        try:
            save_nutrition_targets(connection, target_values)
            save_nutrition_target_snapshot(connection, date.today().isoformat(), target_values)
            st.session_state["simple_nutrition_target_flash"] = True
            st.rerun()
        except ValueError:
            st.error(_ui("最高目标不能低于最低目标。", "The maximum target cannot be below the minimum."))
    if st.session_state.pop("simple_nutrition_target_flash", False):
        st.success(_ui("营养目标已保存，并已同步到营养分类。", "Nutrition targets saved and synced to Nutrition Categories."))
    return load_nutrition_targets(connection)


def _meal_feedback_status_tags(meal_type, summary):
    tags = [("neutral", _meal_name(meal_type))]
    if summary.get("unidentified_food_count"):
        tags.extend([
            ("warning", _ui("部分数据", "Partial data")),
            ("warning", _ui("存在未识别食物", "Unrecognised food")),
        ])
    elif summary.get("identified_food_count"):
        tags.append(("success", _ui("数据完整", "Data complete")))
    else:
        tags.append(("warning", _ui("数据不足", "Insufficient data")))
    return "".join(
        f'<span class="drc-feedback-status {style}">{escape(str(label))}</span>'
        for style, label in tags
    )


def _render_meal_feedback(summary, feedback, meal_type, *, section_number=2):
    header_html = (
        '<div class="drc-feedback-heading">'
        f'<h3>{escape(_ui(f"{section_number}. 本餐反馈", f"{section_number}. Meal Feedback"))}</h3>'
        f'<div class="drc-feedback-statuses">{_meal_feedback_status_tags(meal_type, summary)}</div>'
        '</div>'
    )
    _render_html(header_html)
    metric_cards = "".join(
        '<div class="drc-nutrient-card">'
        f'<div class="drc-nutrient-name">{escape(_feedback_metric_label(metric))}</div>'
        f'<div class="drc-nutrient-value">{escape(_feedback_value(metric, summary.get(metric)))}</div>'
        '</div>'
        for metric in METRICS
    )
    _render_html(f'<div class="drc-nutrient-grid">{metric_cards}</div>')

    situations = feedback["situations"][:3]
    situation_html = "".join(
        f'<li><span class="drc-feedback-dot">•</span>{escape(str(situation))}</li>'
        for situation in situations
    ) or f'<p>{escape(_ui("当前餐次数据不足", "Current meal data is insufficient."))}</p>'
    suggestion_html = escape(str(feedback["suggestion"]))
    detail_html = (
        '<div class="drc-feedback-detail-grid">'
        '<section class="drc-feedback-card">'
        f'<div class="drc-feedback-card-title">{escape(_ui("主要情况", "Key points"))}</div>'
        f'<ul>{situation_html}</ul>'
        '</section>'
        '<section class="drc-feedback-card">'
        f'<div class="drc-feedback-card-title">{escape(_ui("建议", "Suggestion"))}</div>'
        f'<p>{suggestion_html}</p>'
        '</section>'
        '</div>'
    )
    _render_html(detail_html)


def _today_nutrition_status(metric, detail, summary):
    """Return one concise display status without changing nutrition logic."""
    current = detail.get("current")
    if current is not None:
        try:
            if float(current) < 0:
                return "error", _ui("数据异常", "Data anomaly"), _ui("当前值不能为负数。", "The current value cannot be negative.")
        except (TypeError, ValueError):
            return "error", _ui("数据异常", "Data anomaly"), _ui("当前值无法解析。", "The current value cannot be parsed.")
    if current is None or summary.get("unidentified_food_count"):
        return "muted", _ui("数据不足", "Insufficient data"), _ui("当前没有完整的可识别营养数据。", "Complete recognised nutrition data is not available.")
    if detail.get("target"):
        lower, upper = detail["target"]
        if current < lower:
            return "attention", _ui("低于目标", "Below target"), _ui("当前值低于今日目标下限。", "The current value is below today's target minimum.")
        if upper is not None and current > upper:
            return "attention", _ui("高于目标", "Above target"), _ui("当前值高于今日目标上限。", "The current value is above today's target maximum.")
        return "good", _ui("处于目标范围", "In target range"), _ui("当前值处于今日目标范围内。", "The current value is within today's target range.")
    if detail.get("baseline") is None:
        return "muted", _ui("基线建立中", "Baseline building"), _ui("记录更多完整日期后建立个人基线。", "Log more complete days to build a personal baseline.")
    return "muted", _ui("目标未设置", "Target not set"), _ui("当前营养目标尚未设置。", "A nutrition target has not been set.")


def _records_with_live_draft(records, day, live_summary, replacing_record_id):
    """Replace the open meal with its draft for every same-page calculation."""
    aligned_records = [record for record in records if record.get("id") != replacing_record_id]
    food_count = int(live_summary.get("food_count") or 0)
    identified = int(live_summary.get("identified_food_count") or 0)
    unidentified = int(live_summary.get("unidentified_food_count") or 0)
    draft_items = []
    if food_count:
        draft_items.append({
            "food_catalog_id": 1 if identified else None,
            "custom_food_name": None if identified else "draft",
            **{metric: live_summary.get(metric) for metric in METRICS},
        })
        draft_items.extend({"food_catalog_id": 1, "custom_food_name": None} for _ in range(max(identified - 1, 0)))
        draft_items.extend({"food_catalog_id": None, "custom_food_name": "draft"} for _ in range(max(unidentified - (0 if identified else 1), 0)))
    aligned_records.append({"id": replacing_record_id, "date": day, "status": "completed", "items": draft_items})
    return aligned_records


def _category_feedback(service, summary):
    """Short feedback grounded in the same current/goal values as category cards."""
    if not summary.get("identified_food_count"):
        return service.meal_feedback(summary)
    situations, suggestion = [], None
    for metric, detail in service.daily_metrics().items():
        current, target = detail.get("current"), detail.get("target")
        if current is None or not target:
            continue
        lower, upper = target
        label = _feedback_metric_label(metric)
        if current < lower:
            situations.append(_ui(f"{label}低于今日目标。", f"{label} is below today's target."))
            suggestion = suggestion or _ui(f"后续餐次优先补充{label}来源。", f"Prioritise a {label.lower()} source later today.")
        elif upper is not None and current > upper:
            situations.append(_ui(f"{label}高于今日目标。", f"{label} is above today's target."))
        elif len(situations) < 2:
            situations.append(_ui(f"{label}处于今日目标范围。", f"{label} is within today's target range."))
        if len(situations) >= 3:
            break
    return {
        "status": "ready",
        "situations": situations[:3],
        "suggestion": suggestion or _ui("继续完成当天饮食记录后再查看整体反馈。", "Continue logging today's meals for a fuller review."),
    }


def _render_today_nutrition(
    records,
    day,
    *,
    historical=False,
    section_number=3,
    targets=None,
    live_meal_summary=None,
    replacing_record_id=None,
):
    """Render day totals, optionally replacing the open meal with its live draft.

    This keeps the category cards aligned with the values currently visible in
    the food/drink editor instead of waiting for a save-and-rerun cycle.
    """
    aligned_records = records if live_meal_summary is None else _records_with_live_draft(
        records, day, live_meal_summary, replacing_record_id,
    )
    service = NutritionFeedbackService(aligned_records, day, LANGUAGE, targets=targets)
    metrics = service.daily_metrics()
    summary = service.today_summary()
    st.subheader(_ui(f"{section_number}. 营养分类", f"{section_number}. Nutrition Categories"))
    st.caption(_ui(
        "以下为所选日期已记录摄入；未识别食物不会按 0 计算。"
        if historical else "以下数据已与上方饮食记录对齐；未识别食物不会按 0 计算。",
        "These are recorded intakes for the selected date; unrecognised foods are not counted as zero."
        if historical else "These values are aligned with the food record above; unrecognised foods are not counted as zero.",
    ))
    cards = []
    for metric in METRICS:
        detail = metrics[metric]
        status_style, status_text, status_description = _today_nutrition_status(metric, detail, summary)
        baseline_text = _feedback_value(metric, detail["baseline"]) if detail["baseline"] is not None else _ui("建立中", "Building")
        if detail["target"]:
            lower, upper = detail["target"]
            target_text = _feedback_value(metric, lower)
            if upper is not None:
                target_text += f"–{_feedback_value(metric, upper)}"
        else:
            target_text = _ui("未设置", "Not set")
        cards.append(
            '<article class="drc-today-nutrition-card">'
            '<div class="drc-today-nutrition-card-head">'
            f'<div class="drc-today-nutrition-name">{escape(_feedback_metric_label(metric))}</div>'
            f'<div class="drc-today-nutrition-status {status_style}" title="{escape(status_description)}">'
            '<span class="drc-today-nutrition-dot"></span>'
            f'<span>{escape(status_text)}</span>'
            '</div>'
            '</div>'
            f'<div class="drc-today-nutrition-value">{escape(_feedback_value(metric, detail["current"]).replace(" ", "\u00a0"))}</div>'
            '<div class="drc-today-nutrition-meta">'
            f'<span>{escape(_ui("典型值", "Typical"))}：{escape(str(baseline_text))}</span>'
            f'<span>{escape(_ui("目标", "Target"))}：{escape(str(target_text))}</span>'
            '</div>'
            '</article>'
        )
    _render_html(f'<div class="drc-today-nutrition-grid">{"".join(cards)}</div>')
    return service


def _polar_resting_calories(metrics):
    """Derive Polar's resting/BMR estimate from its daily activity fields."""
    total = metrics.get("calories")
    active = metrics.get("active_calories")
    if total in (None, "") or active in (None, ""):
        return None
    try:
        estimate = float(total) - float(active)
    except (TypeError, ValueError):
        return None
    return estimate if estimate >= 0 else None

SIMPLE_NUTRITION_CSS = """
<style>
.drc-simple-title,.drc-simple-position,.drc-nutrition-column-title{display:flex;align-items:center;justify-content:center;text-align: center !important;font-weight:600;min-height:2.5rem}
div[data-testid="stNumberInput"] input{
    box-sizing:border-box!important;
    padding-left:0!important;
    padding-right:0!important;
    text-indent:0!important;
    text-align:center!important;
}
div[data-testid="stNumberInput"] button{display:none!important}
div[data-testid="stNumberInput"] button[aria-label*="Clear"],
div[data-testid="stNumberInput"] button[title*="Clear"],
div[data-testid="stNumberInput"] button[aria-label*="clear" i],
div[data-testid="stNumberInput"] button[title*="clear" i]{
    display:none!important;
}
div[data-testid="stTextInput"] input{text-align:center!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value]{
    flex:1 1 auto!important;
    width:100%!important;
    padding-left:2rem!important;
    text-align:center!important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] input{
    text-align:center!important;
}
div[data-testid="stDateInput"] label,
div[data-testid="stTimeInput"] label{
    display:flex!important;
    justify-content:center!important;
    width:100%!important;
    text-align:center!important;
}
div[data-testid="stDateInput"] input{
    text-align:center!important;
}
div[data-testid="stTimeInput"] div[data-baseweb="select"] div[value]{
    flex:1 1 auto!important;
    width:100%!important;
    text-align:center!important;
    transform:translateX(1rem)!important;
}
.drc-feedback-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin:.7rem 0 .35rem}
.drc-feedback-heading h3{margin:0;font-size:1.75rem;font-weight:600;line-height:1.3}
.drc-feedback-statuses{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.4rem}
.drc-feedback-status{display:inline-flex;align-items:center;padding:.2rem .55rem;border:1px solid var(--secondary-background-color);border-radius:999px;font-size:.78rem;line-height:1.25;white-space:nowrap}
.drc-feedback-status.success{border-color:#2d9d6f;color:#2d9d6f}
.drc-feedback-status.warning{border-color:#d28a28;color:#d28a28}
.drc-nutrient-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:4.35rem;column-gap:.5rem;row-gap:.3rem;margin-bottom:.55rem;align-items:start}
.drc-nutrient-card,.drc-feedback-card{box-sizing:border-box;border:1px solid var(--secondary-background-color);background:var(--secondary-background-color);border-radius:.75rem}
.drc-nutrient-card{display:flex;flex-direction:column;justify-content:center;height:4.35rem;padding:.45rem .75rem}
.drc-nutrient-name{font-size:.8rem;opacity:.78;margin-bottom:.12rem}
.drc-nutrient-value{font-size:1.12rem;font-weight:650;line-height:1.2;white-space:nowrap}
.drc-feedback-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem;margin-bottom:.65rem}
.drc-feedback-card{min-height:5.8rem;padding:.6rem .75rem}
.drc-feedback-card-title{font-weight:650;margin-bottom:.3rem}
.drc-feedback-card p{margin:0;line-height:1.55}
.drc-feedback-card ul{list-style:none;margin:0;padding:0}
.drc-feedback-card li{display:flex;gap:.4rem;line-height:1.55;margin:.18rem 0}
.drc-feedback-dot{color:#ff4b4b;font-weight:700}
.drc-meal-action-title{margin:.25rem 0 .55rem;font-size:.9rem;font-weight:650;opacity:.8}
.drc-today-nutrition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:minmax(7.75rem,auto);gap:.65rem;min-width:0;margin-top:.45rem;margin-bottom:.8rem}
.drc-today-nutrition-card{box-sizing:border-box;display:flex;flex-direction:column;justify-content:flex-start;min-width:0;min-height:7.75rem;height:auto;padding:.8rem .9rem;border:1px solid rgba(127,127,127,.22);border-radius:.9rem;background:var(--secondary-background-color);background:color-mix(in srgb,var(--secondary-background-color) 78%,var(--background-color));box-shadow:0 2px 9px rgba(0,0,0,.08);overflow:visible}
.drc-today-nutrition-card-head{display:flex;align-items:center;justify-content:space-between;gap:.45rem;min-width:0}
.drc-today-nutrition-name{font-size:.84rem;font-weight:650;letter-spacing:.01em;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.drc-today-nutrition-status{display:inline-flex;align-items:center;gap:.28rem;flex:0 0 auto;padding:.18rem .42rem;border-radius:999px;font-size:.69rem;line-height:1.2;white-space:nowrap;background:rgba(127,127,127,.11)}
.drc-today-nutrition-dot{width:.42rem;height:.42rem;border-radius:50%;background:#8c8c8c;display:inline-block;box-shadow:0 0 0 2px rgba(140,140,140,.13)}
.drc-today-nutrition-status.good{color:#218b5e;background:rgba(52,199,89,.12)}.drc-today-nutrition-status.good .drc-today-nutrition-dot{background:#2d9d6f;box-shadow:0 0 0 2px rgba(45,157,111,.14)}
.drc-today-nutrition-status.attention{color:#b86f13;background:rgba(255,159,10,.13)}.drc-today-nutrition-status.attention .drc-today-nutrition-dot{background:#d28a28;box-shadow:0 0 0 2px rgba(210,138,40,.14)}
.drc-today-nutrition-status.error{color:#c23d3d;background:rgba(255,59,48,.12)}.drc-today-nutrition-status.error .drc-today-nutrition-dot{background:#d94b4b;box-shadow:0 0 0 2px rgba(217,75,75,.14)}
.drc-today-nutrition-status.muted{color:#707780}
.drc-today-nutrition-value{margin:.3rem 0 .32rem;min-width:0;font-size:clamp(1.12rem,1.35vw,1.42rem);font-weight:720;letter-spacing:-.015em;line-height:1.15;white-space:nowrap;overflow:visible;font-variant-numeric:tabular-nums}
.drc-today-nutrition-meta{display:flex;flex-direction:column;gap:.12rem;color:var(--text-color);opacity:.62;font-size:.73rem;line-height:1.3;white-space:normal;overflow:visible}
.drc-today-nutrition-meta span{overflow:visible;white-space:nowrap}
.drc-today-evaluation-inline{margin:.15rem 0 .75rem;padding:.55rem .75rem;border-top:1px solid rgba(127,127,127,.18);color:var(--text-color);font-size:.86rem;line-height:1.5}
.drc-today-evaluation-inline strong{font-weight:650}
.drc-today-evaluation-status{color:var(--text-color);opacity:.55;font-size:.76rem}
.drc-nutrition-target-heading{text-align:center;font-size:1rem;font-weight:700;margin:.1rem 0 .4rem}
div[data-testid="stNumberInput"] label{justify-content:center!important;text-align:center!important;width:100%!important}
@media (max-width: 900px){.drc-nutrient-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width: 640px){
  .drc-feedback-heading{align-items:flex-start;flex-direction:column;margin-top:.7rem}
  .drc-feedback-statuses{justify-content:flex-start}
  .drc-nutrient-grid,.drc-feedback-detail-grid,.drc-today-nutrition-grid{grid-template-columns:1fr}
  .drc-feedback-card{min-height:0}
}
@media (min-width: 641px) and (max-width: 900px){.drc-today-nutrition-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
"""
st.markdown(SIMPLE_NUTRITION_CSS, unsafe_allow_html=True)


def _meal_name(value):
    return TR(f"nutrition_entry.meals.{value}")


def _cell(value, css="drc-simple-title"):
    return f'<div class="{css}">{escape(str(value))}</div>'


def _time_value(value):
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).time()
        except (TypeError, ValueError):
            return datetime.now().time().replace(second=0, microsecond=0)


FIXED_RECOMMENDED_MEAL_TIMES = {
    "breakfast": "08:00", "morning_snack": "10:30", "lunch": "12:30",
    "afternoon_snack": "15:30", "dinner": "18:30", "bedtime_fuel": "21:30",
}


def _current_meal_time():
    current = datetime.now().astimezone()
    rounded_minute = (current.minute // 5) * 5
    return current.replace(minute=rounded_minute, second=0, microsecond=0).time()


def _recommended_meal_time(connection, meal_type, meal_date):
    predicted = predict_meal_time(connection, meal_type, meal_date)
    if predicted:
        return predicted
    fixed = FIXED_RECOMMENDED_MEAL_TIMES.get(meal_type)
    if fixed:
        return time.fromisoformat(fixed)
    if meal_type == "training_fuel":
        rows = connection.execute(
            """SELECT start_time FROM polar_training_sessions_raw
               WHERE date=? AND start_time IS NOT NULL ORDER BY start_time""",
            (meal_date.isoformat(),),
        ).fetchall()
        candidates = [_time_value(row[0]) for row in rows if row[0]]
        if candidates:
            reference = _current_meal_time()
            return min(candidates, key=lambda value: abs(
                value.hour * 60 + value.minute - reference.hour * 60 - reference.minute
            ))
    return _current_meal_time()


def _display_food(catalog):
    return catalog["display_name_zh" if LANGUAGE != "en" else "display_name_en"]


def _food_rows_state(existing, item_type):
    record_key = (existing or {}).get("id", 0)
    key = f"simple_food_row_ids_{item_type}_{record_key}"
    if key not in st.session_state:
        count = sum(
            1 for item in (existing or {}).get("items", [])
            if item.get("item_type", "food") == item_type
        )
        st.session_state[key] = list(range(1, max(count, 1) + 1))
    return record_key, key


def _clear_editor_widget_state(editor_key):
    """Force a saved meal to render again from persisted database values."""
    markers = (
        f"simple_food_row_ids_food_{editor_key}",
        f"simple_food_row_ids_beverage_{editor_key}",
        f"food_food_", f"food_beverage_", f"supplement_",
    )
    for key in list(st.session_state):
        if key in markers[:2] or (
            any(key.startswith(prefix) for prefix in markers[2:])
            and f"_{editor_key}" in key
        ):
            del st.session_state[key]


def _food_editor(connection, existing, item_type, editor_key=None):
    catalog_items = list_food_catalog(connection)
    editor_catalog_items = [
        item for item in catalog_items
        if ("beverage" in item["category_tags"]) == (item_type == "beverage")
    ]
    by_id = {item["id"]: item for item in catalog_items}
    by_display_name = {
        name: item
        for item in catalog_items
        for name in (item["canonical_name"], item["display_name_zh"], item["display_name_en"])
        if name
    }
    saved_items = [
        item for item in (existing or {}).get("items", [])
        if item.get("item_type", "food") == item_type
    ]
    record_key, row_ids_key = _food_rows_state(existing, item_type)
    if editor_key is not None:
        record_key = editor_key
        row_ids_key = f"simple_food_row_ids_{item_type}_{record_key}"
        if row_ids_key not in st.session_state:
            st.session_state[row_ids_key] = list(range(1, max(len(saved_items), 1) + 1))
    pending_add_key = f"food_{item_type}_pending_add_{record_key}"
    pending_add = bool(st.session_state.pop(pending_add_key, False))
    if not pending_add:
        active_ids = []
        for row_id in st.session_state[row_ids_key]:
            if row_id <= len(saved_items):
                active_ids.append(row_id)
                continue
            name_key = f"food_{item_type}_name_{record_key}_{row_id}"
            if str(st.session_state.get(name_key) or "").strip():
                active_ids.append(row_id)
        # Every food and beverage editor keeps one blank row, but stale extra
        # rows are discarded instead of appearing after a selection rerun.
        if not active_ids:
            active_ids = [min(st.session_state[row_ids_key], default=1)]
        st.session_state[row_ids_key] = active_ids
    recent = recent_foods(connection)
    recent_names = []
    for recent_item in recent:
        recent_catalog = recent_item.get("catalog")
        if recent_item.get("item_type") != item_type:
            continue
        recent_name = _display_food(recent_catalog) if recent_catalog else recent_item.get("custom_food_name")
        if recent_name and recent_name not in recent_names:
            recent_names.append(recent_name)
    recent_usage = {
        (item["food_catalog_id"] if item["food_catalog_id"] is not None else ("custom", item["custom_food_name"])): item
        for item in recent
    }
    favorites = favorite_foods(connection)
    widget_prefix = f"food_{item_type}"
    item_label = (
        "食物" if item_type == "food" else "饮品"
    ) if LANGUAGE != "en" else (
        "Food" if item_type == "food" else "Beverage"
    )
    add_item_label = TR("simple_nutrition.add_item")
    add_item_label = (
        "添加食物" if item_type == "food" else "添加饮品"
    ) if LANGUAGE != "en" else (
        "Add Food" if item_type == "food" else "Add Beverage"
    )
    if favorites:
        st.caption(TR("simple_nutrition.favorites") + "：" + " · ".join(
            _display_food(item) for item in favorites
        ))

    headers = (item_label, "quantity", "unit", "actions")
    for column, key in zip(st.columns((2.0, 1.0, 0.8, 0.8)), headers):
        label = key if key in {"食物", "饮品", "Food", "Beverage"} else TR(f"simple_nutrition.{key}")
        column.markdown(_cell(label), unsafe_allow_html=True)

    rows = []
    for index, row_id in enumerate(list(st.session_state[row_ids_key])):
        saved = saved_items[row_id - 1] if isinstance(row_id, int) and 1 <= row_id <= len(saved_items) else {}
        saved_catalog = by_id.get(saved.get("food_catalog_id"))
        initial_food_name = _display_food(saved_catalog) if saved_catalog else (saved.get("custom_food_name") or "")
        columns = st.columns((2.0, 1.0, 0.8, 0.8))
        food_name_key = f"{widget_prefix}_name_{record_key}_{row_id}"
        unit_key = f"{widget_prefix}_unit_{record_key}_{row_id}"
        quantity_key = f"{widget_prefix}_quantity_{record_key}_{row_id}"

        def reset_food_preferences(name_state=food_name_key, unit_state=unit_key, quantity_state=quantity_key):
            selected_name = str(st.session_state.get(name_state) or "")
            selected = by_display_name.get(selected_name)
            usage_key = selected["id"] if selected else ("custom", selected_name.strip())
            usage = recent_usage.get(usage_key)
            st.session_state[unit_state] = (
                usage.get("unit") if usage and usage.get("unit") else
                selected["default_unit"] if selected else "g"
            )
            if usage and usage.get("quantity") not in (None, ""):
                st.session_state[quantity_state] = float(usage["quantity"])
            elif selected:
                # A newly selected food must not inherit the previous row's
                # amount (for example, 100 g becoming 100 individual buns).
                st.session_state[quantity_state] = float(selected.get("serving_quantity") or 1.0)

        catalog_names = [_display_food(item) for item in editor_catalog_items]
        food_options = [""] + recent_names + [
            name for name in catalog_names if name not in recent_names
        ]
        if initial_food_name and initial_food_name not in food_options:
            food_options.append(initial_food_name)
        food_name = columns[0].selectbox(
            TR("simple_nutrition.food_or_beverage"), food_options,
            index=food_options.index(initial_food_name) if initial_food_name else 0,
            key=food_name_key,
            on_change=reset_food_preferences, label_visibility="collapsed",
            accept_new_options=True,
            placeholder=("选择或输入食物" if item_type == "food" else "选择或输入饮品")
            if LANGUAGE != "en" else
            ("Select or enter food" if item_type == "food" else "Select or enter beverage"),
        ) or ""
        selected = by_display_name.get(food_name)
        custom_name = None if selected else food_name.strip() or None
        units = list(allowed_food_units(selected))
        usage_key = selected["id"] if selected else ("custom", food_name.strip())
        usage = recent_usage.get(usage_key) or {}
        initial_unit = (
            saved.get("unit") or usage.get("unit") or
            (selected or {}).get("default_unit") or
            ("ml" if item_type == "beverage" else "g")
        )
        if unit_key not in st.session_state or st.session_state[unit_key] not in units:
            st.session_state[unit_key] = initial_unit if initial_unit in units else units[0]
        unit = columns[2].selectbox(
            TR("simple_nutrition.unit"), units, key=unit_key,
            format_func=lambda value: TR(food_unit_label_key(value)),
            label_visibility="collapsed",
        )
        quantity = columns[1].number_input(
            TR("simple_nutrition.quantity"), min_value=0.01,
            value=(
                saved.get("quantity") if saved.get("quantity") not in (None, "") else
                usage.get("quantity") if usage.get("quantity") not in (None, "") else
                None
            ),
            step=1.0 if unit in FOOD_COUNT_UNITS else 0.1,
            key=quantity_key, label_visibility="collapsed",
        )
        if columns[3].button(
            TR("simple_nutrition.delete_row"),
            key=f"{widget_prefix}_delete_{record_key}_{row_id}",
            use_container_width=True,
        ):
            st.session_state[row_ids_key].remove(row_id)
            if not st.session_state[row_ids_key]:
                st.session_state[row_ids_key] = [max(row_id, 1) + 1]
            st.rerun()

        rows.append({
            "uuid": saved.get("uuid"),
            "food_catalog_id": selected["id"] if selected else None,
            "custom_food_name": custom_name,
            "item_type": item_type,
            "quantity": quantity, "unit": unit,
            "brand": saved.get("brand"),
            "cooking_method": saved.get("cooking_method"),
            "notes": saved.get("notes"),
        })
    controls = st.columns((1.6, 5))
    if controls[0].button(add_item_label, key=f"{widget_prefix}_add_{record_key}"):
        next_id = max(st.session_state[row_ids_key], default=0) + 1
        st.session_state[row_ids_key].append(next_id)
        st.session_state[pending_add_key] = True
        # The row list has already been rendered in this Streamlit run.
        # Rerun immediately so a single click displays the new input row.
        st.rerun()
    return rows


def _product_label(product):
    brand = product.get("brand_name") or TR("supplement_products.brand_unspecified")
    variant = f" · {product['product_variant']}" if product.get("product_variant") else ""
    return f"{brand} · {product['product_name']}{variant}"


def _stored_supplement_kind(row, products_by_id):
    """Classify persisted custom rows as well as catalog-backed rows."""
    explicit_kind = row.get("product_kind")
    if explicit_kind in {"supplement", "medication"}:
        return explicit_kind
    product = products_by_id.get(str(row.get("supplement_product_id"))) or {}
    if product.get("product_kind") in {"supplement", "medication"}:
        return product["product_kind"]
    name = str(row.get("custom_product_name") or row.get("item_name") or "").strip().lower()
    brand = str(row.get("custom_brand_name") or row.get("brand_name") or "").strip().lower()
    if "非那雄胺" in name or "finasteride" in name or brand == "保法止":
        return "medication"
    return "supplement"


def _supplement_editor(connection, existing, record_key, taken_at, product_kind="supplement"):
    all_products = list_products(connection)
    all_products_by_id = {str(item["id"]): item for item in all_products}
    products = [item for item in all_products if item.get("product_kind") == product_kind]
    saved_rows = [
        row for row in (existing or {}).get("supplements", [])
        if _stored_supplement_kind(row, all_products_by_id) == product_kind
        and (
            row.get("supplement_product_id")
            or str(row.get("custom_brand_name") or "").strip()
            or str(row.get("custom_product_name") or row.get("item_name") or "").strip()
        )
    ]
    by_id = {item["id"]: item for item in products}
    row_ids_key = f"supplement_row_ids_{product_kind}_{record_key}"
    pending_add_key = f"supplement_pending_add_{product_kind}_{record_key}"
    if row_ids_key not in st.session_state:
        st.session_state[row_ids_key] = list(range(1, max(len(saved_rows), 1) + 1))
    pending_add = bool(st.session_state.pop(pending_add_key, False))
    if not pending_add and st.session_state[row_ids_key]:
        # Clear stale blank rows left in the current Streamlit session. A blank
        # row is kept only for the rerun immediately following Add Supplement /
        # Add Medication.
        active_ids = []
        for row_id in st.session_state[row_ids_key]:
            if row_id <= len(saved_rows):
                active_ids.append(row_id)
                continue
            brand_value = st.session_state.get(f"supplement_brand_{product_kind}_{record_key}_{row_id}", "")
            product_value = st.session_state.get(f"supplement_product_{product_kind}_{record_key}_{row_id}", "")
            values_kind = _stored_supplement_kind(
                {"custom_brand_name": brand_value, "custom_product_name": product_value},
                {},
            )
            if (str(brand_value).strip() or str(product_value).strip()) and values_kind == product_kind:
                active_ids.append(row_id)
        # Keep one empty input row in every supplement/medication editor while
        # removing only stale additional blanks.
        st.session_state[row_ids_key] = active_ids or [min(st.session_state[row_ids_key], default=1)]

    recent = recent_products(connection)
    recent_product_ids = [item["id"] for item in recent if item.get("id")]
    products.sort(key=lambda item: (
        recent_product_ids.index(item["id"]) if item["id"] in recent_product_ids else len(recent_product_ids),
        item.get("product_name") or "",
    ))
    favorites = favorite_products(connection)
    if favorites and product_kind == "supplement":
        st.caption(TR("supplement_products.favorite_product") + "：" + " · ".join(_product_label(item) for item in favorites))

    add_label = _ui("添加补剂", "Add Supplement") if product_kind == "supplement" else _ui("添加用药", "Add Medication")
    rows = []
    if st.session_state[row_ids_key]:
        headers = ("brand", "product_name", "quantity", "unit", "actions")
        supplement_column_widths = (1.0, 1.7, 1.4, .7, .8)
        for column, key in zip(st.columns(supplement_column_widths), headers):
            column.markdown(_cell(TR(f"supplement_products.{key}")), unsafe_allow_html=True)
        for index, row_id in enumerate(list(st.session_state[row_ids_key])):
            saved = saved_rows[row_id - 1] if isinstance(row_id, int) and 1 <= row_id <= len(saved_rows) else {}
            saved_product = by_id.get(int(saved["supplement_product_id"])) if str(saved.get("supplement_product_id") or "").isdigit() else None
            initial_brand = saved_product.get("brand_name") if saved_product else saved.get("custom_brand_name") or ""
            initial_product_name = saved_product.get("product_name") if saved_product else saved.get("custom_product_name") or saved.get("item_name") or ""
            columns = st.columns(supplement_column_widths)
            common_brands = ["ON", "UBIO", "Nutrition29"] if product_kind == "supplement" else ["保法止"]
            brand_options = [""] + common_brands + [item["brand_name"] for item in products if item.get("brand_name") and item["brand_name"] not in common_brands]
            if initial_brand and initial_brand not in brand_options:
                brand_options.append(initial_brand)
            brand = columns[0].selectbox(TR("supplement_products.brand"), brand_options, index=brand_options.index(initial_brand) if initial_brand else 0, key=f"supplement_brand_{product_kind}_{record_key}_{row_id}", label_visibility="collapsed", accept_new_options=True, placeholder="选择或输入品牌" if LANGUAGE != "en" else "Select or enter brand") or ""
            product_options = [""] + [item["product_name"] for item in products if item.get("product_name")]
            if initial_product_name and initial_product_name not in product_options:
                product_options.append(initial_product_name)
            product_label = _ui("补剂类型", "Supplement Type") if product_kind == "supplement" else _ui("用药类型", "Medication Type")
            product_name = columns[1].selectbox(product_label if LANGUAGE != "en" else TR("supplement_products.product_name"), product_options, index=product_options.index(initial_product_name) if initial_product_name else 0, key=f"supplement_product_{product_kind}_{record_key}_{row_id}", label_visibility="collapsed", accept_new_options=True, placeholder=("选择或输入补剂类型" if product_kind == "supplement" else "选择或输入药品名称") if LANGUAGE != "en" else ("Select or enter supplement" if product_kind == "supplement" else "Select or enter medication")) or ""
            selected = next((item for item in products if (item.get("brand_name") or "").strip() == brand.strip() and item.get("product_name", "").strip() == product_name.strip()), None)
            unit_key = f"supplement_unit_{product_kind}_{record_key}_{row_id}"
            initial_unit = saved.get("unit") or (selected or {}).get("default_intake_unit") or "g"
            units = list(SUPPLEMENT_UNITS)
            if unit_key not in st.session_state or st.session_state[unit_key] not in units:
                st.session_state[unit_key] = initial_unit if initial_unit in units else units[0]
            unit = columns[3].selectbox(TR("supplement_products.unit"), units, key=unit_key, format_func=lambda value: TR(unit_label_key(value)), label_visibility="collapsed")
            quantity_key = f"supplement_quantity_{product_kind}_{record_key}_{row_id}"
            if not product_name.strip() and saved.get("quantity") in (None, ""):
                st.session_state[quantity_key] = None
            elif product_name.strip() and st.session_state.get(quantity_key) in (None, ""):
                st.session_state[quantity_key] = saved.get("quantity") if saved.get("quantity") not in (None, "") else 1.0
            quantity = columns[2].number_input(
                TR("supplement_products.quantity"), min_value=0.01,
                value=saved.get("quantity") if saved.get("quantity") not in (None, "") else (1.0 if product_name.strip() else None),
                step=1.0 if unit in {"capsule", "tablet", "sachet", "scoop", "drop"} else .1,
                key=quantity_key, label_visibility="collapsed",
            )
            if columns[4].button(TR("simple_nutrition.delete_row"), key=f"supplement_delete_{product_kind}_{record_key}_{row_id}", use_container_width=True):
                st.session_state[row_ids_key].remove(row_id)
                if not st.session_state[row_ids_key]:
                    st.session_state[row_ids_key] = [max(row_id, 1) + 1]
                st.rerun()
            if selected:
                status_key = "ingredients_calculated" if calculate_intake_ingredients(connection, selected["id"], quantity, unit) is not None else "ingredients_unconfirmed"
                st.caption(TR(f"supplement_products.{status_key}", product=_product_label(selected)))
                if selected["product_kind"] == "medication":
                    st.warning(TR("supplement_products.medication_boundary"))
            rows.append({"supplement_product_id": selected["id"] if selected else None, "custom_brand_name": None if selected else brand.strip() or None, "custom_product_name": None if selected else product_name.strip() or None, "quantity": quantity, "unit": unit, "taken_at": taken_at, "notes": saved.get("notes") or saved.get("item_notes")})
    controls = st.columns((1.2, 5))
    if controls[0].button(add_label, key=f"supplement_add_{product_kind}_{record_key}"):
        ids = st.session_state[row_ids_key]
        if len(ids) < 5:
            ids.append(max(ids, default=0) + 1)
            st.session_state[pending_add_key] = True
            # Render the newly appended blank row on this one click instead
            # of waiting for a second interaction with the page.
            st.rerun()
    return rows


def _quick_actions(connection, existing, meal_type, meal_date, eaten_at, food_items, supplements):
    columns = st.columns(2)
    if columns[0].button(TR("simple_nutrition.copy_yesterday")):
        source_id = find_yesterday_meal_id(connection, meal_type, meal_date.isoformat())
        if source_id:
            new_id = copy_meal_record(connection, source_id, meal_date.isoformat(), eaten_at.isoformat(timespec="seconds"))
            st.session_state["simple_meal_selector_pending"] = new_id; st.success(TR("simple_nutrition.copied")); st.rerun()
        st.warning(TR("simple_nutrition.no_copy_source"))
    if columns[1].button(TR("simple_nutrition.copy_previous_meal")):
        source_id = find_previous_meal_id(connection, (existing or {}).get("id"))
        if source_id:
            new_id = copy_meal_record(connection, source_id, meal_date.isoformat(), eaten_at.isoformat(timespec="seconds"))
            st.session_state["simple_meal_selector_pending"] = new_id; st.success(TR("simple_nutrition.copied")); st.rerun()
        st.warning(TR("simple_nutrition.no_copy_source"))


def _next_unrecorded_meal_type(records, meal_date, extra_meal_type=None):
    recorded = {
        row.get("meal_type") for row in records
        if row.get("date") == meal_date.isoformat()
    }
    if extra_meal_type:
        recorded.add(extra_meal_type)
    return next((meal_type for meal_type in MEAL_TYPES if meal_type not in recorded), MEAL_TYPES[0])



def _meal_form(connection, existing, records, targets=None, flash_key=None):
    record_key = (existing or {}).get("id", 0)
    st.subheader(_ui("2. 饮食记录", "2. Food Record"))
    pending_section = st.session_state.pop("simple_pending_nutrition_section", None)
    if pending_section in {"diet", "supplement", "medication"}:
        st.session_state["simple_active_nutrition_section"] = pending_section
    meal_type = st.selectbox(
        TR("simple_nutrition.meal"), MEAL_TYPES,
        format_func=_meal_name, key="simple_active_meal_type",
    )
    left, right = st.columns(2)
    meal_date = left.date_input(
        TR("nutrition_entry.date"),
        key="simple_active_meal_date",
    )
    recommended_time = _recommended_meal_time(connection, meal_type, meal_date)
    planned_time = _time_value(
        (existing or {}).get("planned_meal_time") or recommended_time
    )
    time_key = f"simple_meal_time_{record_key}"
    recommendation_signature = f"{meal_type}:{meal_date.isoformat()}"
    signature_key = f"simple_meal_recommendation_signature_{record_key}"
    if existing:
        st.session_state.setdefault(
            time_key,
            _time_value(existing.get("actual_meal_time") or existing.get("eaten_at")),
        )
    elif st.session_state.get(signature_key) != recommendation_signature:
        st.session_state[time_key] = recommended_time
        st.session_state[signature_key] = recommendation_signature
    eaten_at = right.time_input(
        TR("simple_nutrition.actual_meal_time"),
        step=300, key=time_key,
    )
    if meal_time_warning(meal_type, eaten_at.isoformat(timespec="seconds")):
        st.warning(TR("simple_nutrition.time_warning"))

    # New meal/date combinations get isolated widget state, so inputs from a
    # previous meal cannot leak into the next one.
    editor_key = f"{record_key}_{meal_type}_{meal_date.isoformat()}"

    section_options = ("diet", "supplement", "medication")
    section_labels = {
        "diet": "🍽 饮食" if LANGUAGE != "en" else "🍽 Diet",
        "supplement": "💊 补剂" if LANGUAGE != "en" else "💊 Supplements",
        "medication": "用药" if LANGUAGE != "en" else "Medication",
    }
    st.session_state.setdefault("simple_active_nutrition_section", "diet")
    active_section = st.segmented_control(
        "分类" if LANGUAGE != "en" else "Category",
        section_options,
        format_func=lambda value: section_labels[value],
        selection_mode="single",
        key="simple_active_nutrition_section",
        label_visibility="collapsed",
        width="stretch",
    ) or "diet"
    persisted_items = (existing or {}).get("items", [])
    persisted_products = {str(item["id"]): item for item in list_products(connection)}
    persisted_supplements = (existing or {}).get("supplements", [])
    persisted_medications = [
        item for item in persisted_supplements
        if _stored_supplement_kind(item, persisted_products) == "medication"
    ]
    persisted_regular_supplements = [
        item for item in persisted_supplements if item not in persisted_medications
    ]
    if active_section == "diet":
        food_items = _food_editor(connection, existing, "food", editor_key)
        beverage_items = _food_editor(connection, existing, "beverage", editor_key)
        food_items.extend(beverage_items)
    else:
        food_items = list(persisted_items)

    if active_section == "supplement":
        supplements = _supplement_editor(
            connection, existing, editor_key, eaten_at.isoformat(timespec="seconds"), "supplement"
        )
    else:
        supplements = list(persisted_regular_supplements)

    if active_section == "medication":
        medications = _supplement_editor(
            connection, existing, editor_key, eaten_at.isoformat(timespec="seconds"), "medication"
        )
        supplements.extend(medications)
    if active_section == "supplement":
        supplements.extend(persisted_medications)
    elif active_section != "medication":
        supplements.extend(persisted_medications)

    action_title_html = (
        f'<div class="drc-meal-action-title">{escape(_ui("操作", "Actions"))}</div>'
    )
    _render_html(action_title_html)
    copy_actions, save_action = st.columns((2, 1))
    with copy_actions:
        _quick_actions(connection, existing, meal_type, meal_date, eaten_at, food_items, supplements)
    with save_action:
        complete = st.button(
            TR("simple_nutrition.save_meal"), type="primary", use_container_width=True,
        )
    if flash_key:
        st.success(TR(flash_key))

    live_summary = summarize_draft_food_items(connection, food_items)
    _render_today_nutrition(
        records,
        meal_date.isoformat(),
        section_number=3,
        targets=targets,
        live_meal_summary=live_summary,
        replacing_record_id=(existing or {}).get("id"),
    )
    aligned_records = _records_with_live_draft(
        records, meal_date.isoformat(), live_summary, (existing or {}).get("id"),
    )
    feedback_service = NutritionFeedbackService(
        aligned_records, meal_date.isoformat(), LANGUAGE, targets=targets,
    )
    # Use the same live day rollup as section 3 so the numbers and feedback
    # stay aligned with the target editor and all recorded meal inputs.
    feedback_summary = feedback_service.today_summary()
    _render_meal_feedback(
        feedback_summary, _category_feedback(feedback_service, feedback_summary), meal_type,
        section_number=4,
    )

    notes_key = f"simple_meal_notes_{record_key}"
    existing_notes = (existing or {}).get("notes") or ""
    current_notes = st.session_state.get(notes_key, existing_notes)
    with st.expander(TR("simple_nutrition.notes"), expanded=bool(str(current_notes).strip())):
        notes = st.text_area(
            TR("simple_nutrition.notes"), value=existing_notes,
            key=notes_key, label_visibility="collapsed",
        )
    if complete:
        try:
            action = save_meal_record if existing else create_meal_record
            meal = {
                "date": meal_date.isoformat(), "meal_type": meal_type,
                "eaten_at": eaten_at.isoformat(timespec="seconds"),
                "planned_meal_time": planned_time.isoformat(timespec="seconds"),
                "actual_meal_time": eaten_at.isoformat(timespec="seconds"),
                "status": "completed", "source": (existing or {}).get("source", "manual"),
                "notes": notes,
            }
            if existing:
                record_id = action(connection, meal, food_items, supplements, existing["id"])
            else:
                record_id = action(connection, meal, food_items, supplements)
            # Apply the active editor category before the next segmented
            # control is created. This keeps medication saves on Medication.
            st.session_state["simple_pending_nutrition_section"] = active_section
            st.session_state["simple_nutrition_advance_on_reentry"] = {
                "meal_type": meal_type,
                "date": meal_date.isoformat(),
            }
            _clear_editor_widget_state(editor_key)
            st.session_state["simple_meal_selector_pending"] = record_id
            st.session_state["simple_nutrition_flash"] = "simple_nutrition.saved"
            st.rerun()
        except Exception as exc:
            st.error(TR("manual_logging.submit_failed", message=str(exc)))


def _daily_nutrition_summaries(records):
    """Build daily rollups once for the history table and selected-day view."""
    daily = {}
    for record in records:
        day = record["date"]
        source = record.get("summary") or {}
        bucket = daily.setdefault(day, {
            "food_count": 0,
            "identified_food_count": 0,
            **{metric: 0.0 for metric in METRICS},
            "known_metrics": set(),
        })
        for key in ("food_count", "identified_food_count"):
            bucket[key] += source.get(key) or 0
        for metric in METRICS:
            if source.get(metric) is not None:
                bucket[metric] += float(source[metric])
                bucket["known_metrics"].add(metric)
    for summary in daily.values():
        for metric in METRICS:
            if metric not in summary["known_metrics"]:
                summary[metric] = None
    return daily


def _historical_nutrition_row(day, summary):
    return {
        TR("nutrition_entry.date"): format_date(day, LANGUAGE),
        TR("simple_nutrition.recorded_count"): summary["food_count"],
        TR("simple_nutrition.identified_count"): summary["identified_food_count"],
        TR("simple_nutrition.calories"): _feedback_value("calories_kcal", summary["calories_kcal"]),
        TR("simple_nutrition.protein"): _feedback_value("protein_g", summary["protein_g"]),
        TR("simple_nutrition.carbohydrate"): _feedback_value("carbohydrate_g", summary["carbohydrate_g"]),
        TR("simple_nutrition.fat"): _feedback_value("fat_g", summary["fat_g"]),
        TR("simple_nutrition.fiber"): _feedback_value("fiber_g", summary["fiber_g"]),
        TR("simple_nutrition.water"): _feedback_value("water_ml", summary["water_ml"]),
    }


def _history(records):
    """Historical nutrition record table with the shared View interaction."""
    st.subheader(TR("simple_nutrition.history"))
    daily = _daily_nutrition_summaries(records)
    if not daily:
        st.info(TR("common.no_data"))
        return None, daily

    dates = sorted(daily, reverse=True)
    selected_date = st.session_state.get("nutrition_history_selected")
    if selected_date not in daily:
        selected_date = dates[0]
        st.session_state["nutrition_history_selected"] = selected_date
    rows = [_historical_nutrition_row(day, daily[day]) for day in dates]
    view_label = _ui("查看", "View")
    headers = list(rows[0]) + [_ui("操作", "Action")]
    widths = [1.05, .85, .95, .95, .95, 1.05, .8, .95, .9, .8]
    with st.container(height=430, border=True):
        header_columns = st.columns(widths)
        for column, label in zip(header_columns, headers):
            _render_html(
                f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>',
                column,
            )
        for day, row in zip(dates, rows):
            columns = st.columns(widths, vertical_alignment="center")
            for column, label in zip(columns[:-1], headers[:-1]):
                _render_html(
                    f'<div style="text-align:center;">{escape(str(row[label]))}</div>',
                    column,
                )
            if columns[-1].button(
                view_label, key=f"nutrition_history_view_{day}", use_container_width=True,
            ):
                st.session_state["nutrition_history_selected"] = day
                st.session_state["nutrition_history_focus_nonce"] = (
                    st.session_state.get("nutrition_history_focus_nonce", 0) + 1
                )
                st.rerun()
    return selected_date, daily


def _history_food_rows(record, item_type, catalog):
    rows = []
    for item in record.get("items", []):
        if item.get("item_type", "food") != item_type:
            continue
        catalog_item = catalog.get(item.get("food_catalog_id"))
        name = _display_food(catalog_item) if catalog_item else item.get("custom_food_name")
        rows.append({
            _ui("食物", "Food") if item_type == "food" else _ui("饮品", "Beverage"):
                name or TR("common.no_data"),
            TR("simple_nutrition.quantity"): _nutrition_number(item.get("quantity")),
            TR("simple_nutrition.unit"): TR(food_unit_label_key(item.get("unit") or "g")),
        })
    return rows


def _history_supplement_rows(record, product_kind, products_by_id):
    rows = []
    for item in record.get("supplements", []):
        if _stored_supplement_kind(item, products_by_id) != product_kind:
            continue
        rows.append({
            TR("supplement_products.brand"): item.get("brand_name") or item.get("custom_brand_name") or TR("common.no_data"),
            _ui("补剂类型", "Supplement Type") if product_kind == "supplement" else _ui("用药类型", "Medication Type"):
                item.get("product_name") or item.get("custom_product_name") or item.get("item_name") or TR("common.no_data"),
            TR("supplement_products.quantity"): _nutrition_number(item.get("quantity")),
            TR("supplement_products.unit"): TR(unit_label_key(item.get("unit") or "g")),
        })
    return rows


def _render_history_rows(rows, empty_text):
    if rows:
        centered_dataframe(rows, max_height="18rem")
    else:
        st.info(empty_text)


def _historical_nutrition_details(connection, records, selected_date):
    """Read-only historical counterpart of the current nutrition details."""
    data_open_key = f"nutrition_history_data_open_{selected_date}"
    details_open_key = f"nutrition_history_details_open_{selected_date}"

    def keep_history_sections_open():
        st.session_state[data_open_key] = True
        st.session_state[details_open_key] = True

    day_records = sorted(
        (item for item in records if item.get("date") == selected_date),
        key=lambda item: str(item.get("actual_meal_time") or item.get("eaten_at") or ""),
    )
    if not day_records:
        st.info(TR("common.no_data"))
        return

    record_by_id = {item["id"]: item for item in day_records}
    selected_meal_id = st.session_state.get(f"nutrition_history_detail_meal_{selected_date}")
    if selected_meal_id not in record_by_id:
        selected_meal_id = day_records[0]["id"]
        st.session_state[f"nutrition_history_detail_meal_{selected_date}"] = selected_meal_id
    selected_record = record_by_id[selected_meal_id]

    st.subheader(_ui("1. 饮食记录", "1. Food Record"))
    st.selectbox(
        TR("simple_nutrition.meal"),
        list(record_by_id),
        format_func=lambda record_id: _meal_name(record_by_id[record_id].get("meal_type")),
        key=f"nutrition_history_detail_meal_{selected_date}", on_change=keep_history_sections_open,
    )
    left, right = st.columns(2)
    left.text_input(
        TR("nutrition_entry.date"), value=format_date(selected_date, LANGUAGE),
        key=f"nutrition_history_detail_date_{selected_date}", disabled=True,
    )
    right.text_input(
        TR("simple_nutrition.actual_meal_time"),
        value=time_to_hms(selected_record.get("actual_meal_time") or selected_record.get("eaten_at")),
        key=f"nutrition_history_detail_time_{selected_date}_{selected_meal_id}", disabled=True,
    )

    section_options = ("diet", "supplement", "medication")
    section_labels = {
        "diet": _ui("🍽 饮食", "🍽 Diet"),
        "supplement": _ui("💊 补剂", "💊 Supplements"),
        "medication": _ui("用药", "Medication"),
    }
    section_key = f"nutrition_history_detail_section_{selected_date}_{selected_meal_id}"
    st.session_state.setdefault(section_key, "diet")
    active_section = st.segmented_control(
        _ui("分类", "Category"), section_options,
        format_func=lambda value: section_labels[value], selection_mode="single",
        key=section_key, label_visibility="collapsed", width="stretch",
        on_change=keep_history_sections_open,
    ) or "diet"

    if active_section == "diet":
        catalog = food_catalog_by_id(connection)
        _render_history_rows(
            _history_food_rows(selected_record, "food", catalog),
            _ui("本餐没有食物记录。", "No food recorded for this meal."),
        )
        _render_history_rows(
            _history_food_rows(selected_record, "beverage", catalog),
            _ui("本餐没有饮品记录。", "No beverages recorded for this meal."),
        )
    else:
        products_by_id = {str(item["id"]): item for item in list_products(connection)}
        _render_history_rows(
            _history_supplement_rows(selected_record, active_section, products_by_id),
            _ui("本餐没有补剂记录。", "No supplements recorded for this meal.")
            if active_section == "supplement" else
            _ui("本餐没有用药记录。", "No medication recorded for this meal."),
        )

    summary = selected_record.get("summary") or {}
    feedback_service = NutritionFeedbackService(records, selected_date, LANGUAGE)
    _render_meal_feedback(
        summary, feedback_service.meal_feedback(summary), selected_record.get("meal_type"),
        section_number=3,
    )
    notes = str(selected_record.get("notes") or "").strip()
    with st.expander(TR("simple_nutrition.notes"), expanded=bool(notes)):
        st.write(notes or TR("common.no_data"))
    _render_today_nutrition(records, selected_date, historical=True, section_number=2)


def _historical_nutrition_situation(connection, records, selected_date, daily, *, auto_expand=False, focus_nonce=0):
    """Selected-day nutrition data and meal details, matching other domains."""
    situation_title = _ui("历史营养情况", "Historical Nutrition Situation")
    data_title = _ui("历史营养数据", "Historical Nutrition Data")
    details_title = _ui("历史营养详情", "Historical Nutrition Details")
    focus_target_id = "nutrition-history-situation"
    _render_html(f'<div id="{focus_target_id}"></div>')
    st.subheader(situation_title)

    data_open_key = f"nutrition_history_data_open_{selected_date}"
    details_open_key = f"nutrition_history_details_open_{selected_date}"
    if auto_expand:
        st.session_state[data_open_key] = True
        st.session_state[details_open_key] = True
    with st.expander(data_title, expanded=bool(st.session_state.get(data_open_key, False))):
        centered_dataframe([_nutrition_energy_row(records, selected_date)])

    with st.expander(details_title, expanded=bool(st.session_state.get(details_open_key, False))):
        _historical_nutrition_details(connection, records, selected_date)

    if auto_expand:
        render_interaction_focus(components, target_id=focus_target_id, nonce=focus_nonce)


def _nutrition_energy_row(records, day):
    """The shared energy-balance data shape for today and historical dates."""
    metrics = get_day_metrics(day) or {}
    intake = sum(
        (record.get("summary") or {}).get("calories_kcal") or 0
        for record in records if record.get("date") == day
    )
    total_consumption = metrics.get("calories")
    # Keep this sign convention explicit for the table: total expenditure
    # minus total intake. Positive is shown as a surplus; negative as a gap.
    calorie_balance = total_consumption - intake if total_consumption is not None else None
    surplus_text = (
        f"{calorie_balance:.2f}" if calorie_balance is not None and calorie_balance > 0 else "—"
    )
    gap_text = (
        f"{abs(calorie_balance):.2f}" if calorie_balance is not None and calorie_balance < 0 else "—"
    )
    return {
        _ui("摄入热量总值（kcal）", "Total Intake (kcal)"): f"{intake:g}" if intake else TR("common.no_data"),
        _ui("运动消耗（kcal）", "Training Expenditure (kcal)"): _nutrition_number(metrics.get("training_calories")),
        _ui("静息消耗估计（kcal）", "Estimated Resting Expenditure (kcal)"): _nutrition_number(_polar_resting_calories(metrics)),
        _ui("活动消耗（kcal）", "Active Expenditure (kcal)"): _nutrition_number(metrics.get("active_calories")),
        _ui("总消耗（kcal）", "Total Expenditure (kcal)"): _nutrition_number(metrics.get("calories")),
        _ui("热量盈余（kcal）", "Calorie Surplus (kcal)"): surplus_text,
        _ui("热量缺口（kcal）", "Calorie Gap (kcal)"): gap_text,
    }


def _today_nutrition_table(records, day):
    st.subheader(TR("simple_nutrition.today_data"))
    centered_dataframe([_nutrition_energy_row(records, day)])


def _personal_nutrition_baseline(records, day):
    baseline = calculate_personal_nutrition_baseline(records, day)
    st.subheader("个人营养基线" if LANGUAGE != "en" else "Personal Nutrition Baseline")
    if baseline["status"] != "ready":
        st.info(
            (f"近 {baseline['window_days']} 天只有 {baseline['sample_days']} 个有记录的日期，"
             "至少需要 3 天后才建立个人基线。")
            if LANGUAGE != "en" else
            (f"Only {baseline['sample_days']} recorded days are available in the last "
             f"{baseline['window_days']} days; at least 3 days are needed."))
        return
    st.caption(
        f"基于近 {baseline['window_days']} 天、{baseline['sample_days']} 个有记录日期的每日摄入中位数；"
        "不包含今天。"
        if LANGUAGE != "en" else
        f"Daily intake medians from {baseline['sample_days']} recorded days in the last "
        f"{baseline['window_days']} days; today is excluded."
    )
    labels = {
        "calories_kcal": "热量（kcal）" if LANGUAGE != "en" else "Calories (kcal)",
        "protein_g": "蛋白质（g）" if LANGUAGE != "en" else "Protein (g)",
        "carbohydrate_g": "碳水化合物（g）" if LANGUAGE != "en" else "Carbohydrate (g)",
        "fat_g": "脂肪（g）" if LANGUAGE != "en" else "Fat (g)",
        "fiber_g": "膳食纤维（g）" if LANGUAGE != "en" else "Fiber (g)",
        "water_ml": "水分（ml）" if LANGUAGE != "en" else "Water (ml)",
    }
    rows = [{
        labels[metric]: baseline["metrics"][metric]["median"]
        if baseline["metrics"][metric]["median"] is not None else TR("common.no_data")
        for metric in labels
    }]
    centered_dataframe(rows)


def _nutrition_advice(records, day):
    baseline = calculate_personal_nutrition_baseline(records, day)
    st.subheader("营养建议" if LANGUAGE != "en" else "Nutrition Advice")
    if baseline["status"] != "ready":
        st.info(
            "继续记录至少 3 天后，系统会根据你的个人营养基线生成更有针对性的建议。"
            if LANGUAGE != "en" else
            "Keep logging for at least 3 days to receive advice based on your personal baseline."
        )
        return

    today_totals = {metric: 0.0 for metric in baseline["metrics"]}
    today_has_value = {metric: False for metric in baseline["metrics"]}
    for record in records:
        if record.get("date") != day or record.get("status", "completed") != "completed":
            continue
        summary = record.get("summary") or {}
        for metric in today_totals:
            value = summary.get(metric)
            if value is not None:
                today_totals[metric] += float(value)
                today_has_value[metric] = True

    messages = []
    labels = {
        "calories_kcal": "热量" if LANGUAGE != "en" else "calories",
        "protein_g": "蛋白质" if LANGUAGE != "en" else "protein",
        "fiber_g": "膳食纤维" if LANGUAGE != "en" else "fiber",
        "water_ml": "水分" if LANGUAGE != "en" else "water",
    }
    for metric in ("calories_kcal", "protein_g", "fiber_g", "water_ml"):
        personal_value = baseline["metrics"][metric]["median"]
        if personal_value is None or not today_has_value[metric] or personal_value <= 0:
            continue
        ratio = today_totals[metric] / personal_value
        if ratio < 0.8:
            messages.append(
                f"今日{labels[metric]}低于你的个人基线，可适度补充。"
                if LANGUAGE != "en" else
                f"Today's {labels[metric]} is below your personal baseline; consider a moderate addition."
            )
        elif ratio > 1.2 and metric != "water_ml":
            messages.append(
                f"今日{labels[metric]}高于你的个人基线，后续可适当平衡。"
                if LANGUAGE != "en" else
                f"Today's {labels[metric]} is above your personal baseline; consider balancing later intake."
            )

    if not messages:
        messages.append(
            "今日已记录的营养摄入整体接近你的个人基线，继续保持记录即可。"
            if LANGUAGE != "en" else
            "Today's recorded intake is broadly close to your personal baseline; keep logging consistently."
        )
    for message in messages:
        st.info(message)


def main():
    st.title(TR("domain.nutrition.title")); st.caption(TR("domain.nutrition.intro"))
    # Nutrition owns the template schema extension, so apply pending migrations
    # before reading templates (existing databases receive template_type here).
    connection = connect(migrate=True)
    try:
        records = list_meal_records(connection, limit=200)
        today_value = date.today().isoformat()
        flash_key = st.session_state.pop("simple_nutrition_flash", None)
        # Keep the original daily nutrition data overview alongside the newer
        # compact nutrition cards below; both use their existing calculations.
        _today_nutrition_table(records, today_value)
        st.subheader(_ui("今日营养详情", "Today's Nutrition Details"))
        returned_to_nutrition = st.session_state.get("drc_previous_page") not in (None, "nutrition")
        deferred_next = st.session_state.get("simple_nutrition_advance_on_reentry")
        pending_selected = st.session_state.pop("simple_meal_selector_pending", None)
        pending_record = get_meal_record(connection, pending_selected) if pending_selected else None
        if deferred_next and returned_to_nutrition:
            deferred_date = date.fromisoformat(deferred_next["date"])
            st.session_state["simple_active_meal_type"] = _next_unrecorded_meal_type(
                records, deferred_date, deferred_next["meal_type"]
            )
            st.session_state["simple_active_meal_date"] = deferred_date
            st.session_state.pop("simple_nutrition_advance_on_reentry", None)
        elif pending_record:
            # The save rerun stays on the meal that was just saved. The next
            # meal is selected only when the user returns from another page.
            st.session_state["simple_active_meal_type"] = pending_record["meal_type"]
            st.session_state["simple_active_meal_date"] = date.fromisoformat(pending_record["date"])

        st.session_state.setdefault(
            "simple_active_meal_type",
            _next_unrecorded_meal_type(records, date.today()),
        )
        st.session_state.setdefault("simple_active_meal_date", date.today())
        active_type = st.session_state["simple_active_meal_type"]
        active_date = st.session_state["simple_active_meal_date"]
        active_date_value = active_date.isoformat() if hasattr(active_date, "isoformat") else str(active_date)
        active_record_id = find_meal_id(connection, active_type, active_date_value)
        existing = get_meal_record(connection, active_record_id) if active_record_id else None
        targets = _render_nutrition_targets(connection)
        _meal_form(connection, existing, records, targets, flash_key)
        selected_history_date, historical_daily = _history(records)
        history_focus_nonce = st.session_state.get("nutrition_history_focus_nonce", 0)
        last_history_focus_nonce = st.session_state.get("nutrition_history_last_scrolled_nonce", 0)
        should_focus_history = history_focus_nonce > last_history_focus_nonce
        if selected_history_date:
            _historical_nutrition_situation(
                connection,
                records,
                selected_history_date,
                historical_daily,
                auto_expand=should_focus_history,
                focus_nonce=history_focus_nonce,
            )
        if should_focus_history:
            st.session_state["nutrition_history_last_scrolled_nonce"] = history_focus_nonce
        _personal_nutrition_baseline(records, today_value)
        _nutrition_advice(records, today_value)
    finally:
        connection.close()
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()
