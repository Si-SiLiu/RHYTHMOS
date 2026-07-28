"""Shared styling for Streamlit controls used for manual data entry."""


MANUAL_INPUT_CSS = """
<style>
/* Keep the first page section aligned across the main app pages. */
section[data-testid="stMain"] > div[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] [data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .main .block-container {
    padding-top: .5rem !important;
    padding-bottom: 2rem !important;
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
html {
    /* Keep the content width identical whether a page needs to scroll or not. */
    overflow-y: scroll;
    scrollbar-gutter: stable;
}
html,
body,
[data-testid="stAppViewContainer"],
section[data-testid="stMain"] {
    min-height: 100%;
}
@media (min-width: 768px) {
    /* Streamlit otherwise recalculates this width while a new page mounts. */
    [data-testid="stSidebar"] {
        min-width: 21rem !important;
        max-width: 21rem !important;
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
