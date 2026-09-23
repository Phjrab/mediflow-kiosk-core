import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import medgemma_service
from services.ai_control.ingress import IngressJournal
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

    def test_managed_ingress_activity_and_raw_port_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            journal = IngressJournal(root / "ingress.sqlite3")
            journal.initialize()
            journal.open(deployment_generation=3, raw_bypass_closed=True)
            server = root / "llama-server"
            server.write_text("fixture", encoding="utf-8")
            env = {
                "AI_DEPLOYMENT_PROFILE": "chat_only",
                "AI_CONTROL_PROJECT_ROOT": str(root),
                "AI_CONTROL_LLAMA_SERVER": str(server),
                "AI_CONTROL_LOCAL_LLM_PID_FILE": str(root / "pid.json"),
                "AI_CONTROL_CHAT_ARTIFACT_ID": "fixture-chat",
                "AI_CONTROL_MANAGED_INGRESS_VERIFIED": "1",
                "AI_CONTROL_INGRESS_STATE_DIR": str(root),
                "AI_CONTROL_CHAT_RAW_PORT": "18080",
            }
            with mock.patch(
                "services.ai_control.runtime.local_llm_service.inspect_service",
                return_value=("running", {}, object()),
            ) as inspect, mock.patch(
                "services.ai_control.runtime.local_llm_service.health_is_ready",
                return_value=True,
            ) as health:
                state = observe_runtime(env)
            self.assertEqual(state.activity_source, "managed_ingress")
            self.assertEqual((state.inflight, state.unknown_inflight, state.admission), (0, 0, "open"))
            self.assertEqual(inspect.call_args.args[0].port, 18080)
            health.assert_called_once_with("http://127.0.0.1:18080/health")

    def test_idle_cli_vlm_is_ready_without_claiming_model_loaded(self):
        env = {"AI_DEPLOYMENT_PROFILE": "vlm_only", "AI_CONTROL_VLM_ARTIFACT_ID": "fixture-vlm"}
        with mock.patch("services.ai_control.runtime._tcp_open", return_value=True):
            state = observe_runtime(env)
        self.assertTrue(state.inference_ready)
        self.assertFalse(state.model_loaded)
        self.assertEqual((state.text_placement, state.vision_placement), ("cuda:0", "cpu"))

    def test_owned_medgemma_process_overrides_static_chat_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec = mock.Mock(pid_path=root / "medgemma.pid.json")
            env = {
                "AI_DEPLOYMENT_PROFILE": "chat_only",
                "AI_CONTROL_MEDGEMMA_PID_FILE": str(spec.pid_path),
                "AI_CONTROL_VLM_ARTIFACT_ID": "fixture-vlm",
            }
            with mock.patch.object(medgemma_service, "build_spec", return_value=spec), \
                    mock.patch.object(medgemma_service, "inspect_service", return_value=("running", {}, object())), \
                    mock.patch.object(medgemma_service, "ready", return_value=True):
                state = observe_runtime(env)
            self.assertEqual(state.observed_profile, "vlm_only")
            self.assertTrue(state.inference_ready)
            self.assertEqual(state.artifact_id, "fixture-vlm")


if __name__ == "__main__":
    unittest.main()
