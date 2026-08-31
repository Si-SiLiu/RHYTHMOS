"""Launch the read-only Streamlit dashboard as a detached local service."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8501
PORT_SEARCH_LIMIT = 10
STARTUP_TIMEOUT_SECONDS = 20.0
STALE_PROCESS_STOP_TIMEOUT_SECONDS = 3.0


def open_dashboard_url(url: str) -> None:
    """Open a loopback Dashboard URL through the native macOS launcher."""
    try:
        subprocess.run(
            ["/usr/bin/open", url],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("DASHBOARD_BROWSER_OPEN_FAILED") from exc


def is_process_running(process_id: int) -> bool:
    """Return whether a local process id is still available."""
    if process_id <= 0:
        return False
    try:
        os.kill(process_id, 0)
    except (OSError, ValueError):
        return False
    return True


def is_port_open(host: str, port: int, timeout: float = 0.2) -> bool:
    """Return whether a TCP service is accepting local connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_available_port(
    host: str = DEFAULT_HOST,
    preferred_port: int = DEFAULT_PORT,
    search_limit: int = PORT_SEARCH_LIMIT,
) -> int:
    """Find an unused local port without binding outside the loopback host."""
    for port in range(preferred_port, preferred_port + search_limit):
        if not is_port_open(host, port):
            return port
    raise RuntimeError("DASHBOARD_PORT_UNAVAILABLE")


def load_runtime_state(state_path: Path) -> dict[str, object] | None:
    """Load non-sensitive launcher state, returning None for stale data."""
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    if not isinstance(state, dict):
        return None
    return state


def runtime_fingerprint(project_root: Path = BASE_DIR) -> str:
    """Fingerprint every local asset Streamlit needs to serve the dashboard."""
    root = project_root.resolve()
    paths = [root / "config" / "versions.json"]
    paths.extend(sorted((root / "src").rglob("*.py")))
    # Streamlit's custom component files are served as static frontend assets.
    # Include them so a rebuilt app never reuses a process that still serves an
    # older training component after an HTML, JavaScript, or CSS-only fix.
    component_root = root / "src" / "cognitive_component_frontend"
    for pattern in ("*.html", "*.js", "*.css"):
        paths.extend(sorted(component_root.rglob(pattern)))
    paths.extend(sorted((root / "locales").glob("*.json")))
    digest = hashlib.sha256()
    try:
        for path in paths:
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    except OSError as exc:
        raise RuntimeError("DASHBOARD_FINGERPRINT_FAILED") from exc
    return digest.hexdigest()


def active_dashboard_url(
    state_path: Path,
    host: str = DEFAULT_HOST,
    expected_fingerprint: str | None = None,
) -> str | None:
    """Return the URL of a launcher-owned dashboard process if it is alive."""
    state = load_runtime_state(state_path)
    if not state:
        return None
    if (
        expected_fingerprint is not None
        and state.get("runtime_fingerprint") != expected_fingerprint
    ):
        return None
    process_id = state.get("pid")
    port = state.get("port")
    if not isinstance(process_id, int) or not isinstance(port, int):
        return None
    if not is_process_running(process_id) or not is_port_open(host, port):
        return None
    return f"http://{host}:{port}"


def _is_owned_dashboard_process(process_id: int, dashboard_path: Path) -> bool:
    """Avoid signaling a reused PID that does not belong to this project."""
    try:
        process = subprocess.run(
            ["/bin/ps", "-p", str(process_id), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    command = process.stdout.strip()
    return (
        process.returncode == 0
        and "streamlit" in command
        and str(dashboard_path.resolve()) in command
    )


def stop_stale_dashboard(state_path: Path, dashboard_path: Path) -> bool:
    """Stop only a launcher-owned stale Streamlit process, then clear its state."""
    state = load_runtime_state(state_path)
    process_id = state.get("pid") if state else None
    stopped = False
    if (
        isinstance(process_id, int)
        and is_process_running(process_id)
        and _is_owned_dashboard_process(process_id, dashboard_path)
    ):
        try:
            # Streamlit handles SIGINT as its graceful shutdown signal.
            os.kill(process_id, signal.SIGINT)
            deadline = time.monotonic() + STALE_PROCESS_STOP_TIMEOUT_SECONDS
            while is_process_running(process_id) and time.monotonic() < deadline:
                time.sleep(0.1)
            stopped = not is_process_running(process_id)
        except OSError:
            stopped = False
    state_path.unlink(missing_ok=True)
    return stopped


def streamlit_command(
    python_path: Path,
    dashboard_path: Path,
    host: str,
    port: int,
) -> list[str]:
    """Build the fixed local-only Streamlit command."""
    return [
        str(python_path),
        "-m",
        "streamlit",
        "run",
        str(dashboard_path),
        f"--server.address={host}",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]


def wait_until_ready(
    process: subprocess.Popen[bytes],
    host: str,
    port: int,
    timeout_seconds: float = STARTUP_TIMEOUT_SECONDS,
) -> None:
    """Wait for Streamlit to accept connections or fail with a safe code."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("DASHBOARD_START_FAILED")
        if is_port_open(host, port):
            return
        time.sleep(0.2)
    process.terminate()
    raise RuntimeError("DASHBOARD_START_TIMEOUT")


def launch_dashboard(
    project_root: Path = BASE_DIR,
    host: str = DEFAULT_HOST,
    preferred_port: int = DEFAULT_PORT,
    should_open_browser: bool = True,
) -> str:
    """Start or reopen the local dashboard and return its loopback URL."""
    project_root = project_root.resolve()
    python_path = project_root / ".venv" / "bin" / "python"
    dashboard_path = project_root / "src" / "dashboard.py"
    logs_dir = project_root / "logs"
    state_path = logs_dir / "dashboard_runtime.json"

    if not python_path.is_file():
        raise RuntimeError("DASHBOARD_PYTHON_NOT_FOUND")
    if not dashboard_path.is_file():
        raise RuntimeError("DASHBOARD_ENTRY_NOT_FOUND")

    fingerprint = runtime_fingerprint(project_root)
    existing_url = active_dashboard_url(
        state_path,
        host,
        expected_fingerprint=fingerprint,
    )
    if existing_url:
        if should_open_browser:
            open_dashboard_url(existing_url)
        return existing_url

    if state_path.exists():
        stop_stale_dashboard(state_path, dashboard_path)

    logs_dir.mkdir(parents=True, exist_ok=True)
    port = find_available_port(host, preferred_port)
    command = streamlit_command(python_path, dashboard_path, host, port)
    log_path = logs_dir / "dashboard.log"
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command,
            cwd=project_root,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        wait_until_ready(process, host, port)
    except RuntimeError:
        state_path.unlink(missing_ok=True)
        raise

    state_path.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "port": port,
                "runtime_fingerprint": fingerprint,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    url = f"http://{host}:{port}"
    if should_open_browser:
        open_dashboard_url(url)
    return url


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动本地 RHYTHMOS｜律衡 看板")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="首选本地端口")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        url = launch_dashboard(
            preferred_port=args.port,
            should_open_browser=not args.no_browser,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Dashboard: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
