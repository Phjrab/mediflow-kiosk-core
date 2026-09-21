"""Fixed-route inference ingress with durable admission and lease ownership."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable

from flask import Flask, jsonify, request

from services.ai_control.core import ControlError, load_management_token
from services.ai_control.ingress import IngressJournal
from utils.ai_config import AIError
from utils.runtime_receipt import validate_runtime_expectation


class UpstreamCompletionUnknown(RuntimeError):
    """The upstream may still be computing after transport loss."""


def load_private_runtime_receipt(path: str | os.PathLike[str]) -> dict[str, Any]:
    receipt_path = Path(path)
    if not receipt_path.is_absolute():
        raise ControlError("unsafe_runtime_receipt", 503)
    try:
        metadata = receipt_path.lstat()
        if (receipt_path.is_symlink() or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077
                or metadata.st_size > 64 * 1024):
            raise ControlError("unsafe_runtime_receipt", 503)
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
        return validate_runtime_expectation(value)
    except ControlError:
        raise
    except (OSError, ValueError, UnicodeError, AIError):
        raise ControlError("unsafe_runtime_receipt", 503) from None


class FixedLoopbackForwarder:
    """Two fixed upstreams; it is deliberately not a general-purpose proxy."""

    def __init__(self, *, chat_port: int, vlm_port: int, chat_key_file: str,
                 vlm_key_file: str, timeout: float = 600):
        for port in (chat_port, vlm_port):
            if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError("invalid upstream port")
        self.ports = {"chat": chat_port, "vlm": vlm_port}
        self.paths = {"chat": "/v1/chat/completions", "vlm": "/v1/analyze-eye"}
        self.keys = {"chat": chat_key_file, "vlm": vlm_key_file}
        self.timeout = timeout

    def __call__(self, route: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.ports[route], timeout=self.timeout)
        sent = False
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(body) > 8 * 1024 * 1024:
                return 413, {"status": "context_too_long"}
            token = load_management_token(self.keys[route])
            connection.request("POST", self.paths[route], body=body, headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            sent = True
            response = connection.getresponse()
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise UpstreamCompletionUnknown()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise UpstreamCompletionUnknown()
            return int(response.status), value
        except (OSError, TimeoutError, http.client.HTTPException, ValueError, UnicodeError):
            if sent:
                raise UpstreamCompletionUnknown() from None
            raise
        finally:
            connection.close()


def create_app(
    *, journal: IngressJournal, forward: Callable[[str, dict[str, Any]], tuple[int, dict[str, Any]]],
    runtime_snapshot: Callable[[], dict[str, Any]], chat_key_file: str,
    vlm_key_file: str,
) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    journal.initialize()

    def error(code: str, status: int):
        response = jsonify({"status": code})
        response.status_code = status
        return response

    def authorized(key_file: str) -> bool:
        try:
            expected = load_management_token(key_file)
        except ControlError:
            return False
        supplied = request.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, "Bearer " + expected)

    @app.after_request
    def harden(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def handle(route: str, key_file: str):
        if not authorized(key_file):
            return error("unauthorized", 401)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return error("invalid_request", 400)
        expected = payload.pop("expected_runtime", None)
        prompt_digest = payload.pop("prompt_digest", None) if route == "chat" else payload.get("prompt_digest")
        actual = None
        if expected is not None:
            try:
                expected = validate_runtime_expectation(expected)
                actual = validate_runtime_expectation(runtime_snapshot())
            except (AIError, ControlError, ValueError):
                return error("configuration_drift", 409)
            valid_prompt_digest = (
                isinstance(prompt_digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", prompt_digest) is not None
            )
            if route == "chat" and valid_prompt_digest:
                messages = payload.get("messages")
                system = (
                    messages[0].get("content")
                    if isinstance(messages, list) and messages
                    and isinstance(messages[0], dict)
                    and messages[0].get("role") == "system"
                    else None
                )
                valid_prompt_digest = (
                    isinstance(system, str)
                    and hmac.compare_digest(
                        prompt_digest,
                        hashlib.sha256(system.encode("utf-8")).hexdigest(),
                    )
                )
            if actual != expected or not valid_prompt_digest:
                return error("configuration_drift", 409)
        try:
            lease_id = journal.admit(
                route,
                expected_generation=(expected or {}).get("deployment_generation"),
            )
        except ControlError as exc:
            status = 409 if exc.code == "configuration_drift" else 503
            return error(exc.code, status)
        try:
            status, response = forward(route, payload)
            if not isinstance(response, dict):
                raise UpstreamCompletionUnknown()
            journal.complete(lease_id)
        except UpstreamCompletionUnknown:
            journal.mark_unknown(lease_id)
            return error("activity_unknown", 503)
        if status == 200 and actual is not None:
            response = dict(response)
            response["runtime_receipt"] = {**actual, "prompt_digest": prompt_digest}
        return jsonify(response), status

    @app.post("/v1/chat/completions")
    def chat():
        return handle("chat", chat_key_file)

    @app.post("/v1/analyze-eye")
    def vlm():
        return handle("vlm", vlm_key_file)

    @app.get("/healthz")
    def healthz():
        state = journal.snapshot()
        return jsonify({"status": "alive", "admission": state["admission"]})

    return app


def main() -> None:
    state_dir = Path(os.environ["AI_INGRESS_STATE_DIR"])
    receipt_file = Path(os.environ["AI_INGRESS_RUNTIME_RECEIPT_FILE"])
    chat_key = os.environ["LOCAL_LLM_API_KEY_FILE"]
    vlm_key = os.environ["MEDGEMMA_API_KEY_FILE"]
    if os.environ.get("AI_INGRESS_RAW_BYPASS_VERIFIED") != "1":
        raise SystemExit("raw runtime bypass closure is not verified")
    journal = IngressJournal(state_dir / "ingress.sqlite3")

    def runtime_snapshot():
        # Private applied receipt contains metadata only, never a prompt or credential.
        return load_private_runtime_receipt(receipt_file)

    forwarder = FixedLoopbackForwarder(
        chat_port=int(os.environ["AI_INGRESS_CHAT_UPSTREAM_PORT"]),
        vlm_port=int(os.environ["AI_INGRESS_VLM_UPSTREAM_PORT"]),
        chat_key_file=chat_key,
        vlm_key_file=vlm_key,
    )
    app = create_app(
        journal=journal, forward=forwarder, runtime_snapshot=runtime_snapshot,
        chat_key_file=chat_key, vlm_key_file=vlm_key,
    )
    app.run(
        host=os.environ.get("AI_INGRESS_HOST", "127.0.0.1"),
        port=int(os.environ.get("AI_INGRESS_PORT", "8080")),
        threaded=True,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()
