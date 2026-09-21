"""Durable admission and lease accounting for controller-owned inference ingress."""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable

from services.ai_control.core import ControlError


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class IngressJournal:
    """Small private database; request bodies, prompts, and credentials are never stored."""

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._initialize_lock = threading.Lock()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> int:
        """Reconcile interrupted active leases to unknown once at ingress startup."""
        with self._initialize_lock:
            self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            info = self.path.parent.stat()
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ControlError("unsafe_state_directory", 503)
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS ingress_state(
                         singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                         admission TEXT NOT NULL CHECK(admission IN ('open','closed','manual_intervention')),
                         deployment_generation INTEGER NOT NULL,
                         raw_bypass_closed INTEGER NOT NULL CHECK(raw_bypass_closed IN (0,1)),
                         updated_at TEXT NOT NULL
                       )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS ingress_leases(
                         lease_id TEXT PRIMARY KEY,
                         route TEXT NOT NULL,
                         deployment_generation INTEGER NOT NULL,
                         state TEXT NOT NULL CHECK(state IN ('active','completed','unknown')),
                         started_at TEXT NOT NULL,
                         updated_at TEXT NOT NULL
                       )"""
                )
                connection.execute(
                    "INSERT OR IGNORE INTO ingress_state VALUES (1,'closed',0,0,?)",
                    (_utc_now(),),
                )
                interrupted = connection.execute(
                    "UPDATE ingress_leases SET state='unknown', updated_at=? WHERE state='active'",
                    (_utc_now(),),
                ).rowcount
                if interrupted:
                    connection.execute(
                        "UPDATE ingress_state SET admission='closed', updated_at=? WHERE singleton=1",
                        (_utc_now(),),
                    )
            os.chmod(self.path, 0o600)
            return interrupted

    def snapshot(self) -> dict[str, Any]:
        with self._connection() as connection:
            state = connection.execute("SELECT * FROM ingress_state WHERE singleton=1").fetchone()
            counts = {
                row["state"]: int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM ingress_leases GROUP BY state"
                )
            }
        if state is None:
            raise ControlError("ingress_uninitialized", 503)
        return {
            "source": "managed_ingress",
            "admission": state["admission"],
            "deployment_generation": int(state["deployment_generation"]),
            "raw_bypass_closed": bool(state["raw_bypass_closed"]),
            "inflight": counts.get("active", 0),
            "unknown_inflight": counts.get("unknown", 0),
        }

    def open(self, *, deployment_generation: int, raw_bypass_closed: bool) -> None:
        if (isinstance(deployment_generation, bool)
                or not isinstance(deployment_generation, int)
                or deployment_generation < 0):
            raise ControlError("invalid_generation")
        if not raw_bypass_closed:
            raise ControlError("raw_ingress_bypass", 409)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT COUNT(*) FROM ingress_leases WHERE state IN ('active','unknown')"
            ).fetchone()[0]
            if pending:
                raise ControlError("activity_unknown", 409)
            connection.execute(
                """UPDATE ingress_state
                   SET admission='open', deployment_generation=?, raw_bypass_closed=1, updated_at=?
                   WHERE singleton=1""",
                (deployment_generation, _utc_now()),
            )

    def close(self, *, manual_intervention: bool = False) -> None:
        state = "manual_intervention" if manual_intervention else "closed"
        with self._connection() as connection:
            connection.execute(
                "UPDATE ingress_state SET admission=?, updated_at=? WHERE singleton=1",
                (state, _utc_now()),
            )

    def admit(self, route: str, *, expected_generation: int | None = None) -> str:
        if route not in {"chat", "vlm"}:
            raise ControlError("invalid_ingress_route")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute("SELECT * FROM ingress_state WHERE singleton=1").fetchone()
            unknown = connection.execute(
                "SELECT COUNT(*) FROM ingress_leases WHERE state='unknown'"
            ).fetchone()[0]
            if state is None or state["admission"] != "open" or not state["raw_bypass_closed"]:
                raise ControlError("admission_closed", 503)
            if unknown:
                raise ControlError("activity_unknown", 503)
            generation = int(state["deployment_generation"])
            if expected_generation is not None and expected_generation != generation:
                raise ControlError("configuration_drift", 409)
            lease_id = uuid.uuid4().hex
            now = _utc_now()
            connection.execute(
                "INSERT INTO ingress_leases VALUES (?,?,?,?,?,?)",
                (lease_id, route, generation, "active", now, now),
            )
        return lease_id

    def complete(self, lease_id: str) -> None:
        self._transition(lease_id, "completed")

    def mark_unknown(self, lease_id: str) -> None:
        self._transition(lease_id, "unknown")
        self.close()

    def _transition(self, lease_id: str, state: str) -> None:
        with self._connection() as connection:
            changed = connection.execute(
                "UPDATE ingress_leases SET state=?, updated_at=? WHERE lease_id=? AND state='active'",
                (state, _utc_now(), lease_id),
            ).rowcount
        if changed != 1:
            raise ControlError("invalid_lease_transition", 409)

    def reconcile_unknown(self, lease_id: str, *, backend_completion_verified: bool) -> None:
        if not backend_completion_verified:
            raise ControlError("activity_unknown", 409)
        with self._connection() as connection:
            changed = connection.execute(
                "UPDATE ingress_leases SET state='completed', updated_at=? WHERE lease_id=? AND state='unknown'",
                (_utc_now(), lease_id),
            ).rowcount
        if changed != 1:
            raise ControlError("invalid_lease_transition", 409)

    def drain(
        self, timeout_seconds: float, *, monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bool:
        if (isinstance(timeout_seconds, bool)
                or not isinstance(timeout_seconds, (int, float))
                or timeout_seconds < 0):
            raise ControlError("invalid_drain_timeout")
        deadline = monotonic() + timeout_seconds
        while True:
            state = self.snapshot()
            if state["unknown_inflight"]:
                return False
            if state["inflight"] == 0:
                return True
            if monotonic() >= deadline:
                return False
            sleep(min(0.05, max(0.0, deadline - monotonic())))


class ManagedIngress:
    def __init__(self, journal: IngressJournal):
        self.journal = journal

    def snapshot(self) -> dict[str, Any]:
        return self.journal.snapshot()

    def close_admission(self) -> None:
        self.journal.close()

    def drain(self, timeout_seconds: int) -> bool:
        return self.journal.drain(timeout_seconds)

    def restore_admission(self, previous: dict[str, Any]) -> None:
        if previous.get("admission") == "open":
            self.journal.open(
                deployment_generation=int(previous["deployment_generation"]),
                raw_bypass_closed=bool(previous.get("raw_bypass_closed")),
            )
        else:
            self.journal.close(
                manual_intervention=previous.get("admission") == "manual_intervention"
            )
