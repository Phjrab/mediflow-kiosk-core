#!/usr/bin/env python3
"""One-window, owner-checked B controller mutation activation with read-only rollback.

Run from the pinned B release only after the A research guard and web process
have been verified. This does not issue any model or inference request.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.request

from scripts.local_llm_service import read_process_snapshot
from utils.lifecycle_lock import acquire_lifecycle_lock, open_lifecycle_lock, release_lifecycle_lock
from utils.runtime_receipt import validate_runtime_expectation


RELEASE = Path("/home/jetson2/mediflow-ai/control/releases/86bebb6")
RELEASE_SHA = "86bebb6d1fd10984a48f8fd401e5c483f8499244"
IDENTITY = Path("/home/jetson2/.local/state/mediflow-ai/admin-control-runtime/controller.pid")
BACKUP = IDENTITY.with_name("controller.pid.before-mutation-94394")
LOCK = Path("/home/jetson2/.local/state/mediflow-ai/device-lifecycle.lock")
READ_ONLY_ENV = Path("/home/jetson2/.config/mediflow-ai/c4-admin-control.env")
ENABLED_ENV = READ_ONLY_ENV.with_name("c4-admin-control-enabled.env")
APPLIED = Path("/home/jetson2/.local/state/mediflow-ai/admin-control/applied.json")
RECEIPT = Path("/home/jetson2/.local/state/mediflow-ai/applied-runtime.json")
OPERATIONS = Path("/home/jetson2/.local/state/mediflow-ai/admin-control/operations.sqlite3")
INGRESS = Path("/home/jetson2/.local/state/mediflow-ai/managed-ingress/ingress.sqlite3")
ARGV = ("python3", "-m", "services.ai_control.app")
EXECUTABLE = "/usr/bin/python3.10"
EXPECTED_PID, EXPECTED_TICKS = 94394, 17692634
PROTECTED_HASHES = {
    READ_ONLY_ENV: "054ccf16cdcdb6f299c9520fc7f74424ad77db5277d0806dc123fe5a0aafa504",
    Path("/home/jetson2/.config/mediflow-ai/admin-control-api-key"): "f010e93c676149b20f5b11b2a755f9c485fa02fa84029cc0b81956f9f89a3381",
    APPLIED: "c127b3de434504924e97c86e1c3bb93511be7673d808d8f2c037589b827bf156",
    RECEIPT: "cff246d0bf0b8b43f9e8cb8d1fbb12ce3ab26981e86d278e360547e90101b709",
}


class ActivationError(RuntimeError):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise ActivationError(code)


def private_bytes(path: Path) -> bytes:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o600, "private_file_drift")
    return path.read_bytes()


def exact_process(pid: int, ticks: int) -> bool:
    snap = read_process_snapshot(pid)
    return bool(snap is not None and snap.pid == pid and snap.uid == os.geteuid()
                and snap.start_ticks == ticks and snap.executable == EXECUTABLE
                and snap.argv == ARGV and snap.cwd == str(RELEASE))


def listeners(port: int, *, loopback: bool = True) -> set[int]:
    result = set()
    for name in ("tcp", "tcp6"):
        for line in (Path("/proc/net") / name).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] != "0A" or int(fields[1].split(":")[1], 16) != port:
                continue
            if loopback:
                require(name == "tcp" and fields[1].split(":")[0] == "0100007F",
                        "port_not_loopback")
            result.add(int(fields[9]))
    return result


def owns_port(pid: int, port: int, *, loopback: bool = True) -> bool:
    inodes = listeners(port, loopback=loopback)
    sockets = set()
    for fd in (Path("/proc") / str(pid) / "fd").iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        if target.startswith("socket:["):
            sockets.add(int(target[8:-1]))
    return len(inodes) == 1 and inodes <= sockets


def process_environment(pid: int) -> dict[str, str]:
    entries = [(item.decode("utf-8", "surrogateescape").split("=", 1))
               for item in (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0") if item]
    require(all(len(item) == 2 for item in entries)
            and len({item[0] for item in entries}) == len(entries), "environment_drift")
    return dict(entries)


def audit_digest() -> str:
    conn = sqlite3.connect("file:" + str(OPERATIONS) + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT * FROM operations ORDER BY operation_id").fetchall()
        require(len(rows) == 13, "audit_count_drift")
        return hashlib.sha256(repr(rows).encode()).hexdigest()
    finally:
        conn.close()


def authenticated(env: dict[str, str], route: str) -> dict:
    token = private_bytes(Path(env["AI_CONTROL_API_KEY_FILE"])).decode("ascii").strip()
    request = urllib.request.Request("http://127.0.0.1:8090/control/v1/" + route,
                                     headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=4) as response:
        require(response.status == 200, "controller_http")
        return json.load(response)


def gates(pid: int, ticks: int, *, enabled: bool, audit_before: str | None = None) -> tuple[dict[str, str], str]:
    require(exact_process(pid, ticks) and owns_port(pid, 8090), "controller_identity_drift")
    require(owns_port(69924, 18080) and not listeners(18081)
            and owns_port(37550, 8080, loopback=False), "engine_or_ingress_drift")
    for path, expected in PROTECTED_HASHES.items():
        require(hashlib.sha256(private_bytes(path)).hexdigest() == expected,
                "protected_file_drift")
    env = process_environment(pid)
    flag = "1" if enabled else "0"
    require(env.get("AI_CONTROL_DRAFTS_ENABLED") == flag
            and env.get("AI_CONTROL_MUTATIONS_ENABLED") == flag
            and env.get("AI_CONTROL_MANAGED_INGRESS_VERIFIED") == "1"
            and env.get("AI_INGRESS_RAW_BYPASS_VERIFIED") == "1"
            and env.get("AI_DEPLOYMENT_PROFILE") == "chat_only"
            and env.get("AI_DEVICE_LIFECYCLE_LOCK") == str(LOCK)
            and env.get("AI_CONTROL_OPERATION_DB") == str(OPERATIONS), "environment_drift")
    with urllib.request.urlopen("http://127.0.0.1:18080/health", timeout=4) as response:
        require(response.status == 200, "chat_health_regression")
    applied = json.loads(private_bytes(APPLIED))
    receipt = validate_runtime_expectation(json.loads(private_bytes(RECEIPT)))
    require(len(receipt) == 7 and applied["config_revision"] == receipt["config_revision"] == 3
            and applied["deployment_generation"] == receipt["deployment_generation"] == 3
            and applied["applied_profile"] == "chat_only"
            and applied["effective_config_digest"] == receipt["effective_config_digest"]
            and applied["effective_config"]["engines"]["chat"]["artifact_id"] == receipt["artifact_id"],
            "receipt_drift")
    conn = sqlite3.connect("file:" + str(INGRESS) + "?mode=ro", uri=True)
    try:
        state = conn.execute("SELECT admission,deployment_generation,raw_bypass_closed FROM ingress_state").fetchone()
        leases = conn.execute("SELECT COUNT(*) FROM ingress_leases WHERE state IN ('active','unknown')").fetchone()[0]
        require(state == ("open", 3, 1) and leases == 0, "ingress_drift")
    finally:
        conn.close()
    digest = audit_digest()
    require(audit_before is None or digest == audit_before, "operation_audit_drift")
    state = authenticated(env, "state")
    capabilities = authenticated(env, "capabilities")
    current = authenticated(env, "configs/current")
    require(state.get("config_revision") == 3 and state.get("deployment_generation") == 3
            and state.get("applied_profile") == state.get("observed_profile") == "chat_only"
            and state.get("lifecycle_state") == "ready" and state.get("active_operation_id") is None
            and state.get("activity") == {"source": "managed_ingress", "admission": "open",
                                          "inflight": 0, "unknown_inflight": 0}
            and state.get("engine", {}).get("inference_ready") is True
            and current.get("receipt") == receipt
            and capabilities.get("drafts_enabled") is enabled
            and capabilities.get("mutations_enabled") is enabled
            and capabilities.get("managed_ingress_verified") is True,
            "controller_state_drift")
    return env, digest


def enabled_config(raw: bytes) -> bytes:
    lines = raw.decode("utf-8").splitlines()
    counts = {"AI_CONTROL_DRAFTS_ENABLED": 0, "AI_CONTROL_MUTATIONS_ENABLED": 0}
    output = []
    for line in lines:
        key = line.split("=", 1)[0]
        if key in counts:
            require(line == key + "=0", "read_only_config_drift")
            counts[key] += 1
            line = key + "=1"
        output.append(line)
    require(all(counts.values()), "read_only_config_drift")
    return ("\n".join(output) + "\n").encode()


def atomic_private_write(path: Path, raw: bytes, *, replace: bool = False) -> None:
    temporary = path.with_name("." + path.name + ".activation-" + str(os.getpid())) if replace else path
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        dirfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if replace:
            temporary.unlink(missing_ok=True)


def stop_exact(pid: int, ticks: int) -> None:
    handle = os.pidfd_open(pid)
    try:
        require(exact_process(pid, ticks) and owns_port(pid, 8090), "stop_identity_drift")
        signal.pidfd_send_signal(handle, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if read_process_snapshot(pid) is None and not listeners(8090):
                return
            time.sleep(0.1)
        raise ActivationError("controller_stop_timeout")
    finally:
        os.close(handle)


def start_controller(env: dict[str, str]) -> tuple[int, int]:
    child = subprocess.Popen(ARGV, cwd=RELEASE, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        snap = read_process_snapshot(child.pid)
        if snap is not None and exact_process(child.pid, snap.start_ticks) and owns_port(child.pid, 8090):
            return child.pid, snap.start_ticks
        if child.poll() is not None:
            break
        time.sleep(0.1)
    snap = read_process_snapshot(child.pid)
    if snap is not None and exact_process(child.pid, snap.start_ticks):
        stop_exact(child.pid, snap.start_ticks)
    raise ActivationError("controller_start_timeout")


def close_admission_after_failed_rollback() -> None:
    # Fail closed only after a restart has been attempted. Never infer that a
    # missing controller makes managed ingress safe to leave open.
    from services.ai_control.ingress import IngressJournal
    IngressJournal(INGRESS).close()


def run(*, check_only: bool) -> None:
    require(os.geteuid() == 1000 and Path.cwd() == RELEASE, "wrong_host_or_release")
    require(subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                           text=True, check=True).stdout.strip() == RELEASE_SHA,
            "release_sha_drift")
    require(not subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, check=True).stdout.strip(), "release_dirty")
    lock = open_lifecycle_lock(LOCK)
    acquire_lifecycle_lock(lock)
    try:
        raw_record = private_bytes(IDENTITY)
        record = json.loads(raw_record)
        snap = read_process_snapshot(EXPECTED_PID)
        require(record == {"version": 1, "pid": EXPECTED_PID, "uid": os.geteuid(),
                           "executable": EXECUTABLE, "argv": list(ARGV), "cwd": str(RELEASE),
                           "start_ticks": EXPECTED_TICKS, "boot_id": snap.boot_id if snap else None}
                and exact_process(EXPECTED_PID, EXPECTED_TICKS), "identity_record_drift")
        env, audit_before = gates(EXPECTED_PID, EXPECTED_TICKS, enabled=False)
        new_config = enabled_config(private_bytes(READ_ONLY_ENV))
        require(not BACKUP.exists() and not ENABLED_ENV.exists(), "activation_already_attempted")
        if check_only:
            print(json.dumps({"result": "preflight_passed", "profile": "3:3:chat_only",
                              "audit_rows": 13, "read_only_pid": EXPECTED_PID}))
            return
        atomic_private_write(BACKUP, raw_record)
        atomic_private_write(ENABLED_ENV, new_config)
        new_pid = new_ticks = None
        try:
            stop_exact(EXPECTED_PID, EXPECTED_TICKS)
            enabled_env = dict(env, AI_CONTROL_DRAFTS_ENABLED="1", AI_CONTROL_MUTATIONS_ENABLED="1")
            new_pid, new_ticks = start_controller(enabled_env)
            gates(new_pid, new_ticks, enabled=True, audit_before=audit_before)
            new_record = dict(record, pid=new_pid, start_ticks=new_ticks)
            atomic_private_write(IDENTITY, (json.dumps(new_record, indent=2, sort_keys=True) + "\n").encode(), replace=True)
            require(json.loads(private_bytes(IDENTITY)) == new_record
                    and exact_process(new_pid, new_ticks), "new_identity_drift")
            gates(new_pid, new_ticks, enabled=True, audit_before=audit_before)
        except Exception:
            try:
                if new_pid is not None and read_process_snapshot(new_pid) is not None:
                    stop_exact(new_pid, new_ticks)
                if exact_process(EXPECTED_PID, EXPECTED_TICKS) and owns_port(EXPECTED_PID, 8090):
                    gates(EXPECTED_PID, EXPECTED_TICKS, enabled=False, audit_before=audit_before)
                    raise ActivationError("activation_stopped_before_controller_change")
                require(not listeners(8090), "rollback_port_owned")
                rollback_pid, rollback_ticks = start_controller(env)
                gates(rollback_pid, rollback_ticks, enabled=False, audit_before=audit_before)
                rollback_record = dict(record, pid=rollback_pid, start_ticks=rollback_ticks)
                atomic_private_write(IDENTITY, (json.dumps(rollback_record, indent=2, sort_keys=True) + "\n").encode(), replace=True)
                print(json.dumps({"result": "read_only_rollback", "controller_pid": rollback_pid,
                                  "audit_rows": 13}))
                raise ActivationError("activation_failed_rolled_back") from None
            except ActivationError as rollback_error:
                if rollback_error.args and rollback_error.args[0] in {
                    "activation_stopped_before_controller_change", "activation_failed_rolled_back"
                }:
                    raise
                close_admission_after_failed_rollback()
                raise ActivationError("rollback_failed_admission_closed") from None
            except Exception:
                close_admission_after_failed_rollback()
                raise ActivationError("rollback_failed_admission_closed") from None
        print(json.dumps({"result": "activated", "controller_pid": new_pid,
                          "start_ticks": new_ticks, "profile": "3:3:chat_only",
                          "audit_rows": 13, "drafts_mutations": True}))
    finally:
        release_lifecycle_lock(lock)


if __name__ == "__main__":
    try:
        require(sys.argv[1:] in ([], ["--check"]), "invalid_action")
        run(check_only=sys.argv[1:] == ["--check"])
    except Exception as error:
        code = error.args[0] if isinstance(error, ActivationError) else "internal_error"
        print("admin_controller_activation_failed:" + str(code), file=sys.stderr)
        raise SystemExit(1) from None
