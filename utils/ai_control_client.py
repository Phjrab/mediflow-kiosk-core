"""Bounded A-to-B management client, isolated from inference client state."""
from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import threading
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

from utils.ai_config import AIError, number, secret


READ_PATHS = {
    "state": "/state",
    "capabilities": "/capabilities",
    "models": "/models",
    "current_config": "/configs/current",
    "events": "/events?limit=20",
}


def _endpoint(env: Mapping[str, str]) -> tuple[str, str, int, str]:
    raw = str(env.get("AI_CONTROL_BASE_URL", "")).strip()
    allowed = {value.strip() for value in str(env.get("AI_CONTROL_ALLOWED_ORIGINS", "")).split(",") if value.strip()}
    try:
        parsed = urlsplit(raw)
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if (parsed.path != "/control/v1" or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None
                or origin not in allowed or address.is_link_local or address.is_unspecified
                or address.is_multicast or not (address.is_private or address.is_loopback)):
            raise ValueError()
        if parsed.scheme == "http" and not address.is_loopback:
            raise ValueError()
        if parsed.scheme not in {"http", "https"}:
            raise ValueError()
        return parsed.scheme, str(address), port, parsed.path
    except (ValueError, TypeError):
        raise AIError("misconfigured") from None


@dataclass(frozen=True)
class AIControlConfig:
    node_id: str
    scheme: str
    host: str
    port: int
    path: str
    token: str = field(repr=False)
    ca_file: str | None = None
    connect_timeout: float = 2
    read_timeout: float = 3
    deadline: float = 5
    cache_seconds: float = 5
    stale_seconds: float = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str]):
        if str(env.get("AI_CONTROL_ENABLED", "0")) != "1":
            raise AIError("disabled")
        node_id = str(env.get("AI_CONTROL_NODE_ID", "")).strip()
        if not node_id or len(node_id) > 120:
            raise AIError("misconfigured")
        if str(env.get("AI_CONTROL_API_KEY", "")).strip():
            raise AIError("misconfigured")
        token = secret(env, "AI_CONTROL")
        scheme, host, port, path = _endpoint(env)
        ca_file = str(env.get("AI_CONTROL_CA_FILE", "")).strip() or None
        if scheme == "https":
            if not ca_file or not Path(ca_file).is_absolute() or not Path(ca_file).is_file():
                raise AIError("misconfigured")
        return cls(
            node_id, scheme, host, port, path, token, ca_file,
            number(env, "AI_CONTROL_CONNECT_TIMEOUT", 2, 30),
            number(env, "AI_CONTROL_READ_TIMEOUT", 3, 60),
            number(env, "AI_CONTROL_REQUEST_DEADLINE", 5, 60),
            number(env, "AI_CONTROL_STATUS_CACHE_SECONDS", 5, 60),
            number(env, "AI_CONTROL_STATUS_STALE_SECONDS", 15, 300),
        )


class AIControlClient:
    def __init__(self, config: AIControlConfig, *, monotonic=time.monotonic):
        self.config = config
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _connection(self):
        if self.config.scheme == "https":
            context = ssl.create_default_context(cafile=self.config.ca_file)
            context.check_hostname = True
            return http.client.HTTPSConnection(
                self.config.host, self.config.port,
                timeout=min(self.config.connect_timeout, self.config.deadline), context=context,
            )
        return http.client.HTTPConnection(
            self.config.host, self.config.port,
            timeout=min(self.config.connect_timeout, self.config.deadline),
        )

    def request(self, method: str, suffix: str, payload: Any = None,
                *, idempotency_key: str | None = None) -> dict[str, Any]:
        if method not in {"GET", "POST"} or not suffix.startswith("/") or "//" in suffix:
            raise AIError("misconfigured")
        if (idempotency_key is not None and (
                method != "POST" or suffix != "/operations"
                or not re.fullmatch(r"[0-9a-f]{32}", idempotency_key))):
            raise AIError("invalid_idempotency_key")
        if method == "POST" and suffix == "/operations" and idempotency_key is None:
            raise AIError("invalid_idempotency_key")
        body = None
        if payload is not None:
            try:
                body = json.dumps(payload, allow_nan=False, ensure_ascii=True).encode("ascii")
            except (TypeError, ValueError):
                raise AIError("invalid_config") from None
            if len(body) > 128 * 1024:
                raise AIError("invalid_config")
        connection = self._connection()
        started = self._monotonic()
        try:
            connection.connect()
            remaining = self.config.deadline - (self._monotonic() - started)
            if remaining <= 0:
                raise AIError("controller_unreachable")
            if connection.sock:
                connection.sock.settimeout(min(self.config.read_timeout, remaining))
            headers = {
                "Authorization": "Bearer " + self.config.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            if idempotency_key is not None:
                headers["Idempotency-Key"] = idempotency_key
            connection.request(method, self.config.path + suffix, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise AIError("controller_invalid_response")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError):
                raise AIError("controller_invalid_response") from None
            if not isinstance(result, dict):
                raise AIError("controller_invalid_response")
            if response.status >= 400:
                code = result.get("error_code")
                raise AIError(code if isinstance(code, str) and len(code) < 100 else "controller_error")
            if response.status not in {200, 201, 202}:
                raise AIError("controller_invalid_response")
            return result
        except AIError:
            raise
        except (OSError, TimeoutError, http.client.HTTPException, ssl.SSLError):
            raise AIError("controller_unreachable") from None
        finally:
            connection.close()

    def read(self, name: str, *, force: bool = False) -> dict[str, Any]:
        if name not in READ_PATHS:
            raise AIError("misconfigured")
        now = self._monotonic()
        with self._lock:
            cached = self._cache.get(name)
            if cached and not force and now - cached[0] < self.config.cache_seconds:
                result = dict(cached[1])
                result["cache"] = {
                    "cached": True,
                    "stale": now - cached[0] >= self.config.stale_seconds,
                    "connection_state": "connected",
                }
                return result
        try:
            result = self.request("GET", READ_PATHS[name])
        except AIError:
            if cached:
                result = dict(cached[1])
                result["cache"] = {
                    "cached": True,
                    "stale": now - cached[0] >= self.config.stale_seconds,
                    "connection_state": "unreachable",
                }
                return result
            raise
        with self._lock:
            self._cache[name] = (now, dict(result))
        result["cache"] = {"cached": False, "stale": False, "connection_state": "connected"}
        return result

    def overview(self, *, force: bool = False) -> dict[str, Any]:
        names = ("state", "capabilities", "models", "current_config")
        with ThreadPoolExecutor(max_workers=len(names), thread_name_prefix="ai-control-read") as executor:
            futures = {name: executor.submit(self.read, name, force=force) for name in names}
            return {name: futures[name].result() for name in names}


_clients: dict[tuple[Any, ...], AIControlClient] = {}
_clients_lock = threading.Lock()


def client_from_env(env: Mapping[str, str] | None = None) -> AIControlClient:
    env = dict(os.environ) if env is None else dict(env)
    config = AIControlConfig.from_env(env)
    key = (
        config.node_id, config.scheme, config.host, config.port, config.path,
        hashlib.sha256(config.token.encode("utf-8")).digest(),
        config.ca_file, config.connect_timeout, config.read_timeout, config.deadline,
        config.cache_seconds, config.stale_seconds,
    )
    with _clients_lock:
        client = _clients.get(key)
        if client is None:
            client = AIControlClient(config)
            _clients[key] = client
        return client
