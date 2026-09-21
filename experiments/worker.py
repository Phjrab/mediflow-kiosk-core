"""Single-slot persistent VLM worker. Importing this module loads no GPU model."""
from __future__ import annotations

import json
import os
import time

from experiments.store import ExperimentStore
from utils.ai_config import AIError, VLMConfig
from utils.vlm_client import analyze_eye


def store_from_env(env=None) -> ExperimentStore:
    env = dict(os.environ) if env is None else env
    data_dir = env.get('EXPERIMENT_DATA_DIR', '').strip()
    if not data_dir:
        raise AIError('misconfigured')
    try:
        queue_max = int(env.get('EXPERIMENT_QUEUE_MAX', '16'))
    except ValueError:
        raise AIError('misconfigured') from None
    return ExperimentStore(
        data_dir,
        queue_max=queue_max,
        allow_real_data=env.get('EXPERIMENT_ALLOW_REAL_DATA', '0') == '1',
    )


def validate_worker_mode(env) -> None:
    if env.get('VLM_ENABLED', '0') != '1' or env.get('AI_EXPERIMENTS_ENABLED', '0') != '1':
        raise AIError('disabled')
    if env.get('AI_EXPERIMENT_MODE', 'shadow') != 'shadow':
        raise AIError('misconfigured')
    if env.get('AI_DEPLOYMENT_PROFILE', 'chat_only') not in ('vlm_only', 'co_resident_verified'):
        raise AIError('profile_unavailable')


def process_one(store: ExperimentStore, env=None) -> bool:
    env = dict(os.environ) if env is None else env
    validate_worker_mode(env)
    arm_ids = ['E1_vlm_image']
    if env.get('SURVEY_VLM_EXPERIMENTS_ENABLED', '0') == '1':
        arm_ids.append('E2_vlm_survey')
    job = store.claim_next(tuple(arm_ids))
    if job is None:
        return False
    started = time.monotonic()
    try:
        run = store.get_run(job['run_id'])
        image = store.sample_image_path(job['sample_id']).read_bytes()
        context = {}
        survey = None
        if run['arm_id'] == 'E2_vlm_survey':
            from experiments.survey import validate_run_config

            validate_run_config(json.loads(run['config_json']))
            survey = store.get_survey(job['sample_id'])
            context = {'survey': survey['responses']}
        result = analyze_eye(VLMConfig.from_env(env), image, context=context)
        if survey is not None:
            result.setdefault('provenance', {})['survey_digest'] = survey['response_digest']
            result['provenance']['survey_schema_version'] = survey['schema_version']
        store.finish(
            job['job_id'],
            job['lease_token'],
            result,
            duration_ms=(time.monotonic() - started) * 1000,
        )
    except AIError as exc:
        store.fail(
            job['job_id'], job['lease_token'], exc.code,
            timed_out=exc.code == 'request_timeout',
        )
    except Exception:
        store.fail(job['job_id'], job['lease_token'], 'worker_error')
    return True


def run_forever(store: ExperimentStore, env=None, poll_seconds: float = 1.0) -> None:
    env = dict(os.environ) if env is None else env
    validate_worker_mode(env)
    store.recover_interrupted()
    while True:
        if not process_one(store, env):
            time.sleep(poll_seconds)
