# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | PARTIAL; exact VLM activation receipt and output-error classification verified, valid managed analysis BLOCKED_GATE |
| C6 | Read-only deployment then approved device mutation verification | `14d7dc3` DEPLOYED; output retry returned 502 and recovered fail-closed; controller read-only |

The approved C1/C2 bootstrap, C4 managed inference ingress, and `14d7dc3`
MedGemma output/lifecycle release are deployed. The A-to-B management
API remains on its loopback SSH tunnel, drafts/mutations are off, raw chat is
loopback-only, VLM is stopped, and network inference is exposed only through
managed ingress. Applied state is restored to exact `1:1:chat_only` after the
single retry reached VLM but returned `502 invalid_model_output` after a completed
70-second backend lease. The maintenance fixture's 64-token budget was below a
complete contract response; the undeployed guard now requires at least 256 while
production remains 512. A separately approved synthetic verification with a
valid budget is the remaining gate; E1/E2 is not complete.
