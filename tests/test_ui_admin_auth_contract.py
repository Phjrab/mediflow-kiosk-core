"""Execute original backend auth helpers without importing model/DB startup."""
import ast
import hmac
from pathlib import Path
import unittest
import uuid
from flask import Flask, jsonify, request, session


class AdminAuthContractTest(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path('eye_server.py').read_text())
        names = {'is_admin_session', 'create_admin_csrf_token', 'is_valid_admin_csrf_token', 'require_admin_csrf', 'api_admin_config_get'}
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        for function in functions:
            function.decorator_list = []
        namespace = dict(session=session, request=request, jsonify=jsonify, hmac=hmac, uuid=uuid,
                         get_admin_config_snapshot=lambda: {}, get_admin_llm_settings_snapshot=lambda: {},
                         get_ai_control_bootstrap_status=lambda: {}, ADMIN_EDITABLE_CONFIG_KEYS={}, ADMIN_LLM_EDITABLE_KEYS={})
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'eye_server.py', 'exec'), namespace)
        app = Flask(__name__)
        app.secret_key = 'synthetic-test-only'
        app.add_url_rule('/config', view_func=namespace['api_admin_config_get'])
        app.add_url_rule('/mutation', view_func=lambda: namespace['require_admin_csrf']() or jsonify(status='ok'), methods=['POST'])
        self.client = app.test_client()

    def test_unauthenticated_read_and_mutation_are_forbidden(self):
        self.assertEqual(self.client.get('/config').status_code, 403)
        self.assertEqual(self.client.post('/mutation', json={}).status_code, 403)

    def test_authenticated_csrf_missing_mismatch_and_valid(self):
        with self.client.session_transaction() as state:
            state['is_admin'] = True
        response = self.client.get('/config')
        self.assertEqual(response.status_code, 200)
        token = response.json['csrf_token']
        self.assertEqual(self.client.post('/mutation', json={}).status_code, 403)
        self.assertEqual(self.client.post('/mutation', json={}, headers={'X-Admin-CSRF':'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/mutation', json={}, headers={'X-Admin-CSRF':token}).status_code, 200)


if __name__ == '__main__':
    unittest.main()
