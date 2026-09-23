"""Pure helpers for reporting Jetson AI runtime compatibility.

The mappings here are deliberately narrow. They cover only the platform family
verified for this project and never select or install a package.
"""
from __future__ import annotations

import re
from typing import Any


_L4T_RELEASE = re.compile(r"\bR(?P<major>\d+)\b.*?\bREVISION:\s*(?P<revision>\d+(?:\.\d+)*)", re.I | re.S)
_VERSION = re.compile(r"(?P<major>\d+)(?:\.(?P<minor>\d+))?")


def parse_l4t_release(value: str) -> str | None:
    """Return an L4T release such as ``36.5.2`` from nv_tegra_release."""
    match = _L4T_RELEASE.search(value or '')
    if not match:
        return None
    return f"{match.group('major')}.{match.group('revision')}"


def version_pair(value: str | None) -> tuple[int, int] | None:
    match = _VERSION.match((value or '').strip())
    if not match:
        return None
    return int(match.group('major')), int(match.group('minor') or 0)


def known_platform(l4t_release: str | None) -> dict[str, str | None]:
    """Return conservative official-stack expectations for a known L4T family."""
    pair = version_pair(l4t_release)
    if pair == (36, 5):
        return {
            'jetpack_family': '6.2.2',
            'expected_cuda_family': '12.6',
            'pytorch_matrix_note': 'JetPack 6.2 rows list NVIDIA PyTorch 2.7/2.8 development builds',
        }
    return {
        'jetpack_family': None,
        'expected_cuda_family': None,
        'pytorch_matrix_note': 'not encoded; consult the current NVIDIA compatibility matrix',
    }


def classify_runtime(
    *,
    architecture: str,
    l4t_release: str | None,
    torch_imported: bool,
    torch_version: str | None,
    torch_cuda: str | None,
    cuda_available: bool,
) -> dict[str, Any]:
    """Classify observations without guessing a replacement package."""
    platform = known_platform(l4t_release)
    reasons: list[str] = []

    if architecture not in {'aarch64', 'arm64'} or not l4t_release:
        reasons.append('Jetson aarch64/L4T identity was not established')
        state = 'NOT_JETSON_OR_UNKNOWN'
    elif not torch_imported:
        reasons.append('PyTorch could not be imported')
        state = 'BLOCKED_MISSING_TORCH'
    else:
        expected_cuda = version_pair(platform['expected_cuda_family'])
        built_cuda = version_pair(torch_cuda)
        torch_pair = version_pair(torch_version)
        if expected_cuda and built_cuda and built_cuda[0] > expected_cuda[0]:
            reasons.append(
                f'PyTorch CUDA build {torch_cuda} is newer than the known platform CUDA family '
                f"{platform['expected_cuda_family']}"
            )
        if platform['jetpack_family'] == '6.2.2' and torch_pair and torch_pair >= (2, 11):
            reasons.append('PyTorch 2.11 is listed for JetPack 7.1, not JetPack 6.2, in the NVIDIA matrix')
        if not cuda_available:
            reasons.append('torch.cuda.is_available() returned false')
        state = 'READY_CORE' if not reasons else 'BLOCKED_COMPATIBILITY'

    return {
        'state': state,
        'reasons': reasons,
        **platform,
        'replacement_selected': False,
        'installation_performed': False,
        'model_loaded': False,
    }
