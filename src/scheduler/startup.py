"""Non-blocking catch-up dispatch when a local RHYTHMOS page opens."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from .config import load_scheduler_config
from .history import SchedulerHistory
from .status import evaluate_catch_up


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StartupCatchUpDispatch:
    """Safe outcome for an app-open catch-up check."""

    state: str
    dispatched: bool
    pid: int | None = None


def start_catch_up_if_due(
    *,
    config_loader=load_scheduler_config,
    history_factory=SchedulerHistory,
    state_evaluator=evaluate_catch_up,
    process_factory=subprocess.Popen,
    project_root: Path | str = BASE_DIR,
) -> StartupCatchUpDispatch:
    """Queue one eligible catch-up without blocking the Streamlit render.

    The child uses the canonical scheduler runner, so its normal catch-up
    limit and process lock remain the authority if two app windows open at
    once.  This function deliberately performs no data or cloud work itself.
    """

    loaded = config_loader()
    state = state_evaluator(loaded.config, scheduler_history=history_factory())
    if not state.eligible:
        return StartupCatchUpDispatch(state.state, False)

    root = Path(project_root).resolve()
    runner = root / "scripts" / "run_scheduled_sync.py"
    python = root / ".venv" / "bin" / "python"
    if not runner.is_file() or not python.is_file():
        return StartupCatchUpDispatch("runtime_unavailable", False)
    try:
        process = process_factory(
            [str(python), str(runner), "--trigger-type", "catch_up"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return StartupCatchUpDispatch("dispatch_failed", False)
    return StartupCatchUpDispatch("queued", True, int(process.pid))
