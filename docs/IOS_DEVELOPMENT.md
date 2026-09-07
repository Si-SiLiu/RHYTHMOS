# iOS development plan

## Decision

RHYTHMOS iOS will be a native SwiftUI client, targeting iOS 17 and later. The
current macOS product remains supported at `dist/RHYTHMOS.app`; this work neither
rebuilds it nor changes its local data. The iOS client must not embed Streamlit,
run a loopback Python server, or open the macOS `data/recovery.db` directly.

Those shortcuts would produce a fragile mobile UI, make iOS background behavior
unreliable, and bypass the current database migration and provenance rules.

## Initial project

[`ios/RHYTHMOS`](../ios/RHYTHMOS) contains the first runnable SwiftUI project:

- `Today` presents readiness, data confidence, and next action without turning
  absent measurements into normal values.
- `DashboardRepository` isolates the presentation layer from storage and future
  data-source decisions.
- The Today toolbar supports a user-selected `MobileDailySnapshot v1` JSON
  import. After validation, it stores an approved snapshot only in the iOS App
  Sandbox so it remains available on later launches. The app does not retain
  folder access or silently copy the desktop database; the user can remove the
  stored snapshot from the same menu.
- The sample repository intentionally displays an insufficient-data state. It
  is safe to run on a simulator and requests no health or account permission.
- The project has a small XCTest target for the readiness-state contract.

## Mobile data boundary

The current Python stack remains authoritative for raw Polar/Kubios ingestion,
normalization, daily metrics, baseline, recovery, confidence, and provenance.
The iOS app should consume a versioned, mobile-safe projection—not raw JSON,
Polar tokens, the desktop SQLite file, or cloud AI context.

```mermaid
flowchart LR
    H[HealthKit — future] --> M[Mobile local store]
    P[Polar — future OAuth] --> M
    M --> C[Versioned daily projection]
    D[Desktop Python + SQLite] --> C
    C --> U[SwiftUI client]
```

The synchronization design still needs an explicit product decision:

1. **Independent local stores** — iPhone computes its own projection from
   HealthKit/Polar. Best privacy and offline behavior; requires a Swift port of
   deterministic algorithms and migration tests.
2. **Encrypted user-approved export/import** — desktop exports only an
   allowlisted, versioned projection for the iPhone. Fastest bridge; no
   background cross-device sync.
3. **End-to-end encrypted sync service** — best device continuity; needs an
   account model, conflict policy, security review, and operating service.

Do not select or implement one implicitly. In all cases, raw provenance must be
preserved, source authority stays Polar-first where currently defined, and a
missing value remains missing.

## Phased delivery

| Phase | Outcome | Gate |
| --- | --- | --- |
| 0 | Native shell, design tokens, sample states | Builds and tests on iOS simulator |
| 1 | Read-only Today, Recovery, Sleep, Training projections | Versioned mobile DTO and fixtures approved |
| 2 | Local manual morning, sleep, training, and nutrition logging | Validation and conflict rules match product policy |
| 3 | HealthKit read integration | Permission UX, data mapping, privacy text, and reconciliation tests approved |
| 4 | Polar OAuth and sync choice | Registered redirect, secure token storage, background behavior verified |
| 5 | Trends, plans, accessibility, localization, TestFlight | Device QA, privacy review, and no-data/migration tests pass |

## Security and App Store constraints

- Keep tokens in Keychain; never in `UserDefaults`, logs, or exported snapshots.
- HealthKit authorization is requested only when Phase 3 has a clear user-facing
  use; add purpose text and capability at that point.
- Health measurements remain local by default. Any cross-device transfer must
  be explicit, encrypted, and documented.
- Do not claim diagnosis, treatment, or emergency guidance. Preserve the
  existing safety language and transparent evidence model.
- Add Privacy Manifest, export controls, app icon, screenshots, and supported
  language metadata before TestFlight—not as a final release afterthought.

## Immediate next implementation task

`MobileDailySnapshot v1` is now implemented by
[`src/mobile_snapshot.py`](../src/mobile_snapshot.py). It contains only the
Today screen's resolved values, compact provenance, recovery confidence, and
training summary. The CLI reads SQLite in read-only mode:

```bash
.venv/bin/python scripts/export_mobile_snapshot.py \
  --output /secure/user-approved/location/today.json
```

No raw JSON, OAuth material, free-text notes, or desktop row identifiers are
included. This is the lowest-risk shared contract: iOS can now work with real
data states before selecting a cross-device synchronization architecture.
