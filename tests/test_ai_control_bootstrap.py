import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from services.ai_control.bootstrap import RuntimeReceiptManager, _validate_arming_state
from services.ai_control.app import create_app
from services.ai_control.core import Catalog, ControlService, PrivateJsonStore, digest


def registry_payload():
    return {
        "schema_version": "1.0",
        "models": [
            {
                "artifact_id": "chat-fixture", "display_name": "Chat", "engine_kind": "chat",
                "origin_model": "fixture/chat", "origin_revision": "a" * 40,
                "runtime_adapter": "fixture", "runtime_revision": "b" * 40,
                "quantization": "Q4", "installed": True, "integrity_verified": True,
                "provenance_verified": True, "engineering_verified": True,
                "medical_validated": False, "eligible_for_activation": True,
                "activation_blockers": [], "artifact_manifest_digest": "c" * 64,
                "file_integrity": [{"role": "weight", "size": 1, "sha256": "d" * 64, "verified": True}],
                "presets": [{"preset_id": "chat-safe", "context_tokens": 4096, "parallel": 1}],
                "placements": {"text": "cuda:0", "vision": None},
            },
            {
                "artifact_id": "vlm-fixture", "display_name": "VLM", "engine_kind": "vlm",
                "origin_model": "fixture/vlm", "origin_revision": "e" * 40,
                "runtime_adapter": "fixture", "runtime_revision": "f" * 40,
                "quantization": "Q4", "installed": True, "integrity_verified": True,
                "provenance_verified": True, "engineering_verified": True,
                "medical_validated": False, "eligible_for_activation": True,
                "activation_blockers": [], "artifact_manifest_digest": "1" * 64,
                "file_integrity": [{"role": "weight", "size": 1, "sha256": "2" * 64, "verified": True}],
                "presets": [{"preset_id": "vlm-safe", "context_tokens": 4096, "parallel": 1}],
                "placements": {"text": "cuda:0", "vision": "cpu"},
            },
        ],
    }


class RuntimeReceiptManagerTest(unittest.TestCase):
    def make_service(self, root: Path):
        registry = root / "registry.json"
        registry.write_text(json.dumps(registry_payload()), encoding="utf-8")
        registry.chmod(0o600)
        service = ControlService(
            node_id="jetson-b", store=PrivateJsonStore(root / "state"),
            catalog=Catalog(registry), drafts_enabled=True, mutations_enabled=True,
            managed_ingress_verified=True,
        )
        desired = {
            "active_profile": "chat_only",
            "engines": {
                "chat": {"artifact_id": "chat-fixture", "preset_id": "chat-safe", "runtime_overrides": {}},
                "vlm": {"artifact_id": "vlm-fixture", "preset_id": "vlm-safe", "runtime_overrides": {}},
            },
        }
        service.save_applied({
            "config_revision": 1, "deployment_generation": 1,
            "applied_profile": "chat_only", "effective_config": desired,
            "last_good_config": desired, "effective_config_digest": digest(desired),
        })
        return service, desired

    def test_next_receipt_is_atomic_private_and_matches_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, desired = self.make_service(root)
            target = {**desired, "active_profile": "vlm_only"}
            manager = RuntimeReceiptManager(root / "private" / "receipt.json", service)
            receipt = manager.write_for(target)
            self.assertEqual(receipt["artifact_id"], "vlm-fixture")
            self.assertEqual((receipt["config_revision"], receipt["deployment_generation"]), (2, 2))
            self.assertEqual(receipt["effective_config_digest"], digest(target))
            self.assertEqual(manager.read(), receipt)
            self.assertEqual(manager.path.stat().st_mode & 0o777, 0o600)

    def test_restore_uses_exact_previous_receipt_without_increment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service, _desired = self.make_service(root)
            manager = RuntimeReceiptManager(root / "private" / "receipt.json", service)
            previous = {
                "node_id": "jetson-b", "artifact_id": "chat-fixture",
                "artifact_manifest_digest": "c" * 64, "runtime_revision": "b" * 40,
                "config_revision": 1, "deployment_generation": 1,
                "effective_config_digest": "9" * 64,
            }
            written = manager.write_for({
                "active_profile": "chat_only", "restore": True,
                "_runtime_receipt": previous,
            })
            self.assertEqual(written, previous)

    def test_mutation_arming_requires_exact_applied_runtime_and_zero_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            service, desired = self.make_service(Path(directory))
            receipt = {
                "node_id": "jetson-b", "artifact_id": "chat-fixture",
                "artifact_manifest_digest": "c" * 64, "runtime_revision": "b" * 40,
                "config_revision": 1, "deployment_generation": 1,
                "effective_config_digest": digest(desired),
            }
            snapshot = {
                "profile": "chat_only", "admission": "open",
                "raw_bypass_closed": True, "inflight": 0, "unknown_inflight": 0,
                "deployment_generation": 1,
            }
            _validate_arming_state(service, snapshot, receipt)
            with self.assertRaisesRegex(RuntimeError, "arming state"):
                _validate_arming_state(service, {**snapshot, "unknown_inflight": 1}, receipt)
            with self.assertRaisesRegex(RuntimeError, "arming receipt"):
                _validate_arming_state(service, snapshot, {**receipt, "artifact_id": "vlm-fixture"})

    def test_app_binds_coordinator_only_when_mutation_bootstrap_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            registry = root / "registry.json"
            registry.write_text(json.dumps(registry_payload()), encoding="utf-8")
            registry.chmod(0o600)
            token = root / "admin.key"
            token.write_text("fixture-admin-token\n", encoding="utf-8")
            token.chmod(0o600)
            env = {
                "AI_CONTROL_STATE_DIR": str(root / "state"),
                "AI_CONTROL_REGISTRY_FILE": str(registry),
                "AI_CONTROL_API_KEY_FILE": str(token),
                "AI_CONTROL_DRAFTS_ENABLED": "1",
                "AI_CONTROL_MUTATIONS_ENABLED": "1",
                "AI_CONTROL_MANAGED_INGRESS_VERIFIED": "1",
            }
            coordinator = object()
            with mock.patch(
                "services.ai_control.bootstrap.build_operation_coordinator",
                return_value=coordinator,
            ) as build:
                app = create_app(env=env)
            service = build.call_args.args[0]
            self.assertIs(service.operation_coordinator, coordinator)
            response = app.test_client().get(
                "/control/v1/capabilities",
                headers={"Authorization": "Bearer fixture-admin-token"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["operations"], [
                "apply_config", "reconcile_manual_intervention",
            ])


if __name__ == "__main__":
    unittest.main()
