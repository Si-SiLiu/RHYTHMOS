"""Regression tests for shared Streamlit shell styling."""

import unittest

from src.ui_controls import APP_SHELL_CSS


class AppShellStyleTests(unittest.TestCase):
    def test_app_shell_defines_shared_heading_scale(self):
        """Page, section, and folding titles must share one global hierarchy."""
        self.assertIn("--drc-page-title-size: 2rem", APP_SHELL_CSS)
        self.assertIn("--drc-section-title-size: 1.25rem", APP_SHELL_CSS)
        self.assertIn("--drc-subsection-title-size: 1rem", APP_SHELL_CSS)
        self.assertIn('[data-testid="stHeadingWithActionElements"] h3', APP_SHELL_CSS)
        self.assertIn('[data-testid="stExpander"] summary p', APP_SHELL_CSS)

    def test_app_shell_keeps_normal_stale_elements_stable(self):
        """Ordinary reruns should not flash the entire current page."""
        self.assertIn(
            '[data-testid="stElementContainer"][data-stale="true"]',
            APP_SHELL_CSS,
        )
        self.assertIn("opacity: 1 !important", APP_SHELL_CSS)
        self.assertIn("transition: none !important", APP_SHELL_CSS)

    def test_app_shell_reserves_scrollbar_space(self):
        """Short and long pages must keep an identical viewport width."""
        self.assertIn("scrollbar-gutter: stable", APP_SHELL_CSS)
        self.assertNotIn("scrollbar-gutter: stable both-edges", APP_SHELL_CSS)

    def test_app_shell_defines_a_raised_surface(self):
        """Primary panels need a distinct theme-aware surface level."""
        self.assertIn("--rh-surface-raised", APP_SHELL_CSS)
        self.assertIn("color-mix(in srgb, var(--background-color) 14%", APP_SHELL_CSS)

    def test_app_shell_preserves_streamlit_icon_fonts(self):
        """A universal font override turns Material icon ligatures into text."""
        self.assertIn('[data-testid="stAppViewContainer"] {', APP_SHELL_CSS)
        self.assertNotIn('[data-testid="stAppViewContainer"] *', APP_SHELL_CSS)

    def test_app_shell_defines_scientific_workspace_navigation_and_card_states(self):
        """The fixed information-card inspection response cannot drift by page."""
        self.assertIn('a[data-testid="stPageLink-NavLink"]', APP_SHELL_CSS)
        self.assertIn('[disabled] {', APP_SHELL_CSS)
        self.assertIn(":focus-visible", APP_SHELL_CSS)
        self.assertIn("@media (hover: hover) and (pointer: fine)", APP_SHELL_CSS)
        self.assertIn('[data-testid="stVerticalBlockBorderWrapper"]', APP_SHELL_CSS)
        self.assertIn('.st-key-personal_weight_trend_card', APP_SHELL_CSS)
        self.assertIn(".rh-system-card", APP_SHELL_CSS)
        self.assertIn("prefers-reduced-motion: no-preference", APP_SHELL_CSS)
        self.assertIn("transform 180ms ease-out", APP_SHELL_CSS)
        self.assertIn("box-shadow 180ms ease-out", APP_SHELL_CSS)
        self.assertIn("border-color 180ms ease-out", APP_SHELL_CSS)
        self.assertIn("transform: translateY(-1px)", APP_SHELL_CSS)
        self.assertIn("0 20px 36px rgba(0, 0, 0, .14)", APP_SHELL_CSS)
        self.assertNotIn("transition: background", APP_SHELL_CSS)

    def test_app_shell_uses_apple_minimal_sidebar_width(self):
        self.assertIn("min-width: 15.875rem !important", APP_SHELL_CSS)
        self.assertIn("max-width: 15.875rem !important", APP_SHELL_CSS)


if __name__ == "__main__":
    unittest.main()
