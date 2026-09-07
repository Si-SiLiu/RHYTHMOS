"""Render and manage the user-level macOS LaunchAgent idempotently."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
from string import Template
import subprocess
import tempfile
from typing import Callable
from xml.sax.saxutils import escape

from .config import SchedulerConfig


BASE_DIR = Path(__file__).resolve().parents[2]
LABEL = "com.daily-recovery-coach.sync"
TEMPLATE_PATH = BASE_DIR / "config" / f"{LABEL}.plist.template"
DEFAULT_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_PLIST_PATH = DEFAULT_LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
DEFAULT_STANDARD_LOG_DIR = Path.home() / "Library" / "Logs" / "Daily Recovery Coach"
ALLOWED_PLIST_KEYS = {
    "Label",
    "ProgramArguments",
    "StartCalendarInterval",
    "RunAtLoad",
    "ProcessType",
    "StandardOutPath",
    "StandardErrorPath",
}


class LaunchAgentError(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchAgentInstallResult:
    path: Path
    changed: bool
    loaded: bool


@dataclass(frozen=True)
class LaunchAgentStatus:
    state: str
    installed: bool
    loaded: bool
    detail_code: str


def _project_paths(project_root: Path) -> dict[str, Path]:
    root = project_root.expanduser().resolve()
    return {
        "root": root,
        "launcher": Path("/usr/bin/env"),
        "python": root / ".venv" / "bin" / "python",
        "runner": root / "scripts" / "run_scheduled_sync.py",
        "stdout": DEFAULT_STANDARD_LOG_DIR / "scheduler.stdout.log",
        "stderr": DEFAULT_STANDARD_LOG_DIR / "scheduler.stderr.log",
    }


def render_launch_agent(
    project_root: Path | str,
    config: SchedulerConfig,
    template_path: Path | str = TEMPLATE_PATH,
    *,
    require_runtime: bool = True,
) -> bytes:
    """Render a validated plist without inheriting environment variables."""
    paths = _project_paths(Path(project_root))
    if require_runtime and not paths["python"].is_file():
        raise LaunchAgentError("SCHEDULER_PYTHON_NOT_FOUND")
    if require_runtime and not paths["runner"].is_file():
        raise LaunchAgentError("SCHEDULER_RUNNER_NOT_FOUND")
    try:
        template = Template(Path(template_path).read_text(encoding="utf-8"))
        schedule_intervals = "".join(
            "<dict><key>Hour</key><integer>"
            f"{int(value[:2])}"
            "</integer><key>Minute</key><integer>"
            f"{int(value[3:])}"
            "</integer></dict>"
            for value in config.scheduled_times
        )
        rendered = template.substitute(
            LABEL=escape(LABEL),
            LAUNCHER_EXECUTABLE=escape(str(paths["launcher"])),
            PYTHON_EXECUTABLE=escape(str(paths["python"])),
            RUNNER_SCRIPT=escape(str(paths["runner"])),
            SCHEDULE_INTERVALS=schedule_intervals,
            STANDARD_OUT_PATH=escape(str(paths["stdout"])),
            STANDARD_ERROR_PATH=escape(str(paths["stderr"])),
        )
        value = plistlib.loads(rendered.encode("utf-8"))
    except (OSError, KeyError, ValueError, plistlib.InvalidFileException) as exc:
        raise LaunchAgentError("SCHEDULER_PLIST_TEMPLATE_INVALID") from exc
    if set(value) != ALLOWED_PLIST_KEYS:
        raise LaunchAgentError("SCHEDULER_PLIST_FIELDS_INVALID")
    if value.get("Label") != LABEL or value.get("RunAtLoad") is not False:
        raise LaunchAgentError("SCHEDULER_PLIST_POLICY_INVALID")
    arguments = value.get("ProgramArguments")
    expected_arguments = [
        str(paths["launcher"]),
        str(paths["python"]),
        str(paths["runner"]),
        "--trigger-type",
        "scheduled",
    ]
    if arguments != expected_arguments:
        raise LaunchAgentError("SCHEDULER_PLIST_ARGUMENTS_INVALID")
    if "EnvironmentVariables" in value:
        raise LaunchAgentError("SCHEDULER_PLIST_ENVIRONMENT_FORBIDDEN")
    return plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=False)


def _atomic_write(path: Path, content: bytes) -> bool:
    previous = path.read_bytes() if path.exists() else None
    if previous == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as plist_file:
            plist_file.write(content)
            plist_file.flush()
            os.fsync(plist_file.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _run_launchctl(
    arguments: list[str],
    *,
    check: bool,
    command_runner: Callable = subprocess.run,
) -> subprocess.CompletedProcess:
    try:
        return command_runner(
            ["/bin/launchctl", *arguments],
            check=check,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LaunchAgentError("SCHEDULER_LAUNCHCTL_FAILED") from exc


def install_launch_agent(
    project_root: Path | str,
    config: SchedulerConfig,
    *,
    plist_path: Path | str = DEFAULT_PLIST_PATH,
    load: bool = True,
    command_runner: Callable = subprocess.run,
) -> LaunchAgentInstallResult:
    if not config.enabled:
        raise LaunchAgentError("SCHEDULER_DISABLED")
    destination = Path(plist_path).expanduser()
    content = render_launch_agent(project_root, config)
    DEFAULT_STANDARD_LOG_DIR.mkdir(parents=True, exist_ok=True)
    changed = _atomic_write(destination, content)
    loaded = False
    if load:
        domain = f"gui/{os.getuid()}"
        _run_launchctl(
            ["bootout", f"{domain}/{LABEL}"],
            check=False,
            command_runner=command_runner,
        )
        _run_launchctl(
            ["bootstrap", domain, str(destination)],
            check=True,
            command_runner=command_runner,
        )
        loaded = True
    return LaunchAgentInstallResult(destination, changed, loaded)


def uninstall_launch_agent(
    *,
    plist_path: Path | str = DEFAULT_PLIST_PATH,
    unload: bool = True,
    command_runner: Callable = subprocess.run,
) -> bool:
    """Unload and remove the plist; repeated calls are harmless."""
    destination = Path(plist_path).expanduser()
    existed = destination.exists()
    if unload and existed:
        _run_launchctl(
            ["bootout", f"gui/{os.getuid()}/{LABEL}"],
            check=False,
            command_runner=command_runner,
        )
    destination.unlink(missing_ok=True)
    return existed


def get_launch_agent_status(
    plist_path: Path | str = DEFAULT_PLIST_PATH,
    *,
    command_runner: Callable = subprocess.run,
) -> LaunchAgentStatus:
    destination = Path(plist_path).expanduser()
    if not destination.is_file():
        return LaunchAgentStatus("not_installed", False, False, "PLIST_NOT_FOUND")
    try:
        with destination.open("rb") as plist_file:
            value = plistlib.load(plist_file)
        if value.get("Label") != LABEL or set(value) != ALLOWED_PLIST_KEYS:
            raise ValueError
    except (OSError, ValueError, plistlib.InvalidFileException):
        return LaunchAgentStatus("abnormal", True, False, "PLIST_INVALID")
    try:
        process = command_runner(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return LaunchAgentStatus("abnormal", True, False, "LAUNCHCTL_UNAVAILABLE")
    if process.returncode != 0:
        return LaunchAgentStatus("abnormal", True, False, "AGENT_NOT_LOADED")
    return LaunchAgentStatus("installed", True, True, "AGENT_LOADED")
