# Admin Control Worklog

## 2026-09-21 — C0 baseline and C1-C5 code/mock

- Read the complete attached Admin Control prompt pack and current repository handoff/worklog.
- Confirmed no `AGENTS.md`, source base `2ccd9f1`, A deploy `6ee537f`, B versioned release `2ccd9f1`, and clean working trees before work.
- Confirmed B 8080 general LLM was the only one of 8080/8081/8090 listening. Made no remote changes.
- Created `codex/admin-control` from the latest source branch rather than an historical prompt-pack SHA.
- Added a headless B control service with management authentication, bounded bodies, read endpoints, strict catalog, cached nullable telemetry, immutable drafts/plans, and operations disabled.
- Added a read-only runtime adapter that reuses `local_llm_service.inspect_service(..., remove_stale=False)` and represents unmanaged ingress activity as unknown.
- Added an isolated A management client with fixed node/origin, HTTPS or loopback-only transport, separate credential, response bound, timeout, and cache.
- Added existing `/admin/config` state UI, generation settings, runtime draft/plan flow, explicit disabled apply, stale/offline and text-GPU/vision-CPU display.
- Added versioned local-chat temperature/top-p/max-token snapshots. The current request snapshots once; OpenAI/Gemini paths are unchanged and no cloud fallback was added.
- Excluded admin config/control routes from vision model lazy initialization while preserving their own admin/CSRF checks.
- Added a private SQLite operation journal, idempotency conflict handling, one active operation, nonblocking lifecycle `flock`, accepted/validate/drain/stop/start/verify states, exact receipt persistence, one rollback attempt, and manual-intervention terminal state. Restart reconciliation never blindly replays a nonterminal operation.
- Added injected lifecycle mock tests for success, duplicate delivery, concurrent operation rejection, cancel-before-worker, prior-stopped restore, rollback failure, and controller restart.
- Added an opt-in research runtime expectation/receipt. E1/E2 run snapshots may pin node, artifact/manifest/runtime, config revision, deployment generation, effective config digest, and prompt digest. The MedGemma endpoint rejects drift before generation, and the worker refuses a mismatched receipt before prediction persistence.
- Added an A-side plan guard for queued/running/cancel-requested research jobs. It reports the counts and never cancels or rewrites a job.

### Tests

- New Admin Control tests: 13 C1-C4 tests, 3 generation tests, 2 admin surface tests, and 2 runtime receipt tests passed. The C4 journal suite also passed with `ResourceWarning` promoted to an error.
- Targeted existing regressions passed: 21 AI client, 7 MedGemma service, 6 experiment worker, 12 experiment store/admin, 6 survey/hybrid, 6 local lifecycle, 5 chat prompt, and 5 F1/evaluation tests.
- Available full local suite after C5: 144 passed, 1 skipped, 0 failed/error. Two pre-existing test modules could not import in the Mac system Python because `pytorch_grad_cam` and `qrcode` are absent; their five tests were not executed locally. No packages were installed to work around this.
- Python AST/compile checks, strict example registry load (2 models), and `git diff --check` passed.
- All six inline JavaScript blocks in `/admin/config` passed `node --check`.
- Committed the implementation as `c7807e1` and pushed `codex/admin-control` to `origin`.

### Changed files

- A: `eye_server.py`, `web/templates/admin_config.html`, `utils/ai_control_client.py`, `utils/ai_generation.py`, `utils/llm_client.py`.
- B control: `services/ai_control/{app,core,runtime,operations}.py`, `config/ai_control_registry.example.json`.
- Research receipt: `utils/runtime_receipt.py`, `utils/vlm_client.py`, `services/medgemma/app.py`, `experiments/{store,survey,worker}.py`.
- Configuration/docs/tests: `.env.example`, this admin-control documentation directory, and focused test modules.

No Jetson deployment, service start/stop, model transition, `.env`, DB, key, model, or user-data change was performed in this phase. The next action requires explicit read-only bootstrap approval as described in `READ_ONLY_RUNBOOK.md`.
