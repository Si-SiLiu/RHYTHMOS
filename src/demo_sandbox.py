"""Per-browser-session anonymous SQLite sandboxes for the public demo."""

from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from uuid import uuid4

# Use the same absolute package import as the Streamlit entrypoint and pages.
# Community Cloud can execute a page with a non-package ``__package__`` value,
# where a relative import such as ``from .db`` fails even though ``src`` is on
# sys.path.
from src.db import DB_PATH, connect, set_current_db_path


DEMO_ROOT = Path(tempfile.gettempdir()) / "daily-recovery-coach-demo"
SESSIONS_ROOT = DEMO_ROOT / "sessions"
SANDBOX_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
SANDBOX_ID_KEY = "drc_demo_sandbox_id"
SANDBOX_DB_PATH_KEY = "drc_demo_db_path"
SANDBOX_SEEDED_KEY = "drc_demo_seeded"
SANDBOX_QUERY_KEY = "drc_demo_session"
LAST_ACCESS_FILENAME = ".last_access"
SANDBOX_TTL_SECONDS = 24 * 60 * 60


def _session_state(st):
    return getattr(st, "session_state", st)


def _query_sandbox_id(st) -> str | None:
    query_params = getattr(st, "query_params", None)
    if query_params is None:
        return None
    try:
        value = query_params.get(SANDBOX_QUERY_KEY)
    except (AttributeError, KeyError, TypeError):
        return None
    return value if _valid_sandbox_id(value) else None


def _persist_query_sandbox_id(st, sandbox_id: str) -> None:
    query_params = getattr(st, "query_params", None)
    if query_params is None:
        return
    try:
        if query_params.get(SANDBOX_QUERY_KEY) != sandbox_id:
            query_params[SANDBOX_QUERY_KEY] = sandbox_id
    except (AttributeError, KeyError, TypeError):
        return


def is_demo_mode() -> bool:
    """Return whether the current process is the public synthetic-data demo."""
    return os.environ.get("DRC_DEMO_MODE") == "1"


def _valid_sandbox_id(value: object) -> bool:
    return isinstance(value, str) and SANDBOX_ID_PATTERN.fullmatch(value) is not None


def _sandbox_path(sandbox_id: str) -> Path:
    if not _valid_sandbox_id(sandbox_id):
        raise ValueError("Invalid demo sandbox id")
    path = (SESSIONS_ROOT / sandbox_id).resolve()
    root = SESSIONS_ROOT.resolve()
    if path.parent != root:
        raise ValueError("Demo sandbox path escaped sessions root")
    return path


def _touch_access(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        (path / LAST_ACCESS_FILENAME).touch()
    except OSError:
        pass


def get_demo_db_path(st) -> Path:
    """Return the current session's validated database path."""
    state = _session_state(st)
    sandbox_id = state.get(SANDBOX_ID_KEY)
    if not _valid_sandbox_id(sandbox_id):
        return ensure_demo_sandbox(st)
    path = _sandbox_path(sandbox_id)
    expected_db = path / "demo.db"
    stored_path = state.get(SANDBOX_DB_PATH_KEY)
    if stored_path and Path(stored_path).resolve() != expected_db.resolve():
        return ensure_demo_sandbox(st)
    _touch_access(path)
    return expected_db


def ensure_demo_sandbox(st) -> Path:
    """Create or reuse the current Streamlit session's anonymous database."""
    state = _session_state(st)
    SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)
    sandbox_id = state.get(SANDBOX_ID_KEY)
    if not _valid_sandbox_id(sandbox_id):
        sandbox_id = _query_sandbox_id(st)
        if sandbox_id:
            state[SANDBOX_ID_KEY] = sandbox_id
            state[SANDBOX_DB_PATH_KEY] = str(
                _sandbox_path(sandbox_id) / "demo.db"
            )
            state[SANDBOX_SEEDED_KEY] = (
                _sandbox_path(sandbox_id) / "demo.db"
            ).exists()
    cleanup_expired_sandboxes(current_sandbox_id=sandbox_id)
    if not _valid_sandbox_id(sandbox_id):
        sandbox_id = uuid4().hex
        path = _sandbox_path(sandbox_id)
        state[SANDBOX_ID_KEY] = sandbox_id
        state[SANDBOX_DB_PATH_KEY] = str(path / "demo.db")
        state[SANDBOX_SEEDED_KEY] = False
    else:
        path = _sandbox_path(sandbox_id)
        state[SANDBOX_DB_PATH_KEY] = str(path / "demo.db")
    _persist_query_sandbox_id(st, sandbox_id)
    db_path = path / "demo.db"
    if not state.get(SANDBOX_SEEDED_KEY) or not db_path.exists():
        seed_demo_database(db_path)
        state[SANDBOX_SEEDED_KEY] = True
    _touch_access(path)
    return db_path


def configure_demo_runtime(st) -> Path:
    """Configure the current database context, preserving local mode."""
    if not is_demo_mode():
        set_current_db_path(None)
        return DB_PATH
    db_path = ensure_demo_sandbox(st)
    set_current_db_path(db_path)
    return db_path


def reset_demo_sandbox(st) -> Path:
    """Delete only this session's sandbox and return a freshly seeded database."""
    state = _session_state(st)
    sandbox_id = state.get(SANDBOX_ID_KEY)
    if _valid_sandbox_id(sandbox_id):
        path = _sandbox_path(sandbox_id)
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError:
            pass
    for key in (SANDBOX_ID_KEY, SANDBOX_DB_PATH_KEY, SANDBOX_SEEDED_KEY):
        state.pop(key, None)
    new_path = ensure_demo_sandbox(st)
    set_current_db_path(new_path)
    return new_path


def cleanup_expired_sandboxes(
    *,
    current_sandbox_id: str | None = None,
    now: float | None = None,
    ttl_seconds: int = SANDBOX_TTL_SECONDS,
) -> None:
    """Best-effort cleanup of stale, validated sandbox directories."""
    now = time.time() if now is None else now
    try:
        children = list(SESSIONS_ROOT.iterdir()) if SESSIONS_ROOT.exists() else []
    except OSError:
        return
    for child in children:
        if not child.is_dir() or not _valid_sandbox_id(child.name):
            continue
        if child.name == current_sandbox_id:
            continue
        marker = child / LAST_ACCESS_FILENAME
        try:
            last_access = marker.stat().st_mtime if marker.exists() else child.stat().st_mtime
            if now - last_access > ttl_seconds:
                shutil.rmtree(child)
        except OSError:
            continue


def seed_demo_database(db_path: Path) -> None:
    """Initialize and seed one sandbox exactly once."""
    db_path = Path(db_path)
    with connect(db_path) as connection:
        existing = connection.execute("SELECT COUNT(*) FROM daily_recovery_metrics").fetchone()[0]
        if existing:
            return
        start = date.today() - timedelta(days=13)
        for offset in range(14):
            day = (start + timedelta(days=offset)).isoformat()
            sleep_score = 68 + (offset % 5) * 4
            hrv = 43 + (offset % 4) * 3
            connection.execute(
                """INSERT INTO daily_recovery_metrics
                (date, steps, calories, active_calories, activity_duration,
                 training_count, training_duration, training_calories,
                 sleep_duration, sleep_score, nightly_hrv_rmssd,
                 nightly_resting_hr, respiration_rate, morning_rmssd,
                 morning_mean_hr, kubios_readiness)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (day, 7200 + offset * 180, 2100 + offset * 12,
                 430 + offset * 8, "PT1H", 1 if offset % 3 else 0,
                 "PT45M" if offset % 3 else "PT0M", 320 if offset % 3 else 0,
                 "PT7H30M", sleep_score, hrv, 57 - (offset % 3),
                 14.2, hrv + 2, 58, "good" if sleep_score >= 76 else "fair"),
            )
            connection.execute(
                """INSERT INTO recovery_scores
                (date, recovery_score, activity_load_score, training_load_score,
                 hrv_score, morning_hr_score, readiness_score, recommendation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (day, min(92, 66 + offset), 70, 64, 74, 78, 72,
                 "Demo guidance: adjust today's load according to how you feel."),
            )
        connection.commit()
