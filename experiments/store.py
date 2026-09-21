"""Durable, bounded SQLite store for shadow research jobs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from utils.ai_config import AIError
from utils.vlm_client import MAX_IMAGE_BYTES, prepare_image, validate_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).with_name('schema.sql')
FORBIDDEN_KEYS = {
    'label', 'ground_truth', 'prediction', 'predicted_class', 'confidence',
    'probabilities', 'gradcam', 'heatmap', 'diagnosis', 'disease',
}
OPAQUE_REF = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
POLICY_REF = re.compile(r'^[A-Za-z0-9_.:/-]{3,200}$')
PURGE_CONFIRMATION = 'DELETE_EXPIRED_RESEARCH_COPIES'
ARMS = {
    'E0_baseline', 'E1_vlm_image', 'E2_vlm_survey',
    'E3_result_explanation', 'E4_hybrid_review',
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _reject_label_leak(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                raise AIError('forbidden_context')
            _reject_label_leak(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_label_leak(nested)


def _without_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _without_secrets(nested)
            for key, nested in value.items()
            if not any(marker in str(key).lower() for marker in ('token', 'secret', 'password', 'api_key'))
        }
    if isinstance(value, list):
        return [_without_secrets(item) for item in value]
    return value


class ExperimentStore:
    def __init__(self, data_dir: str | os.PathLike, *, queue_max: int = 16, allow_real_data: bool = False):
        path = Path(data_dir)
        if not path.is_absolute() or queue_max < 1 or queue_max > 10_000:
            raise ValueError('invalid experiment storage configuration')
        self.data_dir = path.resolve()
        public_dir = (PROJECT_ROOT / 'web' / 'static').resolve()
        if self.data_dir == public_dir or public_dir in self.data_dir.parents:
            raise ValueError('experiment storage must be outside web/static')
        self.samples_dir = self.data_dir / 'samples'
        self.artifacts_dir = self.data_dir / 'artifacts'
        self.db_path = self.data_dir / 'experiments.db'
        self.queue_max = queue_max
        self.allow_real_data = allow_real_data
        self.samples_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.data_dir, 0o700)
        os.chmod(self.samples_dir, 0o700)
        os.chmod(self.artifacts_dir, 0o700)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA busy_timeout = 10000')
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
            columns = {
                str(row['name'])
                for row in connection.execute('PRAGMA table_info(samples)')
            }
            for name in (
                'retention_policy_ref', 'retention_until',
                'source_system', 'source_record_ref',
            ):
                if name not in columns:
                    connection.execute(f'ALTER TABLE samples ADD COLUMN {name} TEXT')
            connection.execute(
                '''CREATE UNIQUE INDEX IF NOT EXISTS samples_source_import_idx
                   ON samples(source_system, source_record_ref, selected_eye, preprocessing_version)
                   WHERE source_system IS NOT NULL AND source_record_ref IS NOT NULL'''
            )
        os.chmod(self.db_path, 0o600)

    def register_sample(self, image_bytes: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            raise ValueError('sample metadata must be an object')
        _reject_label_leak(metadata)
        engineering = metadata.get('engineering_fixture') is True
        synthetic = metadata.get('synthetic') is True
        permission_ref = str(metadata.get('permission_ref') or '').strip() or None
        retention_ref = str(metadata.get('retention_policy_ref') or '').strip() or None
        retention_until = str(metadata.get('retention_until') or '').strip() or None
        if permission_ref and not POLICY_REF.fullmatch(permission_ref):
            raise ValueError('invalid permission_ref')
        if retention_ref and not POLICY_REF.fullmatch(retention_ref):
            raise ValueError('invalid retention_policy_ref')
        if retention_until:
            try:
                retention_date = date.fromisoformat(retention_until)
            except ValueError:
                raise ValueError('invalid retention_until') from None
            if retention_date < datetime.now(timezone.utc).date():
                raise AIError('retention_expired')
        if not engineering and (
            not self.allow_real_data or not permission_ref
            or not retention_ref or not retention_until
        ):
            raise AIError('real_data_not_allowed')
        if engineering and not synthetic:
            raise ValueError('engineering fixtures must be marked synthetic')
        required_refs = ('patient_group_id', 'capture_id', 'source_asset_ref')
        for key in required_refs:
            if not OPAQUE_REF.fullmatch(str(metadata.get(key) or '')):
                raise ValueError(f'invalid {key}')
        selected_eye = str(metadata.get('selected_eye') or 'unknown')
        if selected_eye not in ('L', 'R', 'unknown'):
            raise ValueError('invalid selected_eye')
        if metadata.get('modality') != 'external_eye_webcam':
            raise ValueError('unsupported modality')
        source_system = str(metadata.get('source_system') or '').strip() or None
        source_record_ref = str(metadata.get('source_record_ref') or '').strip() or None
        if (source_system is None) != (source_record_ref is None):
            raise ValueError('incomplete source provenance')
        if source_system and (
            not OPAQUE_REF.fullmatch(source_system)
            or not OPAQUE_REF.fullmatch(source_record_ref)
        ):
            raise ValueError('invalid source provenance')
        split = str(metadata.get('split') or 'engineering_fixture')
        if not engineering and split not in ('train', 'validation', 'test', 'holdout', 'prospective'):
            raise ValueError('invalid research split')

        normalized, _mime_type, normalized_size = prepare_image(image_bytes)
        sample_id = uuid.uuid4().hex
        relative_ref = f'samples/{sample_id}.jpg'
        destination = self.data_dir / relative_ref
        with destination.open('xb') as output:
            output.write(normalized)
        os.chmod(destination, 0o600)
        now = utc_now()
        source_size = metadata.get('source_size') or list(normalized_size)
        bbox = metadata.get('roi_bbox') or [0, 0, source_size[0], source_size[1]]
        try:
            values = [int(value) for value in bbox]
            width, height = [int(value) for value in source_size]
            if len(values) != 4 or width < 1 or height < 1:
                raise ValueError()
            x1, y1, x2, y2 = values
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError()
        except (TypeError, ValueError, IndexError):
            destination.unlink(missing_ok=True)
            raise ValueError('invalid ROI coordinates') from None

        source_digest = str(metadata.get('source_digest') or hashlib.sha256(image_bytes).hexdigest())
        if not re.fullmatch(r'[0-9a-f]{64}', source_digest):
            destination.unlink(missing_ok=True)
            raise ValueError('invalid source_digest')
        record = {
            'sample_id': sample_id,
            'patient_group_id': str(metadata['patient_group_id']),
            'capture_id': str(metadata['capture_id']),
            'capture_time': str(metadata.get('capture_time') or now),
            'modality': 'external_eye_webcam',
            'selected_eye': selected_eye,
            'laterality_basis': str(metadata.get('laterality_basis') or 'unknown'),
            'source_asset_ref': str(metadata['source_asset_ref']),
            'canonical_roi_ref': relative_ref,
            'source_digest': source_digest,
            'roi_digest': hashlib.sha256(normalized).hexdigest(),
            'source_size_json': canonical_json([width, height]),
            'roi_bbox_json': canonical_json(values),
            'orientation': str(metadata.get('orientation') or 'normalized_exif'),
            'mirrored': int(metadata.get('mirrored') is True),
            'crop_version': str(metadata.get('crop_version') or 'fixture-v1'),
            'preprocessing_version': str(metadata.get('preprocessing_version') or 'vlm-jpeg-v1'),
            'quality_state': str(metadata.get('quality_state') or 'unreviewed'),
            'quality_reasons_json': canonical_json(metadata.get('quality_reasons') or []),
            'permission_ref': permission_ref,
            'retention_policy_ref': retention_ref,
            'retention_until': retention_until,
            'source_system': source_system,
            'source_record_ref': source_record_ref,
            'split': split,
            'engineering_fixture': int(engineering),
            'synthetic': int(synthetic),
            'created_at': now,
        }
        try:
            with self._connection() as connection:
                connection.execute(
                    f"INSERT INTO samples ({','.join(record)}) VALUES ({','.join('?' for _ in record)})",
                    tuple(record.values()),
                )
                self._audit(
                    connection,
                    'operational_import' if source_system else 'register',
                    'sample', sample_id, {
                        'engineering_fixture': engineering,
                        'source_system': source_system,
                        'source_record_ref': source_record_ref,
                        'permission_ref': permission_ref,
                        'retention_policy_ref': retention_ref,
                        'retention_until': retention_until,
                    },
                )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return self.get_sample(sample_id)

    def find_imported_sample(
        self,
        source_system: str,
        source_record_ref: str,
        selected_eye: str,
        preprocessing_version: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                '''SELECT * FROM samples
                   WHERE source_system=? AND source_record_ref=?
                     AND selected_eye=? AND preprocessing_version=?''',
                (source_system, source_record_ref, selected_eye, preprocessing_version),
            ).fetchone()
        return dict(row) if row is not None else None

    def retention_status(self) -> dict[str, Any]:
        """Read-only expiry inventory; this method never deletes research data."""
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connection() as connection:
            rows = connection.execute(
                '''SELECT s.sample_id, s.retention_until,
                          SUM(CASE WHEN j.state IN (
                            'queued', 'running', 'cancel_requested'
                          ) THEN 1 ELSE 0 END) AS active_jobs
                   FROM samples s
                   LEFT JOIN jobs j ON j.sample_id=s.sample_id
                   WHERE s.engineering_fixture=0 AND s.retention_until IS NOT NULL
                     AND s.retention_until < ?
                   GROUP BY s.sample_id, s.retention_until
                   ORDER BY s.sample_id''',
                (today,),
            ).fetchall()
        return {
            'as_of': today,
            'expired_samples': [
                {
                    'sample_id': row['sample_id'],
                    'retention_until': row['retention_until'],
                    'status': 'blocked_active_job' if row['active_jobs'] else 'expired',
                }
                for row in rows
            ],
            'mutation_performed': False,
        }

    def purge_expired(
        self,
        sample_ids: list[str] | tuple[str, ...],
        *,
        confirmation: str,
    ) -> dict[str, Any]:
        """Permanently remove explicitly selected, expired research copies only."""
        if confirmation != PURGE_CONFIRMATION:
            raise AIError('purge_confirmation_required')
        if not isinstance(sample_ids, (list, tuple)) or not sample_ids or len(sample_ids) > 100:
            raise ValueError('invalid purge selection')
        selected = sorted(set(str(value) for value in sample_ids))
        if len(selected) != len(sample_ids) or any(not re.fullmatch(r'[0-9a-f]{32}', value) for value in selected):
            raise ValueError('invalid purge selection')

        today = datetime.now(timezone.utc).date().isoformat()
        placeholders = ','.join('?' for _ in selected)
        batch_id = uuid.uuid4().hex
        staged: list[tuple[Path, Path]] = []
        missing_files = 0
        deleted_import_audits = 0
        deleted_jobs = 0
        deleted_survey_inputs = 0
        deleted_hybrid_reviews = 0
        staging_dir = self.data_dir / '.purge-staging' / batch_id

        try:
            with self._connection() as connection:
                connection.execute('BEGIN IMMEDIATE')
                samples = connection.execute(
                    f'''SELECT sample_id, canonical_roi_ref, retention_until,
                               engineering_fixture
                        FROM samples WHERE sample_id IN ({placeholders})''',
                    selected,
                ).fetchall()
                if len(samples) != len(selected):
                    raise AIError('purge_sample_not_found')
                for sample in samples:
                    if sample['engineering_fixture']:
                        raise AIError('purge_scope_rejected')
                    try:
                        expired = date.fromisoformat(str(sample['retention_until'])) < date.fromisoformat(today)
                    except (TypeError, ValueError):
                        raise AIError('retention_unverified') from None
                    if not expired:
                        raise AIError('retention_not_expired')

                active = connection.execute(
                    f'''SELECT COUNT(*) FROM jobs
                        WHERE sample_id IN ({placeholders})
                          AND state IN ('queued', 'running', 'cancel_requested')''',
                    selected,
                ).fetchone()[0]
                if active:
                    raise AIError('purge_active_jobs')

                jobs = connection.execute(
                    f'''SELECT j.job_id, p.result_json
                        FROM jobs j LEFT JOIN predictions p ON p.job_id=j.job_id
                        WHERE j.sample_id IN ({placeholders})''',
                    selected,
                ).fetchall()
                paths: list[Path] = []
                for sample in samples:
                    raw = self.data_dir / str(sample['canonical_roi_ref'])
                    resolved = raw.resolve()
                    if raw.is_symlink() or resolved.parent != self.samples_dir:
                        raise AIError('purge_path_invalid')
                    paths.append(resolved)
                for job in jobs:
                    job_id = str(job['job_id'])
                    artifact = self.artifacts_dir / f'{job_id}-gradcam.jpg'
                    resolved = artifact.resolve()
                    if artifact.is_symlink() or resolved.parent != self.artifacts_dir:
                        raise AIError('purge_path_invalid')
                    referenced = False
                    if job['result_json']:
                        try:
                            payload = json.loads(job['result_json'])
                            reference = payload.get('provenance', {}).get('gradcam_artifact_ref')
                        except (AttributeError, TypeError, json.JSONDecodeError):
                            raise AIError('purge_artifact_unverified') from None
                        if reference is not None:
                            if reference != f'artifacts/{job_id}-gradcam.jpg':
                                raise AIError('purge_artifact_unverified')
                            referenced = True
                    if referenced or artifact.exists() or artifact.is_symlink():
                        paths.append(resolved)

                existing_paths = [path for path in paths if path.is_file()]
                missing_files = len(paths) - len(existing_paths)
                if existing_paths:
                    staging_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
                    os.chmod(staging_dir.parent, 0o700)
                    os.chmod(staging_dir, 0o700)
                    for index, original in enumerate(existing_paths):
                        destination = staging_dir / f'{index:04d}.purge'
                        os.replace(original, destination)
                        staged.append((original, destination))

                deleted_hybrid_reviews = connection.execute(
                    f'''DELETE FROM hybrid_reviews WHERE job_id IN (
                           SELECT job_id FROM jobs WHERE sample_id IN ({placeholders})
                       ) OR baseline_prediction_id IN (
                           SELECT p.prediction_id FROM predictions p
                           JOIN jobs j ON j.job_id=p.job_id
                           WHERE j.sample_id IN ({placeholders})
                       ) OR vlm_prediction_id IN (
                           SELECT p.prediction_id FROM predictions p
                           JOIN jobs j ON j.job_id=p.job_id
                           WHERE j.sample_id IN ({placeholders})
                       )''',
                    selected + selected + selected,
                ).rowcount
                connection.execute(
                    f'''DELETE FROM explanations WHERE job_id IN (
                           SELECT job_id FROM jobs WHERE sample_id IN ({placeholders})
                       ) OR source_prediction_id IN (
                           SELECT p.prediction_id FROM predictions p
                           JOIN jobs j ON j.job_id=p.job_id
                           WHERE j.sample_id IN ({placeholders})
                       )''',
                    selected + selected,
                )
                connection.execute(
                    f'''DELETE FROM predictions WHERE job_id IN (
                           SELECT job_id FROM jobs WHERE sample_id IN ({placeholders})
                       )''',
                    selected,
                )
                deleted_jobs = connection.execute(
                    f'DELETE FROM jobs WHERE sample_id IN ({placeholders})', selected
                ).rowcount
                connection.execute(
                    f'DELETE FROM reference_labels WHERE sample_id IN ({placeholders})', selected
                )
                deleted_survey_inputs = connection.execute(
                    f'DELETE FROM survey_inputs WHERE sample_id IN ({placeholders})', selected
                ).rowcount
                deleted_import_audits = connection.execute(
                    f'''DELETE FROM audit_events
                        WHERE action='operational_import' AND object_type='sample'
                          AND object_id IN ({placeholders})''',
                    selected,
                ).rowcount
                deleted_samples = connection.execute(
                    f'DELETE FROM samples WHERE sample_id IN ({placeholders})', selected
                ).rowcount
                if deleted_samples != len(selected):
                    raise AIError('purge_delete_mismatch')
                self._audit(
                    connection,
                    'retention_purge',
                    'retention_batch',
                    batch_id,
                    {
                        'as_of': today,
                        'sample_count': deleted_samples,
                        'job_count': deleted_jobs,
                        'operational_import_audit_count': deleted_import_audits,
                        'survey_input_count': deleted_survey_inputs,
                        'hybrid_review_count': deleted_hybrid_reviews,
                    },
                )
        except Exception:
            for original, destination in reversed(staged):
                if destination.exists() and not original.exists():
                    os.replace(destination, original)
            if staging_dir.exists():
                staging_dir.rmdir()
            parent = staging_dir.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
            raise

        for _original, destination in staged:
            destination.unlink()
        if staging_dir.exists():
            staging_dir.rmdir()
        parent = staging_dir.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()

        vacuum = self._connect()
        try:
            vacuum.execute('VACUUM')
        finally:
            vacuum.close()
        os.chmod(self.db_path, 0o600)
        return {
            'as_of': today,
            'sample_count': len(selected),
            'job_count': deleted_jobs,
            'file_count': len(staged),
            'missing_file_count': missing_files,
            'operational_import_audit_count': deleted_import_audits,
            'survey_input_count': deleted_survey_inputs,
            'hybrid_review_count': deleted_hybrid_reviews,
            'vacuum_performed': True,
            'mutation_performed': True,
            'operational_source_touched': False,
            'runs_deleted': 0,
        }

    def get_sample(self, sample_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM samples WHERE sample_id = ?', (sample_id,)).fetchone()
        if row is None:
            raise KeyError('sample_not_found')
        return dict(row)

    def set_survey(self, sample_id: str, responses: dict[str, Any], source: str) -> dict[str, Any]:
        from experiments.survey import SURVEY_SCHEMA_VERSION, validate_survey

        normalized = validate_survey(responses)
        source = str(source).strip()
        if not POLICY_REF.fullmatch(source):
            raise ValueError('invalid survey source')
        payload = canonical_json(normalized)
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        now = utc_now()
        with self._connection() as connection:
            if connection.execute('SELECT 1 FROM samples WHERE sample_id=?', (sample_id,)).fetchone() is None:
                raise KeyError('sample_not_found')
            existing = connection.execute(
                'SELECT * FROM survey_inputs WHERE sample_id=?', (sample_id,)
            ).fetchone()
            if existing is not None:
                if existing['response_digest'] != digest or existing['source'] != source:
                    raise AIError('survey_already_frozen')
                return {
                    **dict(existing), 'responses': json.loads(existing['response_json']),
                }
            connection.execute(
                'INSERT INTO survey_inputs VALUES (?, ?, ?, ?, ?, ?)',
                (sample_id, SURVEY_SCHEMA_VERSION, payload, digest, source, now),
            )
            self._audit(connection, 'freeze_survey', 'sample', sample_id, {
                'schema_version': SURVEY_SCHEMA_VERSION, 'response_digest': digest,
            })
        return self.get_survey(sample_id)

    def get_survey(self, sample_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                'SELECT * FROM survey_inputs WHERE sample_id=?', (sample_id,)
            ).fetchone()
        if row is None:
            raise AIError('survey_unavailable')
        value = dict(row)
        value['responses'] = json.loads(value.pop('response_json'))
        return value

    def sample_image_path(self, sample_id: str) -> Path:
        sample = self.get_sample(sample_id)
        path = (self.data_dir / sample['canonical_roi_ref']).resolve()
        if self.data_dir not in path.parents or not path.is_file():
            raise AIError('asset_unavailable')
        return path

    def create_run(
        self,
        arm_id: str,
        config_snapshot: dict[str, Any],
        model_manifest: dict[str, Any],
        *,
        repeat_index: int = 0,
        prompt_digest: str | None = None,
        engineering_fixture: bool = False,
    ) -> dict[str, Any]:
        if arm_id not in ARMS or repeat_index < 0:
            raise ValueError('invalid run configuration')
        if arm_id == 'E1_vlm_image' and 'runtime_expectation' in config_snapshot:
            from utils.runtime_receipt import validate_runtime_expectation

            config_snapshot = dict(config_snapshot)
            config_snapshot['runtime_expectation'] = validate_runtime_expectation(
                config_snapshot['runtime_expectation']
            )
        elif arm_id == 'E2_vlm_survey':
            from experiments.survey import validate_run_config

            config_snapshot = validate_run_config(config_snapshot)
        elif arm_id == 'E3_result_explanation':
            from experiments.explanation import prompt_digest as e3_prompt_digest
            from experiments.explanation import validate_run_config

            config_snapshot = validate_run_config(config_snapshot)
            source_run = self.get_run(config_snapshot['source_run_id'])
            if source_run['arm_id'] != 'E0_baseline':
                raise ValueError('E3 source must be E0_baseline')
            expected_digest = e3_prompt_digest()
            if prompt_digest is not None and prompt_digest != expected_digest:
                raise ValueError('E3 prompt digest mismatch')
            prompt_digest = expected_digest
        elif arm_id == 'E4_hybrid_review':
            from experiments.hybrid import validate_run_config

            config_snapshot = validate_run_config(config_snapshot)
            baseline_run = self.get_run(config_snapshot['baseline_run_id'])
            vlm_run = self.get_run(config_snapshot['vlm_run_id'])
            if baseline_run['arm_id'] != 'E0_baseline':
                raise ValueError('E4 baseline source must be E0_baseline')
            if vlm_run['arm_id'] not in {'E1_vlm_image', 'E2_vlm_survey'}:
                raise ValueError('E4 VLM source must be E1 or E2')
        safe_config = _without_secrets(config_snapshot)
        config_json = canonical_json(safe_config)
        manifest_json = canonical_json(_without_secrets(model_manifest))
        run_id = uuid.uuid4().hex
        now = utc_now()
        with self._connection() as connection:
            connection.execute(
                'INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    run_id, arm_id, repeat_index, config_json,
                    hashlib.sha256(config_json.encode()).hexdigest(), manifest_json,
                    prompt_digest, int(engineering_fixture), now,
                ),
            )
            self._audit(connection, 'create', 'run', run_id, {'arm_id': arm_id})
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if row is None:
            raise KeyError('run_not_found')
        return dict(row)

    def enqueue(self, sample_id: str, run_id: str) -> tuple[dict[str, Any], bool]:
        key = hashlib.sha256(f'{sample_id}:{run_id}'.encode()).hexdigest()
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            sample = connection.execute(
                'SELECT engineering_fixture, retention_until FROM samples WHERE sample_id=?',
                (sample_id,),
            ).fetchone()
            if sample is None:
                raise KeyError('sample_not_found')
            run = connection.execute(
                'SELECT arm_id, config_json FROM runs WHERE run_id=?', (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError('run_not_found')
            if run['arm_id'] == 'E2_vlm_survey':
                from experiments.survey import validate_run_config

                validate_run_config(json.loads(run['config_json']))
                survey = connection.execute(
                    'SELECT sample_id FROM survey_inputs WHERE sample_id=?', (sample_id,)
                ).fetchone()
                if survey is None:
                    raise AIError('survey_unavailable')
            elif run['arm_id'] == 'E3_result_explanation':
                from experiments.explanation import validate_run_config

                run_config = validate_run_config(json.loads(run['config_json']))
                source = connection.execute(
                    '''SELECT p.prediction_id
                       FROM predictions p
                       JOIN jobs j ON j.job_id=p.job_id
                       JOIN runs r ON r.run_id=j.run_id
                       WHERE j.sample_id=? AND j.run_id=? AND j.state='succeeded'
                         AND r.arm_id='E0_baseline' ''',
                    (sample_id, run_config['source_run_id']),
                ).fetchone()
                if source is None:
                    raise AIError('source_result_unavailable')
            elif run['arm_id'] == 'E4_hybrid_review':
                from experiments.hybrid import validate_run_config

                run_config = validate_run_config(json.loads(run['config_json']))
                sources = connection.execute(
                    '''SELECT r.arm_id, j.run_id
                       FROM predictions p
                       JOIN jobs j ON j.job_id=p.job_id
                       JOIN runs r ON r.run_id=j.run_id
                       WHERE j.sample_id=? AND j.state='succeeded'
                         AND j.run_id IN (?, ?)''',
                    (sample_id, run_config['baseline_run_id'], run_config['vlm_run_id']),
                ).fetchall()
                observed = {(row['run_id'], row['arm_id']) for row in sources}
                vlm_arm = connection.execute(
                    'SELECT arm_id FROM runs WHERE run_id=?', (run_config['vlm_run_id'],)
                ).fetchone()
                expected = {
                    (run_config['baseline_run_id'], 'E0_baseline'),
                    (run_config['vlm_run_id'], vlm_arm['arm_id'] if vlm_arm else ''),
                }
                if observed != expected:
                    raise AIError('source_result_unavailable')
            if not sample['engineering_fixture']:
                try:
                    retention_date = date.fromisoformat(str(sample['retention_until']))
                except (TypeError, ValueError):
                    raise AIError('retention_unverified') from None
                if retention_date < datetime.now(timezone.utc).date():
                    raise AIError('retention_expired')
            existing = connection.execute(
                'SELECT * FROM jobs WHERE idempotency_key = ?', (key,)
            ).fetchone()
            if existing is not None:
                return dict(existing), False
            active = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued', 'running', 'cancel_requested')"
            ).fetchone()[0]
            if active >= self.queue_max:
                raise AIError('queue_full')
            job_id = uuid.uuid4().hex
            connection.execute(
                '''INSERT INTO jobs(
                    job_id, sample_id, run_id, idempotency_key, state,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', ?, ?)''',
                (job_id, sample_id, run_id, key, now, now),
            )
            self._audit(connection, 'enqueue', 'job', job_id, {})
            row = connection.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
            return dict(row), True

    def claim_next(self, arm_ids: tuple[str, ...] | None = None) -> dict[str, Any] | None:
        now = utc_now()
        lease = uuid.uuid4().hex
        if arm_ids is not None and (not arm_ids or any(arm not in ARMS for arm in arm_ids)):
            raise ValueError('invalid arm filter')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if arm_ids is None:
                row = connection.execute(
                    "SELECT j.* FROM jobs j WHERE j.state = 'queued' "
                    "ORDER BY j.created_at, j.job_id LIMIT 1"
                ).fetchone()
            else:
                placeholders = ','.join('?' for _ in arm_ids)
                row = connection.execute(
                    f"SELECT j.* FROM jobs j JOIN runs r ON r.run_id=j.run_id "
                    f"WHERE j.state='queued' AND r.arm_id IN ({placeholders}) "
                    "ORDER BY j.created_at, j.job_id LIMIT 1",
                    arm_ids,
                ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                "UPDATE jobs SET state='running', lease_token=?, started_at=?, updated_at=? "
                "WHERE job_id=? AND state='queued'",
                (lease, now, now, row['job_id']),
            ).rowcount
            if updated != 1:
                return None
            claimed = connection.execute(
                'SELECT * FROM jobs WHERE job_id = ?', (row['job_id'],)
            ).fetchone()
            return dict(claimed)

    def write_artifact(self, job_id: str, name: str, payload: bytes) -> str:
        if not re.fullmatch(r'[0-9a-f]{32}', job_id) or name not in {'gradcam.jpg'}:
            raise ValueError('invalid artifact reference')
        if not isinstance(payload, bytes) or not payload or len(payload) > MAX_IMAGE_BYTES:
            raise ValueError('invalid artifact payload')
        self.get_job(job_id)
        relative_ref = f'artifacts/{job_id}-{name}'
        destination = self.data_dir / relative_ref
        with destination.open('xb') as output:
            output.write(payload)
        os.chmod(destination, 0o600)
        return relative_ref

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            row = connection.execute('SELECT state FROM jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError('job_not_found')
            next_state = 'cancelled' if row['state'] == 'queued' else 'cancel_requested'
            if row['state'] not in ('queued', 'running'):
                return self.get_job(job_id)
            connection.execute(
                "UPDATE jobs SET state=?, updated_at=?, finished_at=CASE WHEN ?='cancelled' THEN ? ELSE finished_at END WHERE job_id=?",
                (next_state, now, next_state, now, job_id),
            )
        return self.get_job(job_id)

    def finish(
        self,
        job_id: str,
        lease_token: str,
        result: dict[str, Any],
        *,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        analysis = validate_analysis(result['analysis'])
        provenance = result['provenance']
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone()
            if row is None or row['lease_token'] != lease_token or row['state'] not in ('running', 'cancel_requested'):
                raise AIError('invalid_job_transition')
            if row['state'] == 'cancel_requested':
                connection.execute(
                    "UPDATE jobs SET state='cancelled', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
            else:
                connection.execute(
                    '''INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        uuid.uuid4().hex, job_id, analysis['analysis_status'],
                        analysis['suggested_label'], canonical_json(result),
                        provenance['input_digest'], duration_ms, now,
                    ),
                )
                connection.execute(
                    "UPDATE jobs SET state='succeeded', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
        return self.get_job(job_id)

    def get_prediction_for_sample_run(
        self,
        sample_id: str,
        run_id: str,
        *,
        required_arm: str | None = None,
    ) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                '''SELECT p.prediction_id, p.result_json, r.arm_id
                   FROM predictions p
                   JOIN jobs j ON j.job_id=p.job_id
                   JOIN runs r ON r.run_id=j.run_id
                   WHERE j.sample_id=? AND j.run_id=? AND j.state='succeeded' ''',
                (sample_id, run_id),
            ).fetchone()
        if row is None or (required_arm is not None and row['arm_id'] != required_arm):
            raise AIError('source_result_unavailable')
        raw = str(row['result_json'])
        return {
            'prediction_id': row['prediction_id'],
            'arm_id': row['arm_id'],
            'result': json.loads(raw),
            'result_digest': hashlib.sha256(raw.encode('utf-8')).hexdigest(),
        }

    def finish_explanation(
        self,
        job_id: str,
        lease_token: str,
        *,
        source_prediction_id: str,
        source_result_digest: str,
        input_digest: str,
        explanation_text: str,
        provider: str,
        model: str,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        text = str(explanation_text).strip()
        if (
            provider != 'local' or not text or len(text) > 6000
            or not model or len(model) > 200
            or not re.fullmatch(r'[0-9a-f]{64}', source_result_digest)
            or not re.fullmatch(r'[0-9a-f]{64}', input_digest)
        ):
            raise AIError('invalid_output')
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(
                '''SELECT j.state, j.lease_token, j.sample_id, r.arm_id
                   FROM jobs j JOIN runs r ON r.run_id=j.run_id
                   WHERE j.job_id=?''',
                (job_id,),
            ).fetchone()
            if (
                row is None or row['lease_token'] != lease_token
                or row['state'] not in ('running', 'cancel_requested')
                or row['arm_id'] != 'E3_result_explanation'
            ):
                raise AIError('invalid_job_transition')
            source = connection.execute(
                '''SELECT p.result_json
                   FROM predictions p
                   JOIN jobs j ON j.job_id=p.job_id
                   JOIN runs r ON r.run_id=j.run_id
                   WHERE p.prediction_id=? AND j.sample_id=?
                     AND j.state='succeeded' AND r.arm_id='E0_baseline' ''',
                (source_prediction_id, row['sample_id']),
            ).fetchone()
            if source is None:
                raise AIError('source_result_unavailable')
            actual_digest = hashlib.sha256(str(source['result_json']).encode('utf-8')).hexdigest()
            if actual_digest != source_result_digest:
                raise AIError('source_result_changed')
            if row['state'] == 'cancel_requested':
                connection.execute(
                    "UPDATE jobs SET state='cancelled', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
            else:
                connection.execute(
                    '''INSERT INTO explanations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        uuid.uuid4().hex, job_id, source_prediction_id,
                        source_result_digest, input_digest, text, provider,
                        model, duration_ms, now,
                    ),
                )
                connection.execute(
                    "UPDATE jobs SET state='succeeded', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
        return self.get_job(job_id)

    def finish_hybrid(
        self,
        job_id: str,
        lease_token: str,
        *,
        baseline_prediction_id: str,
        baseline_result_digest: str,
        vlm_prediction_id: str,
        vlm_result_digest: str,
        input_digest: str,
        review: dict[str, Any],
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        from experiments.hybrid import build_review, validate_review, validate_run_config

        review = validate_review(review)
        digests = (baseline_result_digest, vlm_result_digest, input_digest)
        if any(not re.fullmatch(r'[0-9a-f]{64}', value) for value in digests):
            raise AIError('invalid_output')
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(
                '''SELECT j.state, j.lease_token, j.sample_id, r.arm_id, r.config_json
                   FROM jobs j JOIN runs r ON r.run_id=j.run_id WHERE j.job_id=?''',
                (job_id,),
            ).fetchone()
            if (
                row is None or row['lease_token'] != lease_token
                or row['state'] not in ('running', 'cancel_requested')
                or row['arm_id'] != 'E4_hybrid_review'
            ):
                raise AIError('invalid_job_transition')
            config = validate_run_config(json.loads(row['config_json']))
            sources = connection.execute(
                '''SELECT p.prediction_id, p.result_json, j.run_id, r.arm_id
                   FROM predictions p JOIN jobs j ON j.job_id=p.job_id
                   JOIN runs r ON r.run_id=j.run_id
                   WHERE p.prediction_id IN (?, ?) AND j.sample_id=? AND j.state='succeeded' ''',
                (baseline_prediction_id, vlm_prediction_id, row['sample_id']),
            ).fetchall()
            by_id = {source['prediction_id']: source for source in sources}
            baseline = by_id.get(baseline_prediction_id)
            vlm = by_id.get(vlm_prediction_id)
            if (
                baseline is None or vlm is None
                or baseline['run_id'] != config['baseline_run_id']
                or baseline['arm_id'] != 'E0_baseline'
                or vlm['run_id'] != config['vlm_run_id']
                or vlm['arm_id'] not in {'E1_vlm_image', 'E2_vlm_survey'}
            ):
                raise AIError('source_result_unavailable')
            actual_baseline = hashlib.sha256(str(baseline['result_json']).encode('utf-8')).hexdigest()
            actual_vlm = hashlib.sha256(str(vlm['result_json']).encode('utf-8')).hexdigest()
            if actual_baseline != baseline_result_digest or actual_vlm != vlm_result_digest:
                raise AIError('source_result_changed')
            expected_review, expected_input_digest = build_review(
                {
                    'arm_id': baseline['arm_id'],
                    'result': json.loads(str(baseline['result_json'])),
                    'result_digest': actual_baseline,
                },
                {
                    'arm_id': vlm['arm_id'],
                    'result': json.loads(str(vlm['result_json'])),
                    'result_digest': actual_vlm,
                },
            )
            if canonical_json(review) != canonical_json(expected_review) or input_digest != expected_input_digest:
                raise AIError('source_result_changed')
            if row['state'] == 'cancel_requested':
                connection.execute(
                    "UPDATE jobs SET state='cancelled', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
            else:
                connection.execute(
                    'INSERT INTO hybrid_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (
                        uuid.uuid4().hex, job_id, baseline_prediction_id,
                        baseline_result_digest, vlm_prediction_id, vlm_result_digest,
                        input_digest, canonical_json(review), duration_ms, now,
                    ),
                )
                connection.execute(
                    "UPDATE jobs SET state='succeeded', finished_at=?, updated_at=? WHERE job_id=?",
                    (now, now, job_id),
                )
        return self.get_job(job_id)

    def fail(self, job_id: str, lease_token: str, error_code: str, *, timed_out: bool = False) -> dict[str, Any]:
        state = 'timed_out' if timed_out else 'failed'
        now = utc_now()
        with self._connection() as connection:
            updated = connection.execute(
                "UPDATE jobs SET state=?, error_code=?, finished_at=?, updated_at=? "
                "WHERE job_id=? AND lease_token=? AND state IN ('running', 'cancel_requested')",
                (state, error_code[:100], now, now, job_id, lease_token),
            ).rowcount
            if updated != 1:
                raise AIError('invalid_job_transition')
        return self.get_job(job_id)

    def recover_interrupted(self) -> int:
        now = utc_now()
        with self._connection() as connection:
            result = connection.execute(
                "UPDATE jobs SET state='failed', error_code='interrupted', finished_at=?, updated_at=? "
                "WHERE state IN ('running', 'cancel_requested')",
                (now, now),
            )
            return result.rowcount

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
        if row is None:
            raise KeyError('job_not_found')
        return dict(row)

    def list_job_summaries(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connection() as connection:
            rows = connection.execute(
                '''SELECT j.job_id, j.sample_id, j.run_id, j.state AS job_status,
                          j.error_code, j.created_at, j.started_at, j.finished_at,
                          r.arm_id, r.repeat_index,
                          s.selected_eye, s.modality, s.quality_state,
                          s.engineering_fixture,
                          p.analysis_status, p.suggested_label,
                          COALESCE(p.duration_ms, e.duration_ms, h.duration_ms) AS duration_ms,
                          p.result_json,
                          e.explanation_text, e.provider AS explanation_provider,
                          e.model AS explanation_model,
                          e.source_result_digest, e.input_digest AS explanation_input_digest,
                          h.review_json, h.input_digest AS hybrid_input_digest,
                          h.baseline_result_digest, h.vlm_result_digest
                   FROM jobs j
                   JOIN runs r ON r.run_id = j.run_id
                   JOIN samples s ON s.sample_id = j.sample_id
                   LEFT JOIN predictions p ON p.job_id = j.job_id
                   LEFT JOIN explanations e ON e.job_id = j.job_id
                   LEFT JOIN hybrid_reviews h ON h.job_id = j.job_id
                   ORDER BY j.created_at DESC LIMIT ?''',
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            raw_result = item.pop('result_json', None)
            payload = json.loads(raw_result) if raw_result else None
            item['analysis'] = payload['analysis'] if payload else None
            item['provenance'] = payload['provenance'] if payload else None
            explanation_text = item.pop('explanation_text', None)
            explanation_provider = item.pop('explanation_provider', None)
            explanation_model = item.pop('explanation_model', None)
            source_result_digest = item.pop('source_result_digest', None)
            explanation_input_digest = item.pop('explanation_input_digest', None)
            item['explanation'] = ({
                'text': explanation_text,
                'provider': explanation_provider,
                'model': explanation_model,
                'source_result_digest': source_result_digest,
                'input_digest': explanation_input_digest,
            } if explanation_text is not None else None)
            review_json = item.pop('review_json', None)
            hybrid_input_digest = item.pop('hybrid_input_digest', None)
            baseline_result_digest = item.pop('baseline_result_digest', None)
            vlm_result_digest = item.pop('vlm_result_digest', None)
            item['hybrid_review'] = ({
                'review': json.loads(review_json),
                'input_digest': hybrid_input_digest,
                'baseline_result_digest': baseline_result_digest,
                'vlm_result_digest': vlm_result_digest,
            } if review_json is not None else None)
            results.append(item)
        return results

    def active_job_summary(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM jobs "
                "WHERE state IN ('queued','running','cancel_requested') GROUP BY state"
            ).fetchall()
        counts = {state: 0 for state in ('queued', 'running', 'cancel_requested')}
        for row in rows:
            counts[row['state']] = int(row['count'])
        return {**counts, 'total': sum(counts.values())}

    def add_reference_label(self, sample_id: str, label: str, source: str) -> None:
        normalized = str(label)
        source = str(source).strip()
        if normalized not in {'0', '1', '2', '3', '4'} or not source or len(source) > 200:
            raise ValueError('invalid reference label')
        with self._connection() as connection:
            connection.execute(
                '''INSERT INTO reference_labels(sample_id, label, source, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(sample_id) DO UPDATE SET
                     label=excluded.label, source=excluded.source, created_at=excluded.created_at''',
                (sample_id, normalized, source, utc_now()),
            )
            self._audit(connection, 'label', 'sample', sample_id, {'source': source})

    def validate_patient_splits(self) -> None:
        with self._connection() as connection:
            leak = connection.execute(
                '''SELECT patient_group_id, GROUP_CONCAT(DISTINCT split) AS splits
                   FROM samples GROUP BY patient_group_id
                   HAVING COUNT(DISTINCT split) > 1 LIMIT 1'''
            ).fetchone()
        if leak is not None:
            raise AIError('split_leakage')

    @staticmethod
    def _audit(connection, action: str, object_type: str, object_id: str, detail: dict) -> None:
        connection.execute(
            'INSERT INTO audit_events(action, object_type, object_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?)',
            (action, object_type, object_id, canonical_json(detail), utc_now()),
        )
