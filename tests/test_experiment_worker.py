import io
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from experiments.baseline import process_baseline_one
from experiments.store import ExperimentStore
from experiments.worker import process_one, validate_worker_mode
from utils.ai_config import AIError


def png():
    output = io.BytesIO()
    Image.new('RGB', (16, 16), 'white').save(output, format='PNG')
    return output.getvalue()


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExperimentStore(self.temp.name)
        self.sample = self.store.register_sample(png(), {
            'patient_group_id': 'fixture-group',
            'capture_id': 'fixture-capture',
            'source_asset_ref': 'fixture-asset',
            'modality': 'external_eye_webcam',
            'selected_eye': 'L',
            'engineering_fixture': True,
            'synthetic': True,
        })
        self.env = {
            'VLM_ENABLED': '1',
            'AI_EXPERIMENTS_ENABLED': '1',
            'AI_EXPERIMENT_MODE': 'shadow',
            'AI_DEPLOYMENT_PROFILE': 'vlm_only',
            'VLM_BACKEND': 'medgemma_custom_v1',
            'VLM_BASE_URL': 'http://127.0.0.1:8081',
            'VLM_MODEL': 'google/medgemma-test',
            'VLM_API_KEY': 'fixture-token',
            'VLM_MAX_INFLIGHT': '1',
            'AI_ALLOWED_ENDPOINTS': 'http://127.0.0.1:8081',
        }

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def runtime_expectation():
        return {
            'node_id': 'jetson-b', 'artifact_id': 'fixture-vlm',
            'artifact_manifest_digest': 'a' * 64, 'runtime_revision': 'fixture-runtime',
            'config_revision': 2, 'deployment_generation': 3,
            'effective_config_digest': 'b' * 64,
        }

    def test_disabled_flags_do_not_claim_job(self):
        run = self.store.create_run('E1_vlm_image', {}, {})
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        with self.assertRaisesRegex(AIError, 'disabled'):
            process_one(self.store, dict(self.env, VLM_ENABLED='0'))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'queued')

    def test_chat_only_profile_does_not_claim_job(self):
        run = self.store.create_run('E1_vlm_image', {}, {})
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        with self.assertRaisesRegex(AIError, 'profile_unavailable'):
            process_one(self.store, dict(self.env, AI_DEPLOYMENT_PROFILE='chat_only'))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'queued')

    @mock.patch('experiments.worker.analyze_eye')
    def test_e1_worker_persists_structured_abstain(self, analyze_eye):
        analyze_eye.return_value = {
            'analysis': {
                'schema_version': '1.0',
                'analysis_status': 'abstain',
                'image_quality': {'assessable': False, 'reasons': ['fixture']},
                'visual_observations': [],
                'suggested_label': None,
                'limitations': ['fixture'],
                'brief_explanation': 'fixture',
            },
            'provenance': {'input_digest': self.sample['roi_digest']},
        }
        run = self.store.create_run('E1_vlm_image', {}, {})
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        self.assertTrue(process_one(self.store, self.env))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'succeeded')
        analyze_eye.assert_called_once()

    @mock.patch('experiments.worker.analyze_eye')
    def test_e1_worker_forwards_frozen_runtime_expectation(self, analyze_eye):
        expectation = self.runtime_expectation()
        analyze_eye.return_value = {
            'analysis': {
                'schema_version': '1.0', 'analysis_status': 'abstain',
                'image_quality': {'assessable': False, 'reasons': ['fixture']},
                'visual_observations': [], 'suggested_label': None,
                'limitations': ['fixture'], 'brief_explanation': 'fixture',
            },
            'provenance': {'input_digest': self.sample['roi_digest'], 'runtime_receipt': expectation},
        }
        run = self.store.create_run('E1_vlm_image', {'runtime_expectation': expectation}, {})
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        self.assertTrue(process_one(self.store, self.env))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'succeeded')
        self.assertEqual(analyze_eye.call_args.kwargs['runtime_expectation'], expectation)

    def test_vlm_worker_does_not_claim_another_arm(self):
        from experiments.survey import SURVEY_SCHEMA_VERSION

        self.store.set_survey(self.sample['sample_id'], {
            'schema_version': SURVEY_SCHEMA_VERSION,
            'symptoms': [],
            'duration_bucket': 'unknown',
            'contact_lens_use': 'unknown',
            'trauma_or_chemical_exposure': 'unknown',
            'prior_eye_surgery': 'unknown',
        }, 'fixture:survey')
        run = self.store.create_run(
            'E2_vlm_survey', {'survey_schema_version': SURVEY_SCHEMA_VERSION}, {}
        )
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        self.assertFalse(process_one(self.store, self.env))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'queued')

    def test_e0_and_e1_workers_claim_only_their_arms(self):
        baseline = self.store.create_run('E0_baseline', {}, {}, engineering_fixture=True)
        vlm = self.store.create_run('E1_vlm_image', {}, {}, engineering_fixture=True)
        baseline_job, _ = self.store.enqueue(self.sample['sample_id'], baseline['run_id'])
        vlm_job, _ = self.store.enqueue(self.sample['sample_id'], vlm['run_id'])
        classifier = mock.Mock()
        classifier.classify_with_details.return_value = {
            'class': 3,
            'confidence': 0.8,
            'probabilities': [0.05, 0.05, 0.05, 0.8, 0.05],
            'heatmap_image': np.zeros((16, 16, 3), dtype=np.uint8),
        }
        baseline_env = {
            'AI_EXPERIMENTS_ENABLED': '1',
            'BASELINE_EXPERIMENTS_ENABLED': '1',
            'AI_EXPERIMENT_MODE': 'shadow',
            'GRADCAM_MODE': 'always',
        }
        self.assertTrue(process_baseline_one(self.store, baseline_env, classifier=classifier))
        self.assertEqual(self.store.get_job(baseline_job['job_id'])['state'], 'succeeded')
        self.assertEqual(self.store.get_job(vlm_job['job_id'])['state'], 'queued')
        summary = next(
            item for item in self.store.list_job_summaries()
            if item['job_id'] == baseline_job['job_id']
        )
        self.assertEqual(summary['analysis']['suggested_label'], '3')
        artifact = summary['provenance']['gradcam_artifact_ref']
        self.assertTrue((self.store.data_dir / artifact).is_file())


if __name__ == '__main__':
    unittest.main()
