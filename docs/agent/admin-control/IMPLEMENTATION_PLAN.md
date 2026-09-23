# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | DONE; C13 E2 worker succeeded with frozen survey and matching receipt |
| C6 | Read-only deployment then approved device mutation verification | `86bebb6` controller read-only; safe `3:3:chat_only`; admission open at generation 3 |

The approved C1/C2 bootstrap, C4 managed inference ingress, `ee7e03e`
MedGemma output/lifecycle release, and `86bebb6` read-only controller are
deployed. The A-to-B management
API remains on its loopback SSH tunnel, drafts/mutations are off, raw chat is
loopback-only, VLM is stopped, and network inference is exposed only through
managed ingress. In the earlier direct VLM contract window, applied state was
restored to exact `1:1:chat_only` after the
single 224×224, 512-token request returned HTTP 200 in 74.62 seconds with
`vision_ingested=true`, a strict-schema abstention, and a matching runtime
receipt. The completed lease and forward operation remain preserved. This
completes the synthetic managed VLM contract and sequential lifecycle gate. It
does not constitute E2 survey-worker, real-data, load, thermal, accuracy, or
medical-quality validation.

The first approved managed-ingress E2 attempt used new isolated sample, run, and
job identifiers plus a frozen `eye-survey-1.0` digest. It stopped before ingress
with `failed/misconfigured`, created no prediction, and was not retried. The A
head at that attempt, `1ec6f31`, read only inline `VLM_API_KEY`; the safe owner-only
`VLM_API_KEY_FILE` support and regression already exist on this branch from
`8a9efa3`. After that window's fail-closed recovery, B was `ee7e03e`, exact
`1:1:chat_only`, zero active/unknown leases, with drafts/mutations disabled.
The approved exact two-file A client deployment is complete as `f53a1c6` after
22+6+6 focused tests and a successful no-network owner-only key-file load.
Protected file hashes were unchanged and no web process was running, so none was
restarted. A later E2 attempt must use another isolated set of identifiers and
its own approval. The applied scope is preserved in
`A_VLM_KEYFILE_CLIENT.diff` and `A_VLM_KEYFILE_CLIENT_MIGRATION.md`.

The next approved E2 window stopped before run/job creation when an independent
generic probe returned `vlm_ready=false`. That probe omitted the bearer
credential required by MedGemma's protected `/readyz`, so it does not establish
actual service unreadiness; the manager's authenticated startup loop had passed.
Recovery returned B to exact `1:1:chat_only` with controller mutations disabled.
Local source now performs an additional authenticated `medgemma_service.ready`
check during start and withholds the receipt while not ready, allowing operation
rollback to stop the exact-owned process before restoring chat. This change
passes 32 Admin Control and 19 MedGemma tests and is deployed read-only in
`86bebb6` after authenticated mock, exact-owner, rollback, chat-health, receipt,
lease, and shared-lock gates passed. Those gates enabled the separately approved
C13 attempt described below.

The later C13 window completed the synthetic E2 survey-worker contract with one
new isolated sample, run, job, and prediction. Both sequential transition
operations succeeded without co-residency, and the device returned to healthy
chat with VLM stopped. Because the controller correctly advanced its monotonic
revision and generation to 3, a proposed direct rewind to the old `1:1`
metadata was rejected by automatic approval review before execution. At that
window's end, the device was fail-closed at internally consistent
`3:3:chat_only`, zero active/unknown leases, read-only controller, and closed
admission. No further E2 request is needed; direct state-file or
ingress-generation rewrites are out of scope.

A separate approval accepted the monotonic controller-authoritative
`3:3:chat_only` state as the safe baseline. All exact-owner, receipt, lease,
operation-history, raw-bypass, and read-only gates passed; managed ingress
admission then reopened under the shared lifecycle lock without changing
generation, applied state, receipt, model processes, controller capabilities, or
ports. The device is now healthy chat-only with open admission, zero
active/unknown leases, stopped VLM, and drafts/mutations disabled. No inference
request was used to validate this recovery.

The first C13 CLI invocation exposed a local tooling gap: A's system Python
lacks `python-dotenv`, so the CLI exited before claiming the queued job. The
existing worker ran exactly once through a direct invocation. Local source now
supports an explicit process-environment-only CLI mode and verifies it with
mock tests. The exact two-file CLI/test patch was deployed to A as `265e545`.
Its existing project virtualenv passed all 15 focused tests; A's system Python
has a pre-existing NumPy/OpenCV ABI mismatch in the E0 worker test. The change
did not start a worker or inference request and did not touch B.
