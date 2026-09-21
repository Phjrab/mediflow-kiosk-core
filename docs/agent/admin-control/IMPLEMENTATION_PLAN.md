# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS + CHAT_ROLLBACK VERIFIED; permanent mutation/MedGemma launcher binding BLOCKED_GATE |
| C5 | Research queue/run lock and effective B receipt | PARTIAL / CODE + MOCK; actual chat receipt verified, VLM device receipt BLOCKED_GATE |
| C6 | Read-only deployment then approved device mutation verification | CHAT ROLLBACK VERIFIED; permanent mutation BLOCKED_GATE |

The approved C1/C2 bootstrap and C4 managed inference ingress are deployed. The
A-to-B management API remains on its loopback SSH tunnel, and drafts/mutations
remain off. Raw chat is loopback-only, VLM is stopped, and the network-reachable
inference endpoint is the managed ingress. Permanent mutation enablement and a
real MedGemma service-manager binding remain a separate gate.
