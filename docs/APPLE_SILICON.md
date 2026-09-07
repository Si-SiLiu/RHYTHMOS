# Apple Silicon migration

Target: native arm64 on M-series Macs. The app and Vision OCR helper compile for
macOS 14+, matching the minimum of the retained NumPy arm64 wheel. Python and
some libraries may retain universal2 binaries; their executed architecture must
be arm64. Universal2 does not imply Rosetta use.

## Workspace runtime

- Canonical project: `/Users/liuxi/Documents/RHYTHMOS`.
- Sole app output: `dist/RHYTHMOS.app`.
- Prepared Python environment: `.venv-arm64` (Python 3.12.7).
- Activation makes `.venv` an alias of `.venv-arm64` and retains the previous
  directory as `.venv-intel-backup`. The backup is for rollback, not active use.
- The native app explicitly starts Python with `/usr/bin/arch -arm64` for both
  dashboard and catch-up sync. The Python framework retains universal2 support.
- `requirements-macos-arm64.lock` preserves the existing package versions;
  installation uses compatible binary wheels instead of Intel extensions.
- The relocated `.venvsource` Python framework had invalid signatures. Its local
  runtime binaries were ad-hoc signed before native execution was validated.
- Activation/build scripts do not migrate, replace, or remove `data/`.
- Activation checks compiler availability before switching `.venv`.

## Commands

After preparing the environment with native Python and installing the lock file:

```sh
.venv-arm64/bin/python scripts/activate_arm64_runtime.py
.venv/bin/python scripts/build_macos_app.py
.venv/bin/python scripts/verify_apple_silicon.py
```

The builder rejects Intel Python and noncanonical app outputs, explicitly
targets arm64, checks compiled binaries, and signs the app before replacing the
installed bundle. A compilation/signing failure preserves the previous app.
The launcher's runtime fingerprint includes architecture to invalidate a cached
Rosetta dashboard process after migration.

The verifier imports the native dependencies and inspects all `.so`/`.dylib`
files in the active environment and base Python. Its default mode also checks
the app, OCR helper, and bundle signature. It does not access health records.

## Verification status — 2026-09-07

- Prepared native Python and 219 compatible native libraries: passed.
- Dependency consistency (`pip check`): passed.
- Final build, launcher, runtime, screenshot OCR and icon checks: 75 passed.
- Full arm64 suite: 1,099 tests, 9 failures and 8 errors. The same failed cases
  reproduce on Intel: stale governance/release snapshots, UI expectations,
  icon generation, training-plan import and pipeline expectations. The custom
  Intel comparison initially disabled logging, which additionally failed two
  logger tests; both pass with logging enabled. No new arm64 failure was found.
  The final suite has 1,098 cases after removing a redundant startup guard test.
- `.venv` now points to `.venv-arm64`; the old environment is inactive in
  `.venv-intel-backup` for recovery. No second desktop app was retained.
- App and OCR helper are both Mach-O arm64; bundle signature verification passed.
- Xcode license confirmation and `xcodebuild -runFirstLaunch` completed. Initial
  native launches stalled during system loading; after initialization and retry,
  the app entered its normal AppKit event loop and OCR recognized the fixture.
- Live process samples confirmed ARM64 for both RHYTHMOS and its Python service.
- Local service `/_stcore/health` returned `ok` on port 8501.
- Native OCR recognized 3 text blocks in the synthetic measurement-details
  fixture. User health records were not used for this check.
- The 75 final focused tests include the two icon-generation tests that failed
  before toolchain initialization. The historical full-suite failures above are
  recorded separately; a clean full-suite result is not claimed.

This is a locally ad-hoc signed application, not a notarized distribution build.
The native runtime was verified on macOS 26.6.2; macOS 14 is the build/dependency
minimum, not a separately tested system in this migration.
