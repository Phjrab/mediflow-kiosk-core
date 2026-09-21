# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | PARTIAL / MOCK; device adapter and ingress migration BLOCKED_GATE |
| C5 | Research queue/run lock and effective B receipt | PARTIAL / CODE + MOCK; VLM opt-in receipt complete, E3 ingress receipt pending |
| C6 | Read-only deployment then approved device mutation verification | READ_ONLY_DONE; mutation verification BLOCKED_GATE |

The approved C1/C2 bootstrap is deployed through an A-to-B loopback SSH tunnel with drafts and mutations off. Writable ingress migration, draft/device writes, lifecycle mutation, and model switching remain a separate maintenance change requiring explicit approval.
