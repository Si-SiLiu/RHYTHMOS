"""Locale parsing and supported-language policy."""

from .models import Language


DEFAULT_LANGUAGE = "zh-CN"
SUPPORTED_LANGUAGES = {
    "zh-CN": Language("zh-CN", "简体中文"),
    "zh-TW": Language("zh-TW", "繁體中文"),
    "en": Language("en", "English"),
}


def normalize_language(value: object, default: str = DEFAULT_LANGUAGE) -> str:
    """Return a supported language code without guessing unsupported locales."""
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    aliases = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "zh_tw": "zh-TW",
        "zh-tw": "zh-TW",
        "zh_hant": "zh-TW",
        "zh-hant": "zh-TW",
        "zh_hk": "zh-TW",
        "zh-hk": "zh-TW",
        "en-us": "en",
        "en_us": "en",
        "en-gb": "en",
    }
    candidate = aliases.get(candidate.lower(), candidate)
    return candidate if candidate in SUPPORTED_LANGUAGES else default
