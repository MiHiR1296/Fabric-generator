from __future__ import annotations

import os
import shlex
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_paths import BLEND_FILE_PATH, BLENDER_SESSION_ROOT, ensure_runtime_dirs


DEFAULT_BLENDER_BINARY = Path("/Applications/Blender.app/Contents/MacOS/Blender")


@dataclass(frozen=True)
class BlenderSessionConfig:
    session_mode: str
    managed: bool
    host: str
    port: int
    socket_timeout_seconds: float
    startup_timeout_seconds: float
    idle_timeout_seconds: float
    blender_binary: Path
    blend_file: Path
    startup_script: Path
    launch_prefix: tuple[str, ...]
    launch_args: tuple[str, ...]
    log_path: Path


@dataclass
class BlenderSessionState:
    status: str = "stopped"
    message: str = "No managed Blender session has been started yet."
    pid: int | None = None
    launched_by_manager: bool = False
    started_at: str | None = None
    last_used_at: str | None = None
    last_error: str | None = None

    def to_dict(self, config: BlenderSessionConfig, socket_available: bool) -> dict[str, Any]:
        return {
            "mode": config.session_mode,
            "managed": config.managed,
            "status": self.status,
            "message": self.message,
            "pid": self.pid,
            "launchedByManager": self.launched_by_manager,
            "startedAt": self.started_at,
            "lastUsedAt": self.last_used_at,
            "lastError": self.last_error,
            "socketAvailable": socket_available,
            "host": config.host,
            "port": config.port,
            "idleTimeoutSeconds": config.idle_timeout_seconds,
            "startupTimeoutSeconds": config.startup_timeout_seconds,
            "blenderBinary": str(config.blender_binary),
            "blendFile": str(config.blend_file),
            "startupScript": str(config.startup_script),
            "launchPrefix": list(config.launch_prefix),
            "logPath": str(config.log_path),
        }


_LOCK = threading.Lock()
_PROCESS: subprocess.Popen[bytes] | None = None
_IDLE_TIMER: threading.Timer | None = None
_BUSY_COUNT = 0
_STATE = BlenderSessionState()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_blender_session_config() -> BlenderSessionConfig:
    ensure_runtime_dirs()
    session_mode = os.environ.get("BLENDER_SESSION_MODE", "managed").strip().lower() or "managed"
    managed = session_mode != "attach"
    launch_prefix = tuple(shlex.split(os.environ.get("BLENDER_LAUNCH_PREFIX", "")))
    launch_args = tuple(shlex.split(os.environ.get("BLENDER_LAUNCH_ARGS", "")))
    return BlenderSessionConfig(
        session_mode=session_mode,
        managed=managed,
        host=os.environ.get("BLENDER_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLENDER_PORT", "9875")),
        socket_timeout_seconds=float(os.environ.get("BLENDER_TIMEOUT_SECONDS", "30")),
        startup_timeout_seconds=float(os.environ.get("BLENDER_STARTUP_TIMEOUT_SECONDS", "120")),
        idle_timeout_seconds=float(os.environ.get("BLENDER_IDLE_TIMEOUT_SECONDS", "600")),
        blender_binary=Path(os.environ.get("BLENDER_BINARY_PATH", str(DEFAULT_BLENDER_BINARY))).expanduser(),
        blend_file=Path(os.environ.get("WEAVE_BLEND_FILE", str(BLEND_FILE_PATH))).expanduser(),
        startup_script=Path(__file__).resolve().with_name("blender_session_startup.py"),
        launch_prefix=launch_prefix,
        launch_args=launch_args,
        log_path=BLENDER_SESSION_ROOT / "blender-session.log",
    )


def _socket_available(config: BlenderSessionConfig, timeout_seconds: float = 0.5) -> bool:
    try:
        with socket.create_connection((config.host, config.port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def _cancel_idle_timer_locked() -> None:
    global _IDLE_TIMER
    if _IDLE_TIMER is not None:
        _IDLE_TIMER.cancel()
        _IDLE_TIMER = None


def _refresh_process_state_locked() -> None:
    global _PROCESS
    if _PROCESS is not None and _PROCESS.poll() is not None:
        _PROCESS = None
        _STATE.pid = None
        _STATE.launched_by_manager = False
        if _STATE.status not in {"stopped", "error"}:
            _STATE.status = "stopped"
            _STATE.message = "Managed Blender session exited."


def _schedule_idle_timer_locked(config: BlenderSessionConfig) -> None:
    global _IDLE_TIMER
    _cancel_idle_timer_locked()
    if (
        not config.managed
        or config.idle_timeout_seconds <= 0
        or _BUSY_COUNT > 0
        or not _STATE.launched_by_manager
        or _PROCESS is None
        or _PROCESS.poll() is not None
    ):
        return

    timer = threading.Timer(config.idle_timeout_seconds, _handle_idle_timeout)
    timer.daemon = True
    _IDLE_TIMER = timer
    timer.start()


def _mark_usage_locked(config: BlenderSessionConfig) -> None:
    _STATE.last_used_at = _utc_now()
    _schedule_idle_timer_locked(config)


def _finalize_stopped_state_locked(message: str, *, error: str | None = None) -> None:
    global _PROCESS
    _PROCESS = None
    _cancel_idle_timer_locked()
    _STATE.status = "stopped"
    _STATE.message = message
    _STATE.pid = None
    _STATE.launched_by_manager = False
    _STATE.last_error = error


def _terminate_process(process: subprocess.Popen[bytes], message: str) -> None:
    try:
        process.terminate()
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    finally:
        with _LOCK:
            _finalize_stopped_state_locked(message)


def _handle_idle_timeout() -> None:
    config = load_blender_session_config()
    with _LOCK:
        _refresh_process_state_locked()
        if _BUSY_COUNT > 0:
            _schedule_idle_timer_locked(config)
            return
        process = _PROCESS
        launched_by_manager = _STATE.launched_by_manager
        if not launched_by_manager or process is None or process.poll() is not None:
            _schedule_idle_timer_locked(config)
            return
        _STATE.status = "stopping"
        _STATE.message = "Stopping Blender after idle timeout."

    _terminate_process(process, "Managed Blender session stopped after idle timeout.")


def _wait_for_socket(config: BlenderSessionConfig) -> None:
    deadline = time.monotonic() + max(config.startup_timeout_seconds, 1.0)
    while time.monotonic() < deadline:
        with _LOCK:
            process = _PROCESS
            if process is not None and process.poll() is not None:
                _STATE.status = "error"
                _STATE.message = "Managed Blender session exited before opening the socket."
                _STATE.last_error = _STATE.message
                _STATE.pid = None
                _STATE.launched_by_manager = False
                raise RuntimeError(_STATE.message)

        if _socket_available(config):
            with _LOCK:
                _STATE.status = "running"
                _STATE.message = "Managed Blender session is ready."
                _STATE.last_error = None
                _mark_usage_locked(config)
            return
        time.sleep(0.5)

    with _LOCK:
        process = _PROCESS
    if process is not None and process.poll() is None:
        _terminate_process(process, "Managed Blender session timed out while starting.")
    raise RuntimeError(
        f"Managed Blender session did not open {config.host}:{config.port} "
        f"within {config.startup_timeout_seconds} seconds."
    )


def _launch_managed_session(config: BlenderSessionConfig, reason: str | None = None) -> None:
    if not config.blender_binary.exists():
        raise FileNotFoundError(f"Blender binary not found at {config.blender_binary}")
    if not config.blend_file.exists():
        raise FileNotFoundError(f"Blend file not found at {config.blend_file}")
    if not config.startup_script.exists():
        raise FileNotFoundError(f"Blender startup script not found at {config.startup_script}")

    command = [
        *config.launch_prefix,
        str(config.blender_binary),
        str(config.blend_file),
        "--python",
        str(config.startup_script),
        *config.launch_args,
    ]
    config.log_path.parent.mkdir(parents=True, exist_ok=True)
    with config.log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=str(config.blend_file.parent),
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )

    with _LOCK:
        global _PROCESS
        _PROCESS = process
        _STATE.status = "starting"
        _STATE.message = (
            "Launching managed Blender session."
            if not reason
            else f"Launching managed Blender session for {reason}."
        )
        _STATE.pid = process.pid
        _STATE.launched_by_manager = True
        _STATE.started_at = _utc_now()
        _STATE.last_error = None

    _wait_for_socket(config)


def managed_session_enabled() -> bool:
    return load_blender_session_config().managed


def get_blender_session_snapshot() -> dict[str, Any]:
    config = load_blender_session_config()
    socket_available = _socket_available(config)
    with _LOCK:
        _refresh_process_state_locked()
        if socket_available and _STATE.status == "stopped" and not _STATE.launched_by_manager:
            _STATE.status = "running"
            _STATE.message = "Attached to an existing Blender session."
        return _STATE.to_dict(config, socket_available)


def begin_blender_command(reason: str | None = None) -> None:
    config = load_blender_session_config()
    with _LOCK:
        global _BUSY_COUNT
        _BUSY_COUNT += 1
        _STATE.last_used_at = _utc_now()
        _cancel_idle_timer_locked()

    if not config.managed:
        return

    with _LOCK:
        _refresh_process_state_locked()
        socket_available = _socket_available(config)
        if socket_available:
            if _PROCESS is not None and _PROCESS.poll() is None and _STATE.launched_by_manager:
                _STATE.status = "running"
                _STATE.message = "Managed Blender session is ready."
                _STATE.pid = _PROCESS.pid
            else:
                _STATE.status = "running"
                _STATE.message = "Attached to an existing Blender session."
                _STATE.pid = None
                _STATE.launched_by_manager = False
            _STATE.last_error = None
            return

        process = _PROCESS
        launched_by_manager = _STATE.launched_by_manager
        if process is not None and process.poll() is None and launched_by_manager:
            _STATE.status = "restarting"
            _STATE.message = "Managed Blender session became unresponsive. Restarting it."

    if process is not None and launched_by_manager:
        _terminate_process(process, "Managed Blender session was restarted after becoming unresponsive.")

    try:
        _launch_managed_session(config, reason=reason)
    except Exception:
        finish_blender_command(failed=True)
        raise


def finish_blender_command(*, failed: bool = False) -> None:
    config = load_blender_session_config()
    with _LOCK:
        global _BUSY_COUNT
        _BUSY_COUNT = max(0, _BUSY_COUNT - 1)
        if failed and _STATE.last_error is None:
            _STATE.last_error = _STATE.message
        _mark_usage_locked(config)


def stop_blender_session(reason: str = "Stopped by backend request.") -> dict[str, Any]:
    config = load_blender_session_config()
    with _LOCK:
        _refresh_process_state_locked()
        process = _PROCESS
        launched_by_manager = _STATE.launched_by_manager
        if not launched_by_manager or process is None or process.poll() is not None:
            if _socket_available(config):
                _STATE.status = "running"
                _STATE.message = "Blender is running, but it is not managed by this backend."
            else:
                _STATE.status = "stopped"
                _STATE.message = "No managed Blender session is currently running."
            return _STATE.to_dict(config, _socket_available(config))
        _STATE.status = "stopping"
        _STATE.message = reason

    _terminate_process(process, reason)
    return get_blender_session_snapshot()


def restart_blender_session(reason: str = "Restarted by backend request.") -> dict[str, Any]:
    config = load_blender_session_config()
    if config.managed:
        stop_blender_session("Restarting managed Blender session.")
        begin_blender_command(reason=reason)
        finish_blender_command()
        return get_blender_session_snapshot()
    return get_blender_session_snapshot()


def mark_blender_transport_error(message: str) -> None:
    with _LOCK:
        _STATE.last_error = message
        if _STATE.status not in {"starting", "stopping"}:
            _STATE.status = "error"
            _STATE.message = message


def stop_managed_session_on_shutdown() -> None:
    config = load_blender_session_config()
    if not config.managed:
        return
    stop_blender_session("Managed Blender session stopped during backend shutdown.")
