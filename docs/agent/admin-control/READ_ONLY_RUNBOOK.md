# Admin Control Read-Only Bootstrap Runbook

This runbook covers C1/C2 read-only deployment only. It does not authorize a model start, stop, restart, profile switch, raw-port migration, autostart installation, or `.env` replacement.

## Preconditions

1. Record the source commit and A/B deployed revisions.
2. Confirm B's existing general LLM continues to be owned by `scripts/local_llm_service.py` and record its status without cleanup.
3. Prepare a dedicated management token, distinct from LLM and VLM inference tokens. Store one line in owner-only, mode-0600 files on A and B. Never pass the token in argv, a URL, browser data, logs, or the repository.
4. Use a CA and server certificate whose SAN matches the configured B IP, or an approved SSH tunnel with B bound to loopback. Never disable TLS verification. Remote plain HTTP is rejected by the A client.
5. Copy `config/ai_control_registry.example.json` to a private B registry, confirm its fields against the local artifacts, and set owner-only mode 0600. The checked-in file is an example, not an activation record.

## B controller

Configure the B process with a private `AI_CONTROL_STATE_DIR`, private registry and management-key paths, fixed node ID, and the exact existing manager evidence paths. Keep both flags off initially:

```text
AI_CONTROL_DRAFTS_ENABLED=0
AI_CONTROL_MUTATIONS_ENABLED=0
```

Run `services.ai_control.app:create_app` behind the approved TLS listener. The built-in development entrypoint binds loopback and is for manual engineering use only. Do not register boot autostart unless separately approved.

Verify with authenticated GET requests to `state`, `capabilities`, `models`, `configs/current`, and bounded `events`. Repeated reads must not change PID metadata, load a model, generate, or alter ports 8080/8081.

## A integration

Configure the exact management origin, node, CA, and A-side key file. Start with:

```text
AI_CONTROL_ENABLED=0
AI_CONTROL_DRAFTS_ENABLED=0
AI_CONTROL_MUTATIONS_ENABLED=0
```

After the feature-off regression passes, enable only `AI_CONTROL_ENABLED=1`. The browser continues to call same-origin A admin routes and never receives the B endpoint or token. `LOCAL_LLM_GENERATION_CONFIG_FILE` is independent of the B runtime and affects only later local chat requests after an explicit admin save.

## Rollback

Set A `AI_CONTROL_ENABLED=0` and restart only the A web process using its existing owner-validated procedure. Stop only the controller process using its exact service identity. Do not stop a stable inference engine. Preserve the controller journal for diagnosis; it contains no credential or patient payload. If the controller is unavailable, use the existing local B lifecycle manager as the emergency path rather than a generic shell endpoint.
