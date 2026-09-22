# Jetson A VLM key-file client migration

Status: review-only. Not applied to either Jetson.

## Purpose and exact scope

The first managed-ingress E2 worker attempt failed before ingress because the
Jetson A deployed source at `1ec6f31` reads only inline `VLM_API_KEY`. The
owner-only credential is intentionally stored in `VLM_API_KEY_FILE`, so the
deployed client returns bounded error `misconfigured` before opening a lease.

`A_VLM_KEYFILE_CLIENT.diff` is the exact two-file delta from deployed A source
`1ec6f31` to the already-tested implementation on `codex/admin-control`:

- `utils/ai_config.py` loads the VLM credential through the existing `secret`
  helper, which validates either the existing inline form or an owner-only file;
- `tests/test_ai_clients.py` proves the file form is loaded and used by the VLM
  client without changing its response contract.

The patch does not change endpoints, model selection, managed ingress,
controller settings, inference ports, credentials, environment files,
databases, model files, CUDA/PyTorch, user data, or cloud fallback.

## Pre-apply gates

1. Confirm A is on `codex/admin-control-a-deploy` at `1ec6f31`, or stop and
   review the new source difference. Preserve any uncommitted work.
2. Record hashes of A's `.env`, operational database, owner-only VLM key file,
   and existing research databases without reading or printing their contents.
3. Confirm B remains release `ee7e03e`, exact `1:1:chat_only`, healthy chat,
   open admission, raw-bypass closure, zero active/unknown leases, the exact
   seven-field receipt, and drafts/mutations disabled.
4. Verify the diff with `git apply --check`. Apply only these two file changes
   to a new A deployment commit; do not merge unrelated B release changes.

## Verification and stop conditions

Run the focused AI-client, experiment-worker, and survey/hybrid suites. Then run
a no-network configuration check that loads the existing owner-only key file
through `VLMConfig.from_env` and reports only a boolean success result. Never
print the credential, environment, prompt, image, or model response.

If A has an exact-owned web process that imports this code, restart only that
process through its existing lifecycle procedure and verify its prior health.
Do not start or stop either inference model, enable controller mutations, or run
an E2 job in this maintenance action. If source drift, an unsafe file mode, a
hash change outside the deployed source, process ownership mismatch, or health
regression is found, stop and restore the prior A code revision.

## Post-apply evidence

Record the A deployment commit, focused test counts, the bounded key-file
configuration check, any exact-owned web-process identity before and after, and
the unchanged baseline hashes in `WORKLOG.md` and `HANDOFF.md`. A later E2 test
requires a separate approval, a new isolated store, and new sample/run/job IDs;
the failed job `109efdbfb7a34ef0a3756db9828d9d9b` must remain immutable.
