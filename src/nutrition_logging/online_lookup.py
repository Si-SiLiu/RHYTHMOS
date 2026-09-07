"""Conservative online enrichment for manually entered foods.

The resolver only persists values when an exact (or brand-stripped exact)
Chinese food-name match is available from the public China CDC food
composition service.  A failed lookup is intentionally silent to the caller:
the user-entered food remains reusable but nutrition-limited instead of being
filled with a nearby, potentially incorrect result.
"""

from __future__ import annotations

from html.parser import HTMLParser
import re
import sqlite3
from typing import Any

import requests


_BASE_URL = "https://nlc.chinanutri.cn/fq"
_SEARCH_URL = f"{_BASE_URL}/FoodInfoQueryAction!queryFoodInfoList.do"
_TIMEOUT_SECONDS = 5
_KNOWN_OFFICIAL_ALIASES = {
    # The China CDC catalog uses these unambiguous longer display names.
    "鸡胸肉": "880",
    "米饭": "287",
    "面条": "264",
}


class _TableRows(HTMLParser):
    """Extract table-cell text without adding an HTML parsing dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _normalise_name(value: object, strip_brand: bool = False) -> str:
    text = str(value or "").strip().casefold()
    if strip_brand:
        text = re.sub(r"[（(][^）)]*[）)]", "", text)
    return re.sub(r"[\s·•、,，:：\-_/]+", "", text)


def _safe_name_match(user_name: str, source_name: str) -> bool:
    """Allow only identity and a small set of unambiguous food-name variants."""
    expected = _normalise_name(user_name)
    actual = _normalise_name(source_name)
    if expected == actual:
        return True
    aliases = {
        "鸡胸肉": {"鸡胸脯肉"},
        "米饭": {"米饭蒸均值"},
        "面条": {"面条均值"},
    }
    return actual in aliases.get(expected, set())


def _page_title(markup: str) -> str:
    for match in re.finditer(r"<h1[^>]*>(.*?)</h1>", markup, flags=re.IGNORECASE | re.DOTALL):
        title = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if title:
            return title
    return ""


def _first_number(value: object) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def _row_value(rows: list[list[str]], token: str) -> float | None:
    for row in rows:
        if not row or token not in row[0] or len(row) < 2:
            continue
        number = _first_number(row[1])
        if number is not None:
            return number
    return None


def _parse_food_page(markup: str) -> dict[str, float] | None:
    parser = _TableRows()
    parser.feed(markup)
    energy_kj = _row_value(parser.rows, "能量(Energy)")
    protein = _row_value(parser.rows, "蛋白质(Protein)")
    fat = _row_value(parser.rows, "脂肪(Fat)")
    carbohydrate = _row_value(parser.rows, "碳水化合物(CHO)")
    if None in (energy_kj, protein, fat, carbohydrate):
        return None
    fiber = _row_value(parser.rows, "总膳食纤维")
    water = _row_value(parser.rows, "水分(Water)")
    return {
        "calories_per_100g": round(float(energy_kj) / 4.184, 4),
        "protein_per_100g": float(protein),
        "carbohydrate_per_100g": float(carbohydrate),
        "fat_per_100g": float(fat),
        "fiber_per_100g": fiber,
        "water_per_100g": water,
    }


def enrich_manual_food_from_chinanutri(
    connection: sqlite3.Connection,
    food_catalog_id: int,
    food_name: str,
    *,
    session: Any = requests,
) -> dict[str, Any] | None:
    """Look up and save an exact manual-food match from China CDC's catalog.

    Returns saved metadata on success.  Returns ``None`` for unavailable
    network, an ambiguous/mismatched result, incomplete source data, or an
    already enriched item.  No lookup failure is raised into the meal editor.
    """
    name = str(food_name or "").strip()
    if not name:
        return None
    item = connection.execute(
        "SELECT nutrition_source,calories_per_100g FROM food_catalog WHERE id=? AND is_active=1",
        (int(food_catalog_id),),
    ).fetchone()
    if not item or item[0] != "manual_user_input" or item[1] is not None:
        return None

    food_id: str | None = None
    matched_name = ""
    try:
        response = session.post(
            _SEARCH_URL,
            data={
                "categoryOne": 0, "categoryTwo": 0, "foodName": name,
                "pageNum": 1, "field": "0", "flag": 0,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        for candidate in payload.get("list", []):
            if len(candidate) >= 3 and _safe_name_match(name, str(candidate[2])):
                food_id, matched_name = str(candidate[0]), str(candidate[2])
                break

        # The provider's legacy internal search sometimes returns an empty
        # result to non-browser clients.  Use only our verified official-name
        # aliases as fallback, rather than accepting a fuzzy web-search hit.
        if not food_id:
            known_id = _KNOWN_OFFICIAL_ALIASES.get(_normalise_name(name))
            if known_id:
                candidate_page = session.get(
                    f"{_BASE_URL}/foodinfo/{known_id}.html", timeout=_TIMEOUT_SECONDS,
                )
                candidate_page.raise_for_status()
                candidate_name = _page_title(candidate_page.text)
                if _safe_name_match(name, candidate_name):
                    food_id, matched_name, page = known_id, candidate_name, candidate_page
        if not food_id:
            return None
        if "page" not in locals():
            page = session.get(f"{_BASE_URL}/foodinfo/{food_id}.html", timeout=_TIMEOUT_SECONDS)
            page.raise_for_status()
    except (requests.RequestException, ValueError, TypeError):
        return None

    nutrition = _parse_food_page(page.text)
    if not nutrition:
        return None
    source = f"online_chinanutri_fq_{food_id}"
    connection.execute(
        """UPDATE food_catalog SET calories_per_100g=?,protein_per_100g=?,
               carbohydrate_per_100g=?,fat_per_100g=?,fiber_per_100g=?,water_per_100g=?,
               nutrition_source=?,data_quality='reference',updated_at=CURRENT_TIMESTAMP
             WHERE id=? AND nutrition_source='manual_user_input'""",
        (
            nutrition["calories_per_100g"], nutrition["protein_per_100g"],
            nutrition["carbohydrate_per_100g"], nutrition["fat_per_100g"],
            nutrition["fiber_per_100g"], nutrition["water_per_100g"], source,
            int(food_catalog_id),
        ),
    )
    return {"food_catalog_id": int(food_catalog_id), "matched_name": matched_name, "source": source}
