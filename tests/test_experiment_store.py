import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image

from experiments.store import ExperimentStore
from utils.ai_config import AIError


def fixture_image(color='white'):
    output = io.BytesIO()
    Image.new('RGB', (24, 16), color=color).save(output, format='PNG')
    return output.getvalue()


def fixture_metadata(**overrides):
    value = {
        'patient_group_id': 'fixture-group-1',
        'capture_id': 'fixture-capture-1',
        'source_asset_ref': 'fixture-asset-1',
        'modality': 'external_eye_webcam',
        'selected_eye': 'L',
        'laterality_basis': 'engineering_fixture',
        'source_size': [24, 16],
        'roi_bbox': [0, 0, 24, 16],
        'engineering_fixture': True,
        'synthetic': True,
        'split': 'engineering_fixture',
    }
    value.update(overrides)
    return value


def abstain_result(digest):
    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': 'abstain',
            'image_quality': {'assessable': False, 'reasons': ['fixture']},
            'visual_observations': [],
            'suggested_label': None,
            'limitations': ['engineering fixture'],
            'brief_explanation': 'insufficient fixture detail',
        },
        'provenance': {'input_digest': digest},
    }


class ExperimentStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExperimentStore(self.temp.name, queue_max=1)
        self.sample = self.store.register_sample(fixture_image(), fixture_metadata())
        self.run = self.store.create_run(
            'E1_vlm_image',
            {'temperature': 0, 'VLM_API_KEY': 'must-not-persist'},
            {
                'origin_model': 'google/medgemma-fixture',
                'revision': 'fixture',
                'token': 'must-not-persist',
            },
            engineering_fixture=True,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_sample_is_private_and_has_stable_digest(self):
        path = self.store.sample_image_path(self.sample['sample_id'])
        self.assertEqual(oct(path.stat().st_mode & 0o777), '0o600')
        self.assertEqual(len(self.sample['source_digest']), 64)
        self.assertEqual(len(self.sample['roi_digest']), 64)
        self.assertNotIn('label', self.sample)

    def test_real_data_requires_both_flag_and_permission_reference(self):
        metadata = fixture_metadata(engineering_fixture=False, synthetic=False)
        with self.assertRaisesRegex(AIError, 'real_data_not_allowed'):
            self.store.register_sample(fixture_image(), metadata)
        allowed_dir = tempfile.TemporaryDirectory()
        try:
            allowed = ExperimentStore(allowed_dir.name, allow_real_data=True)
            with self.assertRaisesRegex(AIError, 'real_data_not_allowed'):
                allowed.register_sample(fixture_image(), metadata)
            metadata['permission_ref'] = 'approved-study-1'
            with self.assertRaisesRegex(AIError, 'real_data_not_allowed'):
                allowed.register_sample(fixture_image(), metadata)
            metadata['retention_policy_ref'] = 'retention-policy-1'
            metadata['split'] = 'holdout'
            with self.assertRaisesRegex(AIError, 'real_data_not_allowed'):
                allowed.register_sample(fixture_image(), metadata)
            metadata['retention_until'] = '2030-12-31'
            sample = allowed.register_sample(fixture_image(), metadata)
            self.assertEqual(sample['permission_ref'], 'approved-study-1')
            self.assertEqual(sample['retention_policy_ref'], 'retention-policy-1')
            self.assertEqual(sample['retention_until'], '2030-12-31')
        finally:
            allowed_dir.cleanup()

    def test_label_leak_is_rejected_before_file_write(self):
        before = set(self.store.samples_dir.iterdir())
        with self.assertRaisesRegex(AIError, 'forbidden_context'):
            self.store.register_sample(
                fixture_image('red'),
                fixture_metadata(nested={'ground_truth': '3'}),
            )
        self.assertEqual(set(self.store.samples_dir.iterdir()), before)

    def test_run_snapshots_remove_secrets(self):
        self.assertNotIn('must-not-persist', self.run['config_json'])
        self.assertNotIn('must-not-persist', self.run['model_manifest_json'])

    def test_enqueue_is_idempotent_and_queue_is_bounded(self):
        first, created = self.store.enqueue(self.sample['sample_id'], self.run['run_id'])
        duplicate, duplicate_created = self.store.enqueue(self.sample['sample_id'], self.run['run_id'])
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first['job_id'], duplicate['job_id'])

        another_sample = self.store.register_sample(
            fixture_image('blue'), fixture_metadata(capture_id='fixture-capture-2')
        )
        with self.assertRaisesRegex(AIError, 'queue_full'):
            self.store.enqueue(another_sample['sample_id'], self.run['run_id'])

    def test_claim_and_finish_preserve_job_and_analysis_status(self):
        queued, _ = self.store.enqueue(self.sample['sample_id'], self.run['run_id'])
        claimed = self.store.claim_next()
        self.assertEqual(claimed['job_id'], queued['job_id'])
        self.assertEqual(claimed['state'], 'running')
        finished = self.store.finish(
            claimed['job_id'],
            claimed['lease_token'],
            abstain_result(self.sample['roi_digest']),
            duration_ms=12.5,
        )
        self.assertEqual(finished['state'], 'succeeded')
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            prediction = connection.execute(
                'SELECT analysis_status, suggested_label FROM predictions WHERE job_id=?',
                (claimed['job_id'],),
            ).fetchone()
        self.assertEqual(prediction, ('abstain', None))

    def test_running_cancel_does_not_claim_remote_resource_is_free(self):
        queued, _ = self.store.enqueue(self.sample['sample_id'], self.run['run_id'])
        claimed = self.store.claim_next()
        cancelling = self.store.request_cancel(queued['job_id'])
        self.assertEqual(cancelling['state'], 'cancel_requested')
        finished = self.store.finish(
            claimed['job_id'], claimed['lease_token'], abstain_result(self.sample['roi_digest'])
        )
        self.assertEqual(finished['state'], 'cancelled')
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            count = connection.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
        self.assertEqual(count, 0)

    def test_restart_recovery_marks_stale_running_failed(self):
        self.store.enqueue(self.sample['sample_id'], self.run['run_id'])
        self.store.claim_next()
        self.assertEqual(self.store.recover_interrupted(), 1)
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            state, error = connection.execute(
                'SELECT state, error_code FROM jobs'
            ).fetchone()
        self.assertEqual((state, error), ('failed', 'interrupted'))


class ExperimentAdminSurfaceTest(unittest.TestCase):
    def test_state_changing_routes_require_existing_csrf_guard(self):
        source = Path('eye_server.py').read_text(encoding='utf-8')
        create_start = source.index('def api_admin_experiment_jobs_create')
        create_body = source[create_start:source.index("@app.route('/api/admin/ai-experiments/jobs/<job_id>'", create_start)]
        cancel_start = source.index('def api_admin_experiment_job_cancel')
        cancel_body = source[cancel_start:source.index("@app.route('/api/admin/logout'", cancel_start)]
        self.assertIn('require_admin_csrf()', create_body)
        self.assertIn('require_admin_csrf()', cancel_body)
        import_start = source.index('def api_admin_experiment_sample_from_history')
        import_body = source[import_start:source.index("@app.route('/api/admin/ai-experiments/jobs'", import_start)]
        self.assertIn('require_admin_csrf()', import_body)
        self.assertIn("operational_import_ready", import_body)

    def test_model_output_is_rendered_as_text_only(self):
        source = Path('web/templates/admin_ai_experiments.html').read_text(encoding='utf-8')
        self.assertIn('td.textContent', source)
        self.assertNotIn('innerHTML', source)
        self.assertNotIn('document.write', source)

    def test_run_comparison_is_admin_only_and_not_called_accuracy(self):
        server = Path('eye_server.py').read_text(encoding='utf-8')
        start = server.index('def api_admin_experiment_compare')
        end = server.index("@app.route('/api/admin/ai-experiments/jobs/<job_id>/cancel'", start)
        route = server[start:end]
        self.assertIn('is_admin_session()', route)
        self.assertIn('compare_runs', route)
        page = Path('web/templates/admin_ai_experiments.html').read_text(encoding='utf-8')
        self.assertIn('일치율은 정확도가 아닙니다', page)
        self.assertIn('.textContent = JSON.stringify(payload.comparison', page)


if __name__ == '__main__':
    unittest.main()
