#!/usr/bin/env python3
"""Send one explicitly non-sensitive image through the configured VLM adapter."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')

from utils.ai_config import AIError, VLMConfig  # noqa: E402
from utils.vlm_client import analyze_eye  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--confirm-non-sensitive', action='store_true')
    args = parser.parse_args()
    if not args.confirm_non_sensitive:
        print('FAIL: --confirm-non-sensitive is required', file=sys.stderr)
        return 2
    try:
        started = time.monotonic()
        result = analyze_eye(VLMConfig.from_env(dict(os.environ)), Path(args.image).read_bytes())
        duration_ms = (time.monotonic() - started) * 1000
        print(
            'PASS: vision request '
            f'status={result["analysis"]["analysis_status"]} '
            f'duration_ms={duration_ms:.1f} input_digest={result["provenance"]["input_digest"]}'
        )
        return 0
    except (AIError, OSError) as exc:
        code = exc.code if isinstance(exc, AIError) else 'image_unavailable'
        print(f'FAIL: vision request error_code={code}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
