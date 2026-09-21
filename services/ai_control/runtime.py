"""Read-only adapters for existing Jetson B lifecycle evidence."""
from __future__ import annotations

import os
from pathlib import Path
import socket
from typing import Mapping

from scripts import local_llm_service
from services.ai_control.core import RuntimeObservation


def _tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def observe_runtime(env: Mapping[str, str] | None = None) -> RuntimeObservation:
    """Observe without deleting PID records, starting engines, or generating."""
    env = os.environ if env is None else env
    profile = str(env.get("AI_DEPLOYMENT_PROFILE", "unknown")).strip()
    if profile == "vlm_only":
        ready = _tcp_open(8081)
        return RuntimeObservation(
            lifecycle_state="ready" if ready else "stopped",
            process_running=ready,
            model_loaded=False if ready else False,
            inference_ready=ready,
            activity_source="unmanaged_ingress",
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
    spec = local_llm_service.ServiceSpec(
        project_root=project_root,
        launcher=project_root / "scripts" / "run_local_llm_candidate.sh",
        server=server,
        control_dir=pid_path.parent,
        pid_path=pid_path,
        log_path=pid_path.parent / "local-llm.log",
        lock_path=pid_path.parent / "local-llm.lock",
        health_url="http://127.0.0.1:8080/health",
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
            activity_source="unmanaged_ingress",
            artifact_id=str(env.get("AI_CONTROL_CHAT_ARTIFACT_ID", "")).strip() or None,
            requested_context_tokens=_optional_int(env.get("AI_CONTROL_CHAT_CONTEXT_TOKENS")),
            observed_context_tokens=None,
            text_placement="cuda:0",
            observed_profile="chat_only",
        )
    if state == "stopped":
        return RuntimeObservation("stopped", False, False, False, observed_profile="stopped")
    return RuntimeObservation(state, None, None, False)


def _optional_int(value):
    try:
        result = int(str(value).strip())
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None
