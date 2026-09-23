#!/usr/bin/env python3
"""Verify already-downloaded pinned AI files; never downloads or modifies them."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.artifact_manifest import ALLOWED_COMPONENTS, verify_component  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--component', required=True, choices=sorted(ALLOWED_COMPONENTS))
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument(
        '--manifest', type=Path,
        default=PROJECT_ROOT / 'config' / 'ai_artifact_candidates.json',
    )
    args = parser.parse_args()
    try:
        result = verify_component(args.manifest, args.component, args.root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({
            'status': 'ERROR',
            'error_code': str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
        }), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
