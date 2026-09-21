"""E3 local-LLM result explanation worker; it never reads a sample image."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from experiments.store import ExperimentStore, canonical_json
from utils.ai_config import AIError, LocalConfig, provider_from
from utils.llm_client import local_chat
from utils.vlm_client import validate_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = PROJECT_ROOT / 'config' / 'result_explanation_role.txt'
QUESTION_IDS = {
    'explain-result-ko-v1': '이 결과의 의미와 한계를 일반 사용자가 이해할 수 있게 설명하세요.',
}
ALLOWED_PROVENANCE = {'backend', 'confidence_fraction', 'probabilities'}


def role_text() -> str:
    value = ROLE_PATH.read_text(encoding='utf-8').strip()
    if not value or len(value.encode('utf-8')) > 12_000:
        raise AIError('misconfigured')
    return value


def prompt_digest() -> str:
    return hashlib.sha256(role_text().encode('utf-8')).hexdigest()


def validate_run_config(value: dict[str, Any]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {'source_run_id', 'question_id'}:
        raise ValueError('invalid E3 configuration')
    source_run_id = str(value.get('source_run_id') or '')
    question_id = str(value.get('question_id') or '')
    if len(source_run_id) != 32 or any(char not in '0123456789abcdef' for char in source_run_id):
        raise ValueError('invalid E3 source run')
    if question_id not in QUESTION_IDS:
        raise ValueError('invalid E3 question')
    return {'source_run_id': source_run_id, 'question_id': question_id}


def build_input(source_result: dict[str, Any], question_id: str) -> tuple[str, str]:
    analysis = validate_analysis(source_result.get('analysis'))
    provenance = source_result.get('provenance')
    if not isinstance(provenance, dict):
        raise AIError('invalid_output')
    supplied = {
        'analysis_status': analysis['analysis_status'],
        'suggested_label': analysis['suggested_label'],
        'limitations': analysis['limitations'],
        'brief_explanation': analysis['brief_explanation'],
        'model_values': {
            key: provenance[key] for key in sorted(ALLOWED_PROVENANCE) if key in provenance
        },
    }
    serialized = canonical_json(supplied)
    input_digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    message = (
        f'{QUESTION_IDS[question_id]}\n'
        '<BEGIN_UNTRUSTED_RESULT_JSON>\n'
        f'{serialized}\n'
        '<END_UNTRUSTED_RESULT_JSON>'
    )
    return message, input_digest


def validate_mode(env: dict[str, str]) -> None:
    if env.get('AI_EXPERIMENTS_ENABLED', '0') != '1' or env.get('EXPLANATION_EXPERIMENTS_ENABLED', '0') != '1':
        raise AIError('disabled')
    if env.get('AI_EXPERIMENT_MODE', 'shadow') != 'shadow':
        raise AIError('misconfigured')
    if env.get('AI_DEPLOYMENT_PROFILE', 'chat_only') not in ('chat_only', 'co_resident_verified'):
        raise AIError('profile_unavailable')
    if provider_from(env) != 'local':
        raise AIError('unsupported_provider')


def process_explanation_one(
    store: ExperimentStore,
    env: dict[str, str] | None = None,
    *,
    generate: Callable[[LocalConfig, str, str], str] = local_chat,
) -> bool:
    env = dict(os.environ) if env is None else env
    validate_mode(env)
    config = LocalConfig.from_env(env)
    job = store.claim_next(('E3_result_explanation',))
    if job is None:
        return False
    started = time.monotonic()
    try:
        run = store.get_run(job['run_id'])
        run_config = validate_run_config(json.loads(run['config_json']))
        source = store.get_prediction_for_sample_run(
            job['sample_id'], run_config['source_run_id'], required_arm='E0_baseline'
        )
        message, input_digest = build_input(source['result'], run_config['question_id'])
        reply = generate(config, role_text(), message)
        if not isinstance(reply, str) or not reply.strip() or len(reply.strip()) > 6000:
            raise AIError('invalid_output')
        store.finish_explanation(
            job['job_id'],
            job['lease_token'],
            source_prediction_id=source['prediction_id'],
            source_result_digest=source['result_digest'],
            input_digest=input_digest,
            explanation_text=reply.strip(),
            provider='local',
            model=config.model,
            duration_ms=(time.monotonic() - started) * 1000,
        )
    except AIError as exc:
        store.fail(
            job['job_id'], job['lease_token'], exc.code,
            timed_out=exc.code == 'request_timeout',
        )
    except Exception:
        store.fail(job['job_id'], job['lease_token'], 'explanation_worker_error')
    return True
