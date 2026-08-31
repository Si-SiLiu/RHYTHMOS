# RHYTHMOS Project Memory

## Project Identity
- **Name**: RHYTHMOS｜律衡 (Personal Performance OS · 个人表现与恢复系统)
- **Location**: /Users/liuxi/Documents/RHYTHMOS (sole canonical workspace)
- **Build output**: dist/RHYTHMOS.app
- **Tech stack**: Python (Streamlit + Flask), SQLite, Polar API, Kubios HRV, macOS native wrapper, Node/Playwright for cognitive tests
- **i18n**: zh-CN, zh-TW, en

## Architecture Layers
0. External sources (Polar API, Kubios CSV, manual input)
1. Client/OAuth/Fetch (polar_oauth, polar_client, polar_fetch)
2. Raw files + raw tables (data/raw/*.json, polar_*_raw)
3. Daily metrics (daily_recovery_metrics)
4. Baseline Engine (28-day rolling, 7-day minimum)
5. Recovery Engine v1.0.0 (personal baseline scoring)
6. Confidence Engine (independent sidecar) + Local Coach (deterministic advice)
7. Dashboard (read-only Streamlit) + Report + AI Context

## Strict Boundary Rules
- Display layer cannot call Polar API directly
- Algorithm layer cannot import Streamlit
- Client layer cannot import scoring modules
- Raw layer cannot depend on derived tables
- Only db.py write side can run migrations
- Dashboard uses SQLite mode=ro (read-only)
- AI Coach is blocked (no cloud provider approved)

## Current State (as of 2026-08-05)
- App v0.31.0, Schema 0.41.0 (41 migrations)
- 48 days of scored data (2026-06-13 to 2026-08-05)
- project_state.json is STALE (last regenerated 2026-07-26, shows 0.33.0)
- Recent work: Neural Readiness, Cognitive Training, Performance Planner, Nutrition Targets, Food OCR
- Cloud AI Provider: BLOCKED (ZDR requirements unmet)

## Key Commands
- Run app: `.venv/bin/python src/polar_oauth.py` (port 5000)
- Dashboard: `.venv/bin/streamlit run src/dashboard.py` (port 8501)
- One-click sync: `.venv/bin/python src/sync_pipeline.py`
- Regenerate state: `.venv/bin/python scripts/update_project_state.py`
- Run tests: `.venv/bin/python -m unittest discover -s tests`
- Build macOS app: `.venv/bin/python scripts/build_macos_app.py`
