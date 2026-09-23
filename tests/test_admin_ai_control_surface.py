import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from utils.ai_config import AIError


class AdminAIControlSurfaceTest(unittest.TestCase):
    @staticmethod
    def operation_route(**overrides):
        source = Path("eye_server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "api_admin_ai_control_operations")
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
            "client_from_env": lambda env: client,
            "validate_operation_gate": lambda overview, body: body,
            "_ai_control_submission_store": lambda: store,
            "_ai_control_error": lambda exc, status=503: ({"error_code": exc.code}, status),
        }
        namespace.update(overrides)
        exec(compile(ast.Module(body=[function], type_ignores=[]), "eye_server.py", "exec"), namespace)
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
            os=SimpleNamespace(getenv=lambda key, default: "1", environ={}),
            _experiment_store=lambda: SimpleNamespace(active_job_summary=lambda: {"total": 1}),
        )
        self.assertEqual(route("jetson-b")[0]["error_code"], "active_experiment")
        self.assertEqual(calls, [])

        route, calls = self.operation_route()
        response, status = route("jetson-b")
        self.assertEqual(status, 202)
        self.assertEqual(response["operation"]["operation_id"], "a" * 32)
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
        self.assertIn("active_job_summary()", operation_body)
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

    def test_management_routes_skip_vision_model_initialization(self):
        server = Path("eye_server.py").read_text(encoding="utf-8")
        start = server.index("def initialize_on_first_request")
        body = server[start:start + 700]
        self.assertIn("request.path.startswith('/api/admin/ai-control/')", body)
        self.assertIn("'/admin/config'", body)


if __name__ == "__main__":
    unittest.main()
