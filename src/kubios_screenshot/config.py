import json
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "kubios_screenshot_import.json"


@lru_cache(maxsize=4)
def load_config(path=CONFIG_PATH):
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {
        "parser_version", "supported_fields", "capture_fields", "minimum_required_fields",
        "field_aliases", "expected_units", "valid_ranges",
        "auto_accept_threshold", "manual_review_threshold", "reject_threshold",
        "date_formats", "time_formats", "image_preprocessing_defaults",
        "source_priority",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"Kubios screenshot config missing keys: {sorted(missing)}")
    return config
