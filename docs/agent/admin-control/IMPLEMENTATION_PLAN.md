# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | Direct managed contract DONE; A key-file client deployed; E2 blocked by VLM readiness |
| C6 | Read-only deployment then approved device mutation verification | `ee7e03e` DEPLOYED; sequential VLM success and exact chat-only restore; controller read-only |

The approved C1/C2 bootstrap, C4 managed inference ingress, and `ee7e03e`
MedGemma output/lifecycle release are deployed. The A-to-B management
API remains on its loopback SSH tunnel, drafts/mutations are off, raw chat is
loopback-only, VLM is stopped, and network inference is exposed only through
managed ingress. Applied state is restored to exact `1:1:chat_only` after the
single 224×224, 512-token request returned HTTP 200 in 74.62 seconds with
`vision_ingested=true`, a strict-schema abstention, and a matching runtime
receipt. The completed lease and forward operation remain preserved, while the
device is restored to exact `1:1:chat_only` with drafts/mutations off. This
completes the synthetic managed VLM contract and sequential lifecycle gate. It
does not constitute E2 survey-worker, real-data, load, thermal, accuracy, or
medical-quality validation.

The first approved managed-ingress E2 attempt used new isolated sample, run, and
job identifiers plus a frozen `eye-survey-1.0` digest. It stopped before ingress
with `failed/misconfigured`, created no prediction, and was not retried. The A
head at that attempt, `1ec6f31`, read only inline `VLM_API_KEY`; the safe owner-only
`VLM_API_KEY_FILE` support and regression already exist on this branch from
`8a9efa3`. After fail-closed recovery, B remains `ee7e03e`, exact
`1:1:chat_only`, zero active/unknown leases, with drafts/mutations disabled.
The approved exact two-file A client deployment is complete as `f53a1c6` after
22+6+6 focused tests and a successful no-network owner-only key-file load.
Protected file hashes were unchanged and no web process was running, so none was
restarted. A later E2 attempt must use another isolated set of identifiers and
its own approval. The applied scope is preserved in
`A_VLM_KEYFILE_CLIENT.diff` and `A_VLM_KEYFILE_CLIENT_MIGRATION.md`.

The next approved E2 window stopped before run/job creation when the independent
post-transition check found `vlm_ready=false`. Exact ownership and receipt data
matched and there were zero leases, but readiness is a mandatory gate. Recovery
returned B to exact `1:1:chat_only` with controller mutations disabled. Local
source now requires MedGemma's fixed `/readyz` probe during start and withholds
the receipt while not ready, allowing operation rollback to stop the exact-owned
process before restoring chat. This change passes 32 Admin Control and 19
MedGemma tests and remains undeployed. Deploy and validate it in a separate
maintenance scope before considering a new isolated E2 attempt.
