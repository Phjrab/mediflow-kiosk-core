# Admin Control Implementation Plan

| Phase | Scope | Status |
|---|---|---|
| C0 | Current source/device baseline, authority and trust boundary, gate list | DONE / DEVICE_READ_ONLY |
| C1 | Authenticated B state/capabilities/models/current/events, pure process observation, cached telemetry | CODE + MOCK |
| C2 | Separate A management client, same-origin admin proxy, existing `/admin/config` read UI | CODE + MOCK |
| C3 | Versioned local-chat sampling, runtime draft and validation plan, apply disabled | CODE + MOCK |
| C4 | Managed ingress, shared device lock, durable operation, drain/switch/rollback | PARTIAL / MOCK; device adapter and ingress migration BLOCKED_GATE |
| C5 | Research queue/run lock and effective B receipt | PARTIAL / CODE + MOCK; VLM opt-in receipt complete, E3 ingress receipt pending |
| C6 | Read-only deployment then approved device mutation verification | NOT_STARTED |

The next step is the C1/C2 read-only bootstrap: install a dedicated management credential and verified TLS or approved loopback tunnel, deploy the B controller with drafts and mutations off, then enable A read-only status. This changes trust files and starts a new controller process, so it requires the explicit bootstrap approval described in `READ_ONLY_RUNBOOK.md`. Writable ingress migration remains a separate maintenance change.
