# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | DEVICE_READ_ONLY |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | DEVICE_READ_ONLY; kiosk process remains stopped |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | DEVICE_INGRESS VERIFIED; exact chat recovery verified |
| C5 | Research queue/run lock and effective B receipt | PARTIAL; exact VLM activation receipt and output-error classification verified, valid managed analysis BLOCKED_GATE |
| C6 | Read-only deployment then approved device mutation verification | `1eb41c2` DEPLOYED; 224×224/512-token retry returned 502 and recovered fail-closed; controller read-only |

The approved C1/C2 bootstrap, C4 managed inference ingress, and `1eb41c2`
MedGemma output/lifecycle release are deployed. The A-to-B management
API remains on its loopback SSH tunnel, drafts/mutations are off, raw chat is
loopback-only, VLM is stopped, and network inference is exposed only through
managed ingress. Applied state is restored to exact `1:1:chat_only` after the
single 224×224, 512-token retry reached VLM but returned
`502 invalid_model_output` after a completed 74-second backend lease. This rules
out the prior 64-token budget as the sole cause. The deployed guard still rejects
budgets below 256 before generation; production remains 512. Safe structural
diagnosis of the managed llama.cpp output boundary is the next code gate. Any
further synthetic inference requires separate approval; E1/E2 is not complete.
