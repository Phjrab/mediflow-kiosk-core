"""Read-only adapters for existing Jetson B lifecycle evidence."""
from __future__ import annotations

import os
from pathlib import Path
import socket
from typing import Mapping

from scripts import local_llm_service
from services.ai_control.core import RuntimeObservation
from services.ai_control.ingress import IngressJournal


def _tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def observe_runtime(env: Mapping[str, str] | None = None) -> RuntimeObservation:
    """Observe without deleting PID records, starting engines, or generating."""
    env = os.environ if env is None else env
    managed = str(env.get("AI_CONTROL_MANAGED_INGRESS_VERIFIED", "0")) == "1"
    activity = None
    if managed:
        ingress_dir = str(env.get("AI_CONTROL_INGRESS_STATE_DIR", "")).strip()
        if not ingress_dir or not Path(ingress_dir).is_absolute():
            return RuntimeObservation("unknown", None, None, None)
        try:
            activity = IngressJournal(Path(ingress_dir) / "ingress.sqlite3").snapshot()
        except Exception:
            return RuntimeObservation("unknown", None, None, None)
    profile = str(env.get("AI_DEPLOYMENT_PROFILE", "unknown")).strip()
    if profile == "vlm_only":
        vlm_port = _optional_port(env.get("AI_CONTROL_VLM_RAW_PORT"), 8081)
        ready = _tcp_open(vlm_port)
        return RuntimeObservation(
            lifecycle_state="ready" if ready else "stopped",
            process_running=ready,
            model_loaded=False if ready else False,
            inference_ready=ready,
            activity_source="managed_ingress" if managed else "unmanaged_ingress",
            inflight=activity["inflight"] if activity else None,
            unknown_inflight=activity["unknown_inflight"] if activity else None,
            admission=activity["admission"] if activity else None,
            artifact_id=str(env.get("AI_CONTROL_VLM_ARTIFACT_ID", "")).strip() or None,
            text_placement="cuda:0" if ready else None,
            vision_placement="cpu" if ready else None,
            observed_profile="vlm_only",
        )
    required = {
        "project_root": str(env.get("AI_CONTROL_PROJECT_ROOT", "")).strip(),
        "server": str(env.get("AI_CONTROL_LLAMA_SERVER", "")).strip(),
        "pid": str(env.get("AI_CONTROL_LOCAL_LLM_PID_FILE", "")).strip(),
    }
    if not all(required.values()):
        return RuntimeObservation("unknown", None, None, None)
    project_root = Path(required["project_root"]).resolve()
    server = Path(required["server"]).resolve()
    pid_path = Path(required["pid"])
    chat_port = _optional_port(env.get("AI_CONTROL_CHAT_RAW_PORT"), 8080)
    spec = local_llm_service.ServiceSpec(
        project_root=project_root,
        launcher=project_root / "scripts" / "run_local_llm_candidate.sh",
        server=server,
        control_dir=pid_path.parent,
        pid_path=pid_path,
        log_path=pid_path.parent / "local-llm.log",
        lock_path=pid_path.parent / "local-llm.lock",
        health_url=f"http://127.0.0.1:{chat_port}/health",
        port=chat_port,
    )
    try:
        state, _record, _snapshot = local_llm_service.inspect_service(spec, remove_stale=False)
    except local_llm_service.ManagerError:
        return RuntimeObservation("unknown", None, None, None)
    if state == "running":
        ready = local_llm_service.health_is_ready(spec.health_url)
        return RuntimeObservation(
            lifecycle_state="ready" if ready else "loading",
            process_running=True,
            model_loaded=ready,
            inference_ready=ready,
            activity_source="managed_ingress" if managed else "unmanaged_ingress",
            inflight=activity["inflight"] if activity else None,
            unknown_inflight=activity["unknown_inflight"] if activity else None,
            admission=activity["admission"] if activity else None,
            artifact_id=str(env.get("AI_CONTROL_CHAT_ARTIFACT_ID", "")).strip() or None,
            requested_context_tokens=_optional_int(env.get("AI_CONTROL_CHAT_CONTEXT_TOKENS")),
            observed_context_tokens=None,
            text_placement="cuda:0",
            observed_profile="chat_only",
        )
    if state == "stopped":
        return RuntimeObservation(
            "stopped", False, False, False,
            activity_source="managed_ingress" if managed else "unmanaged_ingress",
            inflight=activity["inflight"] if activity else None,
            unknown_inflight=activity["unknown_inflight"] if activity else None,
            admission=activity["admission"] if activity else None,
            observed_profile="stopped",
        )
    return RuntimeObservation(state, None, None, False)


def _optional_int(value):
    try:
        result = int(str(value).strip())
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _optional_port(value, default):
    try:
        result = int(str(value).strip())
        return result if 1 <= result <= 65535 else default
    except (TypeError, ValueError):
        return default
