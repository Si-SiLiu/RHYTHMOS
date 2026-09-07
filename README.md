# RHYTHMOS｜律衡

**Personal Performance OS**

> Know your state. Shape your day.
>
> 读懂状态，掌控节奏。

RHYTHMOS｜律衡 is a local-first personal performance system for understanding
recovery, training readiness, sleep, physiological state, and long-term human
performance. It is built for one practical daily decision: **how am I today,
why, and what should I do next?**

RHYTHMOS is currently a personal-use macOS application. It combines a native
macOS shell with a local Streamlit workspace and SQLite-backed data layer.

## What it helps answer

- **How am I today?** A recovery view brings together current measurements,
  personal baseline context, data confidence, and meaningful cautions.
- **Why?** Evidence modules show current values, typical range, baseline change,
  interpretation, and methodology notes without turning health data into a
  generic score dashboard.
- **What should I do?** Recovery, sleep, training, nutrition, and cognitive
  inputs inform local decision support and a deterministic local coach.
- **What needs attention?** Data freshness, quality, baseline maturity, and
  source alignment are surfaced separately from the underlying measurement.
- **How is my state changing?** Longitudinal views support personal trends
  across recovery, sleep, training load, body measures, and habits.

## Product areas

| Area | Purpose |
| --- | --- |
| Recovery | Morning RMSSD, resting heart rate, stress, respiratory rate, quality, personal baseline, and confidence context. |
| Sleep | Sleep duration, regularity, HRV/heart-rate context, trends, and correction workflows. |
| Training | Polar-backed sessions, structured manual training details, planned-vs-actual work, and cognitive practice. |
| Nutrition | Simple food logging, meal timing, supplements, catalog-backed entries, and daily feedback. |
| Personal | Body measurements, profile, goals, and compact longitudinal body trends. |
| System | Local data freshness, integrity, scheduled sync, source alignment, and operational feedback. |

## Principles

- **Local-first by default.** Health data, credentials, and the local database
  are intended to remain on the device.
- **Personal baseline over population comparison.** Recovery is interpreted
  against the person's own recent history when sufficient high-quality data is
  available.
- **Transparent evidence.** A conclusion should show the measurements and
  baseline context that support it.
- **Calm, precise UI.** The interface favors hierarchy, restrained surfaces,
  low cognitive load, and accessible motion over dashboard decoration.
- **Safety-aware decision support.** RHYTHMOS is not a medical device and does
  not provide diagnosis, treatment, or emergency guidance.

## Data and integrations

- **Polar:** OAuth-backed activity, training, sleep, and selected physiological
  inputs through the existing local sync pipeline.
- **Kubios HRV:** local screenshot import, review, normalization, and
  compatibility-oriented metric storage. Official API integration remains a
  future capability, not a requirement for using RHYTHMOS.
- **Manual inputs:** body, recovery, sleep, nutrition, supplements, training,
  and subjective context can be entered locally.
- **AI:** the default coach is deterministic and on-device. Any future cloud or
  third-party provider is approval-gated and must be configured explicitly.

## Quick start

### macOS application

Build target: Apple Silicon (M-series), macOS 14 or later, native arm64 Python
3.12, and an initialized Xcode/Command Line Tools installation. The retained
NumPy arm64 wheel requires macOS 14. Rosetta is not part of the supported runtime.

```bash
git clone https://github.com/Si-SiLiu/RHYTHMOS.git
cd RHYTHMOS
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=:all: -r requirements-macos-arm64.lock
.venv/bin/python scripts/build_macos_app.py
.venv/bin/python scripts/verify_apple_silicon.py
open dist/RHYTHMOS.app
```

The application starts a loopback-only local dashboard inside a native macOS
window. It does not require a public server.

The build command compiles both the arm64 app shell and local Vision OCR helper.
For the existing Intel workspace migration and its verification status, see
[Apple Silicon migration](docs/APPLE_SILICON.md).

### Development workspace

```bash
.venv/bin/python -m streamlit run src/dashboard.py --server.address 127.0.0.1
```

For Polar sync, copy the example environment file and fill in only your own
credentials locally:

```bash
cp .env.example .env
```

Never commit `.env`, OAuth tokens, SQLite databases, or private exports. Review
any generated report before sharing it outside your device.

## Quality and privacy notes

- The app is designed for personal performance, recovery, and lifestyle
  decision support—not medical diagnosis or treatment.
- Missing measurements remain missing; RHYTHMOS avoids fabricating a value or
  silently treating unavailable data as normal.
- A data confidence/maturity state is distinct from the recovery conclusion.
- Local source precedence and corrections preserve provenance instead of
  overwriting raw provider data.

## Documentation

- [Project overview](docs/PROJECT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Current state](docs/CURRENT_STATE.md)
- [Design system](docs/DESIGN_SYSTEM.md)
- [Recovery engine](docs/RECOVERY_ENGINE.md)
- [Sleep engine](docs/SLEEP_ENGINE.md)
- [Training logging](docs/TRAINING_LOGGING.md)
- [Nutrition logging](docs/NUTRITION_LOGGING.md)
- [Privacy](docs/PRIVACY.md)
- [AI coach design](docs/AI_COACH.md)
- [Testing](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)

## Development

Run the test suite with:

```bash
.venv/bin/python -m unittest discover -s tests
```

The version authority is [`config/versions.json`](config/versions.json). Use
the state updater after a completed development phase:

```bash
.venv/bin/python scripts/update_project_state.py
```

## Maintainer

Maintained by [@Si-SiLiu](https://github.com/Si-SiLiu). RHYTHMOS is evolving
primarily around personal-use needs; interfaces, integrations, and internal
schemas may change as the product matures.
