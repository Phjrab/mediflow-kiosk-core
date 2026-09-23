#!/usr/bin/env python3
"""Manage the isolated experiment store and worker without touching operational DB."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.worker import process_one, run_forever, store_from_env  # noqa: E402
from experiments.store import PURGE_CONFIRMATION  # noqa: E402
from experiments.baseline import process_baseline_one  # noqa: E402
from experiments.explanation import process_explanation_one  # noqa: E402
from experiments.hybrid import process_hybrid_one  # noqa: E402
from utils.ai_config import AIError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        '--explicit-env', action='store_true',
        help='use only the current process environment; do not load the project .env',
    )
    commands = result.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    fixture = commands.add_parser('register-fixture')
    fixture.add_argument('--image', required=True)
    fixture.add_argument('--patient-group-id', required=True)
    fixture.add_argument('--capture-id', required=True)
    fixture.add_argument('--source-asset-ref', required=True)
    fixture.add_argument('--selected-eye', choices=('L', 'R', 'unknown'), default='unknown')
    create_run = commands.add_parser('create-run')
    create_run.add_argument('--arm', required=True)
    create_run.add_argument('--model-manifest', required=True)
    create_run.add_argument('--config', required=True)
    create_run.add_argument('--repeat-index', type=int, default=0)
    create_run.add_argument('--engineering-fixture', action='store_true')
    label = commands.add_parser('add-reference-label')
    label.add_argument('--sample-id', required=True)
    label.add_argument('--label', choices=('0', '1', '2', '3', '4'), required=True)
    label.add_argument('--source', required=True)
    worker = commands.add_parser('worker')
    worker.add_argument('--once', action='store_true')
    commands.add_parser('baseline-once')
    commands.add_parser('explanation-once')
    commands.add_parser('hybrid-once')
    survey = commands.add_parser('add-survey')
    survey.add_argument('--sample-id', required=True)
    survey.add_argument('--responses', required=True)
    survey.add_argument('--source', required=True)
    commands.add_parser('retention-status')
    purge = commands.add_parser('retention-purge')
    purge.add_argument('--sample-id', action='append', required=True)
    purge.add_argument('--confirm', required=True, help=f'must equal {PURGE_CONFIRMATION}')
    enqueue = commands.add_parser('enqueue')
    enqueue.add_argument('--sample-id', required=True)
    enqueue.add_argument('--run-id', required=True)
    status = commands.add_parser('status')
    status.add_argument('--job-id', required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if not args.explicit_env:
            try:
                from dotenv import load_dotenv
            except ModuleNotFoundError as exc:
                if exc.name != 'dotenv':
                    raise
                raise AIError('missing_dotenv') from None
            load_dotenv(PROJECT_ROOT / '.env')
        store = store_from_env()
        if args.command == 'init':
            print(json.dumps({'status': 'ok', 'db': str(store.db_path)}))
        elif args.command == 'register-fixture':
            sample = store.register_sample(Path(args.image).read_bytes(), {
                'patient_group_id': args.patient_group_id,
                'capture_id': args.capture_id,
                'source_asset_ref': args.source_asset_ref,
                'modality': 'external_eye_webcam',
                'selected_eye': args.selected_eye,
                'laterality_basis': 'engineering_fixture',
                'engineering_fixture': True,
                'synthetic': True,
                'split': 'engineering_fixture',
            })
            print(json.dumps({'status': 'ok', 'sample_id': sample['sample_id']}))
        elif args.command == 'create-run':
            model_manifest = json.loads(Path(args.model_manifest).read_text(encoding='utf-8'))
            config_snapshot = json.loads(Path(args.config).read_text(encoding='utf-8'))
            run = store.create_run(
                args.arm,
                config_snapshot,
                model_manifest,
                repeat_index=args.repeat_index,
                engineering_fixture=args.engineering_fixture,
            )
            print(json.dumps({'status': 'ok', 'run_id': run['run_id']}))
        elif args.command == 'add-reference-label':
            store.add_reference_label(args.sample_id, args.label, args.source)
            print(json.dumps({'status': 'ok', 'sample_id': args.sample_id}))
        elif args.command == 'add-survey':
            responses = json.loads(Path(args.responses).read_text(encoding='utf-8'))
            survey = store.set_survey(args.sample_id, responses, args.source)
            print(json.dumps({
                'status': 'ok', 'sample_id': args.sample_id,
                'schema_version': survey['schema_version'],
                'response_digest': survey['response_digest'],
            }))
        elif args.command == 'enqueue':
            job, created = store.enqueue(args.sample_id, args.run_id)
            print(json.dumps({'status': 'ok', 'created': created, 'job_id': job['job_id']}))
        elif args.command == 'status':
            job = store.get_job(args.job_id)
            print(json.dumps({
                'status': 'ok', 'job_id': job['job_id'],
                'job_status': job['state'], 'error_code': job['error_code'],
            }))
        elif args.command == 'baseline-once':
            print(json.dumps({'status': 'ok', 'processed': process_baseline_one(store)}))
        elif args.command == 'explanation-once':
            print(json.dumps({'status': 'ok', 'processed': process_explanation_one(store)}))
        elif args.command == 'hybrid-once':
            print(json.dumps({'status': 'ok', 'processed': process_hybrid_one(store)}))
        elif args.command == 'retention-status':
            print(json.dumps({'status': 'ok', **store.retention_status()}))
        elif args.command == 'retention-purge':
            print(json.dumps({
                'status': 'ok',
                **store.purge_expired(args.sample_id, confirmation=args.confirm),
            }))
        elif args.once:
            print(json.dumps({'status': 'ok', 'processed': process_one(store)}))
        else:
            run_forever(store)
        return 0
    except (AIError, ValueError, KeyError, OSError) as exc:
        code = exc.code if isinstance(exc, AIError) else type(exc).__name__.lower()
        print(json.dumps({'status': 'error', 'error_code': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
