"""Stable RHYTHMOS｜律衡 branding assets with a non-failing Streamlit fallback."""

from pathlib import Path

from PIL import Image


BASE_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = BASE_DIR / "assets"
PAGE_ICON_PATH = ASSETS_DIR / "app_icon_64.png"
BRAND_ICON_PATH = ASSETS_DIR / "app_icon_256.png"

# The checked-in icon files intentionally remain unchanged for this release.
# They still contain the former Daily Recovery Coach wordmark and must be
# replaced with approved RHYTHMOS｜律衡 visual assets in a future design pass.
BRAND_NAME = "RHYTHMOS｜律衡"
POSITIONING_LINES = ("Personal Performance OS", "个人表现与恢复系统")
TAGLINE_LINES = ("Know your state. Shape your day.", "读懂状态，掌控节奏。")


def browser_page_title(section: str | None = None) -> str:
    """Return a consistent browser-tab title without changing page routes."""
    return BRAND_NAME if not section else f"{BRAND_NAME} · {section}"


def load_page_icon(path: Path = PAGE_ICON_PATH):
    """Return a detached PIL image or an emoji fallback when unavailable."""
    try:
        with Image.open(path) as image:
            return image.convert("RGBA").copy()
    except (OSError, ValueError):
        return "💚"


def brand_icon_path(path: Path = BRAND_ICON_PATH) -> Path | None:
    """Return the optimized brand asset only when it is locally readable."""
    return path if path.is_file() else None
