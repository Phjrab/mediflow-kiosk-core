import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from PIL import Image

from experiments.evaluate import evaluate_run
from experiments.hybrid import process_hybrid_one
from experiments.store import ExperimentStore, PURGE_CONFIRMATION
from experiments.survey import SURVEY_SCHEMA_VERSION, validate_survey
from experiments.worker import process_one
from utils.ai_config import AIError


def png(color='white'):
    output = io.BytesIO()
    Image.new('RGB', (16, 16), color).save(output, format='PNG')
    return output.getvalue()


def survey(**overrides):
    value = {
        'schema_version': SURVEY_SCHEMA_VERSION,
        'symptoms': ['redness', 'itching'],
        'duration_bucket': '1_3d',
        'contact_lens_use': 'unknown',
        'trauma_or_chemical_exposure': 'no',
        'prior_eye_surgery': 'no',
    }
    value.update(overrides)
    return value


def result(digest, label='3', status='assessed'):
    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': status,
            'image_quality': {'assessable': status == 'assessed', 'reasons': [] if status == 'assessed' else ['fixture']},
            'visual_observations': [],
            'suggested_label': label if status == 'assessed' else None,
            'limitations': ['fixture'],
            'brief_explanation': 'fixture',
        },
        'provenance': {'input_digest': digest},
    }


class SurveyHybridTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ExperimentStore(self.temp.name, allow_real_data=True)
        self.sample = self.store.register_sample(png(), {
            'patient_group_id': 'fixture-group', 'capture_id': 'fixture-capture',
            'source_asset_ref': 'fixture-asset', 'modality': 'external_eye_webcam',
            'selected_eye': 'L', 'engineering_fixture': True, 'synthetic': True,
        })
        self.vlm_env = {
            'AI_EXPERIMENTS_ENABLED': '1', 'VLM_ENABLED': '1',
            'SURVEY_VLM_EXPERIMENTS_ENABLED': '1', 'AI_EXPERIMENT_MODE': 'shadow',
            'AI_DEPLOYMENT_PROFILE': 'vlm_only', 'VLM_BACKEND': 'medgemma_custom_v1',
            'VLM_BASE_URL': 'http://127.0.0.1:8081',
            'VLM_MODEL': 'google/medgemma-fixture', 'VLM_API_KEY': 'fixture-token',
            'AI_ALLOWED_ENDPOINTS': 'http://127.0.0.1:8081',
        }
        self.hybrid_env = {
            'AI_EXPERIMENTS_ENABLED': '1', 'HYBRID_REVIEW_EXPERIMENTS_ENABLED': '1',
            'AI_EXPERIMENT_MODE': 'shadow', 'AI_DEPLOYMENT_PROFILE': 'chat_only',
        }

    def tearDown(self):
        self.temp.cleanup()

    def complete(self, arm, label='3', config=None):
        run = self.store.create_run(arm, config or {}, {}, engineering_fixture=True)
        self.store.enqueue(self.sample['sample_id'], run['run_id'])
        job = self.store.claim_next((arm,))
        self.store.finish(job['job_id'], job['lease_token'], result(self.sample['roi_digest'], label))
        return run

    def test_survey_schema_is_closed_and_has_no_free_text_or_label(self):
        normalized = validate_survey(survey(symptoms=['itching', 'redness']))
        self.assertEqual(normalized['symptoms'], ['itching', 'redness'])
        for bad in (
            survey(notes='free text'), survey(label='3'), survey(symptoms=['diagnosis']),
            survey(contact_lens_use=True), survey(symptoms=['redness', 'redness']),
        ):
            with self.subTest(bad=bad), self.assertRaisesRegex(AIError, 'invalid_survey'):
                validate_survey(bad)

    def test_survey_is_immutable_and_required_before_e2_enqueue(self):
        run = self.store.create_run(
            'E2_vlm_survey', {'survey_schema_version': SURVEY_SCHEMA_VERSION}, {},
            engineering_fixture=True,
        )
        with self.assertRaisesRegex(AIError, 'survey_unavailable'):
            self.store.enqueue(self.sample['sample_id'], run['run_id'])
        stored = self.store.set_survey(self.sample['sample_id'], survey(), 'fixture:survey')
        again = self.store.set_survey(self.sample['sample_id'], survey(), 'fixture:survey')
        self.assertEqual(stored['response_digest'], again['response_digest'])
        with self.assertRaisesRegex(AIError, 'survey_already_frozen'):
            self.store.set_survey(
                self.sample['sample_id'], survey(duration_bucket='gt_7d'), 'fixture:survey'
            )
        job, created = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        self.assertTrue(created)
        self.assertEqual(job['state'], 'queued')

    @mock.patch('experiments.worker.analyze_eye')
    def test_e2_worker_passes_only_frozen_survey_and_records_digest(self, analyze_eye):
        stored = self.store.set_survey(self.sample['sample_id'], survey(), 'fixture:survey')
        run = self.store.create_run(
            'E2_vlm_survey', {'survey_schema_version': SURVEY_SCHEMA_VERSION}, {},
            engineering_fixture=True,
        )
        job, _ = self.store.enqueue(self.sample['sample_id'], run['run_id'])
        analyze_eye.return_value = result(self.sample['roi_digest'], '3')
        self.assertTrue(process_one(self.store, self.vlm_env))
        context = analyze_eye.call_args.kwargs['context']
        self.assertEqual(context, {'survey': survey(symptoms=['itching', 'redness'])})
        encoded = json.dumps(context)
        self.assertNotIn('prediction', encoded)
        self.assertNotIn('label', encoded)
        summary = next(item for item in self.store.list_job_summaries() if item['job_id'] == job['job_id'])
        self.assertEqual(summary['provenance']['survey_digest'], stored['response_digest'])

    def test_e4_requires_same_sample_completed_sources(self):
        baseline = self.store.create_run('E0_baseline', {}, {}, engineering_fixture=True)
        vlm = self.store.create_run('E1_vlm_image', {}, {}, engineering_fixture=True)
        hybrid = self.store.create_run('E4_hybrid_review', {
            'baseline_run_id': baseline['run_id'], 'vlm_run_id': vlm['run_id'],
            'rule_id': 'paired-review-v1',
        }, {}, engineering_fixture=True)
        with self.assertRaisesRegex(AIError, 'source_result_unavailable'):
            self.store.enqueue(self.sample['sample_id'], hybrid['run_id'])
        for run, arm in ((baseline, 'E0_baseline'), (vlm, 'E1_vlm_image')):
            self.store.enqueue(self.sample['sample_id'], run['run_id'])
            job = self.store.claim_next((arm,))
            self.store.finish(job['job_id'], job['lease_token'], result(self.sample['roi_digest']))
        job, created = self.store.enqueue(self.sample['sample_id'], hybrid['run_id'])
        self.assertTrue(created)
        self.assertEqual(job['state'], 'queued')

    def test_e4_is_deterministic_separate_and_never_reads_image(self):
        baseline = self.complete('E0_baseline', '3')
        vlm = self.complete('E1_vlm_image', '2')
        hybrid = self.store.create_run('E4_hybrid_review', {
            'baseline_run_id': baseline['run_id'], 'vlm_run_id': vlm['run_id'],
            'rule_id': 'paired-review-v1',
        }, {'runtime': 'deterministic-rule'}, engineering_fixture=True)
        job, _ = self.store.enqueue(self.sample['sample_id'], hybrid['run_id'])
        with mock.patch.object(self.store, 'sample_image_path', side_effect=AssertionError('image read')):
            self.assertTrue(process_hybrid_one(self.store, self.hybrid_env))
        summary = next(item for item in self.store.list_job_summaries() if item['job_id'] == job['job_id'])
        review = summary['hybrid_review']['review']
        self.assertEqual(review['outcome'], 'disagreement')
        self.assertTrue(review['manual_review_required'])
        self.assertFalse(review['agreement_is_accuracy'])
        self.assertEqual(review['user_result_action'], 'none')
        self.assertIsNone(summary['analysis'])
        report = evaluate_run(self.store, hybrid['run_id'])
        self.assertEqual(report['evaluation_status'], 'HYBRID_REVIEW_ONLY')
        self.assertIsNone(report['clinical_metrics'])
        self.assertFalse(report['hybrid_review_is_classification_metric'])

    def test_schema_migrates_and_purge_removes_new_sample_scoped_records(self):
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            version = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(version, '3')
        self.assertTrue({'survey_inputs', 'hybrid_reviews'} <= tables)

        real = self.store.register_sample(png('red'), {
            'patient_group_id': 'real-group', 'capture_id': 'real-capture',
            'source_asset_ref': 'real-asset', 'modality': 'external_eye_webcam',
            'selected_eye': 'L', 'engineering_fixture': False, 'synthetic': False,
            'permission_ref': 'permission:fixture', 'retention_policy_ref': 'retention:fixture',
            'retention_until': '2099-01-01', 'split': 'holdout',
        })
        self.store.set_survey(real['sample_id'], survey(), 'fixture:survey')
        source_runs = []
        for arm, label in (('E0_baseline', '3'), ('E1_vlm_image', '2')):
            run = self.store.create_run(arm, {}, {}, engineering_fixture=False)
            self.store.enqueue(real['sample_id'], run['run_id'])
            job = self.store.claim_next((arm,))
            self.store.finish(job['job_id'], job['lease_token'], result(real['roi_digest'], label))
            source_runs.append(run)
        hybrid = self.store.create_run('E4_hybrid_review', {
            'baseline_run_id': source_runs[0]['run_id'],
            'vlm_run_id': source_runs[1]['run_id'],
            'rule_id': 'paired-review-v1',
        }, {'runtime': 'deterministic-rule'}, engineering_fixture=False)
        self.store.enqueue(real['sample_id'], hybrid['run_id'])
        self.assertTrue(process_hybrid_one(self.store, self.hybrid_env))
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM hybrid_reviews').fetchone()[0], 1)
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.execute('UPDATE samples SET retention_until=? WHERE sample_id=?', ('2020-01-01', real['sample_id']))
        report = self.store.purge_expired([real['sample_id']], confirmation=PURGE_CONFIRMATION)
        self.assertTrue(report['vacuum_performed'])
        self.assertEqual(report['job_count'], 3)
        self.assertEqual(report['survey_input_count'], 1)
        self.assertEqual(report['hybrid_review_count'], 1)
        with closing(sqlite3.connect(self.store.db_path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM survey_inputs WHERE sample_id=?', (real['sample_id'],)).fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM hybrid_reviews').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
