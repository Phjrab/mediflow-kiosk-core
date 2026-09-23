import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from PIL import Image

from experiments.store import ExperimentStore
from utils.ai_config import AIError
from utils.research_switch_guard import ResearchSwitchGuard, safe_to_resume


def fixture_image():
    output = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(output, format="PNG")
    return output.getvalue()


class ResearchSwitchGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.research = self.root / "research"
        self.research.mkdir(mode=0o700)
        self.guard_dir = self.root / "guard"
        self.guard_dir.mkdir(mode=0o700)
        self.guard = ResearchSwitchGuard(self.guard_dir)
        self.patch = mock.patch("utils.research_switch_guard.default_guard_dir", return_value=self.guard_dir)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.store = ExperimentStore(self.research / "first")
        sample = self.store.register_sample(fixture_image(), {
            "patient_group_id": "fixture", "capture_id": "fixture-capture",
            "source_asset_ref": "fixture-asset", "modality": "external_eye_webcam",
            "selected_eye": "L", "engineering_fixture": True, "synthetic": True,
        })
        run = self.store.create_run("E1_vlm_image", {}, {}, engineering_fixture=True)
        self.sample_id = sample["sample_id"]
        self.run_id = run["run_id"]
        self.plan = "a" * 32

    def test_existing_queued_job_rejects_pause_without_losing_job(self):
        job, _ = self.store.enqueue(self.sample_id, self.run_id)
        with self.assertRaisesRegex(AIError, "active_experiment"):
            self.guard.pause_for(self.plan, self.research)
        self.assertIsNone(self.guard.paused_plan_id())
        self.assertEqual(self.store.get_job(job["job_id"])["state"], "queued")

    def test_existing_running_job_rejects_pause(self):
        job, _ = self.store.enqueue(self.sample_id, self.run_id)
        self.store.claim_next()
        with self.assertRaisesRegex(AIError, "active_experiment"):
            self.guard.pause_for(self.plan, self.research)
        self.assertEqual(self.store.get_job(job["job_id"])["state"], "running")

    def test_paused_claim_preserves_new_queue_and_blocks_resume(self):
        self.guard.pause_for(self.plan, self.research)
        job, _ = self.store.enqueue(self.sample_id, self.run_id)
        self.assertIsNone(self.store.claim_next())
        self.assertEqual(self.store.get_job(job["job_id"])["state"], "queued")
        with self.assertRaisesRegex(AIError, "active_experiment"):
            self.guard.resume_for(self.plan, self.research)
        self.assertEqual(self.guard.paused_plan_id(), self.plan)
        self.store.request_cancel(job["job_id"])
        self.assertTrue(self.guard.resume_for(self.plan, self.research))
        self.assertIsNone(self.guard.paused_plan_id())

    def test_registered_store_outside_research_root_is_checked(self):
        outside = ExperimentStore(self.root / "outside")
        self.assertIsNone(outside.claim_next())  # Registers under the same lock.
        sample = outside.register_sample(fixture_image(), {
            "patient_group_id": "other", "capture_id": "other-capture",
            "source_asset_ref": "other-asset", "modality": "external_eye_webcam",
            "selected_eye": "R", "engineering_fixture": True, "synthetic": True,
        })
        run = outside.create_run("E1_vlm_image", {}, {}, engineering_fixture=True)
        outside.enqueue(sample["sample_id"], run["run_id"])
        with self.assertRaisesRegex(AIError, "active_experiment"):
            self.guard.pause_for(self.plan, self.research)

    def test_symlink_pause_marker_fails_closed(self):
        target = self.root / "outside.json"
        target.write_text("{}")
        (self.guard_dir / "pause.json").symlink_to(target)
        with self.assertRaisesRegex(AIError, "research_guard_unavailable"):
            self.store.claim_next()

    def test_claim_and_pause_are_serialized_across_threads(self):
        job, _ = self.store.enqueue(self.sample_id, self.run_id)
        inside_claim = threading.Event()
        release_claim = threading.Event()

        def slow_claim():
            inside_claim.set()
            self.assertTrue(release_claim.wait(2))
            return self.store._claim_next_unlocked(None)

        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = pool.submit(self.guard.claim, self.store.db_path, slow_claim)
            self.assertTrue(inside_claim.wait(2))
            pause = pool.submit(self.guard.pause_for, self.plan, self.research)
            release_claim.set()
            self.assertEqual(claimed.result(timeout=2)["job_id"], job["job_id"])
            with self.assertRaisesRegex(AIError, "active_experiment"):
                pause.result(timeout=2)
        self.assertIsNone(self.guard.paused_plan_id())

    def test_pause_survives_guard_recreation(self):
        self.guard.pause_for(self.plan, self.research)
        self.assertEqual(ResearchSwitchGuard(self.guard_dir).paused_plan_id(), self.plan)
        self.assertIsNone(self.store.claim_next())

    def test_admin_path_must_match_worker_default(self):
        with self.assertRaisesRegex(AIError, "research_guard_unavailable"):
            ResearchSwitchGuard.for_admin({"AI_CONTROL_RESEARCH_GUARD_DIR": "/tmp/wrong"})
        self.assertIsInstance(ResearchSwitchGuard.for_admin({
            "AI_CONTROL_RESEARCH_GUARD_DIR": str(self.guard_dir)
        }), ResearchSwitchGuard)

    def test_resume_requires_fresh_idle_matching_receipt(self):
        receipt = {
            "node_id": "jetson-b", "artifact_id": "chat", "artifact_manifest_digest": "a" * 64,
            "runtime_revision": "r1", "config_revision": 3, "deployment_generation": 3,
            "effective_config_digest": "b" * 64,
        }
        cache = {"stale": False, "connection_state": "connected"}
        overview = {
            "state": {"cache": cache, "active_operation_id": None, "lifecycle_state": "ready",
                      "node_id": "jetson-b",
                      "observed_profile": "chat_only", "config_revision": 3,
                      "deployment_generation": 3, "engine": {"artifact_id": "chat", "inference_ready": True},
                      "activity": {"source": "managed_ingress", "admission": "open",
                                   "inflight": 0, "unknown_inflight": 0}},
            "current_config": {"cache": cache, "receipt": receipt, "applied_profile": "chat_only",
                               "config_revision": 3, "deployment_generation": 3,
                               "effective_config_digest": "b" * 64},
            "capabilities": {"cache": cache, "drafts_enabled": True,
                             "mutations_enabled": True, "managed_ingress_verified": True},
        }
        self.assertTrue(safe_to_resume(overview))
        self.assertFalse(safe_to_resume({**overview, "state": {
            **overview["state"], "activity": {**overview["state"]["activity"], "admission": "closed"}
        }}))


if __name__ == "__main__":
    unittest.main()
