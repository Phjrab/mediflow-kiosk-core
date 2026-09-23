#!/usr/bin/env python3
"""Read-only preflight for local LLM/VLM research configuration and CUDA compatibility."""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')

from utils.ai_config import AIError, LocalConfig, VLMConfig, provider_from  # noqa: E402


def report(state: str, label: str, detail: str) -> None:
    print(f'{state}: {label}: {detail}')


def main() -> int:
    failures = 0
    env = dict(os.environ)
    report('INFO', 'host', f'architecture={platform.machine()} python={platform.python_version()}')
    try:
        provider = provider_from(env)
        if provider == 'local':
            config = LocalConfig.from_env(env)
            report('PASS', 'local LLM config', f'host={config.host} port={config.port}; generation NOT_RUN')
        else:
            report('INFO', 'chat provider', f'provider={provider}; external request NOT_RUN')
    except AIError as exc:
        report('SKIP', 'chat config', exc.code)

    experiments = env.get('AI_EXPERIMENTS_ENABLED', '0') == '1'
    vlm = env.get('VLM_ENABLED', '0') == '1'
    if experiments or vlm:
        try:
            config = VLMConfig.from_env(env)
            report('PASS', 'VLM config', f'host={config.host} port={config.port}; image request NOT_RUN')
        except AIError as exc:
            report('FAIL', 'VLM config', exc.code)
            failures += 1
    else:
        report('SKIP', 'VLM config', 'disabled by default')

    data_dir = env.get('EXPERIMENT_DATA_DIR', '').strip()
    if data_dir:
        path = Path(data_dir)
        public = (PROJECT_ROOT / 'web' / 'static').resolve()
        if not path.is_absolute() or path.resolve() == public or public in path.resolve().parents:
            report('FAIL', 'experiment data dir', 'must be absolute and outside web/static')
            failures += 1
        else:
            report('PASS', 'experiment data dir', 'configured outside public assets')
    else:
        report('SKIP', 'experiment data dir', 'not configured')

    try:
        import torch
        version = str(torch.__version__)
        cuda = str(torch.version.cuda)
        if not torch.cuda.is_available():
            raise RuntimeError(f'CUDA unavailable torch={version} torch_cuda={cuda}')
        probe = (torch.ones(4, device='cuda') * 2).sum()
        torch.cuda.synchronize()
        if float(probe.cpu()) != 8:
            raise RuntimeError('unexpected tensor result')
        report('PASS', 'CUDA tensor', f'torch={version} torch_cuda={cuda} device={torch.cuda.get_device_name(0)}')
    except Exception as exc:
        report('FAIL', 'CUDA tensor', f'{type(exc).__name__}: {exc}')
        failures += 1

    print(f'OVERALL: {"NOT READY" if failures else "READY"}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
