"""Deterministic E4 comparison worker; it reads no image and chooses no diagnosis."""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from typing import Any

from experiments.store import ExperimentStore, canonical_json
from utils.ai_config import AIError
from utils.vlm_client import validate_analysis


RULE_ID = 'paired-review-v1'
SCHEMA_VERSION = 'hybrid-review-1.0'


def _run_id(value: Any, field: str) -> str:
    text = str(value or '')
    if len(text) != 32 or any(char not in '0123456789abcdef' for char in text):
        raise ValueError(f'invalid E4 {field}')
    return text


def validate_run_config(value: Any) -> dict[str, str]:
    required = {'baseline_run_id', 'vlm_run_id', 'rule_id'}
    if not isinstance(value, dict) or set(value) != required or value.get('rule_id') != RULE_ID:
        raise ValueError('invalid E4 configuration')
    return {
        'baseline_run_id': _run_id(value.get('baseline_run_id'), 'baseline run'),
        'vlm_run_id': _run_id(value.get('vlm_run_id'), 'VLM run'),
        'rule_id': RULE_ID,
    }


def _summary(source: Mapping[str, Any]) -> dict[str, Any]:
    analysis = validate_analysis(source.get('result', {}).get('analysis'))
    return {
        'arm_id': str(source['arm_id']),
        'analysis_status': analysis['analysis_status'],
        'suggested_label': analysis['suggested_label'],
    }


def build_review(baseline: Mapping[str, Any], vlm: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    base = _summary(baseline)
    vision = _summary(vlm)
    if base['arm_id'] != 'E0_baseline' or vision['arm_id'] not in {'E1_vlm_image', 'E2_vlm_survey'}:
        raise AIError('source_result_unavailable')
    if base['analysis_status'] != 'assessed':
        outcome, reason, manual = 'not_comparable', 'baseline_not_assessed', True
    elif vision['analysis_status'] != 'assessed':
        outcome, reason, manual = 'not_comparable', f"vlm_{vision['analysis_status']}", True
    elif base['suggested_label'] == vision['suggested_label']:
        outcome, reason, manual = 'agreement', 'labels_match', False
    else:
        outcome, reason, manual = 'disagreement', 'labels_differ', True
    review = {
        'schema_version': SCHEMA_VERSION,
        'rule_id': RULE_ID,
        'outcome': outcome,
        'reason': reason,
        'manual_review_required': manual,
        'agreement_is_accuracy': False,
        'user_result_action': 'none',
        'baseline': base,
        'vlm': vision,
    }
    digest_payload = canonical_json({
        'rule_id': RULE_ID,
        'baseline_result_digest': baseline['result_digest'],
        'vlm_result_digest': vlm['result_digest'],
    })
    return review, hashlib.sha256(digest_payload.encode('utf-8')).hexdigest()


def validate_review(value: Any) -> dict[str, Any]:
    required = {
        'schema_version', 'rule_id', 'outcome', 'reason',
        'manual_review_required', 'agreement_is_accuracy',
        'user_result_action', 'baseline', 'vlm',
    }
    if not isinstance(value, dict) or set(value) != required:
        raise AIError('invalid_output')
    if value.get('schema_version') != SCHEMA_VERSION or value.get('rule_id') != RULE_ID:
        raise AIError('invalid_output')
    if value.get('outcome') not in {'agreement', 'disagreement', 'not_comparable'}:
        raise AIError('invalid_output')
    if type(value.get('manual_review_required')) is not bool:
        raise AIError('invalid_output')
    if value.get('agreement_is_accuracy') is not False or value.get('user_result_action') != 'none':
        raise AIError('invalid_output')
    if not isinstance(value.get('reason'), str) or not value['reason'] or len(value['reason']) > 100:
        raise AIError('invalid_output')
    baseline = value.get('baseline')
    vlm = value.get('vlm')
    expected_keys = {'arm_id', 'analysis_status', 'suggested_label'}
    if not isinstance(baseline, dict) or not isinstance(vlm, dict):
        raise AIError('invalid_output')
    if set(baseline) != expected_keys or set(vlm) != expected_keys:
        raise AIError('invalid_output')
    if baseline['arm_id'] != 'E0_baseline' or vlm['arm_id'] not in {'E1_vlm_image', 'E2_vlm_survey'}:
        raise AIError('invalid_output')
    for item in (baseline, vlm):
        if item['analysis_status'] not in {'assessed', 'abstain', 'unsupported_input'}:
            raise AIError('invalid_output')
        label = item['suggested_label']
        if item['analysis_status'] == 'assessed':
            if label not in {'0', '1', '2', '3', '4'}:
                raise AIError('invalid_output')
        elif label is not None:
            raise AIError('invalid_output')
    return value


def validate_mode(env: dict[str, str]) -> None:
    if env.get('AI_EXPERIMENTS_ENABLED', '0') != '1' or env.get('HYBRID_REVIEW_EXPERIMENTS_ENABLED', '0') != '1':
        raise AIError('disabled')
    if env.get('AI_EXPERIMENT_MODE', 'shadow') != 'shadow':
        raise AIError('misconfigured')
    if env.get('AI_DEPLOYMENT_PROFILE', 'chat_only') not in {
        'chat_only', 'vlm_only', 'co_resident_verified'
    }:
        raise AIError('profile_unavailable')


def process_hybrid_one(store: ExperimentStore, env: dict[str, str] | None = None) -> bool:
    env = dict(os.environ) if env is None else env
    validate_mode(env)
    job = store.claim_next(('E4_hybrid_review',))
    if job is None:
        return False
    started = time.monotonic()
    try:
        run = store.get_run(job['run_id'])
        config = validate_run_config(json.loads(run['config_json']))
        baseline = store.get_prediction_for_sample_run(
            job['sample_id'], config['baseline_run_id'], required_arm='E0_baseline'
        )
        vlm = store.get_prediction_for_sample_run(job['sample_id'], config['vlm_run_id'])
        if vlm['arm_id'] not in {'E1_vlm_image', 'E2_vlm_survey'}:
            raise AIError('source_result_unavailable')
        review, input_digest = build_review(baseline, vlm)
        store.finish_hybrid(
            job['job_id'], job['lease_token'],
            baseline_prediction_id=baseline['prediction_id'],
            baseline_result_digest=baseline['result_digest'],
            vlm_prediction_id=vlm['prediction_id'],
            vlm_result_digest=vlm['result_digest'],
            input_digest=input_digest,
            review=review,
            duration_ms=(time.monotonic() - started) * 1000,
        )
    except AIError as exc:
        store.fail(job['job_id'], job['lease_token'], exc.code)
    except Exception:
        store.fail(job['job_id'], job['lease_token'], 'hybrid_worker_error')
    return True
