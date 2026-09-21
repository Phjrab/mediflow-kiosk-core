"""Flask entrypoint for the Jetson B headless AI control API."""
from __future__ import annotations

import hmac
import os

from flask import Flask, jsonify, request

from services.ai_control.core import (
    Catalog, ControlError, ControlService, PrivateJsonStore, load_management_token,
)
from services.ai_control.runtime import observe_runtime


def _error(error: ControlError):
    return jsonify({"status": "error", "error_code": error.code}), error.status


def create_app(service: ControlService | None = None, *, env=None) -> Flask:
    env = dict(os.environ) if env is None else dict(env)
    app = Flask(__name__)
    if service is None:
        state_dir = env.get("AI_CONTROL_STATE_DIR", "").strip()
        if not state_dir:
            raise RuntimeError("AI_CONTROL_STATE_DIR is required")
        service = ControlService(
            node_id=env.get("AI_CONTROL_NODE_ID", "jetson-b"),
            store=PrivateJsonStore(state_dir),
            catalog=Catalog(env.get("AI_CONTROL_REGISTRY_FILE", "").strip() or None),
            observe_runtime=lambda: observe_runtime(env),
            drafts_enabled=env.get("AI_CONTROL_DRAFTS_ENABLED", "0") == "1",
            mutations_enabled=env.get("AI_CONTROL_MUTATIONS_ENABLED", "0") == "1",
            managed_ingress_verified=(
                env.get("AI_CONTROL_MANAGED_INGRESS_VERIFIED", "0") == "1"
            ),
        )
    token_file = env.get("AI_CONTROL_API_KEY_FILE", "").strip()

    @app.before_request
    def authenticate():
        if request.path == "/healthz":
            return None
        if request.content_length is not None and request.content_length > 128 * 1024:
            return _error(ControlError("request_too_large", 413))
        try:
            expected = load_management_token(token_file)
        except ControlError as exc:
            return _error(exc)
        header = request.headers.get("Authorization", "")
        supplied = header[7:] if header.startswith("Bearer ") else ""
        if not supplied or not hmac.compare_digest(supplied, expected):
            return _error(ControlError("unauthorized", 401))
        return None

    @app.after_request
    def harden(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(ControlError)
    def handle_control_error(error):
        return _error(error)

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"status": "ok", "role": "management_only"})

    @app.route("/control/v1/state", methods=["GET"])
    def state():
        return jsonify(service.state())

    @app.route("/control/v1/capabilities", methods=["GET"])
    def capabilities():
        return jsonify(service.capabilities())

    @app.route("/control/v1/models", methods=["GET"])
    def models():
        return jsonify(service.models())

    @app.route("/control/v1/configs/current", methods=["GET"])
    def current_config():
        return jsonify(service.current_config())

    @app.route("/control/v1/events", methods=["GET"])
    def events():
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            raise ControlError("invalid_limit") from None
        return jsonify(service.events(limit))

    @app.route("/control/v1/drafts", methods=["POST"])
    def drafts():
        return jsonify(service.save_draft(request.get_json(silent=True))), 201

    @app.route("/control/v1/plans", methods=["POST"])
    def plans():
        return jsonify(service.create_plan(request.get_json(silent=True))), 201

    @app.route("/control/v1/operations", methods=["POST"])
    def operations():
        idempotency_key = request.headers.get("Idempotency-Key", "")
        operation = service.accept_operation(
            request.get_json(silent=True), idempotency_key=idempotency_key
        )
        return jsonify({
            "operation_id": operation["operation_id"],
            "state": operation["state"],
            "completed": operation["completed"],
        }), 202

    @app.route("/control/v1/operations/<operation_id>", methods=["GET"])
    def operation(operation_id):
        return jsonify(service.get_operation(operation_id))

    @app.route("/control/v1/operations/<operation_id>/cancel", methods=["POST"])
    def cancel_operation(operation_id):
        return jsonify(service.cancel_operation(operation_id))

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=8090, debug=False, use_reloader=False)
