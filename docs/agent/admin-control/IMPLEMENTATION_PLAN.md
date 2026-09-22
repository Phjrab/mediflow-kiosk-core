# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | PARTIAL; fixed MedGemma manager device-start verified, VLM request receipt BLOCKED_GATE |
| C6 | Read-only deployment then approved device mutation verification | FAIL-CLOSED RECOVERY COMPLETE; controller read-only, reconciliation/retry BLOCKED_GATE |

The approved C1/C2 bootstrap, C4 managed inference ingress, and the `8a9efa3`
MedGemma service-manager binding are deployed. The A-to-B management API remains
on its loopback SSH tunnel, and drafts/mutations are off. Raw chat is loopback-
only, VLM is stopped, and the network-reachable inference endpoint is managed
ingress. Applied state is restored to `1:1:chat_only` after the failed C5 window.
The undeployed postmortem fix closes the receipt schema and port-release races
and includes a mock-tested, audit-preserving reconciliation path. Its device
deployment and explicit reconciliation, followed by a separately approved retry,
are the remaining gates.
