import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from utils.ai_control_client import AIControlClient, AIControlConfig, _endpoint
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


if __name__ == "__main__":
    unittest.main()
