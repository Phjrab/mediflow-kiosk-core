import json
import tempfile
import unittest
from pathlib import Path

from services.ai_control.app import create_app
from services.ai_control.core import (
    Catalog, ControlService, PrivateJsonStore, RuntimeObservation, TelemetrySampler,
)


def catalog_payload():
    def item(artifact_id, kind):
        return {
            "artifact_id": artifact_id,
            "display_name": artifact_id,
            "engine_kind": kind,
            "origin_model": "fixture/origin",
            "origin_revision": "fixture-revision",
            "runtime_adapter": "fixture-adapter",
            "runtime_revision": "fixture-runtime",
            "quantization": "fixture-q4",
            "installed": True,
            "integrity_verified": True,
            "provenance_verified": True,
            "engineering_verified": True,
            "medical_validated": False,
            "eligible_for_activation": True,
            "activation_blockers": [],
            "artifact_manifest_digest": "a" * 64,
            "file_integrity": [{"role": "weight", "size": 1024, "sha256": "b" * 64, "verified": True}],
            "presets": [{"preset_id": artifact_id + "-safe", "context_tokens": 4096}],
            "placements": {"text": "cuda:0", "vision": "cpu" if kind == "vlm" else None},
        }
    return {"schema_version": "1.0", "models": [item("fixture-chat", "chat"), item("fixture-vlm", "vlm")]}


class AIControlServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.token = root / "control.key"
        self.token.write_text("management-secret\n", encoding="utf-8")
        self.token.chmod(0o600)
        self.registry = root / "registry.json"
        self.registry.write_text(json.dumps(catalog_payload()), encoding="utf-8")
        self.registry.chmod(0o600)
        calls = []
        self.telemetry_calls = calls

        def sample():
            calls.append("sampled")
            return {"memory_used_mib": None, "gpu_activity_percent": None, "status": "unavailable"}

        observation = RuntimeObservation(
            "ready", True, True, True, activity_source="unmanaged_ingress",
            artifact_id="fixture-chat", text_placement="cuda:0",
        )
        self.service = ControlService(
            node_id="jetson-b",
            store=PrivateJsonStore(root / "state"),
            catalog=Catalog(self.registry),
            observe_runtime=lambda: observation,
            telemetry=TelemetrySampler(sample, ttl=60),
            drafts_enabled=True,
            mutations_enabled=False,
            controller_instance_id="fixture-controller",
        )
        self.app = create_app(self.service, env={"AI_CONTROL_API_KEY_FILE": str(self.token)})
        self.client = self.app.test_client()
        self.headers = {"Authorization": "Bearer management-secret"}

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_require_management_auth_and_do_not_generate_or_mutate(self):
        self.assertEqual(self.client.get("/control/v1/state").status_code, 401)
        state_dir = Path(self.temp.name) / "state"
        before = list(state_dir.glob("*")) if state_dir.exists() else []
        first = self.client.get("/control/v1/state", headers=self.headers)
        second = self.client.get("/control/v1/state", headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json()["engine"]["artifact_id"], "fixture-chat")
        self.assertEqual(first.get_json()["activity"]["inflight"], None)
        self.assertEqual(self.telemetry_calls, ["sampled"])
        after = list(state_dir.glob("*")) if state_dir.exists() else []
        self.assertEqual(before, after)
        self.assertEqual(second.status_code, 200)

    def test_catalog_distinguishes_engineering_from_medical_validation(self):
        response = self.client.get("/control/v1/models", headers=self.headers)
        models = response.get_json()["models"]
        self.assertTrue(models[0]["engineering_verified"])
        self.assertFalse(models[0]["medical_validated"])

    def test_draft_and_plan_never_apply_and_report_write_blockers(self):
        desired = {
            "active_profile": "vlm_only",
            "engines": {
                "chat": {"artifact_id": "fixture-chat", "preset_id": "fixture-chat-safe", "runtime_overrides": {}},
                "vlm": {"artifact_id": "fixture-vlm", "preset_id": "fixture-vlm-safe", "runtime_overrides": {}},
            },
        }
        draft_response = self.client.post("/control/v1/drafts", headers=self.headers, json={
            "schema_version": "1.0", "expected_config_revision": 0, "desired": desired,
        })
        self.assertEqual(draft_response.status_code, 201)
        draft = draft_response.get_json()
        current = self.client.get("/control/v1/configs/current", headers=self.headers).get_json()
        self.assertEqual((current["config_revision"], current["applied_profile"]), (0, "unknown"))
        plan_response = self.client.post("/control/v1/plans", headers=self.headers, json={
            "action": "apply_config", "draft_id": draft["draft_id"],
            "expected_config_revision": 0, "expected_deployment_generation": 0,
            "drain_policy": "wait_then_abort", "drain_timeout_seconds": 120,
        })
        self.assertEqual(plan_response.status_code, 201)
        self.assertEqual(set(plan_response.get_json()["blocking_reasons"]), {"activity_unknown", "mutations_disabled"})
        operation = self.client.post("/control/v1/operations", headers=self.headers, json={})
        self.assertEqual(operation.status_code, 403)
        self.assertEqual(operation.get_json()["error_code"], "mutations_disabled")

    def test_unknown_fields_and_oversized_body_are_rejected(self):
        response = self.client.post("/control/v1/drafts", headers=self.headers, json={"extra": True})
        self.assertEqual(response.status_code, 400)
        oversized = b"x" * (128 * 1024 + 1)
        response = self.client.post("/control/v1/drafts", headers={**self.headers, "Content-Type": "application/json"}, data=oversized)
        self.assertEqual(response.status_code, 413)
        traversal = self.client.post("/control/v1/plans", headers=self.headers, json={
            "action": "apply_config", "draft_id": "../../applied",
            "expected_config_revision": 0, "expected_deployment_generation": 0,
            "drain_policy": "wait_then_abort", "drain_timeout_seconds": 120,
        })
        self.assertEqual(traversal.status_code, 400)


if __name__ == "__main__":
    unittest.main()
