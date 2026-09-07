import tempfile
import unittest
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src import demo_sandbox
from src.i18n import get_translator
from src.performance_planner import add_block, create_plan, transition_block
from src.user_plan import (
    compare_week_plan,
    copy_plan_items,
    create_plan_item,
    create_week_plan,
    delete_plan_item,
    event_color_key,
    event_colour_slot,
    event_colour_slots,
    get_week_plan,
    group_plan_items_for_display,
    list_plan_items,
    merge_plan_slots,
    update_plan_item,
    week_start,
)


class UserPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "user-plan.db"
        self.monday = date(2026, 8, 3)
        self.plan = create_week_plan(
            self.monday, "工作学习计划", "Asia/Shanghai", db_path=self.db_path,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_week_is_normalized_and_items_are_independent(self):
        self.assertEqual(week_start("2026-08-05"), self.monday)
        self.assertEqual(get_week_plan("2026-08-05", db_path=self.db_path)["plan_id"], self.plan["plan_id"])
        item = create_plan_item(
            self.plan["plan_id"], 0, "阅读英语", "06:00", "08:00", "study",
            db_path=self.db_path,
        )
        self.assertEqual(list_plan_items(self.plan["plan_id"], db_path=self.db_path)[0]["item_id"], item["item_id"])

    def test_item_validation_rejects_reverse_time(self):
        with self.assertRaises(ValueError):
            create_plan_item(
                self.plan["plan_id"], 0, "无效事项", "10:00", "09:00", "work",
                db_path=self.db_path,
            )

    def test_custom_time_replaces_overlapping_base_slot(self):
        base_slots = (("06:00", "08:00"), ("08:00", "10:00"), ("10:00", "12:00"))
        items = [
            {"start_time": "08:30", "end_time": "10:30"},
            {"start_time": "10:30", "end_time": "12:00"},
        ]
        self.assertEqual(
            merge_plan_slots(base_slots, items),
            (("06:00", "08:00"), ("08:30", "10:30"), ("10:30", "12:00")),
        )

    def test_base_time_is_kept_when_item_uses_it_exactly(self):
        base_slots = (("06:00", "08:00"), ("08:00", "10:00"))
        items = [{"start_time": "08:00", "end_time": "10:00"}]
        self.assertEqual(merge_plan_slots(base_slots, items), base_slots)

    def test_same_event_title_uses_a_stable_colour_key(self):
        self.assertEqual(event_color_key("课1:室内力量训练"), event_color_key("课1:室内力量训练"))
        self.assertEqual(event_color_key("  餐1:早餐  "), event_color_key("餐1:早餐"))
        self.assertNotEqual(event_color_key("课2:听力主课"), event_color_key("课2:口语主课"))

    def test_different_visible_events_receive_distinct_colour_slots(self):
        titles = [
            "课2:听力主课", "课2:口语主课", "课3:听力专项训练", "课3:口语专项训练",
            "餐1:早餐", "餐2:午餐", "餐3:晚餐", "午睡",
        ]
        slots = event_colour_slots(titles)
        assigned = [event_colour_slot(title, slots) for title in titles]
        self.assertEqual(len(set(assigned)), len(titles))
        self.assertEqual(
            event_colour_slot("课2:听力主课", slots),
            event_colour_slot("  课2:听力主课  ", slots),
        )

    def test_legacy_auto_recipe_is_not_displayed_as_actual_intake(self):
        items = [
            {
                "item_id": "breakfast", "weekday": 0, "title": "餐1:早餐",
                "start_time": "08:00", "end_time": "08:30", "category": "meal",
                "notes": None,
            },
            {
                "item_id": "recipe", "weekday": 0, "title": "早餐：燕麦 50g、水 350ml",
                "start_time": "08:00", "end_time": "08:45", "category": "meal",
                "notes": "__nutrition_auto_recipe__:breakfast|根据历史输入自动生成",
            },
        ]
        display_items = group_plan_items_for_display(items)
        self.assertEqual(len(display_items), 1)
        self.assertEqual(display_items[0]["item_id"], "breakfast")
        self.assertEqual(display_items[0]["start_time"], "08:00")
        self.assertEqual(display_items[0]["end_time"], "08:30")
        self.assertEqual(display_items[0]["detail_titles"], [])

    def test_legacy_auto_recipe_without_a_plan_slot_is_hidden(self):
        recipe = {
            "item_id": "snack", "weekday": 0, "title": "上午加餐：水 350ml",
            "start_time": "10:00", "end_time": "10:45", "category": "meal",
            "notes": "__nutrition_auto_recipe__:morning_snack|根据历史输入自动生成",
        }
        self.assertEqual(group_plan_items_for_display([recipe]), [])

    def test_manual_nutrition_recipe_without_a_plan_slot_is_hidden(self):
        recipe = {
            "item_id": "manual-breakfast", "weekday": 0,
            "title": "06:00：水 350ml、燕麦 100g", "start_time": "06:00", "end_time": "08:15",
            "category": "meal", "notes": "__nutrition_manual_recipe__:breakfast|{}",
        }
        self.assertEqual(group_plan_items_for_display([recipe]), [])

    def test_item_can_be_updated_and_deleted(self):
        item = create_plan_item(
            self.plan["plan_id"], 0, "原计划", "09:00", "10:00", "work",
            db_path=self.db_path,
        )
        updated = update_plan_item(
            item["item_id"], 1, "新计划", "10:30", "12:00", "study",
            notes="备注", db_path=self.db_path,
        )
        self.assertEqual(
            (updated["weekday"], updated["title"], updated["start_time"], updated["end_time"], updated["category"], updated["notes"]),
            (1, "新计划", "10:30", "12:00", "study", "备注"),
        )
        self.assertTrue(delete_plan_item(item["item_id"], db_path=self.db_path))
        self.assertEqual(list_plan_items(self.plan["plan_id"], db_path=self.db_path), [])

    def test_copy_plan_items_is_idempotent_and_preserves_fields(self):
        previous = create_week_plan(
            date(2026, 7, 27), "上周计划", "Asia/Shanghai", db_path=self.db_path,
        )
        create_plan_item(
            previous["plan_id"], 1, "英语课", "08:30", "10:30", "study",
            notes="重点听力", db_path=self.db_path,
        )
        copied = copy_plan_items(previous["plan_id"], self.plan["plan_id"], db_path=self.db_path)
        self.assertEqual(copied, 1)
        item = list_plan_items(self.plan["plan_id"], db_path=self.db_path)[0]
        self.assertEqual(
            (item["weekday"], item["title"], item["start_time"], item["end_time"], item["category"], item["notes"]),
            (1, "英语课", "08:30", "10:30", "study", "重点听力"),
        )
        self.assertEqual(
            copy_plan_items(previous["plan_id"], self.plan["plan_id"], db_path=self.db_path),
            0,
        )

    def test_comparison_reads_execution_status_without_changing_plan(self):
        item = create_plan_item(
            self.plan["plan_id"], 0, "深度工作", "09:00", "10:00", "work",
            db_path=self.db_path,
        )
        comparison = compare_week_plan(self.plan["plan_id"], db_path=self.db_path)
        self.assertEqual(comparison[0]["actual_status"], "unrecorded")

        daily = create_plan(self.monday, "执行日程", "Asia/Shanghai", db_path=self.db_path)
        block = add_block(
            daily["plan_id"], "深度工作", "deep_work",
            "2026-08-03T09:00:00", "2026-08-03T10:00:00",
            db_path=self.db_path,
        )
        transition_block(block["block_id"], "completed", db_path=self.db_path)

        comparison = compare_week_plan(self.plan["plan_id"], db_path=self.db_path)
        self.assertEqual(comparison[0]["item_id"], item["item_id"])
        self.assertEqual(comparison[0]["actual_status"], "completed")
        self.assertEqual(list_plan_items(self.plan["plan_id"], db_path=self.db_path)[0]["title"], "深度工作")

    def test_weekly_plan_page_imports_in_demo_mode(self):
        page = Path(__file__).parents[1] / "src" / "pages" / "9_Weekly_Plan.py"
        with patch.object(demo_sandbox, "SESSIONS_ROOT", Path(self.temp.name) / "sessions"), patch.dict(
            "os.environ", {"DRC_DEMO_MODE": "1"}, clear=False,
        ), patch(
            "src.i18n.ui.render_sidebar",
            return_value=("en", get_translator("en")),
        ), patch("streamlit.page_link", return_value=None):
            app = AppTest.from_file(str(page)).run(timeout=20)
        self.assertEqual(list(app.exception), [])
        self.assertTrue(app.title)
        self.assertFalse(app.expander[0].proto.expanded)

    def test_empty_slot_click_prefills_add_form(self):
        page = Path(__file__).parents[1] / "src" / "pages" / "9_Weekly_Plan.py"
        with patch.object(demo_sandbox, "SESSIONS_ROOT", Path(self.temp.name) / "sessions"), patch.dict(
            "os.environ", {"DRC_DEMO_MODE": "1"}, clear=False,
        ), patch(
            "src.i18n.ui.render_sidebar",
            return_value=("en", get_translator("en")),
        ), patch("streamlit.page_link", return_value=None):
            app = AppTest.from_file(str(page)).run(timeout=20)
            next(button for button in app.button if button.label == "Create weekly plan").click().run(timeout=20)
            self.assertEqual(app.title[0].value, "Performance Planner｜表现计划")
            self.assertNotIn(
                "Performance Planner｜表现计划",
                [element.value for element in app.subheader],
            )
            slot = next(button for button in app.button if button.key == "weekly_plan_slot_0_06:00_08:00")
            slot.click().run(timeout=20)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            next(widget for widget in app.selectbox if widget.key == "weekly_plan_form_weekday").value,
            0,
        )
        self.assertEqual(
            next(widget for widget in app.text_input if widget.key == "weekly_plan_form_start").value,
            "06:00",
        )


if __name__ == "__main__":
    unittest.main()
