#!/usr/bin/env python3
"""One-window, fail-closed repair of the C13 read-only controller identity.

Run only on Jetson B's pinned 86bebb6 release, from an approved maintenance
window. The script never reads an inference request or enables mutations.
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
LOCK = Path("/home/jetson2/.local/state/mediflow-ai/device-lifecycle.lock")
OLD_PID, OLD_TICKS = 47037, 8757518
LIVE_PID, LIVE_TICKS = 69967, 9144933
ARGV = ("python3", "-m", "services.ai_control.app")
EXECUTABLE = "/usr/bin/python3.10"
PROTECTED_HASHES = {
    "/home/jetson2/.config/mediflow-ai/c4-admin-control.env": "054ccf16cdcdb6f299c9520fc7f74424ad77db5277d0806dc123fe5a0aafa504",
    "/home/jetson2/.config/mediflow-ai/admin-control-api-key": "f010e93c676149b20f5b11b2a755f9c485fa02fa84029cc0b81956f9f89a3381",
    "/home/jetson2/.local/state/mediflow-ai/admin-control/applied.json": "c127b3de434504924e97c86e1c3bb93511be7673d808d8f2c037589b827bf156",
    "/home/jetson2/.local/state/mediflow-ai/applied-runtime.json": "cff246d0bf0b8b43f9e8cb8d1fbb12ce3ab26981e86d278e360547e90101b709",
}


class RecoveryError(RuntimeError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RecoveryError(code)


def private_bytes(path: Path) -> bytes:
    metadata = path.lstat()
    require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.geteuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600, "unsafe_private_file")
    return path.read_bytes()


def identity_matches(record: dict, snapshot, *, expected_pid: int, expected_ticks: int) -> bool:
    return (record.get("version") == 1
            and record.get("pid") == expected_pid
            and record.get("start_ticks") == expected_ticks
            and record.get("uid") == os.geteuid()
            and record.get("executable") == EXECUTABLE
            and record.get("argv") == list(ARGV)
            and record.get("cwd") == str(RELEASE)
            and snapshot is not None
            and snapshot.pid == expected_pid
            and snapshot.start_ticks == expected_ticks
            and snapshot.uid == os.geteuid()
            and snapshot.executable == EXECUTABLE
            and snapshot.argv == ARGV
            and snapshot.cwd == str(RELEASE)
            and snapshot.boot_id == record.get("boot_id"))


def validate_recovery_candidates(record: dict, stale_snapshot, current) -> None:
    require(stale_snapshot is None, "stale_pid_reused")
    require(current is not None and current.pid == LIVE_PID
            and current.start_ticks == LIVE_TICKS
            and current.uid == os.geteuid()
            and current.executable == EXECUTABLE
            and current.argv == ARGV
            and current.cwd == str(RELEASE), "live_identity_drift")
    require(record == {
        "version": 1, "pid": OLD_PID, "uid": os.geteuid(),
        "executable": EXECUTABLE, "argv": list(ARGV), "cwd": str(RELEASE),
        "start_ticks": OLD_TICKS, "boot_id": current.boot_id,
    }, "stale_record_drift")


def listener_inodes(port: int) -> set[int]:
    result = set()
    for name in ("tcp", "tcp6"):
        for line in (Path("/proc/net") / name).read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] != "0A" or int(fields[1].split(":")[1], 16) != port:
                continue
            # Raw chat and controller may only bind IPv4 loopback.
            require(name == "tcp" and fields[1].split(":")[0] == "0100007F",
                    "raw_port_not_loopback")
            result.add(int(fields[9]))
    return result


def process_socket_inodes(pid: int) -> set[int]:
    result = set()
    for fd in (Path("/proc") / str(pid) / "fd").iterdir():
        try:
            target = os.readlink(fd)
        except FileNotFoundError:
            continue
        if target.startswith("socket:["):
            result.add(int(target[8:-1]))
    return result


def exact_listener(pid: int, port: int) -> bool:
    listeners = listener_inodes(port)
    return len(listeners) == 1 and listeners <= process_socket_inodes(pid)


def process_environment(pid: int) -> dict[str, str]:
    raw = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
    entries = [item.decode("utf-8", "surrogateescape").split("=", 1)
               for item in raw if item]
    require(all(len(item) == 2 for item in entries)
            and len({item[0] for item in entries}) == len(entries), "invalid_environment")
    return dict(entries)


def authenticated_state(env: dict[str, str]) -> None:
    key_path = Path(env["AI_CONTROL_API_KEY_FILE"])
    token = private_bytes(key_path).decode("ascii").strip()
    for route in ("state", "capabilities"):
        request = urllib.request.Request(
            f"http://127.0.0.1:8090/control/v1/{route}",
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            require(response.status == 200, "controller_http")
            data = json.load(response)
        if route == "state":
            require(data.get("config_revision") == 3
                    and data.get("deployment_generation") == 3
                    and data.get("applied_profile") == "chat_only"
                    and data.get("observed_profile") == "chat_only"
                    and data.get("lifecycle_state") == "ready"
                    and data.get("active_operation_id") is None
                    and data.get("activity") == {
                        "source": "managed_ingress", "admission": "open",
                        "inflight": 0, "unknown_inflight": 0,
                    }, "controller_state_drift")
        else:
            require(data.get("drafts_enabled") is False
                    and data.get("mutations_enabled") is False,
                    "controller_mutation_enabled")


def audit_digest(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT * FROM operations ORDER BY operation_id").fetchall()
        require(len(rows) == 13, "operation_count_drift")
        return hashlib.sha256(repr(rows).encode()).hexdigest()
    finally:
        connection.close()


def gates(pid: int, expected_ticks: int, *, audit_baseline: str | None = None) -> tuple[dict[str, str], str]:
    snapshot = read_process_snapshot(pid)
    require(snapshot is not None and snapshot.uid == os.geteuid()
            and snapshot.executable == EXECUTABLE and snapshot.argv == ARGV
            and snapshot.cwd == str(RELEASE) and snapshot.start_ticks == expected_ticks,
            "controller_identity_drift")
    require(exact_listener(pid, 8090), "controller_port_drift")
    require(not listener_inodes(18081), "vlm_running")
    require(exact_listener(69924, 18080), "chat_port_drift")
    for path, digest in PROTECTED_HASHES.items():
        require(hashlib.sha256(private_bytes(Path(path))).hexdigest() == digest,
                "protected_file_drift")
    env = process_environment(pid)
    require(env.get("AI_CONTROL_DRAFTS_ENABLED") == "0"
            and env.get("AI_CONTROL_MUTATIONS_ENABLED") == "0"
            and env.get("AI_CONTROL_MANAGED_INGRESS_VERIFIED") == "1"
            and env.get("AI_INGRESS_RAW_BYPASS_VERIFIED") == "1"
            and env.get("AI_DEPLOYMENT_PROFILE") == "chat_only"
            and env.get("AI_DEVICE_LIFECYCLE_LOCK") == str(LOCK)
            and env.get("AI_CONTROL_API_KEY_FILE") == "/home/jetson2/.config/mediflow-ai/admin-control-api-key"
            and env.get("AI_CONTROL_OPERATION_DB") == "/home/jetson2/.local/state/mediflow-ai/admin-control/operations.sqlite3",
            "environment_drift")
    applied = json.loads(Path("/home/jetson2/.local/state/mediflow-ai/admin-control/applied.json").read_text())
    receipt = json.loads(Path("/home/jetson2/.local/state/mediflow-ai/applied-runtime.json").read_text())
    validate_runtime_expectation(receipt)
    require(applied.get("config_revision") == receipt["config_revision"] == 3
            and applied.get("deployment_generation") == receipt["deployment_generation"] == 3
            and applied.get("applied_profile") == "chat_only"
            and (applied.get("effective_config") or {}).get("engines", {}).get("chat", {}).get("artifact_id") == receipt["artifact_id"]
            and applied.get("effective_config_digest") == receipt["effective_config_digest"],
            "receipt_drift")
    database = Path(env["AI_CONTROL_INGRESS_STATE_DIR"]) / "ingress.sqlite3"
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        state = connection.execute("SELECT admission,deployment_generation,raw_bypass_closed FROM ingress_state").fetchone()
        pending = connection.execute("SELECT COUNT(*) FROM ingress_leases WHERE state IN ('active','unknown')").fetchone()[0]
        require(state == ("open", 3, 1) and pending == 0, "ingress_drift")
    finally:
        connection.close()
    digest = audit_digest(Path(env["AI_CONTROL_OPERATION_DB"]))
    require(audit_baseline is None or digest == audit_baseline, "operation_audit_drift")
    authenticated_state(env)
    return env, digest


def atomic_private_write(path: Path, payload: bytes, *, replace: bool) -> None:
    temporary = path.with_name("." + path.name + ".recovery-" + str(os.getpid())) if replace else path
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if replace:
            temporary.unlink(missing_ok=True)


def stop_exact(pid: int, ticks: int) -> None:
    pidfd = os.pidfd_open(pid)
    try:
        snapshot = read_process_snapshot(pid)
        require(snapshot is not None and snapshot.start_ticks == ticks
                and snapshot.uid == os.geteuid()
                and snapshot.executable == EXECUTABLE
                and snapshot.argv == ARGV and snapshot.cwd == str(RELEASE),
                "stop_identity_drift")
        signal.pidfd_send_signal(pidfd, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if read_process_snapshot(pid) is None and not listener_inodes(8090):
                return
            time.sleep(0.1)
        raise RecoveryError("controller_stop_timeout")
    finally:
        os.close(pidfd)


def start_read_only(env: dict[str, str]) -> tuple[int, int]:
    child = subprocess.Popen(ARGV, cwd=RELEASE, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True, close_fds=True)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        snapshot = read_process_snapshot(child.pid)
        if snapshot is not None and exact_listener(child.pid, 8090):
            return child.pid, snapshot.start_ticks
        if child.poll() is not None:
            break
        time.sleep(0.1)
    snapshot = read_process_snapshot(child.pid)
    if snapshot is not None and snapshot.argv == ARGV and snapshot.cwd == str(RELEASE):
        stop_exact(child.pid, snapshot.start_ticks)
    raise RecoveryError("controller_start_timeout")


def run(*, check_only: bool = False) -> None:
    require(os.geteuid() == 1000 and Path.cwd() == RELEASE, "wrong_host_or_release")
    result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    require(result.stdout.strip() == RELEASE_SHA, "release_sha_drift")
    require(not subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, check=True).stdout.strip(), "release_dirty")
    handle = open_lifecycle_lock(LOCK)
    acquire_lifecycle_lock(handle)
    try:
        original = private_bytes(IDENTITY)
        record = json.loads(original)
        validate_recovery_candidates(record, read_process_snapshot(OLD_PID),
                                     read_process_snapshot(LIVE_PID))
        env, audit_before = gates(LIVE_PID, LIVE_TICKS)
        backup = IDENTITY.with_name(IDENTITY.name + ".before-recovery-69967")
        require(not backup.exists(), "backup_already_exists")
        if check_only:
            print(json.dumps({"result": "preflight_passed", "controller_pid": LIVE_PID,
                              "stale_record_pid": OLD_PID, "audit_rows": 13,
                              "profile": "3:3:chat_only", "drafts_mutations": False}))
            return
        atomic_private_write(backup, original, replace=False)
        stop_exact(LIVE_PID, LIVE_TICKS)
        new_pid = new_ticks = None
        try:
            new_pid, new_ticks = start_read_only(env)
            gates(new_pid, new_ticks, audit_baseline=audit_before)
            new = dict(record, pid=new_pid, start_ticks=new_ticks)
            atomic_private_write(IDENTITY, (json.dumps(new, indent=2, sort_keys=True) + "\n").encode(), replace=True)
            require(identity_matches(json.loads(private_bytes(IDENTITY)), read_process_snapshot(new_pid),
                                     expected_pid=new_pid, expected_ticks=new_ticks), "new_record_drift")
            gates(new_pid, new_ticks, audit_baseline=audit_before)
            require(private_bytes(backup) == original, "backup_drift")
        except Exception:
            # One read-only rollback attempt; never start a second controller
            # while the new controller still owns its port.
            if new_pid is not None and read_process_snapshot(new_pid) is not None:
                stop_exact(new_pid, new_ticks)
            require(not listener_inodes(8090), "rollback_port_owned")
            rollback_pid, rollback_ticks = start_read_only(env)
            gates(rollback_pid, rollback_ticks, audit_baseline=audit_before)
            rollback_record = dict(record, pid=rollback_pid, start_ticks=rollback_ticks)
            atomic_private_write(IDENTITY, (json.dumps(rollback_record, indent=2, sort_keys=True) + "\n").encode(), replace=True)
            print(json.dumps({"result": "read_only_rollback", "controller_pid": rollback_pid,
                              "backup_preserved": True, "audit_rows": 13}))
            raise RecoveryError("restart_validation_failed_rolled_back") from None
        print(json.dumps({"result": "recovered", "old_pid": LIVE_PID,
                          "new_pid": new_pid, "new_start_ticks": new_ticks,
                          "backup_preserved": True, "audit_rows": 13,
                          "profile": "3:3:chat_only", "drafts_mutations": False}))
    finally:
        release_lifecycle_lock(handle)


if __name__ == "__main__":
    try:
        require(sys.argv[1:] in ([], ["--check"]), "invalid_action")
        run(check_only=sys.argv[1:] == ["--check"])
    except Exception as exc:
        print("controller_identity_recovery_failed:" + type(exc).__name__ + ":" +
              (exc.args[0] if isinstance(exc, RecoveryError) else "internal_error"), file=sys.stderr)
        raise SystemExit(1) from None
