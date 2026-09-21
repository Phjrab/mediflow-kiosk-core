# Admin Control Handoff

Current phase: C0-C3 CODE/MOCK complete and C1/C2 DEVICE_READ_ONLY deployed; C4-C5 remain PARTIAL/CODE/MOCK. The source implementation is `c7807e1`/`f0f0555`, based on `2ccd9f1`.

The existing LLM/VLM, F1, regression, and synthetic E0-E4 device evidence is preserved. A runs deployed checkout `1dffc7a` on `codex/admin-control-a-deploy`; B has release `/home/jetson2/mediflow-ai/control/releases/f0f0555`. A's `.env`, database and user data and B's inference keys, models and lifecycle records were not changed.

Real B apply is intentionally unavailable. The current inference ports do not yet provide controller-authoritative admission/in-flight leases, so a model change cannot safely prove drain completion. C4 must first complete mock concurrency/recovery work and an approved ingress/lifecycle migration plan.

Read-only device state:

- B controller PID 35999 listens only on `127.0.0.1:8090`; private PID record is under `/home/jetson2/.local/state/mediflow-ai/admin-control-runtime/`. It has no autostart entry.
- A tunnel PID 1947132 listens only on `127.0.0.1:18090` and forwards only to B loopback 8090; its private PID record is under `/home/jetson_orin_nano/.local/state/mediflow-ai/admin-control-tunnel/`. It has no autostart entry.
- A reads `/home/jetson_orin_nano/.config/mediflow-ai/admin-control-readonly.env`; the file enables reads but keeps drafts and mutations off. The management credential is a separate owner-only mode-0600 file on each device.
- Authenticated GET state/capabilities/models/current/events succeeded. Capabilities reports drafts false, mutations false and no operations. B's managed general LLM remained PID 9205 with its original start tick and healthy port 8080. MedGemma is stopped and port 8081 is free.
- A's kiosk was already stopped and remains stopped; no web process was available to restart. The same-origin route was instead exercised with the actual A virtualenv and did not load the classifier.

Validation: the A deployment merge passed 144 runnable tests with one skipped; B control suites passed 11; A focused device suites passed 9. The authenticated same-origin read, `.env`/DB hash preservation and exact process identity checks passed. The earlier A 141-test run predates this diff and is retained only as prior evidence.

Still blocked/not run:

- Managed chat/VLM ingress, raw-port closure, actual lifecycle adapter, device drain/switch/restore: BLOCKED_GATE.
- E3 general-LLM runtime receipt: blocked on managed ingress.
- Draft/plan device writes and disabled-endpoint POST probes: NOT_RUN. A proposed POST probe was rejected because the approval covered GET verification only; no POST was sent.
- Any actual B model change, device mutation test, medical quality evaluation, or real-user-data validation: NOT_RUN.

Next action: design and review controller-authoritative ingress plus the actual lifecycle adapter. Enabling drafts, operations, raw-port migration or any model/service transition requires a separate explicit approval and must preserve the current read-only rollback path.
