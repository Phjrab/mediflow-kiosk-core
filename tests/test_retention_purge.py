import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from PIL import Image

from experiments.import_operational import import_history_eye
from experiments.store import ExperimentStore, PURGE_CONFIRMATION
from utils.ai_config import AIError


def image_bytes(color='white'):
    output = io.BytesIO()
    Image.new('RGB', (24, 16), color=color).save(output, format='PNG')
    return output.getvalue()


def baseline_result(digest, artifact_ref=None):
    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': 'assessed',
            'image_quality': {'assessable': True, 'reasons': []},
            'visual_observations': [],
            'suggested_label': '3',
            'limitations': ['fixture'],
            'brief_explanation': 'fixture',
        },
        'provenance': {
            'backend': 'existing_efficientnet_baseline',
            'input_digest': digest,
            'confidence_fraction': 0.8,
            'probabilities': [0.05, 0.05, 0.05, 0.8, 0.05],
            'gradcam_artifact_ref': artifact_ref,
        },
    }


class RetentionPurgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = ExperimentStore(self.root / 'research', allow_real_data=True)

    def tearDown(self):
        self.temp.cleanup()

    def register_real(self, index, color='white'):
        return self.store.register_sample(image_bytes(color), {
            'patient_group_id': f'patient-{index}',
            'capture_id': f'capture-{index}',
            'source_asset_ref': f'asset-{index}',
            'modality': 'external_eye_webcam',
            'selected_eye': 'L',
            'engineering_fixture': False,
            'synthetic': False,
            'permission_ref': 'permission:approved',
            'retention_policy_ref': 'retention:fixture',
            'retention_until': '2099-12-31',
            'split': 'holdout',
        })

    def complete_baseline(self, sample, run, *, gradcam=False):
        self.store.enqueue(sample['sample_id'], run['run_id'])
        job = self.store.claim_next(('E0_baseline',))
        artifact_ref = None
        if gradcam:
            artifact_ref = self.store.write_artifact(job['job_id'], 'gradcam.jpg', b'fixture-cam')
        self.store.finish(
            job['job_id'], job['lease_token'],
            baseline_result(sample['roi_digest'], artifact_ref),
        )
        return job, artifact_ref

    def expire(self, *sample_ids):
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.executemany(
                'UPDATE samples SET retention_until=? WHERE sample_id=?',
                [('2020-01-01', sample_id) for sample_id in sample_ids],
            )

    def imported_sample(self):
        capture_root = self.root / 'operational-images'
        capture_root.mkdir()
        source = capture_root / 'source.png'
        source.write_bytes(image_bytes('red'))
        database = self.root / 'operational.db'
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript(
                '''CREATE TABLE users(id INTEGER PRIMARY KEY, phone_hash TEXT NOT NULL);
                   CREATE TABLE diagnosis_sessions(
                     id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                     diagnosed_at TEXT NOT NULL, ai_reading_json TEXT NOT NULL
                   );
                   CREATE TABLE session_assets(
                     id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL,
                     asset_type TEXT NOT NULL, file_path TEXT NOT NULL,
                     mime_type TEXT, sha256 TEXT
                   );'''
            )
            connection.execute('INSERT INTO users VALUES (?, ?)', (1, 'b' * 64))
            connection.execute(
                'INSERT INTO diagnosis_sessions VALUES (?, ?, ?, ?)',
                (7, 1, '2026-01-01T00:00:00Z', json.dumps({'left_eye': {'bbox': [2, 2, 18, 14]}})),
            )
            connection.execute(
                'INSERT INTO session_assets VALUES (?, ?, ?, ?, ?, ?)',
                (9, 7, 'image_raw', str(source), 'image/png', hashlib.sha256(source.read_bytes()).hexdigest()),
            )
        sample, _created = import_history_eye(
            self.store,
            database_path=database,
            image_root=capture_root,
            history_id=7,
            selected_eye='L',
            permission_ref='permission:approved',
            retention_policy_ref='retention:fixture',
            retention_until='2099-12-31',
            split='holdout',
        )
        return sample, source, database

    def test_purge_removes_expired_research_copy_and_leaves_operational_source(self):
        sample, source, operational_db = self.imported_sample()
        source_bytes = source.read_bytes()
        database_bytes = operational_db.read_bytes()
        source_mtime = source.stat().st_mtime_ns
        database_mtime = operational_db.stat().st_mtime_ns

        baseline = self.store.create_run('E0_baseline', {}, {}, engineering_fixture=False)
        baseline_job, artifact_ref = self.complete_baseline(sample, baseline, gradcam=True)
        source_prediction = self.store.get_prediction_for_sample_run(sample['sample_id'], baseline['run_id'])
        explanation = self.store.create_run(
            'E3_result_explanation',
            {'source_run_id': baseline['run_id'], 'question_id': 'explain-result-ko-v1'},
            {}, engineering_fixture=False,
        )
        self.store.enqueue(sample['sample_id'], explanation['run_id'])
        explanation_job = self.store.claim_next(('E3_result_explanation',))
        self.store.finish_explanation(
            explanation_job['job_id'], explanation_job['lease_token'],
            source_prediction_id=source_prediction['prediction_id'],
            source_result_digest=source_prediction['result_digest'],
            input_digest='f' * 64,
            explanation_text='fixture explanation',
            provider='local', model='fixture-model',
        )
        self.store.add_reference_label(sample['sample_id'], '3', 'fixture-review')
        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.execute(
                "INSERT INTO audit_events(action, object_type, object_id, detail_json, created_at) VALUES ('review_note', 'sample', ?, '{}', 'fixture')",
                (sample['sample_id'],),
            )
        roi_path = self.store.sample_image_path(sample['sample_id'])
        artifact_path = self.store.data_dir / artifact_ref
        self.expire(sample['sample_id'])

        report = self.store.purge_expired(
            [sample['sample_id']], confirmation=PURGE_CONFIRMATION
        )
        self.assertTrue(report['mutation_performed'])
        self.assertTrue(report['vacuum_performed'])
        self.assertFalse(report['operational_source_touched'])
        self.assertEqual(report['sample_count'], 1)
        self.assertEqual(report['job_count'], 2)
        self.assertEqual(report['file_count'], 2)
        self.assertEqual(report['runs_deleted'], 0)
        self.assertFalse(roi_path.exists())
        self.assertFalse(artifact_path.exists())
        self.assertFalse((self.store.data_dir / '.purge-staging').exists())
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(operational_db.read_bytes(), database_bytes)
        self.assertEqual(source.stat().st_mtime_ns, source_mtime)
        self.assertEqual(operational_db.stat().st_mtime_ns, database_mtime)

        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM samples').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM predictions').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM explanations').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM reference_labels').fetchone()[0], 0)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 2)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_events WHERE action='operational_import'").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM audit_events WHERE action='review_note'").fetchone()[0], 1)
            purge_detail = connection.execute(
                "SELECT detail_json FROM audit_events WHERE action='retention_purge'"
            ).fetchone()[0]
            self.assertNotIn(sample['sample_id'], purge_detail)
            self.assertEqual(connection.execute('PRAGMA freelist_count').fetchone()[0], 0)

    def test_shared_run_and_nonexpired_sample_are_preserved(self):
        expired = self.register_real('expired', 'red')
        current = self.register_real('current', 'blue')
        run = self.store.create_run('E0_baseline', {}, {}, engineering_fixture=False)
        expired_job, _ = self.complete_baseline(expired, run)
        current_job, _ = self.complete_baseline(current, run)
        self.expire(expired['sample_id'])

        self.store.purge_expired([expired['sample_id']], confirmation=PURGE_CONFIRMATION)
        self.assertEqual(self.store.get_run(run['run_id'])['run_id'], run['run_id'])
        self.assertEqual(self.store.get_sample(current['sample_id'])['sample_id'], current['sample_id'])
        self.assertEqual(self.store.get_job(current_job['job_id'])['state'], 'succeeded')
        with self.assertRaises(KeyError):
            self.store.get_job(expired_job['job_id'])

    def test_confirmation_active_jobs_and_mixed_batch_fail_before_mutation(self):
        expired = self.register_real('expired')
        current = self.register_real('current')
        self.expire(expired['sample_id'])
        expired_path = self.store.sample_image_path(expired['sample_id'])
        with self.assertRaisesRegex(AIError, 'purge_confirmation_required'):
            self.store.purge_expired([expired['sample_id']], confirmation='yes')
        with self.assertRaisesRegex(AIError, 'retention_not_expired'):
            self.store.purge_expired(
                [expired['sample_id'], current['sample_id']],
                confirmation=PURGE_CONFIRMATION,
            )
        self.assertTrue(expired_path.exists())
        self.assertEqual(self.store.get_sample(expired['sample_id'])['sample_id'], expired['sample_id'])

        with closing(sqlite3.connect(self.store.db_path)) as connection, connection:
            connection.execute(
                'UPDATE samples SET retention_until=? WHERE sample_id=?',
                ('2099-12-31', expired['sample_id']),
            )
        run = self.store.create_run('E0_baseline', {}, {}, engineering_fixture=False)
        self.store.enqueue(expired['sample_id'], run['run_id'])
        self.expire(expired['sample_id'])
        with self.assertRaisesRegex(AIError, 'purge_active_jobs'):
            self.store.purge_expired([expired['sample_id']], confirmation=PURGE_CONFIRMATION)
        self.assertTrue(expired_path.exists())

    def test_engineering_fixture_is_outside_purge_scope(self):
        fixture = self.store.register_sample(image_bytes(), {
            'patient_group_id': 'fixture-group',
            'capture_id': 'fixture-capture',
            'source_asset_ref': 'fixture-asset',
            'modality': 'external_eye_webcam',
            'selected_eye': 'L',
            'engineering_fixture': True,
            'synthetic': True,
        })
        self.expire(fixture['sample_id'])
        with self.assertRaisesRegex(AIError, 'purge_scope_rejected'):
            self.store.purge_expired([fixture['sample_id']], confirmation=PURGE_CONFIRMATION)
        self.assertTrue(self.store.sample_image_path(fixture['sample_id']).is_file())


if __name__ == '__main__':
    unittest.main()
