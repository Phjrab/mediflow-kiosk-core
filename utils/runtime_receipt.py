"""Closed runtime expectation and receipt schema for reproducible research calls."""
from __future__ import annotations

import re
from typing import Any

from utils.ai_config import AIError


RUNTIME_FIELDS = {
    "node_id", "artifact_id", "artifact_manifest_digest", "runtime_revision",
    "config_revision", "deployment_generation", "effective_config_digest",
}
RECEIPT_FIELDS = RUNTIME_FIELDS | {"prompt_digest"}


def validate_runtime_expectation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != RUNTIME_FIELDS:
        raise AIError("invalid_runtime_expectation")
    result = {}
    for key in ("node_id", "artifact_id", "runtime_revision"):
        item = value[key]
        if not isinstance(item, str) or not item.strip() or len(item) > 160:
            raise AIError("invalid_runtime_expectation")
        result[key] = item.strip()
    for key in ("artifact_manifest_digest", "effective_config_digest"):
        item = value[key]
        if not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item):
            raise AIError("invalid_runtime_expectation")
        result[key] = item
    for key in ("config_revision", "deployment_generation"):
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise AIError("invalid_runtime_expectation")
        result[key] = item
    return result


def validate_runtime_receipt(value: Any, expected: dict[str, Any], *, prompt_digest: str) -> dict[str, Any]:
    expected = validate_runtime_expectation(expected)
    if not isinstance(value, dict) or set(value) != RECEIPT_FIELDS:
        raise AIError("runtime_receipt_mismatch")
    try:
        observed = validate_runtime_expectation({key: value[key] for key in RUNTIME_FIELDS})
    except AIError:
        raise AIError("runtime_receipt_mismatch") from None
    receipt_prompt = value.get("prompt_digest")
    if not isinstance(receipt_prompt, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_prompt):
        raise AIError("runtime_receipt_mismatch")
    if observed != expected or receipt_prompt != prompt_digest:
        raise AIError("runtime_receipt_mismatch")
    return {**observed, "prompt_digest": receipt_prompt}
