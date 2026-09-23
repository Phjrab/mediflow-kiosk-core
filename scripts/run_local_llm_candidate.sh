#!/usr/bin/env bash
# Start only the pinned, already-built and already-downloaded general LLM candidate.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_LLAMA_CPP_REVISION="391fac16460f15233a7740550d858ac96df3419d"
MODEL_FILENAME="qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_ALIAS="qwen2.5-3b-instruct-q4-k-m"

: "${LLAMA_CPP_DIR:?set LLAMA_CPP_DIR to the pinned llama.cpp checkout}"
: "${LOCAL_LLM_MODEL_DIR:?set LOCAL_LLM_MODEL_DIR to the private model directory}"
: "${LOCAL_LLM_API_KEY_FILE:?set LOCAL_LLM_API_KEY_FILE to a private mode-0600 key file}"

LOCAL_LLM_HOST="${LOCAL_LLM_HOST:-0.0.0.0}"
LOCAL_LLM_PORT="${LOCAL_LLM_PORT:-8080}"
if [[ "$LOCAL_LLM_HOST" != "0.0.0.0" && "$LOCAL_LLM_HOST" != "127.0.0.1" ]]; then
  echo "LOCAL_LLM_HOST must be 0.0.0.0 or 127.0.0.1" >&2
  exit 1
fi
if [[ ! "$LOCAL_LLM_PORT" =~ ^[0-9]+$ ]] || (( LOCAL_LLM_PORT < 1 || LOCAL_LLM_PORT > 65535 )); then
  echo "LOCAL_LLM_PORT must be an integer from 1 to 65535" >&2
  exit 1
fi

python3 "$PROJECT_ROOT/scripts/verify_ai_artifacts.py" \
  --component general_llm \
  --root "$LOCAL_LLM_MODEL_DIR" >/dev/null

actual_revision="$(git -C "$LLAMA_CPP_DIR" rev-parse HEAD)"
if [[ "$actual_revision" != "$EXPECTED_LLAMA_CPP_REVISION" ]]; then
  echo "llama.cpp revision mismatch" >&2
  exit 1
fi

server="$LLAMA_CPP_DIR/build/bin/llama-server"
if [[ ! -x "$server" ]]; then
  echo "pinned llama-server binary is missing" >&2
  exit 1
fi

python3 - "$LOCAL_LLM_API_KEY_FILE" <<'PY'
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_symlink() or not path.is_file():
    raise SystemExit('API key file must be a regular non-symlink file')
mode = stat.S_IMODE(path.stat().st_mode)
if mode & 0o077:
    raise SystemExit('API key file permissions must be 0600 or stricter')
if not path.read_text(encoding='utf-8').strip():
    raise SystemExit('API key file is empty')
PY

exec "$server" \
  --model "$LOCAL_LLM_MODEL_DIR/$MODEL_FILENAME" \
  --alias "$MODEL_ALIAS" \
  --host "$LOCAL_LLM_HOST" \
  --port "$LOCAL_LLM_PORT" \
  --api-key-file "$LOCAL_LLM_API_KEY_FILE" \
  --n-gpu-layers all \
  --parallel 1 \
  --ctx-size 4096 \
  --n-predict 512 \
  --no-cache-prompt \
  --cache-ram 0 \
  --no-slots \
  --no-webui
