#!/usr/bin/env python3
"""Non-sensitive local LLM generation smoke test for Jetson A -> B."""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from utils.ai_config import AIError, LocalConfig, provider_from  # noqa: E402
from utils.llm_client import local_chat  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--question',
        default='연결 시험입니다. 한 문장으로 준비 상태만 답하세요.',
        help='Use non-sensitive text only.',
    )
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / '.env')
    env = dict(os.environ)

    try:
        if provider_from(env) != 'local':
            raise AIError('misconfigured')
        started = time.monotonic()
        reply = local_chat(
            LocalConfig.from_env(env),
            'This is a connectivity test. Do not provide medical advice.',
            args.question,
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        print(f'PASS: local generation status=ok duration_ms={elapsed_ms:.1f} reply_chars={len(reply)}')
        return 0
    except AIError as exc:
        print(f'FAIL: local generation error_code={exc.code}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
