"""Small, deterministic nutrition feedback for the daily nutrition page.

The feedback intentionally uses only recognised food and beverage nutrients.
Supplements and medication intake records are not part of these totals unless a
future product record carries explicit nutrient information.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .food_catalog import NUTRIENT_COLUMNS, calculate_food_values, food_catalog_by_id
from .nutrition_baseline import BASELINE_METRICS, calculate_personal_nutrition_baseline


METRICS = BASELINE_METRICS


def _text(language: str, zh: str, en: str) -> str:
    return zh if language != "en" else en


def _empty_summary() -> dict[str, Any]:
    return {
        "food_count": 0,
        "identified_food_count": 0,
        "unidentified_food_count": 0,
        **{metric: None for metric in METRICS},
    }


def summarize_food_items(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum only nutrient values that are actually present.

    A custom/unrecognised item remains unknown for every nutrient rather than
    contributing a fabricated zero.  Per-metric ``None`` also means that no
    recognised item supplied a value for that metric.
    """
    summary = _empty_summary()
    values: dict[str, list[float]] = {metric: [] for metric in METRICS}
    for item in items:
        if item.get("deleted_at"):
            continue
        summary["food_count"] += 1
        if item.get("food_catalog_id") is not None:
            summary["identified_food_count"] += 1
        else:
            summary["unidentified_food_count"] += 1
        for metric in METRICS:
            value = item.get(metric)
            if value is not None:
                values[metric].append(float(value))
    for metric, known_values in values.items():
        if known_values:
            summary[metric] = round(sum(known_values), 2)
    return summary


def summarize_draft_food_items(connection, items: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate a live editor summary without saving a meal first."""
    catalog = food_catalog_by_id(connection)
    calculated_items = []
    for item in items:
        catalog_id = item.get("food_catalog_id")
        selected = catalog.get(int(catalog_id)) if catalog_id not in (None, "") else None
        name = str(item.get("custom_food_name") or "").strip()
        if not selected and not name:
            continue
        # A newly added row can briefly have a selected item but no quantity
        # while the user is still filling the form. It is not feedback data
        # yet, so leave it unknown instead of raising from the nutrition math.
        if item.get("quantity") in (None, ""):
            continue
        calculated = calculate_food_values(selected, item.get("quantity"), item.get("unit"))
        calculated_items.append({
            "food_catalog_id": selected["id"] if selected else None,
            **calculated,
        })
    return summarize_food_items(calculated_items)


def summarize_day(records: list[Mapping[str, Any]], day: str) -> dict[str, Any]:
    """Aggregate saved, completed meal records for one day."""
    items = []
    recorded_meals = 0
    for record in records:
        if record.get("date") != day or record.get("status", "completed") != "completed":
            continue
        recorded_meals += 1
        items.extend(record.get("items") or [])
    summary = summarize_food_items(items)
    summary["recorded_meals"] = recorded_meals
    return summary


def nutrition_record_completeness(records: list[Mapping[str, Any]], day: str, confirmed: bool) -> str:
    has_record = any(
        record.get("date") == day and record.get("status", "completed") == "completed"
        for record in records
    )
    if not has_record:
        return "unlogged"
    return "complete" if confirmed else "partial"


def is_day_nutrition_confirmed(connection, day: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM daily_nutrition_completion WHERE date=?", (day,)
    ).fetchone()
    return row is not None


def set_day_nutrition_confirmed(connection, day: str, confirmed: bool) -> None:
    with connection:
        if confirmed:
            connection.execute(
                "INSERT OR IGNORE INTO daily_nutrition_completion(date) VALUES(?)", (day,)
            )
        else:
            connection.execute("DELETE FROM daily_nutrition_completion WHERE date=?", (day,))


class NutritionFeedbackService:
    """Build concise meal and daily feedback from existing nutrition records."""

    def __init__(self, records: list[Mapping[str, Any]], day: str, language: str = "zh-CN", targets=None):
        self.records = records
        self.day = day
        self.language = language
        # Targets are deliberately optional: this project has no persisted
        # nutrition-target source yet, so callers must never invent one.
        self.targets = targets or {}

    def personal_baseline(self) -> dict[str, Any]:
        return calculate_personal_nutrition_baseline(self.records, self.day)

    def today_summary(self) -> dict[str, Any]:
        return summarize_day(self.records, self.day)

    def meal_feedback(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        if not summary.get("identified_food_count"):
            return {
                "status": "insufficient",
                "situations": [],
                "suggestion": _text(self.language, "当前餐次数据不足", "Current meal data is insufficient."),
            }

        good, concerns = [], []
        if (summary.get("protein_g") or 0) >= 20:
            good.append(_text(self.language, "蛋白质摄入较充足。", "Protein intake is substantial."))
        if (summary.get("carbohydrate_g") or 0) >= 30:
            good.append(_text(self.language, "含有较充足的碳水化合物。", "Contains a meaningful carbohydrate source."))
        if (summary.get("fiber_g") or 0) >= 5:
            good.append(_text(self.language, "膳食纤维来源较充足。", "Provides a useful amount of dietary fibre."))
        if (summary.get("water_ml") or 0) >= 250:
            good.append(_text(self.language, "本餐水分摄入较充足。", "Fluid intake in this meal is substantial."))
        if summary.get("unidentified_food_count"):
            concerns.append(_text(self.language, "含有未识别食物，营养汇总可能不完整。", "An unrecognised food makes this summary incomplete."))
        if summary.get("protein_g") is not None and summary["protein_g"] < 15:
            concerns.append(_text(self.language, "本餐蛋白质相对较少。", "Protein is relatively low for this meal."))
        if summary.get("fiber_g") is not None and summary["fiber_g"] < 3:
            concerns.append(_text(self.language, "本餐膳食纤维相对较少。", "Dietary fibre is relatively low for this meal."))

        situations = (good + concerns)[:3]
        if concerns:
            suggestion = _text(self.language, "可优先补充一份蛋白质或高纤维食物。", "Consider adding a protein or high-fibre food.")
        elif not good:
            suggestion = _text(self.language, "继续补充可识别的食物或饮品后再查看反馈。", "Add recognised foods or drinks for a clearer meal review.")
        else:
            suggestion = _text(self.language, "保持当前搭配，并继续完成当天记录。", "Keep this balance and continue the day's logging.")
        return {"status": "ready", "situations": situations, "suggestion": suggestion}

    def daily_metrics(self) -> dict[str, Any]:
        today = self.today_summary()
        baseline = self.personal_baseline()
        result = {}
        for metric in METRICS:
            current = today.get(metric)
            baseline_value = baseline["metrics"][metric]["median"] if baseline["status"] == "ready" else None
            target = self.targets.get(metric)
            if current is None:
                status = _text(self.language, "尚无可识别数据", "No recognised data yet")
            elif target:
                lower, upper = target
                status = (
                    _text(self.language, "目前低于目标范围", "Below target range") if current < lower else
                    _text(self.language, "目前高于目标范围", "Above target range") if upper is not None and current > upper else
                    _text(self.language, "目前处于目标范围", "Within target range")
                )
            elif baseline_value is None:
                status = _text(self.language, "已记录，等待更多对比数据", "Recorded; awaiting comparison data")
            elif current < baseline_value * 0.8:
                status = _text(self.language, "低于个人典型值", "Below personal typical intake")
            elif current > baseline_value * 1.2:
                status = _text(self.language, "高于个人典型值", "Above personal typical intake")
            else:
                status = _text(self.language, "接近个人典型值", "Close to personal typical intake")
            result[metric] = {
                "current": current,
                "baseline": baseline_value,
                "baseline_status": baseline["status"],
                "target": target,
                "status": status,
                "remaining_to_target": (max(target[0] - current, 0) if target and current is not None else None),
            }
        return result

    def daily_evaluation(self, confirmed: bool) -> dict[str, Any]:
        completeness = nutrition_record_completeness(self.records, self.day, confirmed)
        today = self.today_summary()
        baseline = self.personal_baseline()
        if completeness == "unlogged":
            return {"completeness": completeness, "summary": _text(self.language, "尚未记录今日饮食。", "No food has been logged today."), "suggestions": []}
        if completeness == "partial":
            summary = _text(self.language, "当前为已记录摄入，尚不能判断全天是否达标。", "This reflects recorded intake only; the full day cannot be assessed yet.")
        else:
            summary = _text(self.language, "今日记录已完成；以下评价基于完整的已记录摄入。", "Today's log is marked complete; this review uses the full recorded intake.")

        suggestions = []
        for metric, zh, en in (
            ("protein_g", "后续餐次优先补充蛋白质来源。", "Prioritise a protein source in later meals."),
            ("fiber_g", "后续餐次可增加蔬菜、水果或全谷物。", "Add vegetables, fruit, or whole grains later."),
            ("water_ml", "后续注意补充水分。", "Continue to add fluids later today."),
        ):
            personal = baseline["metrics"][metric]["median"] if baseline["status"] == "ready" else None
            current = today.get(metric)
            if personal and current is not None and current < personal * 0.8:
                suggestions.append(_text(self.language, zh, en))
        if completeness == "partial":
            suggestions.append(_text(self.language, "完成后续餐次记录后，再查看全天评价。", "Complete later meal logs before reviewing the full day."))
        return {"completeness": completeness, "summary": summary, "suggestions": suggestions[:3]}
