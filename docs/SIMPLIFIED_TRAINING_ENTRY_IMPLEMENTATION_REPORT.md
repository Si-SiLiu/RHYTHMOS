# Simplified Training Entry Implementation Report

# Goal

Keep the complete professional training model while making everyday post-workout entry fast, conditional, bilingual, local, and suitable for narrower screens.

# Previous Interface

Every exercise displayed category, mode, muscle, equipment, laterality, proficiency, notes, and nearly every set field at once. Set shortcuts and destructive actions competed for the same row.

# New Simple Mode

Simple mode is the default. A strength action shows action name, measurement mode, set number, load, unit, repetitions, and the selected RPE or RIR scale. Notes and catalog metadata are available on demand. New post-entry sets default to completed.

# Advanced Mode

Advanced mode exposes applicable professional fields such as set type, RPE, RIR, rest, side, completion, and notes. It still filters fields that do not make sense for the current measurement mode.

# Conditional Field Rules

Seven measurement modes have explicit visible-field rules. Dance/freeform use practice segments and omit load, repetitions, RIR, and set type. Pace has no schema field, so distance/time retains distance, duration, resistance, and incline without a migration.

# RPE and RIR Preference

The session-level preference is RPE, RIR, or none, defaulting to RPE. Simple mode shows only the selected scale. Advanced mode can show both where applicable. No conversion is performed and the unselected stored value is not removed.

# Exercise Catalog Auto-Fill

Selecting a catalog action fills category, measurement mode, primary muscle, equipment, laterality, and a mode-derived load unit. Simple mode shows these under “View exercise information”.

# Custom Exercise Flow

Custom actions require name, category, and measurement mode. “This session only” is the default. The catalog is written only when “Save to exercise library” is explicitly selected and the main save succeeds through the service.

# Set Entry Layout

Primary rows contain set/practice-segment number plus at most four inputs. Additional applicable advanced fields wrap into separate rows. Inputs remain centered, with theme-neutral responsive CSS.

# Simplified Actions

The main set actions are Add set, Copy previous set, and More actions. Batch copy (1–20) and confirmed set deletion are collapsed. Exercise copy, reorder, confirmed delete, and historical copy are also collapsed.

# Hidden Field Preservation

Visibility helpers are pure and never mutate dictionaries. Mode switching only changes controls. Measurement-mode changes warn about incompatible retained values; they do not silently clear them. Save failures do not clear editor state.

# Responsive Layout

No simple row renders eight to ten inputs. Primary fields are capped at four plus the set label; extra fields wrap. Theme-neutral CSS supports light/dark themes and ordinary 80%, 100%, and 125% zoom.

# Internationalization

All new labels exist with matching leaf keys in Simplified Chinese, Traditional Chinese and English. The i18n coverage check reports zero direct Streamlit literals.

# Tests

Forty-seven numbered acceptance tests plus two catalog-service tests cover modes, dynamic fields, catalog behavior, custom confirmation, RPE/RIR, operations, layout, localization, rerun safety, regressions, privacy, and no-cloud behavior.

# Regression Results

The full suite passes. Strength volume, working-set count, muscle-group counts, Polar priority, Recovery, Baseline, and Confidence remain unchanged. SQLite schema stays at 0.15.0 with no migration.

# Version Changes

App 0.28.0; Dashboard 1.9.0; Training Logging 2.0.0; Training Entry UI 1.0.0. Database Schema remains 0.15.0. Recovery, Baseline, and Confidence remain 1.0.0.

# Documentation Updated

README, Training Logging, Exercise Catalog, Internationalization, Architecture, Current State, Handoff, Roadmap, Changelog, Quality Gate, release note, and ADR are synchronized.

# Known Limitations

Entry-mode and exertion preferences are session-scoped. Pace and secondary-muscle editing have no matching current training-exercise fields. Real-time set-completion preferences remain future work; this UI is optimized for post-entry.

# Quality Gate Result

**PASS.** Simple is the default; strength shows only load/unit/reps and selected effort; catalog metadata auto-fills; dynamic modes work; advanced data is preserved; algorithms are unchanged; tests, i18n, browser, integrity, and packaging checks pass.
