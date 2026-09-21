import json
import tempfile
import unittest
from pathlib import Path

from services.ai_control.core import Catalog, ControlService, PrivateJsonStore, RuntimeObservation, TelemetrySampler
from services.ai_control.operations import LifecycleAdapter, OperationCoordinator, OperationJournal
from test_ai_control_service import catalog_payload


class InlineExecutor:
    def submit(self, function, *args):
        function(*args)


class DeferredExecutor:
    def __init__(self):
        self.calls = []

    def submit(self, function, *args):
        self.calls.append((function, args))


class FakeLifecycle(LifecycleAdapter):
    def __init__(self, *, fail_apply=False, fail_restore=False):
        self.fail_apply = fail_apply
        self.fail_restore = fail_restore
        self.events = []
        self.previous = {"profile": "stopped", "admission": "open"}

    def snapshot(self):
        self.events.append("snapshot")
        return dict(self.previous)

    def close_admission(self):
        self.events.append("close_admission")

    def drain(self, timeout_seconds):
        self.events.append(("drain", timeout_seconds))
        return True

    def apply(self, desired):
        self.events.append(("apply", desired["active_profile"]))
        if self.fail_apply:
            raise RuntimeError("fixture apply failure")

    def verify(self, desired):
        self.events.append(("verify", desired["active_profile"]))
        return {"artifact_id": desired["engines"]["vlm"]["artifact_id"], "observed_profile": desired["active_profile"]}

    def restore(self, previous):
        self.events.append(("restore", previous["profile"]))
        if self.fail_restore:
            raise RuntimeError("fixture restore failure")

    def restore_admission(self, previous):
        self.events.append(("restore_admission", previous["admission"]))


class OperationTest(unittest.TestCase):
    def make_service(self, root: Path, lifecycle: FakeLifecycle):
        registry = root / "registry.json"
        registry.write_text(json.dumps(catalog_payload()), encoding="utf-8")
        registry.chmod(0o600)
        service = ControlService(
            node_id="jetson-b",
            store=PrivateJsonStore(root / "state"),
            catalog=Catalog(registry),
            observe_runtime=lambda: RuntimeObservation(
                "ready", True, True, True, activity_source="managed_ingress",
                inflight=0, unknown_inflight=0, admission="open", observed_profile="chat_only",
            ),
            telemetry=TelemetrySampler(lambda: {"status": "unavailable"}),
            drafts_enabled=True,
            mutations_enabled=True,
        )
        journal = OperationJournal(root / "state" / "operations.sqlite3")
        coordinator = OperationCoordinator(
            journal=journal,
            lifecycle=lifecycle,
            lifecycle_lock_path=root / "state" / "device-lifecycle.lock",
            load_plan=service.load_plan,
            load_draft=service.load_draft,
            load_applied=service._applied,
            save_applied=service.save_applied,
            executor=InlineExecutor(),
        )
        service.operation_coordinator = coordinator
        return service, journal

    @staticmethod
    def desired():
        return {
            "active_profile": "vlm_only",
            "engines": {
                "chat": {"artifact_id": "fixture-chat", "preset_id": "fixture-chat-safe", "runtime_overrides": {}},
                "vlm": {"artifact_id": "fixture-vlm", "preset_id": "fixture-vlm-safe", "runtime_overrides": {}},
            },
        }

    def prepare(self, service):
        draft = service.save_draft({"schema_version": "1.0", "expected_config_revision": 0, "desired": self.desired()})
        plan = service.create_plan({
            "action": "apply_config", "draft_id": draft["draft_id"],
            "expected_config_revision": 0, "expected_deployment_generation": 0,
            "drain_policy": "wait_then_abort", "drain_timeout_seconds": 120,
        })
        self.assertEqual(plan["blocking_reasons"], [])
        request = {
            "plan_id": plan["plan_id"], "plan_digest": plan["plan_digest"],
            "expected_config_revision": 0, "expected_deployment_generation": 0,
            "acknowledgements": plan["required_acknowledgements"],
        }
        return plan, request

    def test_success_is_durable_idempotent_and_verifies_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            lifecycle = FakeLifecycle()
            service, journal = self.make_service(Path(directory), lifecycle)
            _plan, request = self.prepare(service)
            accepted = service.accept_operation(request, idempotency_key="fixture-key")
            finished = journal.get(accepted["operation_id"])
            self.assertEqual(finished["state"], "succeeded")
            self.assertEqual(service.current_config()["deployment_generation"], 1)
            duplicate = service.accept_operation(request, idempotency_key="fixture-key")
            self.assertEqual(duplicate["operation_id"], accepted["operation_id"])
            self.assertEqual(lifecycle.events.count(("apply", "vlm_only")), 1)
            changed = dict(request, acknowledgements=[])
            with self.assertRaisesRegex(Exception, "idempotency_conflict"):
                service.accept_operation(changed, idempotency_key="fixture-key")

    def test_start_failure_restores_previous_stopped_state_once(self):
        with tempfile.TemporaryDirectory() as directory:
            lifecycle = FakeLifecycle(fail_apply=True)
            service, journal = self.make_service(Path(directory), lifecycle)
            _plan, request = self.prepare(service)
            accepted = service.accept_operation(request, idempotency_key="fixture-fail")
            finished = journal.get(accepted["operation_id"])
            self.assertEqual((finished["state"], finished["error_code"]), ("rolled_back", "operation_failed"))
            self.assertEqual(lifecycle.events.count(("restore", "stopped")), 1)
            self.assertEqual(service.current_config()["config_revision"], 0)

    def test_rollback_failure_requires_manual_intervention_without_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            lifecycle = FakeLifecycle(fail_apply=True, fail_restore=True)
            service, journal = self.make_service(Path(directory), lifecycle)
            _plan, request = self.prepare(service)
            accepted = service.accept_operation(request, idempotency_key="fixture-rollback-fail")
            finished = journal.get(accepted["operation_id"])
            self.assertEqual((finished["state"], finished["error_code"]), ("manual_intervention_required", "rollback_failed"))
            self.assertEqual(lifecycle.events.count(("restore", "stopped")), 1)

    def test_restart_reconciliation_never_replays_nonterminal_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            journal = OperationJournal(root / "operations.sqlite3")
            operation, _ = journal.accept(
                principal="management", idempotency_key="fixture-restart",
                request_body={"plan_id": "a" * 32},
            )
            self.assertEqual(journal.reconcile_after_restart(), 1)
            reconciled = journal.get(operation["operation_id"])
            self.assertEqual(reconciled["state"], "manual_intervention_required")
            self.assertEqual(reconciled["error_code"], "controller_restarted_reconcile_required")

    def test_active_operation_blocks_second_and_cancel_wins_before_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lifecycle = FakeLifecycle()
            service, journal = self.make_service(root, lifecycle)
            deferred = DeferredExecutor()
            service.operation_coordinator.executor = deferred
            _plan, request = self.prepare(service)
            first = service.accept_operation(request, idempotency_key="fixture-first")
            with self.assertRaisesRegex(Exception, "operation_in_progress"):
                service.accept_operation(request, idempotency_key="fixture-second")
            cancelled = service.cancel_operation(first["operation_id"])
            self.assertEqual(cancelled["state"], "cancelled")
            function, args = deferred.calls.pop()
            function(*args)
            self.assertEqual(journal.get(first["operation_id"])["state"], "cancelled")
            self.assertNotIn(("apply", "vlm_only"), lifecycle.events)


if __name__ == "__main__":
    unittest.main()
