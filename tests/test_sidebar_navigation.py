"""Regression tests for RHYTHMOS's shared sidebar navigation definition."""

import unittest

from src.i18n.ui import NAVIGATION_GROUPS


class SidebarNavigationTests(unittest.TestCase):
    def test_navigation_uses_three_semantic_groups(self):
        self.assertEqual(
            [group_key for group_key, _ in NAVIGATION_GROUPS],
            [
                "navigation.daily_state",
                "navigation.performance_system",
                "navigation.account",
            ],
        )

    def test_navigation_uses_consistent_material_symbol_icons(self):
        pages = {
            page_key: icon
            for _, group in NAVIGATION_GROUPS
            for page_key, _, icon in group
        }
        self.assertEqual(
            pages,
            {
                "exercise": ":material/fitness_center:",
                "sleep": ":material/bedtime:",
                "recovery": ":material/favorite:",
                "nutrition": ":material/eco:",
                "feedback": ":material/summarize:",
                "performance_planner": ":material/calendar_month:",
                "weekly_plan": ":material/view_week:",
                "training_studio": ":material/psychology:",
                "personal": ":material/person:",
                "system": ":material/settings:",
            },
        )

    def test_current_page_keeps_streamlit_disabled_link_semantics(self):
        source = __import__("pathlib").Path("src/i18n/ui.py").read_text(encoding="utf-8")
        self.assertIn("disabled=active_page == page_key", source)


if __name__ == "__main__":
    unittest.main()
