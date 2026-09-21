import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from experiments.import_operational import import_history_eye
from experiments.store import ExperimentStore
from utils.ai_config import AIError


class OperationalImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image_root = self.root / 'operational-images'
        self.image_root.mkdir()
        self.source = self.image_root / 'source.jpg'
        image = Image.new('RGB', (40, 24), 'white')
        for x in range(5, 20):
            for y in range(4, 16):
                image.putpixel((x, y), (200, 20, 20))
        image.save(self.source, format='JPEG', quality=95)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()

        self.database = self.root / 'operational.db'
        connection = sqlite3.connect(self.database)
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
        analysis = {
            'left_eye': {
                'bbox': [5, 4, 20, 16],
                'class': 3,
                'disease': 'must-not-transfer',
                'confidence': 99.9,
            },
            'right_eye': {'bbox': [22, 4, 37, 16], 'class': 0},
        }
        connection.execute('INSERT INTO users VALUES (?, ?)', (1, 'a' * 64))
        connection.execute(
            'INSERT INTO diagnosis_sessions VALUES (?, ?, ?, ?)',
            (7, 1, '2026-09-20T12:00:00Z', json.dumps(analysis)),
        )
        connection.execute(
            'INSERT INTO session_assets VALUES (?, ?, ?, ?, ?, ?)',
            (9, 7, 'image_raw', str(self.source), 'image/jpeg', digest),
        )
        connection.commit()
        connection.close()
        self.store = ExperimentStore(self.root / 'research', allow_real_data=True)

    def tearDown(self):
        self.temp.cleanup()

    def import_one(self, **overrides):
        values = {
            'database_path': self.database,
            'image_root': self.image_root,
            'history_id': 7,
            'selected_eye': 'L',
            'permission_ref': 'irb:2026:approved-001',
            'retention_policy_ref': 'retention:policy-v1',
            'retention_until': '2030-12-31',
            'split': 'holdout',
        }
        values.update(overrides)
        return import_history_eye(self.store, **values)

    def test_import_copies_only_roi_and_is_idempotent(self):
        database_mtime = self.database.stat().st_mtime_ns
        sample, created = self.import_one()
        self.assertTrue(created)
        self.assertEqual(self.database.stat().st_mtime_ns, database_mtime)
        self.assertEqual(sample['patient_group_id'], 'a' * 64)
        self.assertEqual(json.loads(sample['source_size_json']), [40, 24])
        self.assertEqual(json.loads(sample['roi_bbox_json']), [5, 4, 20, 16])
        with Image.open(self.store.sample_image_path(sample['sample_id'])) as copied:
            self.assertEqual(copied.size, (15, 12))
        database_text = self.store.db_path.read_bytes()
        self.assertNotIn(b'must-not-transfer', database_text)
        connection = sqlite3.connect(self.store.db_path)
        action, detail_json = connection.execute(
            'SELECT action, detail_json FROM audit_events WHERE object_id=?',
            (sample['sample_id'],),
        ).fetchone()
        connection.close()
        self.assertEqual(action, 'operational_import')
        detail = json.loads(detail_json)
        self.assertEqual(detail['permission_ref'], 'irb:2026:approved-001')
        self.assertEqual(detail['retention_until'], '2030-12-31')
        self.assertNotIn('must-not-transfer', detail_json)

        duplicate, duplicate_created = self.import_one()
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate['sample_id'], sample['sample_id'])
        self.assertEqual(len(list(self.store.samples_dir.iterdir())), 1)

    def test_changed_authorization_does_not_relabel_existing_copy(self):
        self.import_one()
        with self.assertRaisesRegex(AIError, 'existing_import_mismatch'):
            self.import_one(permission_ref='irb:2026:different')

    def test_asset_outside_capture_root_is_rejected(self):
        outside = self.root / 'outside.jpg'
        outside.write_bytes(self.source.read_bytes())
        connection = sqlite3.connect(self.database)
        connection.execute('UPDATE session_assets SET file_path=?', (str(outside),))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(AIError, 'asset_unavailable'):
            self.import_one()

    def test_expired_retention_is_rejected_before_copy(self):
        with self.assertRaisesRegex(AIError, 'retention_expired'):
            self.import_one(retention_until='2020-01-01')
        self.assertEqual(list(self.store.samples_dir.iterdir()), [])

    def test_expired_existing_sample_cannot_be_enqueued(self):
        sample, _ = self.import_one()
        run = self.store.create_run('E1_vlm_image', {}, {})
        connection = sqlite3.connect(self.store.db_path)
        connection.execute(
            'UPDATE samples SET retention_until=? WHERE sample_id=?',
            ('2020-01-01', sample['sample_id']),
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(AIError, 'retention_expired'):
            self.store.enqueue(sample['sample_id'], run['run_id'])
        report = self.store.retention_status()
        self.assertFalse(report['mutation_performed'])
        self.assertEqual(report['expired_samples'][0]['sample_id'], sample['sample_id'])
        self.assertEqual(report['expired_samples'][0]['status'], 'expired')
        self.assertTrue(self.store.sample_image_path(sample['sample_id']).is_file())


if __name__ == '__main__':
    unittest.main()
