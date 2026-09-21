"""GPU-free control-plane state, catalog, draft, and plan logic."""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
import uuid
from typing import Any, Callable, Mapping


API_VERSION = "1.0"
ALLOWED_PROFILES = frozenset({"stopped", "chat_only", "vlm_only"})
ALLOWED_ACTIONS = frozenset({
    "apply_config", "start", "stop", "restart", "switch_profile",
    "restore_last_good", "run_smoke",
})


class ControlError(RuntimeError):
    def __init__(self, code: str, status: int = 400):
        self.code = code
        self.status = status
        super().__init__(code)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _private_regular_file(path: Path, *, maximum: int) -> None:
    info = path.lstat()
    if (not path.is_absolute() or stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > maximum):
        raise ControlError("unsafe_private_file", 503)


def load_management_token(path: str | os.PathLike[str]) -> str:
    target = Path(path)
    try:
        _private_regular_file(target, maximum=4096)
        lines = target.read_text(encoding="utf-8").splitlines()
        if len(lines) != 1 or not lines[0].strip() or len(lines[0].strip()) > 4096:
            raise ValueError()
        return lines[0].strip()
    except (OSError, UnicodeError, ValueError, ControlError):
        raise ControlError("management_auth_misconfigured", 503) from None


class PrivateJsonStore:
    """Small atomic JSON records. Credentials never belong in this store."""
    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory)
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ControlError("unsafe_state_directory", 503)

    def read(self, name: str, default: Any) -> Any:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,127}\.json", name):
            raise ControlError("invalid_persistent_key", 400)
        path = self.directory / name
        if not path.exists():
            return default
        try:
            _private_regular_file(path, maximum=1024 * 1024)
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            raise ControlError("invalid_persistent_state", 503) from None

    def write(self, name: str, value: Any) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{0,127}\.json", name):
            raise ControlError("invalid_persistent_key", 400)
        self.initialize()
        path = self.directory / name
        temporary = self.directory / ("." + name + "." + uuid.uuid4().hex)
        payload = canonical_json(value) + "\n"
        with self._lock:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "w", encoding="ascii") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
                os.chmod(path, 0o600)
            finally:
                temporary.unlink(missing_ok=True)


class TelemetrySampler:
    """One process-local cached sampler; it starts no tegrastats process."""
    def __init__(self, sample: Callable[[], dict[str, Any]] | None = None, *, ttl: float = 5.0,
                 monotonic: Callable[[], float] = time.monotonic):
        self._sample = sample or self._sample_linux
        self._ttl = ttl
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._sampled_at = float("-inf")

    @staticmethod
    def _sample_linux() -> dict[str, Any]:
        result: dict[str, Any] = {
            "memory_used_mib": None, "memory_total_mib": None,
            "swap_used_mib": None, "swap_total_mib": None,
            "cpu_activity_percent": None, "gpu_activity_percent": None,
            "temperature_celsius": None, "disk_free_mib": None,
            "status": "partial",
        }
        try:
            entries = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, raw = line.split(":", 1)
                entries[key] = int(raw.strip().split()[0])
            result["memory_total_mib"] = round(entries["MemTotal"] / 1024, 1)
            result["memory_used_mib"] = round((entries["MemTotal"] - entries["MemAvailable"]) / 1024, 1)
            result["swap_total_mib"] = round(entries.get("SwapTotal", 0) / 1024, 1)
            result["swap_used_mib"] = round(
                (entries.get("SwapTotal", 0) - entries.get("SwapFree", 0)) / 1024, 1
            )
        except (OSError, ValueError, KeyError):
            pass
        try:
            result["disk_free_mib"] = round(shutil.disk_usage("/").free / 1024 / 1024, 1)
        except OSError:
            pass
        temperatures = []
        for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                value = float(path.read_text(encoding="ascii").strip())
                temperatures.append(value / 1000 if value > 1000 else value)
            except (OSError, ValueError):
                continue
        if temperatures:
            result["temperature_celsius"] = round(max(temperatures), 1)
        if any(value is not None for key, value in result.items() if key != "status"):
            result["status"] = "available" if all(
                result[key] is not None for key in ("memory_used_mib", "memory_total_mib", "disk_free_mib")
            ) else "partial"
        else:
            result["status"] = "unavailable"
        return result

    def get(self) -> dict[str, Any]:
        now = self._monotonic()
        with self._lock:
            if self._cached is None or now - self._sampled_at >= self._ttl:
                try:
                    self._cached = self._sample()
                except Exception:
                    self._cached = {"status": "unavailable"}
                self._sampled_at = now
            return dict(self._cached)


@dataclass(frozen=True)
class RuntimeObservation:
    lifecycle_state: str
    process_running: bool | None
    model_loaded: bool | None
    inference_ready: bool | None
    activity_source: str = "unmanaged_ingress"
    inflight: int | None = None
    unknown_inflight: int | None = None
    admission: str = "unknown"
    artifact_id: str | None = None
    requested_context_tokens: int | None = None
    observed_context_tokens: int | None = None
    text_placement: str | None = None
    vision_placement: str | None = None
    observed_profile: str | None = None


def unavailable_runtime() -> RuntimeObservation:
    return RuntimeObservation("unknown", None, None, None)


class Catalog:
    def __init__(self, path: str | os.PathLike[str] | None):
        self.path = Path(path) if path else None

    def load(self) -> dict[str, Any]:
        if self.path is None or not self.path.exists():
            return {"schema_version": "1.0", "catalog_digest": digest([]), "models": []}
        try:
            _private_regular_file(self.path, maximum=1024 * 1024)
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, ControlError):
            raise ControlError("invalid_catalog", 503) from None
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "models"} or raw["schema_version"] != "1.0":
            raise ControlError("invalid_catalog", 503)
        models = raw["models"]
        if not isinstance(models, list) or len(models) > 32:
            raise ControlError("invalid_catalog", 503)
        clean = []
        ids = set()
        required = {
            "artifact_id", "display_name", "engine_kind", "origin_model", "origin_revision",
            "runtime_adapter", "runtime_revision", "quantization", "installed",
            "integrity_verified", "provenance_verified", "engineering_verified",
            "medical_validated", "eligible_for_activation", "activation_blockers",
            "artifact_manifest_digest", "file_integrity", "presets", "placements",
        }
        for item in models:
            if not isinstance(item, dict) or set(item) != required:
                raise ControlError("invalid_catalog", 503)
            artifact_id = item.get("artifact_id")
            if (not isinstance(artifact_id, str) or not artifact_id or len(artifact_id) > 120
                    or artifact_id in ids or item.get("engine_kind") not in {"chat", "vlm"}):
                raise ControlError("invalid_catalog", 503)
            if not isinstance(item.get("presets"), list) or len(item["presets"]) > 16:
                raise ControlError("invalid_catalog", 503)
            manifest_digest = item.get("artifact_manifest_digest")
            if not isinstance(manifest_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
                raise ControlError("invalid_catalog", 503)
            files = item.get("file_integrity")
            if not isinstance(files, list) or not 1 <= len(files) <= 8:
                raise ControlError("invalid_catalog", 503)
            for file_item in files:
                if (not isinstance(file_item, dict)
                        or set(file_item) != {"role", "size", "sha256", "verified"}
                        or not isinstance(file_item["role"], str)
                        or isinstance(file_item["size"], bool) or not isinstance(file_item["size"], int)
                        or file_item["size"] <= 0
                        or not isinstance(file_item["sha256"], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", file_item["sha256"])
                        or not isinstance(file_item["verified"], bool)):
                    raise ControlError("invalid_catalog", 503)
            ids.add(artifact_id)
            clean.append(item)
        return {"schema_version": "1.0", "catalog_digest": digest(clean), "models": clean}


class ControlService:
    def __init__(self, *, node_id: str, store: PrivateJsonStore, catalog: Catalog,
                 observe_runtime: Callable[[], RuntimeObservation] = unavailable_runtime,
                 telemetry: TelemetrySampler | None = None,
                 drafts_enabled: bool = False, mutations_enabled: bool = False,
                 controller_instance_id: str | None = None, operation_coordinator=None,
                 managed_ingress_verified: bool = False):
        if not node_id or len(node_id) > 120:
            raise ValueError("invalid node_id")
        self.node_id = node_id
        self.store = store
        self.catalog = catalog
        self.observe_runtime = observe_runtime
        self.telemetry = telemetry or TelemetrySampler()
        self.drafts_enabled = drafts_enabled
        self.mutations_enabled = mutations_enabled
        self.controller_instance_id = controller_instance_id or uuid.uuid4().hex
        self.operation_coordinator = operation_coordinator
        self.managed_ingress_verified = managed_ingress_verified

    def _applied(self) -> dict[str, Any]:
        return self.store.read("applied.json", {
            "config_revision": 0,
            "deployment_generation": 0,
            "applied_profile": "unknown",
            "effective_config": None,
            "last_good_config": None,
        })

    def capabilities(self) -> dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "node_id": self.node_id,
            "drafts_enabled": self.drafts_enabled,
            "mutations_enabled": self.mutations_enabled,
            "profiles": ["stopped", "chat_only", "vlm_only"],
            "max_gpu_heavy_services": 1,
            "co_resident_verified": False,
            "runtime_override_fields": ["context_tokens"],
            "plan_actions": ["apply_config"],
            "operations": ["apply_config"] if self.mutations_enabled and self.operation_coordinator else [],
            "managed_ingress_verified": self.managed_ingress_verified,
            "activity_authoritative": self.managed_ingress_verified,
            "medical_quality_evaluated": False,
        }

    def models(self) -> dict[str, Any]:
        value = self.catalog.load()
        return {"api_version": API_VERSION, "node_id": self.node_id, **value}

    def current_config(self) -> dict[str, Any]:
        return {"api_version": API_VERSION, "node_id": self.node_id, **self._applied()}

    def state(self) -> dict[str, Any]:
        applied = self._applied()
        observation = self.observe_runtime()
        engine = {
            "artifact_id": observation.artifact_id,
            "process_running": observation.process_running,
            "model_loaded": observation.model_loaded,
            "inference_ready": observation.inference_ready,
            "last_smoke_status": "not_run",
            "requested_context_tokens": observation.requested_context_tokens,
            "observed_context_tokens": observation.observed_context_tokens,
            "placements": {"text": observation.text_placement, "vision": observation.vision_placement},
        }
        return {
            "api_version": API_VERSION,
            "node_id": self.node_id,
            "controller_instance_id": self.controller_instance_id,
            "state_version": int(applied.get("deployment_generation", 0)),
            "observed_at": utc_now(),
            "config_revision": int(applied.get("config_revision", 0)),
            "deployment_generation": int(applied.get("deployment_generation", 0)),
            "applied_profile": applied.get("applied_profile", "unknown"),
            "observed_profile": observation.observed_profile,
            "lifecycle_state": observation.lifecycle_state,
            "active_operation_id": self.operation_coordinator.journal.active_id() if self.operation_coordinator else None,
            "activity": {
                "source": observation.activity_source,
                "inflight": observation.inflight,
                "unknown_inflight": observation.unknown_inflight,
                "admission": observation.admission,
            },
            "engine": engine,
            "telemetry": self.telemetry.get(),
        }

    @staticmethod
    def _validate_desired(value: Any, catalog: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != {"active_profile", "engines"}:
            raise ControlError("invalid_config")
        profile = value["active_profile"]
        if profile not in ALLOWED_PROFILES:
            raise ControlError("invalid_config")
        engines = value["engines"]
        if not isinstance(engines, dict) or set(engines) != {"chat", "vlm"}:
            raise ControlError("invalid_config")
        by_id = {item["artifact_id"]: item for item in catalog["models"]}
        normalized = {"active_profile": profile, "engines": {}}
        for kind in ("chat", "vlm"):
            item = engines[kind]
            if not isinstance(item, dict) or set(item) != {"artifact_id", "preset_id", "runtime_overrides"}:
                raise ControlError("invalid_config")
            artifact = by_id.get(item["artifact_id"])
            if artifact is None or artifact["engine_kind"] != kind:
                raise ControlError("artifact_unavailable")
            preset_ids = {preset["preset_id"] for preset in artifact["presets"]}
            if item["preset_id"] not in preset_ids:
                raise ControlError("unsupported_setting")
            overrides = item["runtime_overrides"]
            if not isinstance(overrides, dict) or set(overrides) - {"context_tokens"}:
                raise ControlError("unsupported_setting")
            if "context_tokens" in overrides:
                token_value = overrides["context_tokens"]
                if isinstance(token_value, bool) or not isinstance(token_value, int) or not 256 <= token_value <= 32768:
                    raise ControlError("invalid_config")
            normalized["engines"][kind] = {
                "artifact_id": item["artifact_id"],
                "preset_id": item["preset_id"],
                "runtime_overrides": dict(overrides),
            }
        active_kind = "chat" if profile == "chat_only" else "vlm" if profile == "vlm_only" else None
        if active_kind and not by_id[normalized["engines"][active_kind]["artifact_id"]]["eligible_for_activation"]:
            raise ControlError("artifact_unavailable")
        return normalized

    def save_draft(self, body: Any) -> dict[str, Any]:
        if not self.drafts_enabled:
            raise ControlError("drafts_disabled", 403)
        if not isinstance(body, dict) or set(body) != {"schema_version", "expected_config_revision", "desired"}:
            raise ControlError("invalid_config")
        applied = self._applied()
        revision = body["expected_config_revision"]
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ControlError("invalid_config")
        if revision != applied["config_revision"]:
            raise ControlError("stale_config_revision", 409)
        catalog = self.models()
        desired = self._validate_desired(body["desired"], catalog)
        draft = {
            "draft_id": uuid.uuid4().hex,
            "created_at": utc_now(),
            "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "expected_config_revision": revision,
            "catalog_digest": catalog["catalog_digest"],
            "desired": desired,
        }
        self.store.write("draft-" + draft["draft_id"] + ".json", draft)
        return draft

    def create_plan(self, body: Any) -> dict[str, Any]:
        if not self.drafts_enabled:
            raise ControlError("drafts_disabled", 403)
        required = {"action", "draft_id", "expected_config_revision", "expected_deployment_generation", "drain_policy", "drain_timeout_seconds"}
        if not isinstance(body, dict) or set(body) != required or body.get("action") != "apply_config":
            raise ControlError("invalid_plan")
        if not isinstance(body["draft_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", body["draft_id"]):
            raise ControlError("invalid_plan")
        for field in ("expected_config_revision", "expected_deployment_generation"):
            if isinstance(body[field], bool) or not isinstance(body[field], int) or body[field] < 0:
                raise ControlError("invalid_plan")
        if body["drain_policy"] != "wait_then_abort" or isinstance(body["drain_timeout_seconds"], bool) \
                or not isinstance(body["drain_timeout_seconds"], int) or not 1 <= body["drain_timeout_seconds"] <= 600:
            raise ControlError("invalid_plan")
        applied = self._applied()
        if body["expected_config_revision"] != applied["config_revision"] or body["expected_deployment_generation"] != applied["deployment_generation"]:
            raise ControlError("state_changed", 412)
        draft = self.store.read("draft-" + str(body["draft_id"]) + ".json", None)
        if draft is None:
            raise ControlError("draft_not_found", 404)
        if draft["expected_config_revision"] != applied["config_revision"]:
            raise ControlError("stale_plan", 409)
        state = self.state()
        blocking = []
        if not self.managed_ingress_verified:
            blocking.append("raw_ingress_bypass")
        if state["activity"]["source"] != "managed_ingress" or state["activity"]["unknown_inflight"] is None:
            blocking.append("activity_unknown")
        if not self.mutations_enabled:
            blocking.append("mutations_disabled")
        elif self.operation_coordinator is None:
            blocking.append("operation_executor_unavailable")
        before = applied.get("effective_config")
        after = draft["desired"]
        plan = {
            "plan_id": uuid.uuid4().hex,
            "created_at": utc_now(),
            "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "action": body["action"],
            "draft_id": draft["draft_id"],
            "expected_config_revision": applied["config_revision"],
            "expected_deployment_generation": applied["deployment_generation"],
            "catalog_digest": draft["catalog_digest"],
            "changes": [] if before == after else [{"field": "runtime_config", "before": before, "after": after}],
            "restart_required": before != after,
            "services_affected": [after["active_profile"]] if after["active_profile"] != "stopped" else [],
            "expected_chat_unavailability": before != after,
            "observed_inflight": state["activity"]["inflight"],
            "blocking_reasons": blocking,
            "required_acknowledgements": ["temporary_chat_unavailability"] if before != after else [],
            "estimated_resource_requirement": {"status": "unverified", "basis": "catalog_only"},
            "drain_timeout_seconds": body["drain_timeout_seconds"],
        }
        plan["plan_digest"] = digest(plan)
        self.store.write("plan-" + plan["plan_id"] + ".json", plan)
        return plan

    def events(self, limit: int) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ControlError("invalid_limit")
        events = self.store.read("events.json", [])
        if not isinstance(events, list):
            raise ControlError("invalid_persistent_state", 503)
        return {"api_version": API_VERSION, "node_id": self.node_id, "events": events[-limit:]}

    def reject_operation(self) -> None:
        raise ControlError("mutations_disabled", 403)

    @staticmethod
    def _record_id(value: Any, kind: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ControlError(kind + "_not_found", 404)
        return value

    def load_plan(self, plan_id: str) -> dict[str, Any]:
        plan_id = self._record_id(plan_id, "plan")
        value = self.store.read("plan-" + plan_id + ".json", None)
        if value is None:
            raise ControlError("plan_not_found", 404)
        return value

    def load_draft(self, draft_id: str) -> dict[str, Any]:
        draft_id = self._record_id(draft_id, "draft")
        value = self.store.read("draft-" + draft_id + ".json", None)
        if value is None:
            raise ControlError("draft_not_found", 404)
        return value

    def save_applied(self, value: dict[str, Any]) -> None:
        self.store.write("applied.json", value)

    def accept_operation(self, body: Any, *, idempotency_key: str) -> dict[str, Any]:
        if not self.mutations_enabled or self.operation_coordinator is None:
            self.reject_operation()
        return self.operation_coordinator.accept(body, idempotency_key=idempotency_key)

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        if self.operation_coordinator is None:
            raise ControlError("operation_not_found", 404)
        return self.operation_coordinator.get(operation_id)

    def cancel_operation(self, operation_id: str) -> dict[str, Any]:
        if not self.mutations_enabled or self.operation_coordinator is None:
            self.reject_operation()
        return self.operation_coordinator.cancel(operation_id)
