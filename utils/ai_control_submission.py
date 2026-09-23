"""Private A-side idempotency record written before controller mutation requests."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import uuid
from typing import Any, Callable

from utils.ai_config import AIError
from utils.runtime_receipt import validate_runtime_expectation


_ID = re.compile(r"[0-9a-f]{32}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {
    "plan_id", "plan_digest", "expected_config_revision",
    "expected_deployment_generation", "acknowledgements",
}


def validate_operation_request(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise AIError("invalid_operation")
    if not isinstance(body["plan_id"], str) or not _ID.fullmatch(body["plan_id"]):
        raise AIError("invalid_operation")
    if not isinstance(body["plan_digest"], str) or not _DIGEST.fullmatch(body["plan_digest"]):
        raise AIError("invalid_operation")
    for field in ("expected_config_revision", "expected_deployment_generation"):
        if isinstance(body[field], bool) or not isinstance(body[field], int) or body[field] < 0:
            raise AIError("invalid_operation")
    acknowledgements = body["acknowledgements"]
    if (not isinstance(acknowledgements, list) or len(acknowledgements) > 16
            or any(not isinstance(item, str) or not item or len(item) > 120
                   for item in acknowledgements)
            or len(set(acknowledgements)) != len(acknowledgements)):
        raise AIError("invalid_operation")
    return body


def validate_operation_gate(overview: Any, body: Any) -> dict[str, Any]:
    request = validate_operation_request(body)
    if not isinstance(overview, dict):
        raise AIError("controller_invalid_response")
    try:
        state = overview["state"]
        capabilities = overview["capabilities"]
        current = overview["current_config"]
        for item in (state, capabilities, current):
            cache = item["cache"]
            if cache["stale"] or cache["connection_state"] != "connected":
                raise AIError("controller_unreachable")
        activity = state["activity"]
        if (not capabilities["drafts_enabled"] or not capabilities["mutations_enabled"]
                or not capabilities["managed_ingress_verified"]
                or state["active_operation_id"] is not None
                or activity["source"] != "managed_ingress"
                or activity["admission"] != "open"
                or activity["inflight"] != 0 or activity["unknown_inflight"] != 0):
            raise AIError("activity_unknown")
        receipt = validate_runtime_expectation(current["receipt"])
        if (receipt["config_revision"] != current["config_revision"]
                or receipt["deployment_generation"] != current["deployment_generation"]
                or receipt["effective_config_digest"] != current["effective_config_digest"]
                or receipt["artifact_id"] != state["engine"]["artifact_id"]
                or receipt["node_id"] != state["node_id"]
                or current["config_revision"] != state["config_revision"]
                or current["deployment_generation"] != state["deployment_generation"]
                or current["applied_profile"] != state["observed_profile"]
                or request["expected_config_revision"] != current["config_revision"]
                or request["expected_deployment_generation"] != current["deployment_generation"]):
            raise AIError("state_changed")
    except AIError:
        raise
    except (KeyError, TypeError, ValueError):
        raise AIError("controller_invalid_response") from None
    return request


class OperationSubmissionStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise AIError("misconfigured")
        try:
            info = self.root.stat()
        except OSError:
            raise AIError("misconfigured") from None
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise AIError("misconfigured")

    def _open_private(self, name: str, flags: int, mode: int = 0o600) -> int:
        try:
            fd = os.open(self.root / name, flags | os.O_NOFOLLOW, mode)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                os.close(fd)
                raise AIError("unsafe_state_file")
            return fd
        except OSError:
            raise AIError("unsafe_state_file") from None

    def _read(self, plan_id: str) -> dict[str, Any] | None:
        try:
            fd = self._open_private(plan_id + ".json", os.O_RDONLY)
        except AIError as exc:
            if not (self.root / (plan_id + ".json")).exists():
                return None
            raise exc
        with os.fdopen(fd, "r", encoding="utf-8") as source:
            try:
                value = json.load(source)
            except (ValueError, UnicodeError):
                raise AIError("unsafe_state_file") from None
        if not isinstance(value, dict) or set(value) != {"request", "client_request_id", "operation_id", "status"}:
            raise AIError("unsafe_state_file")
        if not isinstance(value["client_request_id"], str) or not _ID.fullmatch(value["client_request_id"]):
            raise AIError("unsafe_state_file")
        if value["status"] not in {"pending", "known", "rejected"}:
            raise AIError("unsafe_state_file")
        return value

    def _write(self, plan_id: str, value: dict[str, Any], *, replace: bool) -> None:
        name = ("tmp-" + uuid.uuid4().hex + ".json") if replace else (plan_id + ".json")
        fd = self._open_private(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(value, output, sort_keys=True, separators=(",", ":"))
                output.flush()
                os.fsync(output.fileno())
            if replace:
                os.replace(self.root / name, self.root / (plan_id + ".json"))
            directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            if replace:
                (self.root / name).unlink(missing_ok=True)
            raise

    def submit(self, body: Any, send: Callable[[dict[str, Any], str], dict[str, Any]]) -> dict[str, Any]:
        request = validate_operation_request(body)
        lock_fd = self._open_private("submit.lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            plan_id = request["plan_id"]
            value = self._read(plan_id)
            if value is None:
                for path in self.root.glob("*.json"):
                    if _ID.fullmatch(path.stem):
                        other = self._read(path.stem)
                        if other is not None and other["status"] == "pending":
                            raise AIError("submission_unknown")
                value = {"request": request, "client_request_id": uuid.uuid4().hex,
                         "operation_id": None, "status": "pending"}
                self._write(plan_id, value, replace=False)
            elif value["request"] != request:
                raise AIError("idempotency_conflict")
            elif value["status"] == "rejected":
                raise AIError("operation_rejected")
            try:
                response = send(request, value["client_request_id"])
            except AIError as exc:
                if exc.code not in {"controller_unreachable", "controller_invalid_response"}:
                    self._write(plan_id, {**value, "status": "rejected"}, replace=True)
                raise
            operation_id = response.get("operation_id")
            if not isinstance(operation_id, str) or not _ID.fullmatch(operation_id):
                raise AIError("controller_invalid_response")
            if value["operation_id"] not in (None, operation_id):
                raise AIError("controller_invalid_response")
            if value["operation_id"] is None:
                self._write(plan_id, {**value, "operation_id": operation_id,
                                      "status": "known"}, replace=True)
            return {"operation_id": operation_id, "state": response.get("state"),
                    "completed": response.get("completed"), "client_request_id": value["client_request_id"]}
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def latest(self) -> dict[str, Any] | None:
        records = sorted((path for path in self.root.glob("*.json") if _ID.fullmatch(path.stem)),
                         key=lambda path: path.stat().st_mtime_ns, reverse=True)
        if not records:
            return None
        value = self._read(records[0].stem)
        if value is None:
            raise AIError("unsafe_state_file")
        return {"plan_id": records[0].stem, "operation_id": value["operation_id"],
                "submission_unknown": value["status"] == "pending",
                "submission_rejected": value["status"] == "rejected"}
