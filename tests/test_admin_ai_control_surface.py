import unittest
from pathlib import Path


class AdminAIControlSurfaceTest(unittest.TestCase):
    def test_admin_routes_preserve_auth_csrf_and_disable_apply(self):
        server = Path("eye_server.py").read_text(encoding="utf-8")
        self.assertIn("def api_admin_ai_control_overview", server)
        self.assertIn("if not is_admin_session()", server[server.index("def api_admin_ai_control_overview"):server.index("def api_admin_ai_control_drafts")])
        for name in ("api_admin_ai_control_generation_update", "api_admin_ai_control_drafts", "api_admin_ai_control_plans", "api_admin_ai_control_operations_disabled"):
            start = server.index("def " + name)
            self.assertIn("require_admin_csrf()", server[start:start + 700])
        plan_start = server.index("def api_admin_ai_control_plans")
        plan_body = server[plan_start:server.index("def api_admin_ai_control_operations_disabled", plan_start)]
        self.assertIn("active_job_summary()", plan_body)
        self.assertIn("active_experiment", plan_body)
        page = Path("web/templates/admin_config.html").read_text(encoding="utf-8")
        self.assertIn("실제 적용 비활성", page)
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
