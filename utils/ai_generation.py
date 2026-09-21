"""Versioned local-chat sampling settings stored separately from connection config."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping

from utils.ai_config import AIError


SCHEMA_VERSION = "1.0"


def _finite_number(value: Any, name: str, *, minimum: float, maximum: float,
                   minimum_inclusive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AIError("invalid_generation_config")
    number = float(value)
    if not math.isfinite(number):
        raise AIError("invalid_generation_config")
    lower_ok = number >= minimum if minimum_inclusive else number > minimum
    if not lower_ok or number > maximum:
        raise AIError("invalid_generation_config")
    return number


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AIError("invalid_generation_config")
    if not minimum <= value <= maximum:
        raise AIError("invalid_generation_config")
    return value


@dataclass(frozen=True)
class GenerationSettings:
    generation_revision: int
    temperature: float | None
    top_p: float | None
    max_tokens: int
    source: str = "versioned_file"

    def request_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {"max_tokens": self.max_tokens}
        if self.temperature is not None:
            result["temperature"] = self.temperature
        if self.top_p is not None:
            result["top_p"] = self.top_p
        return result

    def public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            **asdict(self),
            "scope": "local_chat_only",
        }


def validate_values(value: Mapping[str, Any], *, max_tokens_cap: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"temperature", "top_p", "max_tokens"}:
        raise AIError("invalid_generation_config")
    return {
        "temperature": _finite_number(value["temperature"], "temperature", minimum=0, maximum=1),
        "top_p": _finite_number(
            value["top_p"], "top_p", minimum=0, maximum=1, minimum_inclusive=False
        ),
        "max_tokens": _integer(value["max_tokens"], "max_tokens", minimum=1, maximum=max_tokens_cap),
    }


class GenerationConfigStore:
    def __init__(self, path: str | os.PathLike[str], *, max_tokens_cap: int = 4096):
        self.path = Path(path)
        self.max_tokens_cap = max_tokens_cap

    def _verify_parent(self) -> None:
        parent = self.path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata = parent.stat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o077:
            raise AIError("unsafe_generation_store")

    def load(self, *, legacy_max_tokens: int) -> GenerationSettings:
        if not self.path.exists():
            return GenerationSettings(0, None, None, legacy_max_tokens, "legacy_effective")
        try:
            metadata = self.path.lstat()
            if (stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077
                    or metadata.st_size > 16384):
                raise ValueError()
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or set(raw) != {
                "schema_version", "generation_revision", "scope",
                "temperature", "top_p", "max_tokens",
            }:
                raise ValueError()
            if raw["schema_version"] != SCHEMA_VERSION or raw["scope"] != "local_chat_only":
                raise ValueError()
            revision = _integer(raw["generation_revision"], "generation_revision", minimum=1, maximum=2**31 - 1)
            values = validate_values(
                {key: raw[key] for key in ("temperature", "top_p", "max_tokens")},
                max_tokens_cap=self.max_tokens_cap,
            )
            return GenerationSettings(revision, source="versioned_file", **values)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError, AIError):
            raise AIError("invalid_generation_config") from None

    def save(self, expected_revision: int, values: Mapping[str, Any], *, legacy_max_tokens: int) -> GenerationSettings:
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
            raise AIError("invalid_generation_config")
        current = self.load(legacy_max_tokens=legacy_max_tokens)
        if current.generation_revision != expected_revision:
            raise AIError("stale_generation_revision")
        normalized = validate_values(values, max_tokens_cap=self.max_tokens_cap)
        next_value = GenerationSettings(expected_revision + 1, source="versioned_file", **normalized)
        self._verify_parent()
        payload = next_value.public_dict()
        payload.pop("source")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".generation-", dir=self.path.parent)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            os.chmod(self.path, 0o600)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
        return next_value


def store_from_env(env: Mapping[str, str]) -> GenerationConfigStore | None:
    raw = str(env.get("LOCAL_LLM_GENERATION_CONFIG_FILE", "")).strip()
    path = Path(raw) if raw else Path.home() / ".config" / "mediflow-ai" / "local-chat-generation.json"
    if not path.is_absolute():
        raise AIError("misconfigured")
    try:
        cap = int(env.get("LOCAL_LLM_MAX_TOKENS", "512"))
    except (TypeError, ValueError):
        raise AIError("misconfigured") from None
    if not 1 <= cap <= 4096:
        raise AIError("misconfigured")
    return GenerationConfigStore(path, max_tokens_cap=cap)


def settings_from_env(env: Mapping[str, str]) -> GenerationSettings:
    try:
        legacy = int(env.get("LOCAL_LLM_MAX_TOKENS", "512"))
    except (TypeError, ValueError):
        raise AIError("misconfigured") from None
    store = store_from_env(env)
    if store is None:
        return GenerationSettings(0, None, None, legacy, "legacy_effective")
    return store.load(legacy_max_tokens=legacy)
