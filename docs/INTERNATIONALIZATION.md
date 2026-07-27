# Internationalization v1.0

Structured training labels, actions, statuses, exercise categories, measurement
modes, set types, load units and sides have matching `zh-CN`, `zh-TW` and `en`
keys.
Canonical database codes and UUIDs are language-independent.

Simple nutrition labels, actions, statuses, summaries and twelve food units are
available in matching `zh-CN`, `zh-TW` and `en` keys. Stored unit and catalog canonical
codes remain language-independent.

Supplement codes are presentation-independent. Chinese renders 克、毫克、微克、
毫升、粒、片、袋、勺、滴、国际单位; English renders g, mg, μg, mL, capsule,
tablet, sachet, scoop, drop, IU.

## Kubios metrics

All core and advanced Kubios metric names, definitions, safety notes, page
navigation, grouping controls, empty states, and report labels are present in
`zh-CN`, `zh-TW` and `en` with identical keys. Stored field names, source codes, units,
and formulas remain language-neutral.

Kubios Screenshot Import adds matching `kubios_screenshot.*` Chinese and
English resources for upload, recognition, per-field confidence, manual edit,
confirmation, conflicts, batch status, deletion, privacy and safe failures.
Internal import statuses, source types and conflict choices remain stable
English codes and are localized only at the presentation boundary.

## Supported languages

- `zh-CN` — 简体中文
- `zh-TW` — 繁體中文
- `en` — English

The default is `zh-CN`. The Dashboard and Daily Log show language names in
their own language and do not use flags.

## Architecture

`src/i18n/translator.py` loads UTF-8 JSON resources and performs safe
placeholder formatting. `locale.py` owns supported codes and normalization;
`storage.py` owns local preference persistence; `validation.py` requires
identical leaf keys; `models.py` defines typed resources; `formatters.py`
formats dates, numbers, percentages, and durations; `ui.py` owns shared
Streamlit selection and navigation.

Resources live in `locales/zh-CN.json`, `locales/zh-TW.json` and
`locales/en.json`. Keys are grouped
by common UI, navigation, Dashboard, metrics, Recovery, Confidence, baseline,
Local Coach, Personal Logging, AI Context, System Status, sync, reports,
errors, and safety.

## Preference

`config/user_preferences.json` contains only `{ "language": "..." }`. It does
not contain health or identity data. Writes are atomic and idempotent. A
missing, malformed, or unsupported value falls back to `zh-CN`; `.env` is not
used.

## Adding a language

1. Add its code and self-displayed name to `SUPPORTED_LANGUAGES`.
2. Copy an existing locale JSON and translate every value without changing keys.
3. Preserve health meaning, Recovery/Confidence distinction, Local Coach
   deterministic boundary, and complete safety language.
4. Run `scripts/check_i18n_coverage.py` and the complete test suite.
5. Perform a usability review before release.

## Internal codes versus display text

Database values and machine contracts remain stable English codes. For example,
`breakfast`, `strength`, `normal_training`, `high`, and
`moderate_reduction` are stored or exported unchanged; only presentation uses
translated labels. Language changes do not write health tables.

## Dates, numbers, and units

Chinese dates use `2026年7月15日`; English dates use `July 15, 2026`. All
languages remain metric. Missing values display using the selected locale.
Formatting occurs only at the display/export-rendering boundary.

## Fallback

Lookup order is selected locale, `zh-CN`, then `[missing: key]`. Missing keys
and formatting errors are logged. The UI never silently renders an empty value
and translation failure does not crash the application.

## Reports and exports

`python -m src.report --language zh-CN|zh-TW|en` writes Markdown to
`reports/{language-code}/`. CLI and pipeline entry points use the saved
preference when language is omitted. AI Context JSON keeps English keys and
enum codes, and adds `display_language` and `localized_summary`. Markdown is
localized; CSV headers remain stable English paths by default.

## Test requirements

All locale resources must load and share identical keys. Tests cover fallback,
formatting, preference corruption, navigation, chart labels, Recovery,
Confidence, Local Coach, Personal Logging, reports, AI Context schema, CSV,
database non-mutation, icon access, no-network boundaries, and unchanged engine
imports. `scripts/check_i18n_coverage.py` scans direct user-visible Streamlit
literals while allowing internal codes and non-user identifiers.

## Known limitations

User-authored free text is not translated. Existing historical Local Coach text
remains stored in Chinese, but Dashboard and report presentation derive
localized wording from stable status codes. Machine-readable JSON/CSV fields
intentionally remain English. A usability review remains required for future
language additions.

Scheduler status, catch-up controls, manual activity/sleep/recovery forms,
validation guidance, scale direction, and source labels are present in
`zh-CN`, `zh-TW` and `en`. Stored canonical source codes and resolution reasons remain
language-independent; only presentation labels are localized.
# Supplement product catalog

Brand, product, variant, barcode, dosage form, product kind, serving,
verification, source, recent/favorite, candidate confirmation and medication
boundary labels are available in `zh-CN`, `zh-TW` and `en`. Stable database enum codes and
ingredient units do not change with the interface language.

## Simplified training entry

Simple/Advanced mode, RPE/RIR/none preference, action information, custom action
scope, practice segment, proficiency guidance, more actions, and delete
confirmation have matching `zh-CN`, `zh-TW` and `en` keys. Measurement-mode and database
enum codes remain stable English values.
