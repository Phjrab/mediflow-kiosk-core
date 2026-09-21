"""Fail-closed controller mutation bootstrap for the two owned Jetson B engines."""
from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any, Mapping

from scripts import local_llm_service, medgemma_service
from services.ai_control.core import ControlService, canonical_json, digest
from services.ai_control.ingress import IngressJournal, ManagedIngress
from services.ai_control.ingress_app import load_private_runtime_receipt
from services.ai_control.lifecycle import (
    LocalLlmEngine,
    OwnedMedGemmaEngine,
    OwnedProcessSpec,
    SequentialLifecycleAdapter,
)
from services.ai_control.operations import LifecycleFailure, OperationCoordinator, OperationJournal
from utils.ai_config import AIError, secret
from utils.runtime_receipt import validate_runtime_expectation


def _absolute(env: Mapping[str, str], name: str) -> Path:
    raw = str(env.get(name, "")).strip()
    path = Path(raw).expanduser()
    if not raw or not path.is_absolute():
        raise RuntimeError(f"{name} must be absolute")
    return path


def _private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.parent.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("runtime receipt parent must be private and owner-only")


class RuntimeReceiptManager:
    def __init__(self, path: Path, service: ControlService):
        if not path.is_absolute():
            raise RuntimeError("runtime receipt path must be absolute")
        _private_parent(path)
        self.path = path
        self.service = service

    def read(self) -> dict[str, Any]:
        return load_private_runtime_receipt(self.path)

    def _next(self, desired: dict[str, Any]) -> dict[str, Any]:
        restored = desired.get("_runtime_receipt")
        if restored is not None:
            try:
                return validate_runtime_expectation(restored)
            except AIError:
                raise LifecycleFailure("restore_receipt_invalid") from None
        if set(desired) != {"active_profile", "engines"}:
            raise LifecycleFailure("invalid_runtime_config")
        profile = desired["active_profile"]
        kind = "chat" if profile == "chat_only" else "vlm" if profile == "vlm_only" else None
        if kind is None:
            raise LifecycleFailure("runtime_receipt_unavailable")
        selection = desired.get("engines", {}).get(kind, {})
        artifact_id = selection.get("artifact_id")
        catalog = self.service.catalog.load()
        artifact = next((item for item in catalog["models"] if item["artifact_id"] == artifact_id), None)
        if artifact is None or artifact.get("engine_kind") != kind or not artifact.get("eligible_for_activation"):
            raise LifecycleFailure("artifact_unavailable")
        applied = self.service._applied()
        try:
            return validate_runtime_expectation({
                "node_id": self.service.node_id,
                "artifact_id": artifact["artifact_id"],
                "artifact_manifest_digest": artifact["artifact_manifest_digest"],
                "runtime_revision": artifact["runtime_revision"],
                "config_revision": int(applied["config_revision"]) + 1,
                "deployment_generation": int(applied["deployment_generation"]) + 1,
                "effective_config_digest": digest(desired),
            })
        except (KeyError, TypeError, ValueError, AIError):
            raise LifecycleFailure("runtime_receipt_unavailable") from None

    def write_for(self, desired: dict[str, Any]) -> dict[str, Any]:
        receipt = self._next(desired)
        if self.path.exists():
            info = self.path.lstat()
            if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.geteuid() or info.st_mode & 0o077):
                raise LifecycleFailure("unsafe_runtime_receipt")
        temporary = self.path.with_name("." + self.path.name + ".next")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                handle.write(canonical_json(receipt) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)
        return receipt

    @staticmethod
    def child_environment(receipt: Mapping[str, Any]) -> dict[str, str]:
        return {
            "AI_CONTROL_NODE_ID": str(receipt["node_id"]),
            "AI_CONTROL_ARTIFACT_ID": str(receipt["artifact_id"]),
            "AI_CONTROL_ARTIFACT_MANIFEST_DIGEST": str(receipt["artifact_manifest_digest"]),
            "AI_CONTROL_RUNTIME_REVISION": str(receipt["runtime_revision"]),
            "AI_CONTROL_CONFIG_REVISION": str(receipt["config_revision"]),
            "AI_CONTROL_DEPLOYMENT_GENERATION": str(receipt["deployment_generation"]),
            "AI_CONTROL_EFFECTIVE_CONFIG_DIGEST": str(receipt["effective_config_digest"]),
        }


def _chat_spec(env: Mapping[str, str]) -> local_llm_service.ServiceSpec:
    project_root = _absolute(env, "AI_CONTROL_PROJECT_ROOT").resolve(strict=True)
    server = _absolute(env, "AI_CONTROL_LLAMA_SERVER").resolve(strict=True)
    pid_path = _absolute(env, "AI_CONTROL_LOCAL_LLM_PID_FILE")
    raw_port = str(env.get("AI_CONTROL_CHAT_RAW_PORT", "")).strip()
    if raw_port != "18080" or str(env.get("LOCAL_LLM_HOST", "")).strip() != "127.0.0.1" \
            or str(env.get("LOCAL_LLM_PORT", "")).strip() != "18080":
        raise RuntimeError("managed chat must use loopback port 18080")
    launcher = project_root / "scripts" / "run_local_llm_candidate.sh"
    model_dir = _absolute(env, "LOCAL_LLM_MODEL_DIR")
    if not launcher.is_file() or not server.is_file() or not os.access(server, os.X_OK) or not model_dir.is_dir():
        raise RuntimeError("managed chat paths are unavailable")
    try:
        secret(env, "LOCAL_LLM")
    except AIError:
        raise RuntimeError("local LLM key file is unsafe") from None
    if str(env.get("LOCAL_LLM_API_KEY", "")).strip():
        raise RuntimeError("managed chat forbids an inline API key")
    control_dir = pid_path.parent
    local_llm_service.ensure_private_directory(control_dir)
    return local_llm_service.ServiceSpec(
        project_root=project_root,
        launcher=launcher,
        server=server,
        control_dir=control_dir,
        pid_path=pid_path,
        log_path=control_dir / "local-llm.log",
        lock_path=control_dir / "local-llm.lock",
        health_url="http://127.0.0.1:18080/health",
        port=18080,
    )


def _validate_arming_state(
    service: ControlService, snapshot: Mapping[str, Any], receipt: Mapping[str, Any],
) -> None:
    applied = service._applied()
    profile = applied.get("applied_profile")
    activity_ok = (
        snapshot.get("admission") == "open"
        and snapshot.get("raw_bypass_closed") is True
        and snapshot.get("inflight") == 0
        and snapshot.get("unknown_inflight") == 0
        and snapshot.get("deployment_generation") == applied.get("deployment_generation")
    )
    if not activity_ok or snapshot.get("profile") != profile:
        raise RuntimeError("mutation arming state does not match the applied runtime")
    if profile not in {"chat_only", "vlm_only"}:
        raise RuntimeError("mutation arming requires one exact-owned active profile")
    kind = "chat" if profile == "chat_only" else "vlm"
    expected_artifact = (
        (applied.get("effective_config") or {}).get("engines", {}).get(kind, {}).get("artifact_id")
    )
    expected = {
        "artifact_id": expected_artifact,
        "config_revision": applied.get("config_revision"),
        "deployment_generation": applied.get("deployment_generation"),
        "effective_config_digest": applied.get("effective_config_digest"),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RuntimeError("mutation arming receipt does not match the applied runtime")


def build_operation_coordinator(
    service: ControlService, env: Mapping[str, str],
) -> OperationCoordinator:
    if not service.drafts_enabled or not service.mutations_enabled or not service.managed_ingress_verified:
        raise RuntimeError("mutation bootstrap requires drafts, mutations and managed ingress")
    lifecycle_lock = _absolute(env, "AI_DEVICE_LIFECYCLE_LOCK")
    ingress_dir = _absolute(env, "AI_CONTROL_INGRESS_STATE_DIR")
    if str(env.get("AI_CONTROL_VLM_RAW_PORT", "")).strip() != "18081":
        raise RuntimeError("managed VLM must use loopback port 18081")
    receipt_manager = RuntimeReceiptManager(
        _absolute(env, "AI_INGRESS_RUNTIME_RECEIPT_FILE"), service
    )
    # Refuse to arm mutation unless the current receipt is already safe and complete.
    current_receipt = receipt_manager.read()

    chat_spec = _chat_spec(env)
    medgemma_spec = medgemma_service.build_spec(
        env, project_root=Path(__file__).resolve().parents[2]
    )
    if _absolute(env, "AI_CONTROL_MEDGEMMA_PID_FILE") != medgemma_spec.pid_path:
        raise RuntimeError("AI_CONTROL_MEDGEMMA_PID_FILE does not match the owned manager")
    chat = LocalLlmEngine(
        chat_spec,
        receipt=receipt_manager.read,
        prepare_start=receipt_manager.write_for,
    )

    def start_vlm(desired: dict[str, Any]) -> None:
        receipt = receipt_manager.write_for(desired)
        child_env = dict(env)
        child_env.update(RuntimeReceiptManager.child_environment(receipt))
        try:
            medgemma_service.start_service(medgemma_spec, env=child_env)
        except medgemma_service.ManagerError as exc:
            raise LifecycleFailure("vlm_start_failed") from exc

    def stop_vlm(pid: int) -> None:
        try:
            medgemma_service.stop_owned(medgemma_spec, pid)
        except medgemma_service.ManagerError as exc:
            raise LifecycleFailure("process_identity_unverified") from exc

    vlm = OwnedMedGemmaEngine(
        OwnedProcessSpec(
            medgemma_spec.pid_path,
            os.geteuid(),
            medgemma_spec.executable,
            medgemma_spec.argv,
            str(medgemma_spec.project_root),
        ),
        start=start_vlm,
        stop=stop_vlm,
        receipt=receipt_manager.read,
        unmanaged_present=lambda: local_llm_service.port_is_open(medgemma_spec.port),
    )
    ingress_journal = IngressJournal(ingress_dir / "ingress.sqlite3")
    ingress_journal.initialize()
    lifecycle = SequentialLifecycleAdapter(
        chat=chat, vlm=vlm, ingress=ManagedIngress(ingress_journal)
    )
    operation_path = Path(
        str(env.get("AI_CONTROL_OPERATION_DB", "")).strip()
        or str(service.store.directory / "operations.sqlite3")
    )
    if not operation_path.is_absolute():
        raise RuntimeError("AI_CONTROL_OPERATION_DB must be absolute")
    journal = OperationJournal(operation_path)
    reconciled = journal.reconcile_after_restart()
    if reconciled:
        ingress_journal.close(manual_intervention=True)
        raise RuntimeError("unfinished operation requires manual reconciliation")
    # This snapshot is the final arming gate: exact ownership, no co-residency,
    # no activity ambiguity, and a receipt that matches durable applied state.
    snapshot = lifecycle.snapshot()
    _validate_arming_state(service, snapshot, current_receipt)
    return OperationCoordinator(
        journal=journal,
        lifecycle=lifecycle,
        lifecycle_lock_path=lifecycle_lock,
        load_plan=service.load_plan,
        load_draft=service.load_draft,
        load_applied=service._applied,
        save_applied=service.save_applied,
    )
