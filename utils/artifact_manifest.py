"""Strict, offline verification for pinned local AI artifacts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
REVISION_RE = re.compile(r'^[0-9a-f]{40}$')
ALLOWED_COMPONENTS = frozenset({'general_llm', 'medgemma_source', 'medgemma_gguf'})


def load_candidates(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('schema_version') != 1:
        raise ValueError('invalid_manifest_schema')
    artifacts = payload.get('artifacts')
    if not isinstance(artifacts, dict) or not ALLOWED_COMPONENTS.issubset(artifacts):
        raise ValueError('invalid_manifest_artifacts')
    for name in ALLOWED_COMPONENTS:
        artifact = artifacts[name]
        if not isinstance(artifact, dict) or not REVISION_RE.fullmatch(str(artifact.get('revision', ''))):
            raise ValueError('invalid_manifest_revision')
        files = artifact.get('files')
        if not isinstance(files, list) or not files:
            raise ValueError('invalid_manifest_files')
        seen: set[str] = set()
        for item in files:
            if not isinstance(item, dict) or set(item) != {'path', 'size', 'sha256'}:
                raise ValueError('invalid_manifest_file')
            relative = Path(str(item['path']))
            if relative.is_absolute() or len(relative.parts) != 1 or relative.name in seen:
                raise ValueError('invalid_manifest_path')
            seen.add(relative.name)
            if not isinstance(item['size'], int) or item['size'] <= 0:
                raise ValueError('invalid_manifest_size')
            if not SHA256_RE.fullmatch(str(item['sha256'])):
                raise ValueError('invalid_manifest_sha256')
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_component(manifest_path: Path, component: str, root: Path) -> dict[str, Any]:
    if component not in ALLOWED_COMPONENTS:
        raise ValueError('invalid_component')
    payload = load_candidates(manifest_path)
    if root.is_symlink():
        raise ValueError('invalid_artifact_root')
    base = root.resolve(strict=True)
    if not base.is_dir():
        raise ValueError('invalid_artifact_root')
    results = []
    for expected in payload['artifacts'][component]['files']:
        candidate = base / expected['path']
        if candidate.is_symlink():
            raise ValueError('artifact_symlink_rejected')
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError('artifact_missing') from exc
        if resolved.parent != base or not resolved.is_file():
            raise ValueError('artifact_path_escape')
        size = resolved.stat().st_size
        digest = _sha256(resolved)
        if size != expected['size']:
            raise ValueError('artifact_size_mismatch')
        if digest != expected['sha256']:
            raise ValueError('artifact_digest_mismatch')
        results.append({'path': expected['path'], 'size': size, 'sha256': digest})
    artifact = payload['artifacts'][component]
    return {
        'status': 'VERIFIED',
        'component': component,
        'origin_model': artifact['origin_model'],
        'revision': artifact['revision'],
        'files': results,
    }
