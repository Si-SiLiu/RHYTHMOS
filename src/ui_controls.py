"""Shared styling for Streamlit controls used for manual data entry."""


MANUAL_INPUT_CSS = """
<style>
/* Keep the first page section aligned across the main app pages. */
section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] [data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .main .block-container {
    padding-top: var(--rh-page-top) !important;
    padding-bottom: var(--rh-page-bottom) !important;
}
/* Use direct numeric typing everywhere; Streamlit's +/- stepper buttons add
   visual noise and make compact entry rows harder to scan. */
div[data-testid="stNumberInput"] button {
    display: none !important;
}
div[data-testid="stNumberInput"] input {
    padding-left: 0 !important;
    padding-right: 0 !important;
    text-indent: 0 !important;
}
div[data-testid="stNumberInput"] input::-webkit-inner-spin-button,
div[data-testid="stNumberInput"] input::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
}
/* Newer Streamlit versions render the clear × as an input adornment instead
   of a regular button. Hide only adornments that do not contain the input. */
div[data-testid="stNumberInput"] [data-baseweb="input"] > div:not(:has(input)),
div[data-testid="stTextInput"] [data-baseweb="input"] > div:not(:has(input)),
div[data-testid="stTextArea"] [data-baseweb="textarea"] > div:not(:has(textarea)),
div[data-testid="stNumberInput"] [data-baseweb="input"] svg,
div[data-testid="stTextInput"] [data-baseweb="input"] svg,
div[data-testid="stTextArea"] [data-baseweb="textarea"] svg {
    display: none !important;
}
/* Hide any value-clearing affordance that a Streamlit version may render. */
div[data-testid="stNumberInput"] button[aria-label*="clear" i],
div[data-testid="stNumberInput"] button[title*="clear" i],
div[data-testid="stNumberInput"] button[data-testid*="clear" i],
div[data-testid="stNumberInput"] [data-baseweb="input"] [role="button"],
div[data-testid="stNumberInput"] [data-baseweb="input"] [aria-label*="clear" i],
div[data-testid="stNumberInput"] [data-baseweb="input"] [title*="clear" i],
div[data-testid="stTextInput"] button[aria-label*="clear" i],
div[data-testid="stTextInput"] button[title*="clear" i],
div[data-testid="stTextInput"] button[data-testid*="clear" i],
div[data-testid="stTextInput"] [data-baseweb="input"] [role="button"],
div[data-testid="stTextInput"] [data-baseweb="input"] [aria-label*="clear" i],
div[data-testid="stTextInput"] [data-baseweb="input"] [title*="clear" i],
div[data-testid="stTextArea"] button[aria-label*="clear" i],
div[data-testid="stTextArea"] button[title*="clear" i],
div[data-testid="stTextArea"] button[data-testid*="clear" i],
div[data-testid="stTextArea"] [data-baseweb="textarea"] [role="button"],
div[data-testid="stTextArea"] [data-baseweb="textarea"] [aria-label*="clear" i],
div[data-testid="stTextArea"] [data-baseweb="textarea"] [title*="clear" i] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
</style>
"""


# Every Streamlit page is rendered independently during navigation.  Without a
# reserved scrollbar gutter, switching between a short and a long page changes
# the available viewport width and makes the sidebar plus the complete page
# appear to jump horizontally.  Apply this shell styling from the shared
# sidebar renderer so it is present on every first-party page.
APP_SHELL_CSS = """
<style>
:root {
    /* Small, semantic visual foundation shared by first-party pages.  Keep
       values tied to existing Streamlit theme variables so light and dark
       themes remain supported without a parallel theme system. */
    --rh-font-sans: ui-sans-serif, -apple-system, BlinkMacSystemFont,
        "SF Pro Text", "PingFang SC", "PingFang TC", "Microsoft YaHei",
        "Segoe UI", sans-serif;
    --rh-page-top: 1.5rem;
    --rh-page-bottom: 3rem;
    --rh-radius-small: 6px;
    --rh-radius-standard: 10px;
    --rh-radius-emphasis: 14px;
    --rh-surface: var(--secondary-background-color);
    --rh-surface-raised: var(--secondary-background-color);
    --rh-surface-inset: var(--secondary-background-color);
    --rh-border-subtle: rgba(99, 115, 129, .22);
    --rh-border-strong: rgba(78, 96, 114, .34);
    --rh-text: var(--text-color);
    --rh-text-secondary: var(--text-color);
    --rh-text-muted: var(--text-color);
    --rh-status-positive: #216343;
    --rh-status-positive-surface: #e8f3ed;
    --rh-status-caution: #855100;
    --rh-status-caution-surface: #fcf1df;
    --rh-status-negative: #8c3535;
    --rh-status-negative-surface: #f9e8e8;
    --rh-shadow-raised: 0 1px 2px rgba(27, 42, 57, .07), 0 4px 12px rgba(27, 42, 57, .035);
    --drc-page-title-size: 2rem;
    --drc-section-title-size: 1.25rem;
    --drc-subsection-title-size: 1rem;
}
@supports (background: color-mix(in srgb, white 50%, black)) {
    :root {
        --rh-surface: color-mix(in srgb, var(--background-color) 54%, var(--secondary-background-color));
        --rh-surface-raised: color-mix(in srgb, var(--background-color) 14%, var(--secondary-background-color));
        --rh-surface-inset: color-mix(in srgb, var(--secondary-background-color) 76%, var(--background-color));
        --rh-border-subtle: color-mix(in srgb, var(--text-color) 14%, transparent);
        --rh-border-strong: color-mix(in srgb, var(--text-color) 24%, transparent);
        --rh-text-secondary: color-mix(in srgb, var(--text-color) 72%, transparent);
        --rh-text-muted: color-mix(in srgb, var(--text-color) 54%, transparent);
        --rh-status-positive: color-mix(in srgb, #277452 66%, var(--text-color));
        --rh-status-positive-surface: color-mix(in srgb, #2f7d5c 13%, var(--background-color));
        --rh-status-caution: color-mix(in srgb, #9a671d 72%, var(--text-color));
        --rh-status-caution-surface: color-mix(in srgb, #a76d1a 13%, var(--background-color));
        --rh-status-negative: color-mix(in srgb, #af4545 72%, var(--text-color));
        --rh-status-negative-surface: color-mix(in srgb, #b94b4b 12%, var(--background-color));
    }
}
[data-testid="stAppViewContainer"] {
    font-family: var(--rh-font-sans);
}
/* Streamlit shows a transient keyboard/count hint whenever a text control is
   focused. Keep the input surface quiet and consistent across every page;
   keyboard submission itself remains available. */
[data-testid="InputInstructions"] {
    display: none !important;
}
/* Scientific Workspace shell: quiet product chrome that frames the content
   without creating a second dashboard inside the sidebar.  These selectors
   target Streamlit's documented test IDs and page-link attribute rather than
   generated Emotion class names. */
[data-testid="stSidebar"] {
    border-right: 1px solid rgba(117, 130, 148, .11);
}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding: 1.2rem .75rem 1.4rem;
}
[data-testid="stSidebar"] .rh-sidebar-brand {
    margin: .1rem .5rem 1rem;
}
[data-testid="stSidebar"] .rh-sidebar-brand-name {
    color: inherit;
    font-size: 1rem;
    font-weight: 680;
    letter-spacing: -.012em;
    line-height: 1.25;
}
[data-testid="stSidebar"] .rh-sidebar-brand-descriptor {
    margin-top: .5rem;
    color: inherit;
    font-size: .6875rem;
    font-weight: 550;
    letter-spacing: .015em;
    line-height: 1.45;
    opacity: .56;
}
[data-testid="stSidebar"] .rh-sidebar-brand-chinese {
    margin-top: .12rem;
    color: inherit;
    font-size: .6875rem;
    line-height: 1.45;
    opacity: .42;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] {
    margin: 0 .3rem 1rem;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] {
    margin-bottom: .25rem;
    color: inherit;
    font-size: .625rem;
    font-weight: 600;
    letter-spacing: .04em;
    line-height: 1.4;
    opacity: .46;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
    min-height: 1.875rem;
    border: 1px solid transparent !important;
    border-radius: var(--rh-radius-small) !important;
    background: rgba(117, 130, 148, .04) !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"]:focus-within > div {
    outline: 2px solid rgba(82, 105, 128, .72);
    outline-offset: 2px;
}
[data-testid="stSidebar"] .rh-sidebar-group-label {
    margin: 1rem .55rem .3rem;
    color: inherit;
    font-size: .5625rem;
    font-weight: 650;
    letter-spacing: .075em;
    line-height: 1.35;
    opacity: .38;
}
[data-testid="stSidebar"] .rh-sidebar-group-label:first-of-type {
    margin-top: 0;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    min-height: 2.25rem;
    margin: .0625rem 0;
    border-radius: 8px;
    color: inherit !important;
    font-size: .8125rem;
    font-weight: 550;
    opacity: .66;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] > span,
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {
    color: inherit !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] [data-testid="stIconMaterial"] {
    font-size: 1rem;
    opacity: .8;
}
@media (hover: hover) and (pointer: fine) {
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
        background: rgba(117, 130, 148, .055);
        color: inherit !important;
        opacity: .9;
    }
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:focus-visible {
    outline: 2px solid rgba(82, 105, 128, .78);
    outline-offset: 2px;
    opacity: 1;
}
/* Streamlit marks the current page as a disabled link. Keep that native
   routing/accessibility behaviour and give it a distinct, static surface. */
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][disabled] {
    background: rgba(117, 130, 148, .065);
    box-shadow: none;
    color: inherit !important;
    font-weight: 650;
    opacity: 1;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][disabled] [data-testid="stIconMaterial"] {
    font-variation-settings: "FILL" 0, "wght" 600, "GRAD" 0, "opsz" 20;
}
/* Keep the application information hierarchy identical on every page.
   Scope heading rules to Streamlit's heading wrapper so card-internal h1-h3
   elements can retain their deliberately compact component typography. */
[data-testid="stHeadingWithActionElements"] h1 {
    font-size: var(--drc-page-title-size) !important;
}
[data-testid="stHeadingWithActionElements"] h2 {
    font-size: var(--drc-section-title-size) !important;
}
[data-testid="stHeadingWithActionElements"] h3,
[data-testid="stExpander"] summary p {
    font-size: var(--drc-subsection-title-size) !important;
    font-weight: 600 !important;
    line-height: 1.4 !important;
}
/*
 * Keep the current page stable during normal reruns. Hiding every stale
 * element makes even a small control change look like a full-page refresh.
 */
[data-testid="stElementContainer"][data-stale="true"] {
    opacity: 1 !important;
    transition: none !important;
}
/* A card should acknowledge inspection without acting like a button.  This
 * shared selector covers native Streamlit bordered containers and the
 * first-party information-card families; page-specific cards can retain the
 * same rule locally when they need a more specific surface treatment. */
@media (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference) {
    :is(
        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stVerticalBlockBorderWrapper"]:has(.personal-trend-marker),
        .st-key-personal_weight_trend_card,
        .drc-core-card,
        .drc-detail-card,
        .drc-sleep-card,
        .drc-baseline-card,
        .drc-sleep-guidance-card,
        .drc-load-card,
        .drc-load-week,
        .drc-nutrient-card,
        .drc-feedback-card,
        .drc-today-nutrition-card,
        .rh-system-card,
        .rh-system-health,
        .rh-feedback-card,
        .rh-feedback-advice,
        .rh-feedback-summary,
        .personal-overview-section
    ) {
        transition: transform 180ms ease-out, box-shadow 180ms ease-out, border-color 180ms ease-out;
    }
    :is(
        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stVerticalBlockBorderWrapper"]:has(.personal-trend-marker),
        .st-key-personal_weight_trend_card,
        .drc-core-card,
        .drc-detail-card,
        .drc-sleep-card,
        .drc-baseline-card,
        .drc-sleep-guidance-card,
        .drc-load-card,
        .drc-load-week,
        .drc-nutrient-card,
        .drc-feedback-card,
        .drc-today-nutrition-card,
        .rh-system-card,
        .rh-system-health,
        .rh-feedback-card,
        .rh-feedback-advice,
        .rh-feedback-summary,
        .personal-overview-section
    ):hover {
        transform: translateY(-1px);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, .18), 0 20px 36px rgba(0, 0, 0, .14);
    }
}
html {
    /* Keep the content width identical whether a page needs to scroll or not. */
    overflow-y: scroll;
    scrollbar-gutter: stable;
}
/* Streamlit scrolls inside its main panel on some versions, rather than on
   the document. Reserve one gutter on that panel's scrollbar side. Do not
   use `both-edges`: its inherited left gutter shifts the sidebar and page
   content sideways while a new route is mounting. */
section[data-testid="stMain"],
section.stMain {
    overflow-y: scroll;
    scrollbar-gutter: stable;
}
html,
body,
section[data-testid="stMain"] {
    min-height: 100%;
}
@media (min-width: 768px) {
    /* Streamlit otherwise recalculates this width while a new page mounts. */
    [data-testid="stSidebar"] {
        min-width: 15.875rem !important;
        max-width: 15.875rem !important;
    }
}
@media (max-width: 767px) {
    :root {
        --rh-page-top: 1rem;
        --rh-page-bottom: 2rem;
        --drc-page-title-size: 1.75rem;
        --drc-section-title-size: 1.2rem;
        --drc-subsection-title-size: 1rem;
    }
}
</style>
"""


def render_app_shell_styles(streamlit):
    """Apply navigation-stable dimensions shared by every app page."""
    streamlit.markdown(APP_SHELL_CSS, unsafe_allow_html=True)


def render_manual_input_styles(streamlit):
    """Apply shared page spacing and editable-control styling."""
    streamlit.markdown(MANUAL_INPUT_CSS, unsafe_allow_html=True)
