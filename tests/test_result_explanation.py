import io
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from PIL import Image

from experiments.evaluate import evaluate_run
from experiments.explanation import process_explanation_one, prompt_digest
from experiments.store import ExperimentStore
from utils.ai_config import AIError


def png():
    output = io.BytesIO()
    Image.new('RGB', (16, 16), 'white').save(output, format='PNG')
    return output.getvalue()


def baseline_result(digest):
    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': 'assessed',
            'image_quality': {'assessable': True, 'reasons': []},
            'visual_observations': [],
            'suggested_label': '3',
            'limitations': ['fixture baseline'],
            'brief_explanation': 'fixture result',
        },
        'provenance': {
            'backend': 'existing_efficientnet_baseline',
            'input_digest': digest,
            'confidence_fraction': 0.8,
            'probabilities': [0.05, 0.05, 0.05, 0.8, 0.05],
            'gradcam_artifact_ref': 'must-not-enter-E3',
        },
    }


class ResultExplanationTest(unittest.TestCase):
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
        self.source_run = self.store.create_run(
            'E0_baseline', {}, {'origin_model': 'fixture'}, engineering_fixture=True
        )
        self.store.enqueue(self.sample['sample_id'], self.source_run['run_id'])
        source_job = self.store.claim_next(('E0_baseline',))
        self.store.finish(
            source_job['job_id'], source_job['lease_token'],
            baseline_result(self.sample['roi_digest']),
        )
        self.env = {
            'AI_EXPERIMENTS_ENABLED': '1',
            'EXPLANATION_EXPERIMENTS_ENABLED': '1',
            'AI_EXPERIMENT_MODE': 'shadow',
            'AI_DEPLOYMENT_PROFILE': 'chat_only',
            'LLM_PROVIDER': 'local',
            'LOCAL_LLM_BASE_URL': 'http://127.0.0.1:8080/v1',
            'LOCAL_LLM_MODEL': 'fixture-local-model',
            'LOCAL_LLM_API_KEY': 'fixture-token',
            'AI_ALLOWED_ENDPOINTS': 'http://127.0.0.1:8080',
        }

    def tearDown(self):
        self.temp.cleanup()

    def runtime_expectation(self):
        return {
            'node_id': 'jetson-b', 'artifact_id': 'fixture-chat',
            'artifact_manifest_digest': 'a' * 64,
            'runtime_revision': 'fixture-runtime', 'config_revision': 2,
            'deployment_generation': 3, 'effective_config_digest': 'b' * 64,
        }

    def create_e3(self, *, runtime_expectation=None):
        config = {'source_run_id': self.source_run['run_id'], 'question_id': 'explain-result-ko-v1'}
        if runtime_expectation is not None:
            config['runtime_expectation'] = runtime_expectation
        return self.store.create_run(
            'E3_result_explanation',
            config,
            {'origin_model': 'fixture-local-model'},
            engineering_fixture=True,
        )

    def test_e3_uses_completed_e0_json_without_reading_image_or_label(self):
        run = self.create_e3()
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        generate = mock.Mock(return_value='기존 분류 결과의 연구용 설명입니다.')
        with mock.patch.object(self.store, 'sample_image_path', side_effect=AssertionError('image read')):
            self.assertTrue(process_explanation_one(self.store, self.env, generate=generate))

        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'succeeded')
        config, system_prompt, user_message = generate.call_args.args
        self.assertEqual(config.model, 'fixture-local-model')
        self.assertIn('not given an image', system_prompt)
        self.assertIn('"suggested_label":"3"', user_message)
        self.assertNotIn('gradcam_artifact_ref', user_message)
        self.assertNotIn('reference_label', user_message)

        summary = next(item for item in self.store.list_job_summaries() if item['job_id'] == job['job_id'])
        self.assertIsNone(summary['analysis'])
        self.assertEqual(summary['explanation']['provider'], 'local')
        self.assertEqual(summary['explanation']['text'], '기존 분류 결과의 연구용 설명입니다.')
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM explanations').fetchone()[0], 1)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM predictions').fetchone()[0], 1)

    def test_e3_evaluation_never_reports_classification_metrics(self):
        self.store.add_reference_label(self.sample['sample_id'], '3', 'fixture-label')
        run = self.create_e3()
        self.store.enqueue(self.sample['sample_id'], run['run_id'])
        process_explanation_one(self.store, self.env, generate=lambda *_: '설명')
        report = evaluate_run(self.store, run['run_id'])
        self.assertEqual(report['evaluation_status'], 'EXPLANATION_REVIEW_REQUIRED')
        self.assertEqual(report['N_explanations'], 1)
        self.assertIsNone(report['clinical_metrics'])
        self.assertFalse(report['explanation_is_classification_metric'])

    def test_e3_rejects_nonbaseline_source_and_cloud_provider_before_claim(self):
        e1 = self.store.create_run('E1_vlm_image', {}, {}, engineering_fixture=True)
        with self.assertRaisesRegex(ValueError, 'E3 source must be E0_baseline'):
            self.store.create_run(
                'E3_result_explanation',
                {'source_run_id': e1['run_id'], 'question_id': 'explain-result-ko-v1'},
                {}, engineering_fixture=True,
            )
        run = self.create_e3()
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        with self.assertRaisesRegex(AIError, 'unsupported_provider'):
            process_explanation_one(self.store, dict(self.env, LLM_PROVIDER='openai'))
        self.assertEqual(self.store.get_job(job['job_id'])['state'], 'queued')

    def test_e3_enqueue_requires_source_result_for_same_sample(self):
        other = self.store.register_sample(png(), {
            'patient_group_id': 'fixture-group-2',
            'capture_id': 'fixture-capture-2',
            'source_asset_ref': 'fixture-asset-2',
            'modality': 'external_eye_webcam',
            'selected_eye': 'R',
            'engineering_fixture': True,
            'synthetic': True,
        })
        run = self.create_e3()
        with self.assertRaisesRegex(AIError, 'source_result_unavailable'):
            self.store.enqueue(other['sample_id'], run['run_id'])

    def test_existing_schema_is_forward_migrated_for_explanations(self):
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.execute('DROP TABLE explanations')
            connection.execute(
                "UPDATE schema_metadata SET value='1' WHERE key='schema_version'"
            )
        migrated = ExperimentStore(self.temp.name)
        with closing(sqlite3.connect(migrated.db_path)) as connection, connection:
            version = connection.execute(
                "SELECT value FROM schema_metadata WHERE key='schema_version'"
            ).fetchone()[0]
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='explanations'"
            ).fetchone()
        self.assertEqual(version, '4')
        self.assertEqual(table[0], 'explanations')

    def test_e3_requires_and_persists_matching_runtime_receipt_when_pinned(self):
        expected = self.runtime_expectation()
        run = self.create_e3(runtime_expectation=expected)
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        receipt = {**expected, 'prompt_digest': prompt_digest()}
        self.assertTrue(process_explanation_one(
            self.store, self.env,
            generate=lambda *_: ('고정 런타임 설명', receipt),
        ))
        summary = next(item for item in self.store.list_job_summaries() if item['job_id'] == job['job_id'])
        self.assertEqual(summary['explanation']['runtime_receipt'], receipt)

        second = self.create_e3(runtime_expectation=expected)
        second_job, _ = self.store.enqueue(self.sample['sample_id'], second['run_id'])
        self.assertTrue(process_explanation_one(
            self.store, self.env, generate=lambda *_: 'receipt 없는 설명',
        ))
        self.assertEqual(self.store.get_job(second_job['job_id'])['state'], 'failed')
        self.assertEqual(self.store.get_job(second_job['job_id'])['error_code'], 'runtime_receipt_mismatch')

        third = self.create_e3(runtime_expectation=expected)
        third_job, _ = self.store.enqueue(self.sample['sample_id'], third['run_id'])
        mismatched = {**receipt, 'deployment_generation': 4}
        self.assertTrue(process_explanation_one(
            self.store, self.env, generate=lambda *_: ('잘못된 receipt', mismatched),
        ))
        self.assertEqual(self.store.get_job(third_job['job_id'])['state'], 'failed')
        self.assertEqual(self.store.get_job(third_job['job_id'])['error_code'], 'runtime_receipt_mismatch')


if __name__ == '__main__':
    unittest.main()
