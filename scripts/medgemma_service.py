#!/usr/bin/env python3
"""Manage the fixed MedGemma API process without autostart or broad signalling."""
from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

_IMPORT_ROOT = Path(__file__).resolve().parent.parent
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts import local_llm_service
from utils.ai_config import AIError, secret
from utils.lifecycle_lock import (
    LifecycleLockError,
    acquire_lifecycle_lock,
    open_lifecycle_lock,
    release_lifecycle_lock,
)


PROJECT_ROOT = _IMPORT_ROOT
COMMAND_NAME = "medgemma_service.py"
ALLOWED_ACTIONS = frozenset({"start", "stop", "restart", "status", "logs"})
FIXED_HOST = "127.0.0.1"
FIXED_PORT = 18081
START_TIMEOUT_SECONDS = 45.0
STOP_TIMEOUT_SECONDS = 15.0
KILL_TIMEOUT_SECONDS = 3.0
PORT_RELEASE_TIMEOUT_SECONDS = 5.0
LOG_LINE_LIMIT = 100


class ManagerError(RuntimeError):
    """The requested action cannot be completed with proven ownership."""


class UsageError(ManagerError):
    pass


@dataclasses.dataclass(frozen=True)
class ServiceSpec:
    project_root: Path
    executable: str
    argv: tuple[str, ...]
    control_dir: Path
    pid_path: Path
    log_path: Path
    lock_path: Path
    key_file: Path
    ready_url: str
    port: int = FIXED_PORT


def parse_action(argv: Sequence[str]) -> str:
    if len(argv) != 2 or argv[1] not in ALLOWED_ACTIONS:
        allowed = "|".join(sorted(ALLOWED_ACTIONS))
        raise UsageError(f"usage: python3 scripts/{COMMAND_NAME} <{allowed}>")
    return argv[1]


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
        raise ManagerError("MedGemma control directory must be private and owner-only")


def _required_regular(env: Mapping[str, str], name: str, *, executable: bool = False) -> Path:
    raw = str(env.get(name, "")).strip()
    if not raw:
        raise ManagerError(f"{name} is required")
    path = Path(raw).expanduser()
    try:
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or (executable and not os.access(path, os.X_OK))):
            raise ValueError()
        return path.resolve(strict=True)
    except (OSError, ValueError):
        raise ManagerError(f"{name} must name an approved absolute regular file") from None


def build_spec(
    env: Mapping[str, str] | None = None, *, project_root: Path = PROJECT_ROOT,
) -> ServiceSpec:
    env = os.environ if env is None else env
    root = project_root.resolve(strict=True)
    if str(env.get("MEDGEMMA_RUNTIME", "")).strip() != "llama_cpp_cli":
        raise ManagerError("managed MedGemma requires MEDGEMMA_RUNTIME=llama_cpp_cli")
    if str(env.get("MEDGEMMA_HOST", FIXED_HOST)).strip() != FIXED_HOST:
        raise ManagerError("managed MedGemma host must be 127.0.0.1")
    raw_port = str(env.get("MEDGEMMA_PORT", str(FIXED_PORT))).strip()
    if raw_port != str(FIXED_PORT):
        raise ManagerError("managed MedGemma port must be 18081")
    for name, executable in (
        ("MEDGEMMA_MODEL_MANIFEST", False),
        ("MEDGEMMA_LLAMA_CPP_BIN", True),
        ("MEDGEMMA_GGUF_MODEL", False),
        ("MEDGEMMA_GGUF_MMPROJ", False),
    ):
        _required_regular(env, name, executable=executable)
    try:
        secret(env, "MEDGEMMA")
    except AIError:
        raise ManagerError("MEDGEMMA_API_KEY_FILE must be a private owner-only file") from None
    key_file = _required_regular(env, "MEDGEMMA_API_KEY_FILE")
    inline = str(env.get("MEDGEMMA_API_KEY", "")).strip()
    if inline:
        raise ManagerError("managed MedGemma forbids an inline API key")

    raw_control = str(env.get("MEDGEMMA_CONTROL_DIR", "")).strip()
    control_dir = Path(raw_control).expanduser() if raw_control else Path.home() / ".local/state/mediflow-medgemma"
    if not control_dir.is_absolute():
        raise ManagerError("MEDGEMMA_CONTROL_DIR must be absolute")
    _private_directory(control_dir)
    executable = str(Path(sys.executable).resolve(strict=True))
    argv = (executable, "-m", "services.medgemma.app")
    return ServiceSpec(
        project_root=root,
        executable=executable,
        argv=argv,
        control_dir=control_dir,
        pid_path=control_dir / "medgemma.pid.json",
        log_path=control_dir / "medgemma.log",
        lock_path=control_dir / "medgemma.lock",
        key_file=key_file,
        ready_url=f"http://{FIXED_HOST}:{FIXED_PORT}/readyz",
    )


def _record(spec: ServiceSpec, snapshot: local_llm_service.ProcessSnapshot) -> dict[str, Any]:
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
    spec: ServiceSpec, record: Mapping[str, Any],
) -> tuple[bool, str, local_llm_service.ProcessSnapshot | None]:
    try:
        pid = int(record["pid"])
        expected = {
            "version": 1,
            "uid": os.getuid(),
            "executable": spec.executable,
            "argv": list(spec.argv),
            "cwd": str(spec.project_root),
            "boot_id": local_llm_service.read_boot_id(),
        }
        if pid <= 1 or not isinstance(record.get("start_ticks"), int):
            return False, "invalid process identity", None
        for key, value in expected.items():
            if record.get(key) != value:
                return False, f"metadata mismatch: {key}", local_llm_service.read_process_snapshot(pid)
    except (KeyError, TypeError, ValueError):
        return False, "invalid metadata fields", None
    snapshot = local_llm_service.read_process_snapshot(pid)
    if snapshot is None:
        return False, "process is not running", None
    matches = (
        snapshot.pid == pid
        and snapshot.uid == os.getuid()
        and snapshot.executable == spec.executable
        and snapshot.argv == spec.argv
        and snapshot.cwd == str(spec.project_root)
        and snapshot.start_ticks == record["start_ticks"]
        and snapshot.boot_id == record["boot_id"]
    )
    return (True, "running", snapshot) if matches else (False, "live process identity mismatch", snapshot)


def inspect_service(
    spec: ServiceSpec, *, remove_stale: bool = False,
) -> tuple[str, dict[str, Any] | None, local_llm_service.ProcessSnapshot | None]:
    record = local_llm_service.load_record(spec.pid_path)
    if record is None:
        return ("unmanaged-port" if local_llm_service.port_is_open(spec.port) else "stopped"), None, None
    valid, reason, snapshot = validate_record(spec, record)
    if valid:
        return "running", record, snapshot
    if snapshot is None and remove_stale:
        spec.pid_path.unlink(missing_ok=True)
        return "stopped", None, None
    return f"invalid:{reason}", record, snapshot


def ready(spec: ServiceSpec, env: Mapping[str, str]) -> bool:
    try:
        token = secret(env, "MEDGEMMA")
        request = urllib.request.Request(
            spec.ready_url, headers={"Authorization": "Bearer " + token}, method="GET"
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read(4097))
        return int(response.status) == 200 and payload.get("status") == "ready" and payload.get("vision_ready") is True
    except (AIError, OSError, ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError):
        return False


def start_service(spec: ServiceSpec, *, env: Mapping[str, str] | None = None) -> None:
    child_env = dict(os.environ if env is None else env)
    state, record, _snapshot = inspect_service(spec, remove_stale=True)
    if state == "running" and record is not None:
        return
    if state != "stopped" or local_llm_service.port_is_open(spec.port):
        raise ManagerError(f"refusing to start: {state}")
    descriptor = os.open(spec.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(spec.log_path, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8", buffering=1) as log_handle:
        log_handle.write(f"\n[{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}] MedGemma manager starting fixed API\n")
        process = subprocess.Popen(
            list(spec.argv), cwd=str(spec.project_root), env=child_env,
            stdin=subprocess.DEVNULL, stdout=log_handle, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True,
        )
    try:
        deadline = time.monotonic() + 10
        snapshot = None
        while time.monotonic() < deadline:
            candidate = local_llm_service.read_process_snapshot(process.pid)
            if (candidate is not None and candidate.executable == spec.executable
                    and candidate.argv == spec.argv and candidate.cwd == str(spec.project_root)):
                snapshot = candidate
                break
            if process.poll() is not None:
                raise ManagerError("MedGemma process exited during launch")
            time.sleep(0.05)
        if snapshot is None:
            raise ManagerError("MedGemma process identity was not established")
        record = _record(spec, snapshot)
        local_llm_service.write_record(spec.pid_path, record)
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            valid, reason, _live = validate_record(spec, record)
            if not valid:
                raise ManagerError(f"MedGemma exited during startup: {reason}")
            if ready(spec, child_env):
                return
            time.sleep(0.25)
        raise ManagerError("MedGemma readiness check timed out")
    except Exception:
        current = local_llm_service.load_record(spec.pid_path)
        if current is not None:
            try:
                terminate_record(spec, current)
            except ManagerError:
                pass
        else:
            local_llm_service.terminate_unrecorded_child(process)
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
        valid, _reason, _snapshot = validate_record(spec, record)
        if not valid:
            spec.pid_path.unlink(missing_ok=True)
            return
        time.sleep(0.2)
    valid, reason, snapshot = validate_record(spec, record)
    if valid and snapshot is not None:
        os.kill(snapshot.pid, signal.SIGKILL)
        deadline = time.monotonic() + KILL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            valid, _reason, _snapshot = validate_record(spec, record)
            if not valid:
                spec.pid_path.unlink(missing_ok=True)
                return
            time.sleep(0.1)
    raise ManagerError(f"failed to stop MedGemma: {reason}")


def stop_owned(spec: ServiceSpec, pid: int) -> None:
    record = local_llm_service.load_record(spec.pid_path)
    if record is None or record.get("pid") != pid:
        raise ManagerError("refusing to stop: PID record changed")
    terminate_record(spec, record)
    deadline = time.monotonic() + PORT_RELEASE_TIMEOUT_SECONDS
    while local_llm_service.port_is_open(spec.port) and time.monotonic() < deadline:
        time.sleep(0.05)
    if local_llm_service.port_is_open(spec.port):
        raise ManagerError(f"MedGemma stopped but port {spec.port} is still in use")


def stop_service(spec: ServiceSpec) -> None:
    state, record, _snapshot = inspect_service(spec, remove_stale=True)
    if state == "stopped":
        return
    if state != "running" or record is None:
        raise ManagerError(f"refusing to stop: {state}")
    terminate_record(spec, record)
    deadline = time.monotonic() + PORT_RELEASE_TIMEOUT_SECONDS
    while local_llm_service.port_is_open(spec.port) and time.monotonic() < deadline:
        time.sleep(0.05)
    if local_llm_service.port_is_open(spec.port):
        raise ManagerError(f"MedGemma stopped but port {spec.port} is still in use")


def run_locked(action: str, spec: ServiceSpec, *, env: Mapping[str, str] | None = None) -> None:
    env = os.environ if env is None else env
    configured = str(env.get("AI_DEVICE_LIFECYCLE_LOCK", "")).strip()
    lock_path = Path(configured) if configured else spec.lock_path
    handle = None
    try:
        handle = open_lifecycle_lock(lock_path)
        acquire_lifecycle_lock(handle)
        if action == "start":
            start_service(spec, env=env)
        elif action == "stop":
            stop_service(spec)
        elif action == "restart":
            stop_service(spec)
            start_service(spec, env=env)
        elif action == "status":
            state, record, _snapshot = inspect_service(spec, remove_stale=False)
            pid = record.get("pid") if record else None
            print(f"medgemma: {state} | PID={pid or '-'} | port={spec.port}")
        elif action == "logs":
            if spec.log_path.exists():
                with spec.log_path.open("r", encoding="utf-8", errors="replace") as handle_in:
                    for line in collections.deque(handle_in, maxlen=LOG_LINE_LIMIT):
                        print(line, end="" if line.endswith("\n") else "\n")
        else:
            raise AssertionError("unsupported action")
    except LifecycleLockError as exc:
        if exc.code == "operation_in_progress":
            raise ManagerError("another device lifecycle action is already running") from None
        raise ManagerError("unsafe lifecycle lock") from None
    finally:
        if handle is not None:
            release_lifecycle_lock(handle)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        action = parse_action(sys.argv if argv is None else argv)
        spec = build_spec()
        run_locked(action, spec)
        return 0
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ManagerError as exc:
        print(f"medgemma error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
