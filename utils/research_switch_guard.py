"""A-side durable pause between research job claims and admin model switching.

The guard is deliberately inactive until its owner-only directory exists. Once
installed, every updated ExperimentStore claim uses the same process lock and
pause marker, including workers with an explicit isolated research store.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid
from typing import Callable, Iterator, TypeVar

from utils.ai_config import AIError
from utils.runtime_receipt import validate_runtime_expectation


T = TypeVar("T")
_ID = re.compile(r"[0-9a-f]{32}\Z")


def default_guard_dir() -> Path:
    return Path.home() / ".local" / "state" / "mediflow-ai" / "research-switch-guard"


def _private_file(path: Path) -> bytes:
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise AIError("research_guard_unavailable")
        return path.read_bytes()
    except OSError:
        raise AIError("research_guard_unavailable") from None


class ResearchSwitchGuard:
    def __init__(self, directory: Path):
        self.directory = directory
        try:
            info = directory.lstat()
            if (not directory.is_absolute() or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077):
                raise AIError("research_guard_unavailable")
        except OSError:
            raise AIError("research_guard_unavailable") from None

    @classmethod
    def for_admin(cls, env) -> "ResearchSwitchGuard":
        configured = str(env.get("AI_CONTROL_RESEARCH_GUARD_DIR", "")).strip()
        # A's admin server and every worker must resolve the identical path.
        if configured != str(default_guard_dir()):
            raise AIError("research_guard_unavailable")
        return cls(default_guard_dir())

    @contextmanager
    def _lock(self) -> Iterator[None]:
        path = self.directory / "guard.lock"
        try:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                os.close(descriptor)
                raise AIError("research_guard_unavailable")
            with os.fdopen(descriptor, "r+") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            raise AIError("research_guard_unavailable") from None

    def _read_json(self, name: str, default):
        path = self.directory / name
        if not path.exists() and not path.is_symlink():
            return default
        try:
            return json.loads(_private_file(path))
        except (ValueError, UnicodeError):
            raise AIError("research_guard_unavailable") from None

    def _write_json(self, name: str, value) -> None:
        path = self.directory / name
        temporary = self.directory / ("." + name + "." + uuid.uuid4().hex)
        payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            self._sync_dir()
        finally:
            temporary.unlink(missing_ok=True)

    def _sync_dir(self) -> None:
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _registered(self) -> set[Path]:
        raw = self._read_json("stores.json", [])
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise AIError("research_guard_unavailable")
        result = {Path(item) for item in raw}
        if any(not path.is_absolute() for path in result):
            raise AIError("research_guard_unavailable")
        return result

    def _pause(self) -> dict | None:
        value = self._read_json("pause.json", None)
        if value is not None and (not isinstance(value, dict)
                                  or set(value) != {"plan_id"}
                                  or not isinstance(value["plan_id"], str)
                                  or not _ID.fullmatch(value["plan_id"])):
            raise AIError("research_guard_unavailable")
        return value

    @staticmethod
    def _active_jobs(path: Path) -> int:
        _private_file(path)
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
            try:
                return int(connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','cancel_requested')"
                ).fetchone()[0])
            finally:
                connection.close()
        except (sqlite3.Error, TypeError, ValueError):
            raise AIError("research_guard_unavailable") from None

    def claim(self, db_path: Path, callback: Callable[[], T]) -> T | None:
        with self._lock():
            path = db_path.resolve(strict=True)
            _private_file(path)
            stores = self._registered()
            if path not in stores:
                stores.add(path)
                self._write_json("stores.json", sorted(str(item) for item in stores))
            if self._pause() is not None:
                return None
            return callback()

    def _stores(self, research_root: Path) -> set[Path]:
        try:
            info = research_root.lstat()
            if (not research_root.is_absolute() or not stat.S_ISDIR(info.st_mode)
                    or info.st_uid != os.geteuid()):
                raise AIError("research_guard_unavailable")
        except OSError:
            raise AIError("research_guard_unavailable") from None
        stores = self._registered() | set(research_root.rglob("experiments.db"))
        if not stores:
            raise AIError("research_guard_unavailable")
        return stores

    def pause_for(self, plan_id: str, research_root: Path) -> None:
        if not isinstance(plan_id, str) or not _ID.fullmatch(plan_id):
            raise AIError("research_guard_unavailable")
        with self._lock():
            previous = self._pause()
            if previous is not None:
                if previous["plan_id"] == plan_id:
                    return
                raise AIError("activity_unknown")
            stores = self._stores(research_root)
            if any(self._active_jobs(path) for path in stores):
                raise AIError("active_experiment")
            self._write_json("pause.json", {"plan_id": plan_id})

    def resume_for(self, plan_id: str, research_root: Path) -> bool:
        with self._lock():
            previous = self._pause()
            if previous is None:
                return False
            if previous["plan_id"] != plan_id:
                raise AIError("activity_unknown")
            if any(self._active_jobs(path) for path in self._stores(research_root)):
                raise AIError("active_experiment")
            (self.directory / "pause.json").unlink()
            self._sync_dir()
            return True

    def paused_plan_id(self) -> str | None:
        with self._lock():
            previous = self._pause()
            return previous["plan_id"] if previous else None


def guarded_claim(db_path: Path, callback: Callable[[], T]) -> T | None:
    directory = default_guard_dir()
    if not directory.exists() and not directory.is_symlink():
        return callback()
    return ResearchSwitchGuard(directory).claim(db_path, callback)


def safe_to_resume(overview: dict) -> bool:
    """Require a fresh, idle, receipt-consistent controller before unpausing."""
    try:
        state = overview["state"]
        current = overview["current_config"]
        capabilities = overview["capabilities"]
        for item in (state, current, capabilities):
            cache = item["cache"]
            if cache["stale"] or cache["connection_state"] != "connected":
                return False
        activity = state["activity"]
        receipt = validate_runtime_expectation(current["receipt"])
        return bool(
            capabilities["drafts_enabled"] and capabilities["mutations_enabled"]
            and capabilities["managed_ingress_verified"]
            and state["active_operation_id"] is None
            and state["lifecycle_state"] == "ready"
            and state["engine"]["inference_ready"] is True
            and state["observed_profile"] == current["applied_profile"]
            and state["node_id"] == receipt["node_id"]
            and state["config_revision"] == current["config_revision"] == receipt["config_revision"]
            and state["deployment_generation"] == current["deployment_generation"] == receipt["deployment_generation"]
            and state["engine"]["artifact_id"] == receipt["artifact_id"]
            and current["effective_config_digest"] == receipt["effective_config_digest"]
            and activity == {"source": "managed_ingress", "admission": "open",
                             "inflight": 0, "unknown_inflight": 0}
        )
    except (AIError, KeyError, TypeError, ValueError):
        return False
