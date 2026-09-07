# RHYTHMOS iOS

This directory is the native iOS client. It deliberately does not embed the
macOS Streamlit dashboard or open its SQLite database in place.

## Current scope

- SwiftUI shell for iOS 17+.
- A calm, local-first Today surface with explicit missing-data states.
- A local manual check-in for subjective recovery, training intent, and an
  optional note. It stays separate from Polar measurements and never changes
  imported measurements.
- A repository protocol and deterministic sample repository so UI work can
  proceed without live health credentials or a backend.
- Unit coverage for readiness state mapping.

## Open in Xcode

Open `RHYTHMOS.xcodeproj`, choose an iOS 17+ simulator, and run the
`RHYTHMOS` scheme. Before installing on a physical device, set a unique bundle
identifier and your Apple development team in the target's Signing settings.

## Non-goals of this scaffold

- Polar automatic sync is intentionally routed through a secure backend; the
  app never embeds a Polar client secret or refresh token. See
  [`docs/POLAR_IOS_AUTO_SYNC.md`](../docs/POLAR_IOS_AUTO_SYNC.md).
- No HealthKit permission is requested yet.
- No direct reuse of `data/recovery.db`; its migrations and Python-only
  algorithms remain desktop-owned until a versioned export/import contract is
  implemented.

See [`docs/IOS_DEVELOPMENT.md`](../docs/IOS_DEVELOPMENT.md) for the migration
boundary and phased delivery plan.
