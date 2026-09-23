import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.ai_control_client import AIControlClient, AIControlConfig, _endpoint
from utils.ai_control_submission import OperationSubmissionStore, validate_operation_gate
from utils.ai_config import AIError


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        type(self).requests.append((self.path, self.headers.get("Authorization")))
        payload = json.dumps({"node_id": "jetson-b", "observed_at": "fixture"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        type(self).requests.append((self.path, self.headers.get("Idempotency-Key")))
        payload = json.dumps({"operation_id": "a" * 32, "state": "accepted", "completed": False}).encode()
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format, *_args):
        return


class AIControlClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        Handler.requests = []
        self.config = AIControlConfig(
            "jetson-b", "http", "127.0.0.1", self.server.server_port, "/control/v1",
            "management-secret", cache_seconds=60,
        )

    def test_read_uses_management_token_and_cache_without_inference_state(self):
        client = AIControlClient(self.config)
        first = client.read("state")
        second = client.read("state")
        self.assertFalse(first["cache"]["cached"])
        self.assertTrue(second["cache"]["cached"])
        self.assertEqual(Handler.requests, [
            ("/control/v1/state", "Bearer management-secret")
        ])

    def test_endpoint_rejects_remote_plaintext_userinfo_and_query(self):
        port = self.server.server_port
        allowed = f"http://127.0.0.1:{port}"
        valid = {
            "AI_CONTROL_BASE_URL": allowed + "/control/v1",
            "AI_CONTROL_ALLOWED_ORIGINS": allowed,
        }
        self.assertEqual(_endpoint(valid)[1], "127.0.0.1")
        for url in (
            "http://192.168.50.11:8090/control/v1",
            f"http://user@127.0.0.1:{port}/control/v1",
            allowed + "/control/v1?token=secret",
        ):
            with self.subTest(url=url), self.assertRaisesRegex(AIError, "misconfigured"):
                _endpoint({**valid, "AI_CONTROL_BASE_URL": url})

    def test_operation_request_requires_and_sends_idempotency_key(self):
        client = AIControlClient(self.config)
        with self.assertRaisesRegex(AIError, "invalid_idempotency_key"):
            client.request("POST", "/operations", {})
        response = client.request("POST", "/operations", {}, idempotency_key="b" * 32)
        self.assertEqual(response["operation_id"], "a" * 32)
        self.assertEqual(Handler.requests, [("/control/v1/operations", "b" * 32)])

    def test_private_submission_reuses_key_after_uncertain_response(self):
        body = {
            "plan_id": "c" * 32, "plan_digest": "d" * 64,
            "expected_config_revision": 3, "expected_deployment_generation": 3,
            "acknowledgements": ["temporary_chat_unavailability"],
        }
        with tempfile.TemporaryDirectory() as directory:
            store = OperationSubmissionStore(directory)
            keys = []

            def uncertain(request, key):
                self.assertEqual(request, body)
                self.assertTrue((Path(directory) / (body["plan_id"] + ".json")).exists())
                keys.append(key)
                raise AIError("controller_unreachable")

            with self.assertRaisesRegex(AIError, "controller_unreachable"):
                store.submit(body, uncertain)
            self.assertTrue(store.latest()["submission_unknown"])
            with self.assertRaisesRegex(AIError, "submission_unknown"):
                store.submit({**body, "plan_id": "f" * 32}, uncertain)

            accepted = store.submit(body, lambda request, key: (
                keys.append(key) or {"operation_id": "e" * 32, "state": "accepted", "completed": False}
            ))
            self.assertEqual(keys[0], keys[1])
            self.assertEqual(accepted["operation_id"], "e" * 32)
            self.assertFalse(store.latest()["submission_unknown"])
            with self.assertRaisesRegex(AIError, "idempotency_conflict"):
                store.submit({**body, "expected_config_revision": 4}, uncertain)

    def test_definitive_controller_rejection_does_not_claim_unknown_acceptance(self):
        body = {
            "plan_id": "c" * 32, "plan_digest": "d" * 64,
            "expected_config_revision": 3, "expected_deployment_generation": 3,
            "acknowledgements": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            store = OperationSubmissionStore(directory)

            def rejected(_request, _key):
                raise AIError("plan_blocked")

            with self.assertRaisesRegex(AIError, "plan_blocked"):
                store.submit(body, rejected)
            self.assertTrue(store.latest()["submission_rejected"])
            with self.assertRaisesRegex(AIError, "operation_rejected"):
                store.submit(body, rejected)

    def test_submission_refuses_world_readable_or_symlink_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / "private"
            private.mkdir(mode=0o700)
            public = root / "public"
            public.mkdir(mode=0o755)
            link = root / "link"
            link.symlink_to(private)
            OperationSubmissionStore(private)
            with self.assertRaisesRegex(AIError, "misconfigured"):
                OperationSubmissionStore(public)
            with self.assertRaisesRegex(AIError, "misconfigured"):
                OperationSubmissionStore(link)

    def test_operation_gate_requires_fresh_owned_idle_matching_runtime(self):
        body = {
            "plan_id": "c" * 32, "plan_digest": "d" * 64,
            "expected_config_revision": 3, "expected_deployment_generation": 3,
            "acknowledgements": ["temporary_chat_unavailability"],
        }
        cache = {"stale": False, "connection_state": "connected"}
        overview = {
            "state": {
                "cache": cache, "node_id": "jetson-b", "active_operation_id": None,
                "config_revision": 3, "deployment_generation": 3,
                "observed_profile": "chat_only", "engine": {"artifact_id": "chat"},
                "activity": {"source": "managed_ingress", "admission": "open",
                             "inflight": 0, "unknown_inflight": 0},
            },
            "capabilities": {"cache": cache, "drafts_enabled": True,
                             "mutations_enabled": True, "managed_ingress_verified": True},
            "current_config": {
                "cache": cache, "config_revision": 3, "deployment_generation": 3,
                "applied_profile": "chat_only", "effective_config_digest": "f" * 64,
                "receipt": {"node_id": "jetson-b", "artifact_id": "chat",
                            "artifact_manifest_digest": "a" * 64,
                            "runtime_revision": "runtime", "config_revision": 3,
                            "deployment_generation": 3,
                            "effective_config_digest": "f" * 64},
            },
        }
        self.assertEqual(validate_operation_gate(overview, body), body)
        for section, path, value, error in (
            ("state", ("activity", "unknown_inflight"), 1, "activity_unknown"),
            ("state", ("activity", "admission"), "closed", "activity_unknown"),
            ("state", ("active_operation_id",), "e" * 32, "activity_unknown"),
            ("capabilities", ("mutations_enabled",), False, "activity_unknown"),
            ("state", ("cache", "stale"), True, "controller_unreachable"),
            ("current_config", ("receipt", "effective_config_digest"), "b" * 64, "state_changed"),
        ):
            changed = copy.deepcopy(overview)
            target = changed[section]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaisesRegex(AIError, error):
                validate_operation_gate(changed, body)
        with self.assertRaisesRegex(AIError, "state_changed"):
            validate_operation_gate(overview, {**body, "expected_deployment_generation": 2})


if __name__ == "__main__":
    unittest.main()
