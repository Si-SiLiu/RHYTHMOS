import unittest

from src.ui_scroll import FOCUS_DELAYS_MS, collapse_expander, render_interaction_focus


class _Components:
    def __init__(self):
        self.calls = []

    def html(self, script, **kwargs):
        self.calls.append((script, kwargs))


class InteractionFocusTests(unittest.TestCase):
    def test_shared_focus_uses_fixed_schedule_nonce_guard_and_tolerance(self):
        components = _Components()
        render_interaction_focus(
            components,
            target_id="recovery-history-situation",
            nonce=7,
        )
        self.assertEqual(len(components.calls), 1)
        script, kwargs = components.calls[0]
        self.assertIn('"recovery-history-situation"', script)
        self.assertIn('"recovery-history-situation:7"', script)
        self.assertIn(str(list(FOCUS_DELAYS_MS)), script)
        self.assertIn("dataset.drcFocusKey", script)
        self.assertIn("positionTolerance = 2", script)
        self.assertIn("Math.abs(offset) <= positionTolerance", script)
        self.assertIn("const topOffset = 144", script)
        self.assertIn("target.scrollIntoView", script)
        self.assertEqual(kwargs, {"height": 0, "width": 0})

    def test_focus_can_target_an_existing_expander_without_a_spacer(self):
        components = _Components()
        render_interaction_focus(
            components,
            target_expander_label="Historical Sleep Data",
            nonce=3,
            top_offset=80,
        )
        script, _ = components.calls[0]
        self.assertIn('"Historical Sleep Data"', script)
        self.assertIn("targetExpanderLabel", script)
        self.assertIn('[data-testid=\"stExpander\"]', script)
        self.assertIn("innerText.includes(targetExpanderLabel)", script)
        self.assertIn("const topOffset = 80", script)

    def test_completed_save_can_close_a_previously_open_expander(self):
        components = _Components()
        collapse_expander(
            components,
            target_expander_label="编辑今日恢复数据",
            nonce=4,
        )
        self.assertEqual(len(components.calls), 1)
        script, kwargs = components.calls[0]
        self.assertIn("const targetLabel", script)
        self.assertIn("details?.open", script)
        self.assertIn("summary.click()", script)
        self.assertEqual(kwargs, {"height": 0, "width": 0})


if __name__ == "__main__":
    unittest.main()
