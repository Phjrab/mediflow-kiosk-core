"""GPU-free image client and strict output validator for the custom VLM contract."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from utils.ai_config import AIError, VLMConfig
from utils.llm_client import post_json


PROJECT_DIR = Path(__file__).resolve().parents[1]
ROLE_PATH = PROJECT_DIR / 'config' / 'vlm_analysis_role.txt'
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
ALLOWED_LABELS = {'0', '1', '2', '3', '4'}
FORBIDDEN_CONTEXT_KEYS = {
    'label', 'ground_truth', 'prediction', 'predicted_class', 'confidence',
    'probabilities', 'gradcam', 'heatmap', 'diagnosis', 'disease',
}


def _bounded_string(value: Any, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AIError('invalid_output')
    text = value.strip()
    if (not allow_empty and not text) or len(text) > maximum:
        raise AIError('invalid_output')
    return text


def _bounded_strings(value: Any, *, maximum_items: int, maximum_length: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise AIError('invalid_output')
    return [_bounded_string(item, maximum=maximum_length) for item in value]


def validate_analysis(value: Any) -> dict[str, Any]:
    required = {
        'schema_version', 'analysis_status', 'image_quality',
        'visual_observations', 'suggested_label', 'limitations',
        'brief_explanation',
    }
    if not isinstance(value, dict) or set(value) != required:
        raise AIError('invalid_output')
    if value['schema_version'] != '1.0':
        raise AIError('invalid_output')
    status = value['analysis_status']
    if status not in ('assessed', 'abstain', 'unsupported_input'):
        raise AIError('invalid_output')
    quality = value['image_quality']
    if not isinstance(quality, dict) or set(quality) != {'assessable', 'reasons'}:
        raise AIError('invalid_output')
    if type(quality['assessable']) is not bool:
        raise AIError('invalid_output')
    reasons = _bounded_strings(quality['reasons'], maximum_items=8, maximum_length=120)
    observations = _bounded_strings(
        value['visual_observations'], maximum_items=8, maximum_length=300
    )
    limitations = _bounded_strings(value['limitations'], maximum_items=8, maximum_length=300)
    label = value['suggested_label']
    if label is not None:
        label = str(label)
        if label not in ALLOWED_LABELS:
            raise AIError('invalid_output')
    if status != 'assessed' and label is not None:
        raise AIError('invalid_output')
    if status == 'assessed' and (label is None or not quality['assessable']):
        raise AIError('invalid_output')
    return {
        'schema_version': '1.0',
        'analysis_status': status,
        'image_quality': {'assessable': quality['assessable'], 'reasons': reasons},
        'visual_observations': observations,
        'suggested_label': label,
        'limitations': limitations,
        'brief_explanation': _bounded_string(
            value['brief_explanation'], maximum=600
        ),
    }


def _reject_forbidden_context(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).strip().lower() in FORBIDDEN_CONTEXT_KEYS:
                raise AIError('forbidden_context')
            _reject_forbidden_context(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_forbidden_context(nested)


def prepare_image(image_bytes: bytes) -> tuple[bytes, str, tuple[int, int]]:
    if not isinstance(image_bytes, bytes) or not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise AIError('invalid_image')
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in ('JPEG', 'PNG'):
                raise AIError('invalid_image')
            width, height = image.size
            if width < 8 or height < 8 or width * height > MAX_PIXELS:
                raise AIError('invalid_image')
            image.verify()
        with Image.open(io.BytesIO(image_bytes)) as image:
            normalized = ImageOps.exif_transpose(image).convert('RGB')
            output = io.BytesIO()
            normalized.save(output, format='JPEG', quality=95, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AIError('invalid_image') from None
    encoded = output.getvalue()
    if len(encoded) > MAX_IMAGE_BYTES:
        raise AIError('invalid_image')
    return encoded, 'image/jpeg', (normalized.width, normalized.height)


def analyze_eye(
    config: VLMConfig,
    image_bytes: bytes,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = {} if context is None else context
    if not isinstance(context, dict):
        raise AIError('forbidden_context')
    _reject_forbidden_context(context)
    context_json = json.dumps(context, ensure_ascii=False, allow_nan=False)
    if len(context_json.encode('utf-8')) > 8_000:
        raise AIError('context_too_long')
    try:
        role = ROLE_PATH.read_text(encoding='utf-8').strip()
    except OSError:
        raise AIError('misconfigured') from None
    if not role:
        raise AIError('misconfigured')

    image, mime_type, size = prepare_image(image_bytes)
    digest = hashlib.sha256(image).hexdigest()
    response = post_json(config, '/v1/analyze-eye', {
        'model': config.model,
        'max_new_tokens': config.max_new_tokens,
        'prompt_digest': hashlib.sha256(role.encode('utf-8')).hexdigest(),
        'class_mapping': {
            '0': 'conjunctivitis', '1': 'eyelid', '2': 'cataract',
            '3': 'normal', '4': 'uveitis',
        },
        'context': context,
        'image': {
            'mime_type': mime_type,
            'data_base64': base64.b64encode(image).decode('ascii'),
        },
    })
    if response.get('vision_ingested') is not True:
        raise AIError('vision_not_ready')
    analysis = validate_analysis(response.get('analysis'))
    return {
        'analysis': analysis,
        'provenance': {
            'model': config.model,
            'backend': config.backend,
            'input_digest': digest,
            'normalized_mime_type': mime_type,
            'normalized_size': list(size),
            'prompt_digest': hashlib.sha256(role.encode('utf-8')).hexdigest(),
        },
    }
