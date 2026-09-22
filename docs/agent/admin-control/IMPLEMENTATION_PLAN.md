# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | PARTIAL; exact seven-field VLM activation receipt verified, generation output contract BLOCKED_GATE |
| C6 | Read-only deployment then approved device mutation verification | `27c5da9` DEPLOYED; reconciliation verified; single retry recovered fail-closed; controller read-only |

The approved C1/C2 bootstrap, C4 managed inference ingress, and `27c5da9`
MedGemma lifecycle/reconciliation release are deployed. The A-to-B management
API remains on its loopback SSH tunnel, drafts/mutations are off, raw chat is
loopback-only, VLM is stopped, and network inference is exposed only through
managed ingress. Applied state is restored to exact `1:1:chat_only` after the
single retry reached VLM but returned HTTP 400 after a completed 72-second
backend lease. The remaining gate is the undeployed output-channel hardening and
a separately approved synthetic verification; E1/E2 is not complete.
