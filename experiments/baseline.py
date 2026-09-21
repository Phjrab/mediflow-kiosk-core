"""Manual E0 worker for an approved sample already held in the research store."""
from __future__ import annotations

import hashlib
import os
import time
from typing import Any

from experiments.store import ExperimentStore
from utils.ai_config import AIError
from utils.gradcam_policy import gradcam_mode, gradcam_result_state, should_generate_gradcam


def validate_baseline_mode(env: dict[str, str]) -> None:
    if env.get('AI_EXPERIMENTS_ENABLED', '0') != '1':
        raise AIError('disabled')
    if env.get('BASELINE_EXPERIMENTS_ENABLED', '0') != '1':
        raise AIError('disabled')
    if env.get('AI_EXPERIMENT_MODE', 'shadow') != 'shadow':
        raise AIError('misconfigured')
    gradcam_mode(env.get('GRADCAM_MODE', 'always'))


def _classifier_result(store: ExperimentStore, job: dict[str, Any], classifier, env) -> dict[str, Any]:
    import cv2

    sample = store.get_sample(job['sample_id'])
    path = store.sample_image_path(job['sample_id'])
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise AIError('invalid_image')
    mode = gradcam_mode(env.get('GRADCAM_MODE', 'always'))
    details = classifier.classify_with_details(
        image,
        generate_cam=should_generate_gradcam(mode),
    )
    label = str(details.get('class'))
    probabilities = details.get('probabilities')
    confidence = details.get('confidence')
    if label not in {'0', '1', '2', '3', '4'}:
        raise AIError('invalid_output')
    if not isinstance(probabilities, list) or len(probabilities) != 5:
        raise AIError('invalid_output')
    try:
        probabilities = [float(value) for value in probabilities]
        confidence = float(confidence)
    except (TypeError, ValueError):
        raise AIError('invalid_output') from None
    if any(value < 0 or value > 1 for value in probabilities) or not 0 <= confidence <= 1:
        raise AIError('invalid_output')

    heatmap = details.get('heatmap_image')
    artifact_ref = None
    if heatmap is not None:
        encoded_ok, encoded = cv2.imencode('.jpg', heatmap)
        if not encoded_ok:
            raise AIError('artifact_write_failed')
        artifact_ref = store.write_artifact(job['job_id'], 'gradcam.jpg', encoded.tobytes())

    return {
        'analysis': {
            'schema_version': '1.0',
            'analysis_status': 'assessed',
            'image_quality': {'assessable': True, 'reasons': []},
            'visual_observations': [],
            'suggested_label': label,
            'limitations': ['기존 EfficientNet 기준선 분류 결과이며 확진이 아닙니다.'],
            'brief_explanation': '승인된 연구 샘플에 기존 분류 기준선을 실행했습니다.',
        },
        'provenance': {
            'backend': 'existing_efficientnet_baseline',
            'input_digest': sample['roi_digest'],
            'input_file_digest': hashlib.sha256(path.read_bytes()).hexdigest(),
            'confidence_fraction': confidence,
            'probabilities': probabilities,
            'gradcam_status': gradcam_result_state(mode, heatmap is not None),
            'gradcam_artifact_ref': artifact_ref,
        },
    }


def process_baseline_one(
    store: ExperimentStore,
    env: dict[str, str] | None = None,
    *,
    classifier=None,
) -> bool:
    env = dict(os.environ) if env is None else env
    validate_baseline_mode(env)
    job = store.claim_next(('E0_baseline',))
    if job is None:
        return False
    started = time.monotonic()
    try:
        if classifier is None:
            from modules.classifier import DiseaseClassifier
            classifier = DiseaseClassifier()
        result = _classifier_result(store, job, classifier, env)
        store.finish(
            job['job_id'], job['lease_token'], result,
            duration_ms=(time.monotonic() - started) * 1000,
        )
    except AIError as exc:
        store.fail(job['job_id'], job['lease_token'], exc.code)
    except Exception:
        store.fail(job['job_id'], job['lease_token'], 'baseline_worker_error')
    return True
