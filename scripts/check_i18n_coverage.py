"""Report direct user-visible literals in the primary Streamlit pages."""

import ast
from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PATHS = (
    BASE_DIR / "src" / "dashboard.py",
    *sorted((BASE_DIR / "src" / "pages").glob("*.py")),
)
VISIBLE_METHODS = {
    "title", "header", "subheader", "button", "warning", "error", "info",
    "success", "metric", "caption", "markdown", "write", "tabs", "date_input",
    "number_input", "text_input", "text_area", "selectbox", "multiselect",
    "checkbox", "form_submit_button",
}
ALLOWLIST = {"BMI"}


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip()
    if isinstance(node, ast.JoinedStr):
        literal = "".join(part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)).strip()
        # A dynamic HTML fragment can contain only tag names/classes in its
        # literal portions while the visible copy comes from translated
        # expressions (for example ``<div>{TR(...)} </div>``). Do not report
        # those structural fragments as hard-coded user-facing text.
        visible = re.sub(r"<[^>]*>", "", literal)
        return literal if re.search(r"[A-Za-z0-9\u4e00-\u9fff]", visible) else None
    if isinstance(node, (ast.Tuple, ast.List)):
        values = [_literal_text(item) for item in node.elts]
        if values and all(value is not None for value in values):
            return " | ".join(values)
    return None


def find_hardcoded(path: Path) -> list[tuple[int, str, str]]:
    """Return line, widget, and literal for direct display strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method not in VISIBLE_METHODS or not node.args:
            continue
        text = _literal_text(node.args[0])
        if text and text not in ALLOWLIST:
            violations.append((node.lineno, method, text))
    return sorted(violations)


def scan(paths=DEFAULT_PATHS) -> dict[Path, list[tuple[int, str, str]]]:
    return {Path(path): find_hardcoded(Path(path)) for path in paths}


def main() -> int:
    results = scan()
    violations = sum((items for items in results.values()), [])
    if not violations:
        print(f"i18n coverage: PASS ({len(results)} Streamlit pages, 0 direct literals)")
        return 0
    print("i18n coverage: FAIL")
    for path, items in results.items():
        for line, method, text in items:
            print(f"{path.relative_to(BASE_DIR)}:{line}: {method}: {text}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
