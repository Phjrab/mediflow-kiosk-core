"""Durable C4 operation coordinator with injected lifecycle adapters."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any, Callable

from services.ai_control.core import ControlError, canonical_json, digest, utc_now
from utils.lifecycle_lock import (
    LifecycleLockError,
    acquire_lifecycle_lock,
    open_lifecycle_lock,
    release_lifecycle_lock,
)


TERMINAL_STATES = frozenset({"succeeded", "failed", "rolled_back", "manual_intervention_required", "cancelled"})
ACTIVE_STATES = frozenset({"accepted", "validating", "draining", "stopping", "starting", "verifying", "restoring"})


class LifecycleFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LifecycleAdapter:
    """Concrete adapters must own admission and process identity."""
    def snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def close_admission(self) -> None:
        raise NotImplementedError

    def drain(self, timeout_seconds: int) -> bool:
        raise NotImplementedError

    def apply(self, desired: dict[str, Any]) -> None:
        raise NotImplementedError

    def verify(self, desired: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def restore(self, previous: dict[str, Any]) -> None:
        raise NotImplementedError

    def restore_admission(self, previous: dict[str, Any]) -> None:
        raise NotImplementedError


class OperationJournal:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._initialize_lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._initialize_lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            parent = self.path.parent.stat()
            if parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
                raise ControlError("unsafe_state_directory", 503)
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS operations(
                        operation_id TEXT PRIMARY KEY,
                        principal TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        result_json TEXT,
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(principal, idempotency_key)
                    )"""
                )
            os.chmod(self.path, 0o600)

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        value["request"] = json.loads(value.pop("request_json"))
        raw_result = value.pop("result_json")
        value["result"] = json.loads(raw_result) if raw_result else None
        value["completed"] = value["state"] in TERMINAL_STATES
        return value

    def accept(self, *, principal: str, idempotency_key: str, request_body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not principal or len(principal) > 120 or not idempotency_key or len(idempotency_key) > 200:
            raise ControlError("invalid_idempotency_key")
        self.initialize()
        request_json = canonical_json(request_body)
        payload_hash = digest(request_body)
        now = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM operations WHERE principal=? AND idempotency_key=?",
                (principal, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise ControlError("idempotency_conflict", 409)
                return self._row(existing), False
            manual = connection.execute(
                "SELECT operation_id FROM operations WHERE state='manual_intervention_required' LIMIT 1"
            ).fetchone()
            if manual is not None:
                raise ControlError("manual_intervention_required", 409)
            active = connection.execute(
                "SELECT operation_id FROM operations WHERE state IN (?,?,?,?,?,?,?) LIMIT 1",
                tuple(sorted(ACTIVE_STATES)),
            ).fetchone()
            if active is not None:
                raise ControlError("operation_in_progress", 409)
            operation_id = uuid.uuid4().hex
            connection.execute(
                "INSERT INTO operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (operation_id, principal, idempotency_key, payload_hash, request_json,
                 "accepted", "accepted", None, None, now, now),
            )
            row = connection.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            return self._row(row), True

    def get(self, operation_id: str) -> dict[str, Any]:
        if not isinstance(operation_id, str) or len(operation_id) != 32:
            raise ControlError("operation_not_found", 404)
        self.initialize()
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            raise ControlError("operation_not_found", 404)
        return self._row(row)

    def update(self, operation_id: str, state: str, *, result: Any = None,
               error_code: str | None = None, expected_states: set[str] | None = None) -> dict[str, Any]:
        if state not in ACTIVE_STATES | TERMINAL_STATES:
            raise ValueError("invalid operation state")
        result_json = canonical_json(result) if result is not None else None
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            query = "UPDATE operations SET state=?, stage=?, result_json=?, error_code=?, updated_at=? WHERE operation_id=?"
            parameters: list[Any] = [state, state, result_json, error_code, utc_now(), operation_id]
            if expected_states:
                query += " AND state IN (" + ",".join("?" for _ in expected_states) + ")"
                parameters.extend(sorted(expected_states))
            changed = connection.execute(query, parameters).rowcount
            if changed != 1:
                row = connection.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
                if row is None:
                    raise ControlError("operation_not_found", 404)
                return self._row(row)
            row = connection.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            return self._row(row)

    def active_id(self) -> str | None:
        self.initialize()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT operation_id FROM operations WHERE state IN (?,?,?,?,?,?,?) ORDER BY created_at LIMIT 1",
                tuple(sorted(ACTIVE_STATES)),
            ).fetchone()
        return row["operation_id"] if row else None

    def reconcile_after_restart(self) -> int:
        """Never replay an operation after controller restart without device evidence."""
        self.initialize()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE operations SET state='manual_intervention_required', stage='manual_intervention_required', "
                "error_code='controller_restarted_reconcile_required', updated_at=? "
                "WHERE state IN (?,?,?,?,?,?,?)",
                (utc_now(), *tuple(sorted(ACTIVE_STATES))),
            ).rowcount
        return changed


class OperationCoordinator:
    def __init__(self, *, journal: OperationJournal, lifecycle: LifecycleAdapter,
                 lifecycle_lock_path: str | os.PathLike[str], load_plan: Callable[[str], dict[str, Any]],
                 load_draft: Callable[[str], dict[str, Any]], load_applied: Callable[[], dict[str, Any]],
                 save_applied: Callable[[dict[str, Any]], None], executor=None):
        self.journal = journal
        self.lifecycle = lifecycle
        self.lifecycle_lock_path = Path(lifecycle_lock_path)
        self.load_plan = load_plan
        self.load_draft = load_draft
        self.load_applied = load_applied
        self.save_applied = save_applied
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-control-operation")

    @staticmethod
    def _validate_request(body: Any) -> dict[str, Any]:
        required = {"plan_id", "plan_digest", "expected_config_revision", "expected_deployment_generation", "acknowledgements"}
        if not isinstance(body, dict) or set(body) != required:
            raise ControlError("invalid_operation")
        for field in ("plan_id", "plan_digest"):
            if not isinstance(body[field], str) or not body[field]:
                raise ControlError("invalid_operation")
        for field in ("expected_config_revision", "expected_deployment_generation"):
            if isinstance(body[field], bool) or not isinstance(body[field], int) or body[field] < 0:
                raise ControlError("invalid_operation")
        acknowledgements = body["acknowledgements"]
        if (not isinstance(acknowledgements, list) or len(acknowledgements) > 16
                or any(not isinstance(item, str) or len(item) > 120 for item in acknowledgements)
                or len(set(acknowledgements)) != len(acknowledgements)):
            raise ControlError("invalid_operation")
        return body

    def accept(self, body: Any, *, idempotency_key: str, principal: str = "management") -> dict[str, Any]:
        request_body = self._validate_request(body)
        operation, created = self.journal.accept(
            principal=principal, idempotency_key=idempotency_key, request_body=request_body
        )
        if created:
            self.executor.submit(self._run, operation["operation_id"])
        return operation

    def _validate_plan(self, request_body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        plan = self.load_plan(request_body["plan_id"])
        if plan.get("plan_digest") != request_body["plan_digest"]:
            raise LifecycleFailure("stale_plan")
        if plan.get("blocking_reasons"):
            raise LifecycleFailure("plan_blocked")
        expires = str(plan.get("expires_at", ""))
        try:
            expires_at = dt.datetime.fromisoformat(expires.replace("Z", "+00:00"))
        except ValueError:
            raise LifecycleFailure("stale_plan") from None
        if expires_at <= dt.datetime.now(dt.timezone.utc):
            raise LifecycleFailure("stale_plan")
        applied = self.load_applied()
        expected = (request_body["expected_config_revision"], request_body["expected_deployment_generation"])
        if expected != (applied["config_revision"], applied["deployment_generation"]):
            raise LifecycleFailure("state_changed")
        if expected != (plan["expected_config_revision"], plan["expected_deployment_generation"]):
            raise LifecycleFailure("state_changed")
        required = set(plan.get("required_acknowledgements", []))
        if not required.issubset(request_body["acknowledgements"]):
            raise LifecycleFailure("acknowledgement_required")
        draft = self.load_draft(plan["draft_id"])
        return plan, draft, applied

    def _run(self, operation_id: str) -> None:
        operation = self.journal.get(operation_id)
        previous_runtime = None
        previous_applied = None
        applied_written = False
        admission_closed = False
        lock_handle = None
        try:
            try:
                lock_handle = open_lifecycle_lock(self.lifecycle_lock_path)
                acquire_lifecycle_lock(lock_handle)
            except LifecycleLockError as exc:
                raise LifecycleFailure(exc.code) from None
            transitioned = self.journal.update(
                operation_id, "validating", expected_states={"accepted"}
            )
            if transitioned["state"] != "validating":
                return
            plan, draft, applied = self._validate_plan(operation["request"])
            previous_applied = applied
            previous_runtime = self.lifecycle.snapshot()
            self.journal.update(operation_id, "draining")
            self.lifecycle.close_admission()
            admission_closed = True
            if not self.lifecycle.drain(int(plan.get("drain_timeout_seconds", 120))):
                raise LifecycleFailure("drain_timeout")
            self.journal.update(operation_id, "stopping")
            self.lifecycle.apply(draft["desired"])
            self.journal.update(operation_id, "starting")
            self.journal.update(operation_id, "verifying")
            receipt = self.lifecycle.verify(draft["desired"])
            next_applied = {
                "config_revision": applied["config_revision"] + 1,
                "deployment_generation": applied["deployment_generation"] + 1,
                "applied_profile": draft["desired"]["active_profile"],
                "effective_config": draft["desired"],
                "last_good_config": draft["desired"],
                "effective_config_digest": digest(draft["desired"]),
                "receipt": receipt,
            }
            self.save_applied(next_applied)
            applied_written = True
            self.lifecycle.restore_admission({
                **previous_runtime,
                "deployment_generation": next_applied["deployment_generation"],
            })
            admission_closed = False
            self.journal.update(operation_id, "succeeded", result={
                "config_revision": next_applied["config_revision"],
                "deployment_generation": next_applied["deployment_generation"],
                "effective_config_digest": next_applied["effective_config_digest"],
                "receipt": receipt,
            })
        except Exception as exc:
            code = exc.code if isinstance(exc, (LifecycleFailure, ControlError)) else "operation_failed"
            if previous_runtime is None:
                self.journal.update(operation_id, "failed", error_code=code)
            else:
                try:
                    self.journal.update(operation_id, "restoring", error_code=code)
                    self.lifecycle.restore(previous_runtime)
                    if admission_closed:
                        self.lifecycle.restore_admission(previous_runtime)
                    if applied_written and previous_applied is not None:
                        self.save_applied(previous_applied)
                    self.journal.update(operation_id, "rolled_back", error_code=code)
                except Exception:
                    self.journal.update(
                        operation_id, "manual_intervention_required",
                        error_code="rollback_failed",
                    )
        finally:
            if lock_handle is not None:
                release_lifecycle_lock(lock_handle)

    def get(self, operation_id: str) -> dict[str, Any]:
        return self.journal.get(operation_id)

    def cancel(self, operation_id: str) -> dict[str, Any]:
        operation = self.journal.get(operation_id)
        if operation["state"] != "accepted":
            raise ControlError("operation_not_cancellable", 409)
        updated = self.journal.update(
            operation_id, "cancelled", expected_states={"accepted"}
        )
        if updated["state"] != "cancelled":
            raise ControlError("operation_not_cancellable", 409)
        return updated
