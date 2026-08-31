"""Direct-manipulation editor for a normalized screenshot OCR region."""

import base64
import io
from pathlib import Path

from PIL import Image
import streamlit.components.v1 as components


_COMPONENT = components.declare_component(
    "rhythmos_region_calibrator",
    path=str(Path(__file__).with_name("region_calibrator_frontend")),
)


def _image_data_url(path: str | Path) -> str:
    """Provide a browser-safe PNG preview, including for HEIC uploads."""
    with Image.open(path) as image:
        preview = image.convert("RGB")
        buffer = io.BytesIO()
        preview.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_region_calibrator(*, image_path: str | Path, region: dict, key: str):
    """Render a draggable region and return normalized coordinates on release."""
    coordinates = {name: float(region[name]) for name in ("x", "y", "width", "height")}
    return _COMPONENT(
        image_url=_image_data_url(image_path),
        region=coordinates,
        default=None,
        key=key,
    )
