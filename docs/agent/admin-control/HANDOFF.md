# Admin Control Handoff

Current phase: C0-C3 CODE/MOCK complete; C4-C5 PARTIAL/CODE/MOCK on pushed branch `codex/admin-control`. The implementation commit is `c7807e1`, based on `2ccd9f1`.

The existing LLM/VLM, F1, regression, and synthetic E0-E4 device evidence is preserved. Jetson A and B have not received Admin Control code. B remains in its prior general-LLM state; no model, service, `.env`, database, credential, or user data was changed by this task.

Real B apply is intentionally unavailable. The current inference ports do not yet provide controller-authoritative admission/in-flight leases, so a model change cannot safely prove drain completion. C4 must first complete mock concurrency/recovery work and an approved ingress/lifecycle migration plan.

Implemented but not device-enabled:

- Headless B read API, strict private registry, nullable cached telemetry, pure existing-manager observation.
- A same-origin admin client/UI with separate request/runtime authorities and versioned local generation snapshots.
- Draft/plan and durable operation core with mock lifecycle, idempotency, recovery, and rollback.
- Research active-job plan guard and opt-in E1/E2 MedGemma runtime receipt.

Validation: 144 runnable local tests passed and one platform test skipped. Two existing modules (five tests) were not runnable in the Mac system Python because `pytorch_grad_cam` and `qrcode` are absent. The previously recorded A 141-test device run predates this Admin Control diff and must not be reported as validation of these new files.

Still blocked/not run:

- B controller deployment and A read-only deployment: NOT_RUN.
- Management key/CA installation and TLS/tunnel validation: NOT_RUN.
- Managed chat/VLM ingress, raw-port closure, actual lifecycle adapter, device drain/switch/restore: BLOCKED_GATE.
- E3 general-LLM runtime receipt: blocked on managed ingress.
- Any actual B model change, device mutation test, medical quality evaluation, or real-user-data validation: NOT_RUN.

Next action: obtain explicit bootstrap approval for a dedicated management credential plus verified transport, then deploy only the B read controller and A read-only integration with both draft and mutation flags off. Do not enable mutations or switch the running model in that step.
