#!/usr/bin/env python3
"""Export explicit-denominator research metrics from the protected store."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')

from experiments.evaluate import export_report  # noqa: E402
from experiments.worker import store_from_env  # noqa: E402
from utils.ai_config import AIError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    try:
        paths = export_report(store_from_env(), args.run_id, args.output_dir)
        print(json.dumps({key: str(value) for key, value in paths.items()}))
        return 0
    except (AIError, ValueError, KeyError, OSError) as exc:
        code = exc.code if isinstance(exc, AIError) else type(exc).__name__.lower()
        print(json.dumps({'status': 'error', 'error_code': code}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
