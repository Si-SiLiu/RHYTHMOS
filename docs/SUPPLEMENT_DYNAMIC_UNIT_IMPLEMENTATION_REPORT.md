# SUPPLEMENT_DYNAMIC_UNIT_IMPLEMENTATION_REPORT

## Goal
Replace gram-only supplement recording with a unit-safe model and add Recovery history.

## Previous Design
Supplements reused name plus `剂量（克）` with only g/ml storage.

## New Dose Model
Name + quantity + unit + optional paired active amount/unit + timing + notes.

## Supported Units
g, mg, mcg, ml, capsule, tablet, sachet, scoop, drop, iu.

## Supplement Catalog
Ten built-ins cover creatine, protein powder, fish oil, lutein, D3, D3K2,
magnesium, electrolyte powder, caffeine tablet and collagen.

## Default Unit Rules
Creatine defaults to g; fish oil/lutein/vitamins to capsule; magnesium to tablet.

## Database Migration
Schema 0.12.0 rebuilds the item table, adds constraints and seeds the catalog.

## Legacy Data Migration
Historical gram quantities remain unchanged with `unit='g'`.

## Dashboard Changes
Supplement rows use quantity, unit selectbox, optional active dose, timing,
notes, and add/remove controls. `剂量（克）` is absent from this region.
History combines an optional component note with its active dose, for example
`鱼油：1 粒 (EPA+DHA 840 毫克)`.

## Internationalization
All supplement fields and units support Simplified Chinese, Traditional Chinese and English.

## Nutrition Summary Behavior
Only matching name/unit pairs aggregate; unlike units remain separate.

## AI Context Changes
Original units and optional active dose are retained; notes are excluded.

## Tests
Migration, constraints, catalog, CRUD, summaries, AI units and i18n are covered.

## Regression Results
589/589 automated tests pass. Streamlit smoke testing verified the dynamic
supplement controls and Recovery history. Recovery, Baseline and Confidence
versions/formulas remain unchanged; no cloud AI or credential access was introduced.

## Version Changes
App 0.24.0; schema 0.12.0; Dashboard 1.5.0; Nutrition 3.0.0; AI Context 1.1.0.

## Documentation Updated
Nutrition, database, dictionary, architecture, roadmap, changelog, i18n,
AI Context, quality gate, ADR, release and handoff records.

## Known Limitations
No automatic conversion or serving-size inference; maximum five rows per meal.

## Quality Gate Result
PASS. `剂量（克）` is fully replaced within the supplement region; creatine
defaults to g; fish oil, lutein and vitamins default to capsule; magnesium
defaults to tablet; legacy data is retained; unlike units are never summed;
SQLite integrity is `ok`; all existing and new tests pass.
