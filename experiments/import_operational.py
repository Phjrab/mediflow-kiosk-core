"""Explicit, audited import of one operational eye ROI into research storage."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from experiments.store import ExperimentStore, POLICY_REF
from utils.ai_config import AIError


SOURCE_SYSTEM = 'mediflow_operational_db_v1'
PREPROCESSING_VERSION = 'operational-history-roi-v1'
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_PIXELS = 32_000_000
HASH_ID = re.compile(r'^[0-9a-f]{64}$')


def _read_only_connection(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise AIError('operational_source_unavailable')
    try:
        connection = sqlite3.connect(database_path.resolve().as_uri() + '?mode=ro', uri=True)
    except sqlite3.Error:
        raise AIError('operational_source_unavailable') from None
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA query_only = ON')
    return connection


def import_history_eye(
    store: ExperimentStore,
    *,
    database_path: str | os.PathLike,
    image_root: str | os.PathLike,
    history_id: int,
    selected_eye: str,
    permission_ref: str,
    retention_policy_ref: str,
    retention_until: str,
    split: str,
) -> tuple[dict, bool]:
    """Copy only the selected canonical ROI; never copy predictions or the full frame."""
    if not store.allow_real_data:
        raise AIError('real_data_not_allowed')
    if type(history_id) is not int or history_id < 1:
        raise ValueError('invalid history id')
    side = str(selected_eye or '').strip().upper()
    if side not in ('L', 'R'):
        raise ValueError('invalid selected_eye')
    permission_ref = str(permission_ref or '').strip()
    retention_policy_ref = str(retention_policy_ref or '').strip()
    retention_until = str(retention_until or '').strip()
    if not POLICY_REF.fullmatch(permission_ref):
        raise ValueError('invalid permission_ref')
    if not POLICY_REF.fullmatch(retention_policy_ref):
        raise ValueError('invalid retention_policy_ref')
    if split not in ('train', 'validation', 'test', 'holdout', 'prospective'):
        raise ValueError('invalid research split')

    database_path = Path(database_path).resolve()
    image_root = Path(image_root).resolve()
    try:
        connection = _read_only_connection(database_path)
        try:
            row = connection.execute(
                '''SELECT sessions.id AS session_id, sessions.diagnosed_at,
                          sessions.ai_reading_json, users.phone_hash,
                          assets.id AS asset_id, assets.file_path, assets.mime_type,
                          assets.sha256 AS recorded_sha256
                   FROM diagnosis_sessions AS sessions
                   JOIN users ON users.id=sessions.user_id
                   JOIN session_assets AS assets ON assets.id=(
                     SELECT candidate.id FROM session_assets AS candidate
                     WHERE candidate.session_id=sessions.id
                       AND candidate.asset_type='image_raw'
                     ORDER BY candidate.id LIMIT 1
                   )
                   WHERE sessions.id=?''',
                (history_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        raise AIError('operational_source_unavailable') from None
    if row is None:
        raise KeyError('history_not_found')
    patient_group_id = str(row['phone_hash'] or '').lower()
    if not HASH_ID.fullmatch(patient_group_id):
        raise AIError('invalid_operational_identifier')

    source_path = Path(str(row['file_path'] or '')).resolve()
    if image_root != source_path and image_root not in source_path.parents:
        raise AIError('asset_unavailable')
    try:
        size = source_path.stat().st_size
        if size < 1 or size > MAX_SOURCE_BYTES:
            raise AIError('invalid_image')
        source_bytes = source_path.read_bytes()
    except OSError:
        raise AIError('asset_unavailable') from None
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    recorded_digest = str(row['recorded_sha256'] or '').lower()
    if recorded_digest and (
        not re.fullmatch(r'[0-9a-f]{64}', recorded_digest)
        or recorded_digest != source_digest
    ):
        raise AIError('source_digest_mismatch')

    source_record_ref = f'session:{history_id}:asset:{int(row["asset_id"])}'
    existing = store.find_imported_sample(
        SOURCE_SYSTEM, source_record_ref, side, PREPROCESSING_VERSION
    )
    if existing is not None:
        if (
            existing['source_digest'] != source_digest
            or existing['permission_ref'] != permission_ref
            or existing['retention_policy_ref'] != retention_policy_ref
            or existing['retention_until'] != retention_until
            or existing['split'] != split
        ):
            raise AIError('existing_import_mismatch')
        return existing, False

    try:
        analysis = json.loads(row['ai_reading_json'])
        eye = analysis['left_eye' if side == 'L' else 'right_eye']
        bbox = eye['bbox']
        if not isinstance(eye, dict) or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError()
        with Image.open(io.BytesIO(source_bytes)) as image:
            if image.format not in ('JPEG', 'PNG'):
                raise ValueError()
            width, height = image.size
            if width < 8 or height < 8 or width * height > MAX_SOURCE_PIXELS:
                raise ValueError()
            x1, y1, x2, y2 = [int(value) for value in bbox]
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError()
            cropped = image.convert('RGB').crop((x1, y1, x2, y2))
            output = io.BytesIO()
            cropped.save(output, format='JPEG', quality=95, optimize=True)
    except (
        KeyError, TypeError, ValueError, json.JSONDecodeError,
        OSError, UnidentifiedImageError, Image.DecompressionBombError,
    ):
        raise AIError('baseline_unverified') from None

    sample = store.register_sample(output.getvalue(), {
        'patient_group_id': patient_group_id,
        'capture_id': f'operational-session-{history_id}',
        'capture_time': str(row['diagnosed_at']),
        'source_asset_ref': f'operational-image-asset-{int(row["asset_id"])}',
        'source_system': SOURCE_SYSTEM,
        'source_record_ref': source_record_ref,
        'source_digest': source_digest,
        'modality': 'external_eye_webcam',
        'selected_eye': side,
        'laterality_basis': 'stored_analysis_bbox',
        'source_size': [width, height],
        'roi_bbox': [x1, y1, x2, y2],
        'orientation': 'stored_camera_frame',
        'mirrored': False,
        'crop_version': PREPROCESSING_VERSION,
        'preprocessing_version': PREPROCESSING_VERSION,
        'quality_state': 'unreviewed',
        'quality_reasons': [],
        'permission_ref': permission_ref,
        'retention_policy_ref': retention_policy_ref,
        'retention_until': retention_until,
        'split': split,
        'engineering_fixture': False,
        'synthetic': False,
    })
    return sample, True
