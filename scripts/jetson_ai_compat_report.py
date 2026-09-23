#!/usr/bin/env python3
"""Emit a bounded, read-only Jetson/L4T/PyTorch compatibility report."""
from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.jetson_compat import classify_runtime, parse_l4t_release  # noqa: E402


MAX_DETAIL = 500
PACKAGE_NAMES = (
    'nvidia-l4t-core',
    'nvidia-jetpack',
    'cuda-toolkit-12-6',
    'libcudnn9',
    'tensorrt',
)


def bounded_error(exc: BaseException) -> str:
    return f'{type(exc).__name__}: {str(exc).replace(chr(10), " ")[:MAX_DETAIL]}'


def read_l4t() -> tuple[str | None, str | None]:
    path = Path('/etc/nv_tegra_release')
    try:
        raw = path.read_text(encoding='utf-8', errors='replace')[:4096]
    except OSError as exc:
        return None, bounded_error(exc)
    return parse_l4t_release(raw), None


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGE_NAMES:
        try:
            result = subprocess.run(
                ['dpkg-query', '-W', '-f=${Version}', name],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            versions[name] = result.stdout.strip()[:MAX_DETAIL] if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            versions[name] = None
    return versions


def distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def torch_observation() -> dict[str, Any]:
    observed: dict[str, Any] = {
        'imported': False,
        'version': None,
        'built_cuda': None,
        'cuda_available': False,
        'device_count': None,
        'device_name': None,
        'error': None,
    }
    try:
        import torch

        observed['imported'] = True
        observed['version'] = str(torch.__version__)
        observed['built_cuda'] = str(torch.version.cuda) if torch.version.cuda else None
        observed['cuda_available'] = bool(torch.cuda.is_available())
        if observed['cuda_available']:
            observed['device_count'] = int(torch.cuda.device_count())
            observed['device_name'] = str(torch.cuda.get_device_name(0))[:MAX_DETAIL]
    except Exception as exc:
        observed['error'] = bounded_error(exc)
    return observed


def build_report() -> dict[str, Any]:
    architecture = platform.machine()
    l4t_release, l4t_error = read_l4t()
    torch = torch_observation()
    compatibility = classify_runtime(
        architecture=architecture,
        l4t_release=l4t_release,
        torch_imported=bool(torch['imported']),
        torch_version=torch['version'],
        torch_cuda=torch['built_cuda'],
        cuda_available=bool(torch['cuda_available']),
    )
    return {
        'schema_version': 1,
        'inspection': 'read_only_no_network_no_model_load',
        'host': {
            'architecture': architecture,
            'python': platform.python_version(),
            'l4t_release': l4t_release,
            'l4t_read_error': l4t_error,
        },
        'packages': package_versions(),
        'python_packages': {
            'transformers': distribution_version('transformers'),
            'accelerate': distribution_version('accelerate'),
        },
        'torch': torch,
        'compatibility': compatibility,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report['compatibility']['state'] == 'READY_CORE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
