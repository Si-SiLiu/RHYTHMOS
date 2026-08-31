"""Shared Streamlit table configuration with centered cell content."""

from __future__ import annotations

from html import escape
import math
from numbers import Real

import streamlit as st


def centered_text(label=None, **kwargs):
    return st.column_config.TextColumn(label, alignment="center", **kwargs)


def centered_number(label=None, **kwargs):
    return st.column_config.NumberColumn(label, alignment="center", **kwargs)


def centered_columns(data) -> dict:
    """Build centered configs for every visible column in a read-only table."""
    config = {}
    columns, rows = _tabular_values(data)
    for index, name in enumerate(columns):
        values = [row[index] for row in rows if index < len(row)]
        observed = [value for value in values if value is not None]
        if observed and all(isinstance(value, Real) and not isinstance(value, bool) for value in observed):
            config[name] = centered_number(str(name))
        else:
            config[name] = centered_text(str(name))
    return config


def centered_dataframe(data, **kwargs):
    """Render a scrollable read-only HTML table with truly centered headers."""
    # Do not leak Streamlit's DeltaGenerator return value to callers.  A bare
    # wrapper call can otherwise be picked up by Streamlit's magic display and
    # rendered as the internal DeltaGenerator help page.
    st.markdown(centered_table_html(data, **kwargs), unsafe_allow_html=True)


def _cell_text(value) -> str:
    if value is None:
        return "None"
    if isinstance(value, Real) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return "None"
        return f"{float(value):.4f}".rstrip("0").rstrip(".")
    # Avoid importing the full pandas stack merely to render a list of dicts.
    # DataFrame callers can still pass pandas' scalar missing values.
    if value.__class__.__module__.startswith("pandas") and str(value) in {"<NA>", "NaT"}:
        return "None"
    return str(value)


def _tabular_values(data) -> tuple[list, list[tuple]]:
    """Normalize common table inputs without eagerly importing pandas."""
    if hasattr(data, "columns") and hasattr(data, "itertuples"):
        return list(data.columns), list(data.itertuples(index=False, name=None))

    records = list(data or [])
    if not records:
        return [], []
    if isinstance(records[0], dict):
        columns = list(dict.fromkeys(key for record in records for key in record))
        return columns, [tuple(record.get(name) for name in columns) for record in records]
    return list(range(len(records[0]))), [tuple(record) for record in records]


def centered_table_html(data, max_height="32rem") -> str:
    """Build escaped table markup because Streamlit's canvas headers ignore CSS."""
    columns, values = _tabular_values(data)
    headers = "".join(f"<th>{escape(str(name))}</th>" for name in columns)
    rows = []
    for row in values:
        cells = "".join(f"<td>{escape(_cell_text(value))}</td>" for value in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"""
    <style>
    .drc-centered-table-wrap {{
        max-height: {escape(str(max_height))};
        overflow: auto;
        border-radius: 0.5rem;
    }}
    .drc-centered-table {{
        width: 100%;
        min-width: max-content;
        border-collapse: collapse;
        color: var(--text-color);
        font-size: 0.9rem;
    }}
    .drc-centered-table th,
    .drc-centered-table td {{
        height: 3.5rem;
        padding: 0 0.75rem;
        border: 1px solid rgba(128, 128, 128, 0.28);
        text-align: center !important;
        vertical-align: middle !important;
        line-height: 1.25rem;
        white-space: nowrap;
    }}
    .drc-centered-table th {{
        position: sticky;
        top: 0;
        z-index: 1;
        background: var(--secondary-background-color);
        font-weight: 600;
    }}
    </style>
    <div class="drc-centered-table-wrap">
      <table class="drc-centered-table">
        <thead><tr>{headers}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """
