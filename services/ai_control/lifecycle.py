"""Sequential, ownership-preserving lifecycle adapters used by C4 operations."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable

from scripts import local_llm_service
from services.ai_control.core import digest
from services.ai_control.operations import LifecycleAdapter, LifecycleFailure
from utils.ai_config import AIError
from utils.runtime_receipt import validate_runtime_expectation


@dataclass(frozen=True)
class EngineState:
    state: str
    managed: bool
    identity: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None


class EngineAdapter:
    """An engine may stop only a process whose persisted identity it validates."""

    def snapshot(self) -> EngineState:
        raise NotImplementedError

    def start(self, desired: dict[str, Any]) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class LocalLlmEngine(EngineAdapter):
    """Reuse the existing local LLM manager rather than duplicating PID logic."""

    def __init__(self, spec: local_llm_service.ServiceSpec, *, receipt: Callable[[], dict[str, Any]],
                 prepare_start: Callable[[dict[str, Any]], None] | None = None):
        self.spec = spec
        self._receipt = receipt
        self._prepare_start = prepare_start

    def snapshot(self) -> EngineState:
        state, record, _process = local_llm_service.inspect_service(
            self.spec, remove_stale=False
        )
        if state == "running":
            return EngineState("running", True, dict(record or {}), self._receipt())
        if state == "stopped":
            return EngineState("stopped", True)
        return EngineState(state, False, dict(record or {}) if record else None)

    def start(self, desired: dict[str, Any]) -> None:
        if self._prepare_start is not None:
            self._prepare_start(desired)
        local_llm_service.start_service(self.spec)

    def stop(self) -> None:
        # stop_service revalidates UID/executable/argv/cwd/boot/start-tick before signal.
        local_llm_service.stop_service(self.spec)


@dataclass(frozen=True)
class OwnedProcessSpec:
    pid_path: Path
    uid: int
    executable: str
    argv: tuple[str, ...]
    cwd: str


class OwnedProcessEngine(EngineAdapter):
    """Exact-record owner adapter for a process without a reusable manager.

    The adapter validates the private PID record and the live `/proc` identity
    before it passes a PID to the stop callback. A missing record is considered
    stopped only when the engine-specific unmanaged probe is also clear.
    """

    def __init__(
        self, spec: OwnedProcessSpec, *, start: Callable[[dict[str, Any]], None],
        stop: Callable[[int], None], receipt: Callable[[], dict[str, Any]],
        unmanaged_present: Callable[[], bool],
        read_snapshot: Callable[[int], local_llm_service.ProcessSnapshot | None] =
        local_llm_service.read_process_snapshot,
    ):
        self.spec = spec
        self._start = start
        self._stop = stop
        self._receipt = receipt
        self._unmanaged_present = unmanaged_present
        self._read_snapshot = read_snapshot

    def _record(self) -> dict[str, Any] | None:
        path = self.spec.pid_path
        if self.spec.uid != os.geteuid():
            raise LifecycleFailure("process_identity_unverified")
        if path.is_symlink():
            raise LifecycleFailure("process_identity_unverified")
        if not path.exists():
            return None
        try:
            metadata = path.lstat()
            if (path.is_symlink() or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != self.spec.uid or metadata.st_mode & 0o077
                    or metadata.st_size > 64 * 1024):
                raise ValueError("unsafe record")
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("invalid record")
            return value
        except (OSError, ValueError, UnicodeError):
            raise LifecycleFailure("process_identity_unverified") from None

    def _validated(self) -> tuple[EngineState, int | None]:
        record = self._record()
        if record is None:
            if self._unmanaged_present():
                return EngineState("unmanaged_process", False), None
            return EngineState("stopped", True), None
        try:
            pid = int(record["pid"])
            recorded_argv = tuple(record["argv"])
            if (record.get("version") != 1 or pid <= 1
                    or record.get("uid") != self.spec.uid
                    or record.get("executable") != self.spec.executable
                    or recorded_argv != self.spec.argv
                    or record.get("cwd") != self.spec.cwd
                    or not isinstance(record.get("start_ticks"), int)
                    or not isinstance(record.get("boot_id"), str)):
                return EngineState("identity_mismatch", False, record), None
        except (KeyError, TypeError, ValueError):
            return EngineState("identity_mismatch", False, record), None
        live = self._read_snapshot(pid)
        if live is None:
            return EngineState("stale_record", False, record), None
        matches = (
            live.pid == pid
            and live.uid == self.spec.uid
            and live.executable == self.spec.executable
            and live.argv == self.spec.argv
            and live.cwd == self.spec.cwd
            and live.start_ticks == record["start_ticks"]
            and live.boot_id == record["boot_id"]
        )
        if not matches:
            return EngineState("identity_mismatch", False, record), None
        return EngineState("running", True, record, self._receipt()), pid

    def snapshot(self) -> EngineState:
        state, _pid = self._validated()
        return state

    def start(self, desired: dict[str, Any]) -> None:
        state, _pid = self._validated()
        if not state.managed or state.state != "stopped":
            raise LifecycleFailure("unmanaged_process")
        self._start(desired)
        started, _pid = self._validated()
        if not started.managed or started.state != "running":
            raise LifecycleFailure("start_identity_unverified")

    def stop(self) -> None:
        state, pid = self._validated()
        if not state.managed:
            raise LifecycleFailure("unmanaged_process")
        if state.state == "stopped":
            return
        assert pid is not None
        self._stop(pid)
        stopped, _pid = self._validated()
        if not stopped.managed or stopped.state != "stopped":
            raise LifecycleFailure("stop_identity_unverified")


class OwnedMedGemmaEngine(OwnedProcessEngine):
    """MedGemma ownership adapter; deployment supplies fixed launch/stop probes."""


class SequentialLifecycleAdapter(LifecycleAdapter):
    """Never permits two heavy engines and delegates admission to managed ingress."""

    def __init__(self, *, chat: EngineAdapter, vlm: EngineAdapter, ingress):
        self.chat = chat
        self.vlm = vlm
        self.ingress = ingress

    def snapshot(self) -> dict[str, Any]:
        chat = self.chat.snapshot()
        vlm = self.vlm.snapshot()
        for engine in (chat, vlm):
            if not engine.managed:
                raise LifecycleFailure("unmanaged_process")
        running = [name for name, state in (("chat_only", chat), ("vlm_only", vlm)) if state.state == "running"]
        if len(running) > 1:
            raise LifecycleFailure("co_residency_unverified")
        return {
            "profile": running[0] if running else "stopped",
            "chat": chat,
            "vlm": vlm,
            **self.ingress.snapshot(),
        }

    def close_admission(self) -> None:
        self.ingress.close_admission()

    def drain(self, timeout_seconds: int) -> bool:
        return self.ingress.drain(timeout_seconds)

    def _stop_running(self) -> None:
        chat = self.chat.snapshot()
        vlm = self.vlm.snapshot()
        if not chat.managed or not vlm.managed:
            raise LifecycleFailure("unmanaged_process")
        if chat.state == "running":
            self.chat.stop()
        if vlm.state == "running":
            self.vlm.stop()

    def apply(self, desired: dict[str, Any]) -> None:
        profile = desired["active_profile"]
        if profile not in {"stopped", "chat_only", "vlm_only"}:
            raise LifecycleFailure("invalid_profile")
        self._stop_running()
        if profile == "chat_only":
            self.chat.start(desired)
        elif profile == "vlm_only":
            self.vlm.start(desired)

    def verify(self, desired: dict[str, Any]) -> dict[str, Any]:
        observed = self.snapshot()
        profile = desired["active_profile"]
        if observed["profile"] != profile:
            raise LifecycleFailure("verification_failed")
        if profile == "stopped":
            return {
                "observed_profile": "stopped",
                "effective_config_digest": digest(desired),
            }
        engine = observed["chat"] if profile == "chat_only" else observed["vlm"]
        if not engine.receipt:
            raise LifecycleFailure("verification_failed")
        engine_name = "chat" if profile == "chat_only" else "vlm"
        expected_artifact = desired.get("engines", {}).get(engine_name, {}).get("artifact_id")
        expected_digest = digest(desired)
        if (not expected_artifact
                or engine.receipt.get("artifact_id") != expected_artifact
                or engine.receipt.get("effective_config_digest") != expected_digest):
            raise LifecycleFailure("verification_failed")
        try:
            receipt = validate_runtime_expectation(dict(engine.receipt))
        except AIError:
            raise LifecycleFailure("verification_failed") from None
        return {**receipt, "effective_config_digest": expected_digest}

    def restore(self, previous: dict[str, Any]) -> None:
        self._stop_running()
        profile = previous["profile"]
        if profile == "chat_only":
            self.chat.start({
                "active_profile": profile, "restore": True,
                "_runtime_receipt": previous["chat"].receipt,
            })
        elif profile == "vlm_only":
            self.vlm.start({
                "active_profile": profile, "restore": True,
                "_runtime_receipt": previous["vlm"].receipt,
            })
        elif profile != "stopped":
            raise LifecycleFailure("restore_state_invalid")

    def restore_admission(self, previous: dict[str, Any]) -> None:
        self.ingress.restore_admission(previous)
