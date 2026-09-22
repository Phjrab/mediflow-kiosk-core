# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | Direct managed contract DONE; managed E2 worker BLOCKED on A deployed key-file client drift |
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
with `failed/misconfigured`, created no prediction, and was not retried. A's
deployed head `1ec6f31` reads only inline `VLM_API_KEY`; the safe owner-only
`VLM_API_KEY_FILE` support and regression already exist on this branch from
`8a9efa3`. After fail-closed recovery, B remains `ee7e03e`, exact
`1:1:chat_only`, zero active/unknown leases, with drafts/mutations disabled.
Next, deploy only the existing A client key-file support under a separately
approved scope. A later E2 attempt must use another isolated set of identifiers
and its own approval.
