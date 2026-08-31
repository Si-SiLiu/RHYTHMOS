import re

from .config import load_config


def normalized_label(value):
    return " ".join(re.sub(r"[^a-z0-9%]+", " ", str(value).lower()).split())


def alias_index(config=None):
    config = config or load_config()
    return {
        field: sorted(
            {normalized_label(field), *(normalized_label(alias) for alias in aliases)},
            key=len,
            reverse=True,
        )
        for field, aliases in config["field_aliases"].items()
    }


def match_field_label(text, config=None):
    normalized = normalized_label(text)
    matches = []
    for field, aliases in alias_index(config).items():
        for alias in aliases:
            if normalized == alias or normalized.startswith(alias + " "):
                matches.append((len(alias), field, alias))
    if matches:
        # Prefer the most specific label across every field. For example,
        # ``LF power n.u.`` must never be consumed by the shorter ``LF power``.
        _, field, alias = max(matches, key=lambda match: match[0])
        return field, alias
    return None, None
