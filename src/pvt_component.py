"""A small local Streamlit component for browser-timed PVT sessions."""

from pathlib import Path

import streamlit.components.v1 as components


_COMPONENT = components.declare_component(
    "rhythmos_pvt_runner", path=str(Path(__file__).with_name("pvt_component_frontend"))
)


def render_pvt(*, run_id: str, duration_seconds: int, practice: bool = False,
               protocol_version: str = "alertness_probe_v1"):
    """Render one browser-owned PVT run and return its final payload once."""
    return _COMPONENT(
        run_id=run_id,
        duration_seconds=duration_seconds,
        practice=practice,
        protocol_version=protocol_version,
        default=None,
        key=f"rhythmos_pvt_{run_id}",
    )
