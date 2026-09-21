#!/usr/bin/env python3
"""Isolated MedGemma custom service for Jetson B/C; never imported by kiosk A."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import Flask, jsonify, request
from PIL import Image, ImageOps, UnidentifiedImageError
from utils.ai_config import AIError, secret
from utils.runtime_receipt import validate_runtime_expectation


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
EXPECTED_MODEL_ID = 'google/medgemma-1.5-4b-it'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROLE_PATH = PROJECT_ROOT / 'config' / 'vlm_analysis_role.txt'
FORBIDDEN_CONTEXT_KEYS = {
    'label', 'ground_truth', 'prediction', 'predicted_class', 'confidence',
    'probabilities', 'gradcam', 'heatmap', 'diagnosis', 'disease',
}
ANALYSIS_JSON_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': [
        'schema_version', 'analysis_status', 'image_quality',
        'visual_observations', 'suggested_label', 'limitations',
        'brief_explanation',
    ],
    'properties': {
        'schema_version': {'const': '1.0'},
        'analysis_status': {
            'enum': ['assessed', 'abstain', 'unsupported_input'],
        },
        'image_quality': {
            'type': 'object',
            'additionalProperties': False,
            'required': ['assessable', 'reasons'],
            'properties': {
                'assessable': {'type': 'boolean'},
                'reasons': {
                    'type': 'array', 'maxItems': 8,
                    'items': {'type': 'string', 'maxLength': 120},
                },
            },
        },
        'visual_observations': {
            'type': 'array', 'maxItems': 8,
            'items': {'type': 'string', 'maxLength': 300},
        },
        'suggested_label': {
            'anyOf': [
                {'enum': ['0', '1', '2', '3', '4']},
                {'type': 'null'},
            ],
        },
        'limitations': {
            'type': 'array', 'maxItems': 8,
            'items': {'type': 'string', 'maxLength': 300},
        },
        'brief_explanation': {'type': 'string', 'maxLength': 600},
    },
}

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
generation_slot = threading.BoundedSemaphore(1)
runtime = {
    'backend': None,
    'model': None,
    'processor': None,
    'manifest': None,
    'device_map': None,
    'cli': None,
}


def _secret() -> str:
    try:
        return secret(os.environ, 'MEDGEMMA')
    except AIError:
        raise RuntimeError('MEDGEMMA API key is misconfigured') from None


def _authorized() -> bool:
    supplied = request.headers.get('Authorization', '')
    return hmac.compare_digest(supplied, 'Bearer ' + _secret())


def _runtime_receipt(prompt_digest: str) -> dict:
    try:
        expectation = validate_runtime_expectation({
            'node_id': os.environ['AI_CONTROL_NODE_ID'],
            'artifact_id': os.environ['AI_CONTROL_ARTIFACT_ID'],
            'artifact_manifest_digest': os.environ['AI_CONTROL_ARTIFACT_MANIFEST_DIGEST'],
            'runtime_revision': os.environ['AI_CONTROL_RUNTIME_REVISION'],
            'config_revision': int(os.environ['AI_CONTROL_CONFIG_REVISION']),
            'deployment_generation': int(os.environ['AI_CONTROL_DEPLOYMENT_GENERATION']),
            'effective_config_digest': os.environ['AI_CONTROL_EFFECTIVE_CONFIG_DIGEST'],
        })
    except (KeyError, ValueError, AIError):
        raise AIError('configuration_drift') from None
    return {**expectation, 'prompt_digest': prompt_digest}


def _load_manifest() -> dict:
    manifest_path = Path(os.environ['MEDGEMMA_MODEL_MANIFEST'])
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    required = {'origin_model', 'revision', 'runtime', 'dtype', 'quantization'}
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise RuntimeError('model manifest is incomplete')
    if payload['origin_model'] != EXPECTED_MODEL_ID or not str(payload['revision']).strip():
        raise RuntimeError('model manifest origin/revision is invalid')
    return payload


def _required_regular_file(name: str, *, executable: bool = False) -> Path:
    raw = os.getenv(name, '').strip()
    if not raw:
        raise RuntimeError(f'{name} is required')
    path = Path(raw).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise RuntimeError(f'{name} must name an absolute regular non-symlink file')
    if executable and not os.access(path, os.X_OK):
        raise RuntimeError(f'{name} must be executable')
    return path.resolve(strict=True)


def _load_llama_cpp_runtime(manifest: dict) -> None:
    binary = _required_regular_file('MEDGEMMA_LLAMA_CPP_BIN', executable=True)
    model = _required_regular_file('MEDGEMMA_GGUF_MODEL')
    mmproj = _required_regular_file('MEDGEMMA_GGUF_MMPROJ')
    if str(manifest.get('quantization', '')).upper() != 'Q4_K_M':
        raise RuntimeError('llama.cpp manifest must declare Q4_K_M')
    revision = str(manifest.get('runtime_revision', '')).strip()
    if len(revision) != 40 or any(char not in '0123456789abcdef' for char in revision):
        raise RuntimeError('llama.cpp runtime revision is invalid')
    version = subprocess.run(
        [str(binary), '--version'],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    version_text = (version.stdout + '\n' + version.stderr).lower()
    if version.returncode != 0 or revision[:9] not in version_text:
        raise RuntimeError('llama.cpp binary revision mismatch')
    runtime.update(
        backend='llama_cpp_cli',
        model=str(model),
        processor=str(mmproj),
        manifest=manifest,
        device_map=['cuda:0:text', 'cpu:mmproj'],
        cli=str(binary),
    )


def load_runtime() -> None:
    """Load an approved local runtime without network acquisition or silent fallback."""
    manifest = _load_manifest()
    backend = os.getenv('MEDGEMMA_RUNTIME', 'transformers').strip().lower()
    if backend == 'llama_cpp_cli':
        _load_llama_cpp_runtime(manifest)
        return
    if backend != 'transformers':
        raise RuntimeError('unsupported MEDGEMMA_RUNTIME')
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; CPU fallback is not allowed')
    model_dir = Path(os.environ['MEDGEMMA_MODEL_DIR']).resolve(strict=True)
    processor = AutoProcessor.from_pretrained(model_dir, local_files_only=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_dir,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        device_map='auto',
    )
    device_map = getattr(model, 'hf_device_map', None)
    if device_map:
        placements = {str(value) for value in device_map.values()}
    else:
        placements = {str(next(model.parameters()).device)}
    if not placements or any(not value.startswith('cuda') for value in placements):
        raise RuntimeError(f'non-CUDA model placement rejected: {sorted(placements)}')
    probe = (torch.ones(4, device='cuda') * 2).sum()
    torch.cuda.synchronize()
    if float(probe.cpu()) != 8:
        raise RuntimeError('CUDA tensor probe failed')
    runtime.update(
        backend='transformers',
        model=model,
        processor=processor,
        manifest=manifest,
        device_map=sorted(placements),
    )


def _parse_json_output(text: str) -> dict:
    candidate = text.strip()
    start = candidate.find('{')
    if start < 0:
        raise ValueError('invalid_model_output')
    value, offset = json.JSONDecoder().raw_decode(candidate[start:])
    if candidate[start + offset:].strip() or not isinstance(value, dict):
        raise ValueError('invalid_model_output')
    return value


def _parse_process_json_output(stdout: str, stderr: str) -> dict:
    """Accept llama.cpp's JSON channel without merging diagnostic streams."""
    for candidate in (stdout, stderr):
        if not candidate.strip():
            continue
        try:
            return _parse_json_output(candidate)
        except (ValueError, json.JSONDecodeError):
            continue
    raise ValueError('invalid_model_output')


def _llama_cpp_generate(image: Image.Image, prompt: str, max_new_tokens: int) -> dict:
    timeout_seconds = int(os.getenv('MEDGEMMA_GENERATION_TIMEOUT_SECONDS', '180'))
    if not 30 <= timeout_seconds <= 600:
        raise RuntimeError('MEDGEMMA_GENERATION_TIMEOUT_SECONDS must be between 30 and 600')
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix='medgemma-', suffix='.png', delete=False) as handle:
            temporary_path = Path(handle.name)
            image.save(handle, format='PNG')
        os.chmod(temporary_path, 0o600)
        command = [
            runtime['cli'], '--offline',
            '-m', runtime['model'], '--mmproj', runtime['processor'],
            '--image', str(temporary_path), '-p', prompt,
            '--temp', '0', '-n', str(max_new_tokens),
            '-c', '2048', '-b', '512', '-ub', '512',
            '-ctk', 'q8_0', '-ctv', 'q8_0',
            '-ngl', 'all', '--fit', 'on', '--fit-target', '1024',
            '--no-mmproj-offload', '--image-max-tokens', '256',
            '--json-schema', json.dumps(ANALYSIS_JSON_SCHEMA, separators=(',', ':')),
        ]
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError('llama.cpp generation failed')
        # llama-mtmd-cli has emitted generated text on either stream across
        # revisions/build modes. Keep them separate so diagnostics cannot be
        # mistaken for a model response, then accept the first strict JSON body.
        return _parse_process_json_output(result.stdout, result.stderr)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _decode_image(data: str) -> Image.Image:
    try:
        raw = base64.b64decode(data, validate=True)
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG', 'PNG'):
                raise ValueError()
            width, height = source.size
            if width < 8 or height < 8 or width * height > MAX_PIXELS:
                raise ValueError()
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            return ImageOps.exif_transpose(source).convert('RGB')
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ValueError('invalid_image') from None


def _reject_forbidden_context(value) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).strip().lower() in FORBIDDEN_CONTEXT_KEYS:
                raise ValueError('forbidden_context')
            _reject_forbidden_context(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_forbidden_context(nested)


@app.get('/healthz')
def healthz():
    return jsonify({'status': 'alive'})


@app.get('/readyz')
def readyz():
    if not _authorized():
        return jsonify({'status': 'unauthorized'}), 401
    ready = runtime['model'] is not None and runtime['processor'] is not None
    return jsonify({
        'status': 'ready' if ready else 'loading',
        'vision_ready': ready,
        'model': EXPECTED_MODEL_ID if ready else None,
        'device_placements': runtime['device_map'] if ready else [],
    }), 200 if ready else 503


@app.post('/v1/analyze-eye')
def analyze_eye():
    if not _authorized():
        return jsonify({'status': 'unauthorized'}), 401
    if runtime['model'] is None:
        return jsonify({'status': 'loading'}), 503
    if not generation_slot.acquire(blocking=False):
        return jsonify({'status': 'busy'}), 429
    try:
        payload = request.get_json(silent=True)
        required = {'model', 'max_new_tokens', 'prompt_digest', 'class_mapping', 'context', 'image'}
        if not isinstance(payload, dict) or set(payload) not in (required, required | {'expected_runtime'}):
            raise ValueError('invalid_request')
        if payload['model'] != EXPECTED_MODEL_ID:
            return jsonify({'status': 'model_not_found'}), 404
        image_payload = payload['image']
        if not isinstance(image_payload, dict) or set(image_payload) != {'mime_type', 'data_base64'}:
            raise ValueError('invalid_image')
        if image_payload['mime_type'] not in ('image/jpeg', 'image/png'):
            raise ValueError('invalid_image')
        image = _decode_image(image_payload['data_base64'])
        max_new_tokens = int(payload['max_new_tokens'])
        if not 1 <= max_new_tokens <= 4096:
            raise ValueError('invalid_request')
        role = ROLE_PATH.read_text(encoding='utf-8').strip()
        expected_prompt_digest = hashlib.sha256(role.encode('utf-8')).hexdigest()
        if not role or not hmac.compare_digest(str(payload['prompt_digest']), expected_prompt_digest):
            raise ValueError('prompt_mismatch')
        runtime_receipt = None
        if 'expected_runtime' in payload:
            try:
                expected_runtime = validate_runtime_expectation(payload['expected_runtime'])
                runtime_receipt = _runtime_receipt(expected_prompt_digest)
            except AIError as exc:
                code = 'configuration_drift' if exc.code == 'configuration_drift' else 'invalid_request'
                return jsonify({'status': code}), 409 if code == 'configuration_drift' else 400
            if any(runtime_receipt[key] != value for key, value in expected_runtime.items()):
                return jsonify({'status': 'configuration_drift'}), 409
        _reject_forbidden_context(payload['context'])
        context = json.dumps(payload['context'], ensure_ascii=False, sort_keys=True)
        mapping = json.dumps(payload['class_mapping'], ensure_ascii=False, sort_keys=True)
        prompt = (
            f'{role}\n\nClass mapping: {mapping}\nContext data: {context}\n'
            'Return the required JSON object only.'
        )
        if runtime['backend'] == 'llama_cpp_cli':
            analysis = _llama_cpp_generate(image, prompt, max_new_tokens)
        else:
            messages = [{
                'role': 'user',
                'content': [
                    {'type': 'image', 'image': image},
                    {'type': 'text', 'text': prompt},
                ],
            }]
            processor = runtime['processor']
            model = runtime['model']
            import torch
            inputs = processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors='pt',
            ).to(model.device, dtype=torch.bfloat16)
            if 'pixel_values' not in inputs:
                raise RuntimeError('vision processor output missing')
            input_length = inputs['input_ids'].shape[-1]
            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                )
            decoded = processor.decode(output[0][input_length:], skip_special_tokens=True)
            analysis = json.loads(decoded)
        response = {'vision_ingested': True, 'analysis': analysis}
        if runtime_receipt is not None:
            response['runtime_receipt'] = runtime_receipt
        return jsonify(response)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        app.logger.info('request rejected: %s', type(exc).__name__)
        return jsonify({'status': 'invalid_request'}), 400
    except Exception:
        app.logger.exception('generation failed without request content')
        return jsonify({'status': 'backend_unavailable'}), 503
    finally:
        generation_slot.release()


def main() -> None:
    _secret()
    load_runtime()
    app.run(
        host=os.getenv('MEDGEMMA_HOST', '127.0.0.1'),
        port=int(os.getenv('MEDGEMMA_PORT', '8081')),
        debug=False,
        threaded=True,
    )


if __name__ == '__main__':
    main()
