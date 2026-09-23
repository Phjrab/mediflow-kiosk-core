import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from utils.ai_config import AIError


class AdminAIControlSurfaceTest(unittest.TestCase):
    @staticmethod
    def operation_route(**overrides):
        source = Path("eye_server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name in {"_resume_research_after_rejected_submission",
                                       "api_admin_ai_control_operations"}]
        for function in functions:
            function.decorator_list = []
        calls = []
        client = SimpleNamespace(
            overview=lambda force: {"fresh": force},
            request=lambda method, path, payload, idempotency_key: (
                calls.append((method, path, payload, idempotency_key))
                or {"operation_id": "a" * 32, "state": "accepted", "completed": False}
            ),
        )
        store = SimpleNamespace(submit=lambda body, send: send(body, "b" * 32))
        guard = SimpleNamespace(pause_for=lambda plan_id, root: None)
        namespace = {
            "require_admin_csrf": lambda: None,
            "get_ai_control_bootstrap_status": lambda: {
                "node_id": "jetson-b", "enabled": True,
                "drafts_enabled": True, "mutations_enabled": True,
            },
            "jsonify": lambda value: value,
            "AIError": AIError,
            "request": SimpleNamespace(get_json=lambda silent: {"plan_id": "c" * 32}),
            "os": SimpleNamespace(getenv=lambda key, default: "0", environ={}),
            "_experiment_store": lambda: SimpleNamespace(active_job_summary=lambda: {"total": 0}),
            "_research_switch_guard": lambda: guard,
            "_admin_research_root": lambda: Path("/private/research"),
            "client_from_env": lambda env: client,
            "validate_operation_gate": lambda overview, body: body,
            "_ai_control_submission_store": lambda: store,
            "_ai_control_error": lambda exc, status=503: ({"error_code": exc.code}, status),
        }
        namespace.update(overrides)
        exec(compile(ast.Module(body=functions, type_ignores=[]), "eye_server.py", "exec"), namespace)
        return namespace["api_admin_ai_control_operations"], calls

    def test_operation_route_fails_closed_before_proxy_and_sends_saved_key(self):
        route, calls = self.operation_route(require_admin_csrf=lambda: ({"error": "csrf"}, 403))
        self.assertEqual(route("jetson-b")[1], 403)
        self.assertEqual(calls, [])

        route, calls = self.operation_route(get_ai_control_bootstrap_status=lambda: {
            "node_id": "jetson-b", "enabled": True,
            "drafts_enabled": False, "mutations_enabled": False,
        })
        self.assertEqual(route("jetson-b")[0]["error_code"], "mutations_disabled")
        self.assertEqual(calls, [])

        route, calls = self.operation_route(
            _research_switch_guard=lambda: SimpleNamespace(
                pause_for=lambda plan_id, root: (_ for _ in ()).throw(AIError("active_experiment"))
            ),
        )
        self.assertEqual(route("jetson-b")[0]["error_code"], "active_experiment")
        self.assertEqual(calls, [])

        route, calls = self.operation_route(
            _research_switch_guard=lambda: SimpleNamespace(
                pause_for=lambda plan_id, root: (_ for _ in ()).throw(AIError("research_guard_unavailable"))
            ),
        )
        self.assertEqual(route("jetson-b")[0]["error_code"], "research_guard_unavailable")
        self.assertEqual(calls, [])

        paused = []
        route, calls = self.operation_route(_research_switch_guard=lambda: SimpleNamespace(
            pause_for=lambda plan_id, root: paused.append(plan_id)
        ))
        response, status = route("jetson-b")
        self.assertEqual(status, 202)
        self.assertEqual(response["operation"]["operation_id"], "a" * 32)
        self.assertEqual(paused, ["c" * 32])
        self.assertEqual(calls, [("POST", "/operations", {"plan_id": "c" * 32}, "b" * 32)])

    def test_admin_routes_preserve_auth_csrf_and_gate_apply(self):
        server = Path("eye_server.py").read_text(encoding="utf-8")
        self.assertIn("def api_admin_ai_control_overview", server)
        self.assertIn("if not is_admin_session()", server[server.index("def api_admin_ai_control_overview"):server.index("def api_admin_ai_control_drafts")])
        for name in ("api_admin_ai_control_generation_update", "api_admin_ai_control_drafts", "api_admin_ai_control_plans", "api_admin_ai_control_operations"):
            start = server.index("def " + name)
            self.assertIn("require_admin_csrf()", server[start:start + 700])
        plan_start = server.index("def api_admin_ai_control_plans")
        plan_body = server[plan_start:server.index("def api_admin_ai_control_operations", plan_start)]
        self.assertIn("active_job_summary()", plan_body)
        self.assertIn("active_experiment", plan_body)
        operation_start = server.index("def api_admin_ai_control_operations")
        operation_body = server[operation_start:server.index("def api_admin_ai_control_operation_latest", operation_start)]
        self.assertIn("mutations_enabled", operation_body)
        self.assertIn("pause_for", operation_body)
        self.assertIn("_ai_control_submission_store", operation_body)
        self.assertIn("validate_operation_gate", operation_body)
        self.assertIn("idempotency_key=key", operation_body)
        page = Path("web/templates/admin_config.html").read_text(encoding="utf-8")
        self.assertIn("ai-apply", page)
        self.assertIn('onclick="applyRuntimePlan()" disabled', page)
        self.assertIn('function updateRuntimeApplyButton()', page)
        self.assertIn('async function loadLatestRuntimeOperation()', page)
        self.assertIn('async function refreshRuntimeOperation()', page)
        self.assertIn("textContent", page)
        self.assertNotIn("AI_CONTROL_API_KEY", page)
        self.assertNotIn("192.168.50.11", page)

    def test_research_pause_releases_only_after_matching_safe_terminal_operation(self):
        tree = ast.parse(Path("eye_server.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "_resume_research_after_verified_operation")
        releases = []
        namespace = {
            "_research_switch_guard": lambda: SimpleNamespace(
                resume_for=lambda plan_id, root: releases.append(plan_id) or True
            ),
            "_admin_research_root": lambda: Path("/private/research"),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), "eye_server.py", "exec"), namespace)
        resume = namespace["_resume_research_after_verified_operation"]
        submission = {"plan_id": "a" * 32, "operation_id": "b" * 32}
        client = SimpleNamespace(overview=lambda force: {"fresh": force})
        with mock.patch("utils.research_switch_guard.safe_to_resume", return_value=True):
            self.assertFalse(resume(submission, {"operation_id": "b" * 32,
                                                 "state": "manual_intervention_required"}, client))
            self.assertFalse(resume(submission, {"operation_id": "c" * 32,
                                                 "state": "succeeded"}, client))
            self.assertEqual(releases, [])
            self.assertTrue(resume(submission, {"operation_id": "b" * 32,
                                                "state": "succeeded"}, client))
            self.assertEqual(releases, ["a" * 32])
        with mock.patch("utils.research_switch_guard.safe_to_resume", return_value=False):
            self.assertFalse(resume(submission, {"operation_id": "b" * 32,
                                                 "state": "rolled_back"}, client))
        self.assertEqual(releases, ["a" * 32])

    def test_definite_rejection_releases_pause_only_with_safe_idle_controller(self):
        plan_id = "c" * 32
        resumed = []
        guard = SimpleNamespace(
            pause_for=lambda plan, root: None,
            resume_for=lambda plan, root: resumed.append(plan) or True,
        )
        rejected = {"plan_id": plan_id, "operation_id": None,
                    "submission_rejected": True}
        store = SimpleNamespace(
            submit=lambda body, send: (_ for _ in ()).throw(AIError("stale_plan")),
            latest=lambda: rejected,
        )
        client = SimpleNamespace(overview=lambda force: {"fresh": force})
        route, calls = self.operation_route(
            _research_switch_guard=lambda: guard,
            _ai_control_submission_store=lambda: store,
            client_from_env=lambda env: client,
        )
        with mock.patch("utils.research_switch_guard.safe_to_resume", return_value=True):
            self.assertEqual(route("jetson-b")[0]["error_code"], "stale_plan")
        self.assertEqual(resumed, [plan_id])
        self.assertEqual(calls, [])

        resumed.clear()
        with mock.patch("utils.research_switch_guard.safe_to_resume", return_value=False):
            self.assertEqual(route("jetson-b")[0]["error_code"], "stale_plan")
        self.assertEqual(resumed, [])

        for uncertain in (
            {**rejected, "submission_rejected": False},
            {**rejected, "operation_id": "d" * 32},
            {**rejected, "plan_id": "e" * 32},
        ):
            store.latest = lambda value=uncertain: value
            with mock.patch("utils.research_switch_guard.safe_to_resume", return_value=True) as safe:
                self.assertEqual(route("jetson-b")[0]["error_code"], "stale_plan")
                safe.assert_not_called()
            self.assertEqual(resumed, [])

    def test_management_routes_skip_vision_model_initialization(self):
        server = Path("eye_server.py").read_text(encoding="utf-8")
        start = server.index("def initialize_on_first_request")
        body = server[start:start + 700]
        self.assertIn("request.path.startswith('/api/admin/ai-control/')", body)
        self.assertIn("'/admin/config'", body)


if __name__ == "__main__":
    unittest.main()
