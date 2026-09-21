#!/usr/bin/env python3
"""Manually manage the pinned local LLM without installing an autostart service."""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

# Direct `python3 scripts/local_llm_service.py ...` execution puts only the
# scripts directory on sys.path. Add the fixed repository root before importing
# the shared lifecycle-lock module used by both CLI and controller.
_IMPORT_ROOT = Path(__file__).resolve().parent.parent
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from utils.lifecycle_lock import (
    LifecycleLockError,
    acquire_lifecycle_lock,
    open_lifecycle_lock,
    release_lifecycle_lock,
)


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = _IMPORT_ROOT
COMMAND_NAME = "local_llm_service.py"
ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "status", "logs"})
DEFAULT_PORT = 8080
START_TIMEOUT_SECONDS = 120.0
STOP_TIMEOUT_SECONDS = 15.0
KILL_TIMEOUT_SECONDS = 3.0
LOG_LINE_LIMIT = 100


class ManagerError(RuntimeError):
    """Raised when the requested lifecycle action cannot be completed safely."""


class UsageError(ManagerError):
    """Raised for unsupported command-line input."""


@dataclasses.dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    uid: int
    executable: str
    argv: tuple[str, ...]
    cwd: str
    state: str
    start_ticks: int
    boot_id: str


@dataclasses.dataclass(frozen=True)
class ServiceSpec:
    project_root: Path
    launcher: Path
    server: Path
    control_dir: Path
    pid_path: Path
    log_path: Path
    lock_path: Path
    health_url: str
    port: int = DEFAULT_PORT


def parse_action(argv: Sequence[str]) -> str:
    if len(argv) != 2 or argv[1] not in ALLOWED_ACTIONS:
        allowed = "|".join(sorted(ALLOWED_ACTIONS))
        raise UsageError(f"usage: python3 scripts/{COMMAND_NAME} <{allowed}>")
    return argv[1]


def required_directory(name: str) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise ManagerError(f"{name} is required")
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ManagerError(f"{name} must name an existing absolute directory")
    return path.resolve()


def control_directory() -> Path:
    raw = os.environ.get("LOCAL_LLM_CONTROL_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise ManagerError("LOCAL_LLM_CONTROL_DIR must be absolute")
        return path
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "mediflow-local-llm"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.stat()
    if metadata.st_uid != os.getuid():
        raise ManagerError(f"control directory is not owned by the current user: {path}")
    if metadata.st_mode & 0o077:
        raise ManagerError(f"control directory must deny group/other access: {path}")


def build_spec(*, require_start_inputs: bool) -> ServiceSpec:
    llama_cpp_dir = required_directory("LLAMA_CPP_DIR")
    server = llama_cpp_dir / "build" / "bin" / "llama-server"
    if not server.is_file() or not os.access(server, os.X_OK):
        raise ManagerError("the pinned llama-server executable is missing")

    launcher = PROJECT_ROOT / "scripts" / "run_local_llm_candidate.sh"
    if not launcher.is_file():
        raise ManagerError(f"candidate launcher is missing: {launcher}")

    if require_start_inputs:
        required_directory("LOCAL_LLM_MODEL_DIR")
        key_raw = os.environ.get("LOCAL_LLM_API_KEY_FILE", "").strip()
        if not key_raw:
            raise ManagerError("LOCAL_LLM_API_KEY_FILE is required")
        key_path = Path(key_raw).expanduser()
        if not key_path.is_absolute() or key_path.is_symlink() or not key_path.is_file():
            raise ManagerError("LOCAL_LLM_API_KEY_FILE must be an absolute regular non-symlink file")
        key_metadata = key_path.stat()
        if key_metadata.st_uid != os.getuid() or key_metadata.st_mode & 0o077:
            raise ManagerError("LOCAL_LLM_API_KEY_FILE must be owned by this user and mode 0600 or stricter")

    control_dir = control_directory()
    ensure_private_directory(control_dir)
    raw_port = os.environ.get("LOCAL_LLM_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        raise ManagerError("LOCAL_LLM_PORT must be an integer from 1 to 65535") from None
    if str(port) != raw_port or not 1 <= port <= 65535:
        raise ManagerError("LOCAL_LLM_PORT must be an integer from 1 to 65535")
    return ServiceSpec(
        project_root=PROJECT_ROOT,
        launcher=launcher,
        server=server.resolve(),
        control_dir=control_dir,
        pid_path=control_dir / "local-llm.pid.json",
        log_path=control_dir / "local-llm.log",
        lock_path=control_dir / "local-llm.lock",
        health_url=f"http://127.0.0.1:{port}/health",
        port=port,
    )


def read_boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()


def read_process_snapshot(pid: int) -> ProcessSnapshot | None:
    proc_dir = Path("/proc") / str(pid)
    try:
        stat_text = (proc_dir / "stat").read_text(encoding="utf-8")
        closing_paren = stat_text.rfind(")")
        if closing_paren < 0:
            return None
        fields = stat_text[closing_paren + 2 :].split()
        state = fields[0]
        if state == "Z":
            return None
        start_ticks = int(fields[19])

        uid = -1
        for line in (proc_dir / "status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Uid:"):
                uid = int(line.split()[1])
                break
        if uid < 0:
            return None

        raw_argv = (proc_dir / "cmdline").read_bytes().split(b"\0")
        argv = tuple(item.decode("utf-8", "surrogateescape") for item in raw_argv if item)
        return ProcessSnapshot(
            pid=pid,
            uid=uid,
            executable=str((proc_dir / "exe").resolve(strict=True)),
            argv=argv,
            cwd=str((proc_dir / "cwd").resolve(strict=True)),
            state=state,
            start_ticks=start_ticks,
            boot_id=read_boot_id(),
        )
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError, IndexError):
        return None


def snapshot_matches_spec(snapshot: ProcessSnapshot, spec: ServiceSpec) -> bool:
    return (
        snapshot.uid == os.getuid()
        and snapshot.executable == str(spec.server)
        and snapshot.cwd == str(spec.project_root)
        and bool(snapshot.argv)
        and snapshot.argv[0] == str(spec.server)
    )


def write_record(path: Path, record: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def load_record(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise ManagerError(f"unsafe PID metadata permissions: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManagerError(f"invalid PID metadata: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManagerError(f"invalid PID metadata object: {path}")
    return payload


def build_record(spec: ServiceSpec, snapshot: ProcessSnapshot) -> dict[str, Any]:
    return {
        "version": 1,
        "pid": snapshot.pid,
        "uid": snapshot.uid,
        "executable": snapshot.executable,
        "argv": list(snapshot.argv),
        "cwd": snapshot.cwd,
        "start_ticks": snapshot.start_ticks,
        "boot_id": snapshot.boot_id,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def validate_record(
    spec: ServiceSpec, record: Mapping[str, Any]
) -> tuple[bool, str, ProcessSnapshot | None]:
    try:
        pid = int(record["pid"])
        start_ticks = int(record["start_ticks"])
        expected = {
            "version": 1,
            "uid": os.getuid(),
            "executable": str(spec.server),
            "cwd": str(spec.project_root),
            "boot_id": read_boot_id(),
        }
        for key, value in expected.items():
            if record.get(key) != value:
                return False, f"metadata mismatch: {key}", read_process_snapshot(pid)
        recorded_argv = tuple(record["argv"])
        if pid <= 1 or not recorded_argv:
            return False, "invalid process identity", None
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"invalid metadata fields: {exc}", None

    snapshot = read_process_snapshot(pid)
    if snapshot is None:
        return False, "process is not running", None
    if snapshot.start_ticks != start_ticks:
        return False, "PID was reused", snapshot
    if not snapshot_matches_spec(snapshot, spec):
        return False, "live process identity mismatch", snapshot
    if snapshot.argv != recorded_argv:
        return False, "live command line mismatch", snapshot
    return True, "running", snapshot


def port_is_open(port: int = DEFAULT_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def health_is_ready(url: str) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def inspect_service(
    spec: ServiceSpec, *, remove_stale: bool = False
) -> tuple[str, dict[str, Any] | None, ProcessSnapshot | None]:
    record = load_record(spec.pid_path)
    if record is None:
        return ("unmanaged-port" if port_is_open(spec.port) else "stopped"), None, None
    valid, reason, snapshot = validate_record(spec, record)
    if valid:
        return "running", record, snapshot
    if snapshot is None and remove_stale:
        spec.pid_path.unlink(missing_ok=True)
        return "stopped", None, None
    return f"invalid:{reason}", record, snapshot


def wait_for_server_process(spec: ServiceSpec, process: subprocess.Popen[bytes]) -> ProcessSnapshot:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        snapshot = read_process_snapshot(process.pid)
        if snapshot is not None and snapshot_matches_spec(snapshot, spec):
            return snapshot
        if process.poll() is not None:
            raise ManagerError("candidate launcher exited before llama-server started")
        time.sleep(0.05)
    raise ManagerError("candidate launcher did not become the expected llama-server process")


def terminate_unrecorded_child(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def start_service(spec: ServiceSpec) -> None:
    state, record, _ = inspect_service(spec, remove_stale=True)
    if state == "running" and record is not None:
        print(f"local-llm: already running | PID={record['pid']} | port={spec.port}")
        return
    if state != "stopped":
        raise ManagerError(f"refusing to start: {state}")
    if port_is_open(spec.port):
        raise ManagerError(f"refusing to start: port {spec.port} is used by an unmanaged process")

    descriptor = os.open(spec.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(spec.log_path, 0o600)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with os.fdopen(descriptor, "a", encoding="utf-8", buffering=1) as log_handle:
        log_handle.write(f"\n[{timestamp}] local LLM manager starting pinned candidate\n")
        process = subprocess.Popen(
            ["/bin/bash", str(spec.launcher)],
            cwd=str(spec.project_root),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )

    try:
        snapshot = wait_for_server_process(spec, process)
        record = build_record(spec, snapshot)
        write_record(spec.pid_path, record)
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            valid, reason, _ = validate_record(spec, record)
            if not valid:
                raise ManagerError(f"llama-server exited during startup: {reason}")
            if health_is_ready(spec.health_url):
                print(f"local-llm: running | PID={snapshot.pid} | port={spec.port}")
                return
            time.sleep(0.5)
        raise ManagerError("llama-server health check timed out")
    except Exception:
        current_record = load_record(spec.pid_path)
        if current_record is not None:
            try:
                terminate_record(spec, current_record)
            except ManagerError:
                pass
        else:
            terminate_unrecorded_child(process)
        raise


def terminate_record(spec: ServiceSpec, record: Mapping[str, Any]) -> None:
    valid, reason, snapshot = validate_record(spec, record)
    if not valid:
        if snapshot is None:
            spec.pid_path.unlink(missing_ok=True)
            return
        raise ManagerError(f"refusing to stop: {reason}")

    assert snapshot is not None
    os.kill(snapshot.pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        valid, _, _ = validate_record(spec, record)
        if not valid:
            spec.pid_path.unlink(missing_ok=True)
            return
        time.sleep(0.2)

    valid, reason, snapshot = validate_record(spec, record)
    if valid and snapshot is not None:
        os.kill(snapshot.pid, signal.SIGKILL)
        deadline = time.monotonic() + KILL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            valid, _, _ = validate_record(spec, record)
            if not valid:
                spec.pid_path.unlink(missing_ok=True)
                return
            time.sleep(0.1)
    raise ManagerError(f"failed to stop llama-server: {reason}")


def stop_service(spec: ServiceSpec) -> None:
    state, record, _ = inspect_service(spec, remove_stale=True)
    if state == "stopped":
        print("local-llm: stopped")
        return
    if state != "running" or record is None:
        raise ManagerError(f"refusing to stop: {state}")
    terminate_record(spec, record)
    print("local-llm: stopped")


def print_status(spec: ServiceSpec) -> None:
    state, record, snapshot = inspect_service(spec, remove_stale=True)
    if state == "running" and record is not None and snapshot is not None:
        health = "ready" if health_is_ready(spec.health_url) else "not-ready"
        print(
            f"local-llm: running | PID={snapshot.pid} | port={spec.port} | health={health} "
            f"| started={record.get('started_at', 'unknown')}"
        )
    elif state == "unmanaged-port":
        print(f"local-llm: unmanaged process detected on port {spec.port}")
    else:
        print(f"local-llm: {state} | port={spec.port}")


def print_logs(spec: ServiceSpec) -> None:
    print(f"== local-llm: {spec.log_path} (last {LOG_LINE_LIMIT} lines) ==")
    if not spec.log_path.exists():
        print("(no log entries)")
        return
    with spec.log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in collections.deque(handle, maxlen=LOG_LINE_LIMIT):
            print(line, end="" if line.endswith("\n") else "\n")


def run_locked(action: str, spec: ServiceSpec) -> None:
    configured_lock = os.environ.get("AI_DEVICE_LIFECYCLE_LOCK", "").strip()
    lock_path = Path(configured_lock) if configured_lock else spec.lock_path
    lock_handle = None
    try:
        lock_handle = open_lifecycle_lock(lock_path)
        acquire_lifecycle_lock(lock_handle)
        if action == "start":
            start_service(spec)
        elif action == "stop":
            stop_service(spec)
        elif action == "restart":
            stop_service(spec)
            start_service(spec)
        elif action == "status":
            print_status(spec)
        elif action == "logs":
            print_logs(spec)
        else:
            raise AssertionError(f"unsupported action: {action}")
    except LifecycleLockError as exc:
        if exc.code == "operation_in_progress":
            raise ManagerError("another device lifecycle action is already running") from exc
        if configured_lock and not lock_path.is_absolute():
            raise ManagerError("AI_DEVICE_LIFECYCLE_LOCK must be absolute") from exc
        raise ManagerError("unsafe lifecycle lock") from exc
    finally:
        if lock_handle is not None:
            release_lifecycle_lock(lock_handle)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        action = parse_action(sys.argv if argv is None else argv)
        spec = build_spec(require_start_inputs=action in {"start", "restart"})
        run_locked(action, spec)
        return 0
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ManagerError as exc:
        print(f"local-llm error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
