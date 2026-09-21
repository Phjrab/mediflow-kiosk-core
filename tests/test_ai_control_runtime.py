import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.ai_control.runtime import observe_runtime


class RuntimeObservationTest(unittest.TestCase):
    def test_general_llm_reuses_manager_pure_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = root / "llama-server"
            server.write_text("fixture", encoding="utf-8")
            pid = root / "local-llm.pid.json"
            env = {
                "AI_DEPLOYMENT_PROFILE": "chat_only",
                "AI_CONTROL_PROJECT_ROOT": str(root),
                "AI_CONTROL_LLAMA_SERVER": str(server),
                "AI_CONTROL_LOCAL_LLM_PID_FILE": str(pid),
                "AI_CONTROL_CHAT_ARTIFACT_ID": "fixture-chat",
            }
            with mock.patch("services.ai_control.runtime.local_llm_service.inspect_service", return_value=("running", {}, object())) as inspect, mock.patch(
                "services.ai_control.runtime.local_llm_service.health_is_ready", return_value=True
            ):
                state = observe_runtime(env)
            self.assertTrue(state.inference_ready)
            self.assertEqual(state.observed_profile, "chat_only")
            self.assertEqual(state.activity_source, "unmanaged_ingress")
            self.assertIsNone(state.inflight)
            self.assertFalse(inspect.call_args.kwargs["remove_stale"])

    def test_idle_cli_vlm_is_ready_without_claiming_model_loaded(self):
        env = {"AI_DEPLOYMENT_PROFILE": "vlm_only", "AI_CONTROL_VLM_ARTIFACT_ID": "fixture-vlm"}
        with mock.patch("services.ai_control.runtime._tcp_open", return_value=True):
            state = observe_runtime(env)
        self.assertTrue(state.inference_ready)
        self.assertFalse(state.model_loaded)
        self.assertEqual((state.text_placement, state.vision_placement), ("cuda:0", "cpu"))


if __name__ == "__main__":
    unittest.main()
