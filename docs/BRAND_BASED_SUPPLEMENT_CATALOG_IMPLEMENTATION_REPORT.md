# BRAND_BASED_SUPPLEMENT_CATALOG_IMPLEMENTATION_REPORT

## Goal

Replace repeated daily active-ingredient entry with reusable brand/product
profiles while retaining provenance, version history and local safety gates.

## Previous Daily Input Model

Supplement name, intake quantity/unit and optional manually repeated active
ingredient name/amount/unit.

## New Daily Input Model

Brand, product, quantity, unit, meal time as intake time, optional note and row
actions. Recent/favorite products, row copy and meal-copy shortcuts are supported.

## Removed Daily Fields

Active ingredient name, amount and unit are absent from the default daily editor.
Their legacy database columns remain for compatibility.

## Brand and Product Fields

Known profiles are selected by searchable brand and product controls; unmatched
products can save a custom brand/product with an explicit unverified state.

## Product Catalog

Profiles store identity, variant, barcode, region, form, kind, serving, version,
label references, source, verification and soft deletion.

## Ingredient Model

Multiple active/nutrient ingredients belong to a product version. Carrier and
excipient roles are retained but excluded from ordinary AI/nutrition analysis.

## Product Versioning

Formula/label versions, valid dates, hashes and `supersedes_product_id` preserve
history; old formulas are never overwritten.

## Daily Intake Records

`supplement_intake_records` references a profile or stores custom brand/product.
Legacy rows remain linked through an immutable compatibility ID.

## Effective Ingredient Calculation

Only confirmed/verified, non-stale profiles with an exact serving-unit match are
calculated. Multiplication is deterministic. Unknown values remain unavailable.

## Barcode Flow

Local exact matching and candidate contracts are present; external lookup is
blocked until a provider is approved.

## Label OCR Flow

Image path and candidate contracts are present. OCR is reserved; future results
must remain candidates until user confirmation.

## AI-Assisted Search Architecture

Provider-neutral models, provider interface, resolver, validation and source rank
are implemented. AI may propose candidates but cannot author facts.

## Provider Gate Status

`provider_blocked`; no cloud request is made.

## User Confirmation Workflow

The product panel shows status and ingredients and requires an explicit confirm
action. Confirmation records verification time.

## Medication Separation

Medication is a separate product kind. Finasteride is forced into that kind and
does not enter supplement calculation or dose advice.

## Legacy Data Migration

Migration 0.15.0 is backed up, ledgered, idempotent and conservative. Existing
active ingredient columns are retained. The real database contained no legacy
supplement rows at migration time, so zero product/intake rows were synthesized.

## Dashboard Changes

The default Supplement grid is Brand | Product | Quantity | Unit | Actions.
Product creation/search/information/confirmation is local and separate.

## Internationalization

Simplified Chinese, Traditional Chinese and English product, verification, source and medication
labels were added.

## AI Context Changes

Confirmed ingredients are allowlisted; unconfirmed products export identity,
quantity, unit and status only. Notes and images remain excluded.

## Tests

Fifty-one focused product/migration/safety scenarios were added in addition to
the existing suite.

## Regression Results

The full local suite passes: 671 tests run, 671 passed, zero failed. The focused
brand-based supplement module contributes 51 migration, catalog, safety, UI and
regression scenarios.

## Version Changes

App 0.27.0; schema 0.15.0; Dashboard 1.8.0; Nutrition 5.0.0; Supplement
Catalog 2.0.0; Product Enrichment 1.0.0; AI Context 1.4.0.

## Documentation Updated

Catalog, enrichment, nutrition, database, dictionary, architecture, AI, provider,
i18n, state, handoff, roadmap, changelog, quality gate, README, ADR and release.

## Known Limitations

Barcode lookup and label OCR are contract-only until an approved provider/local
recognizer exists. No external product data is bundled.

## Quality Gate Result

PASS. Database integrity, foreign keys, migration ledger, Provider Gate,
localization, AI collaboration and the complete regression suite pass.
