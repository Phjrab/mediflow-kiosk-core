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

## 2026-09-21 — approved C1/C2 read-only device bootstrap

- Received explicit approval for read-only deployment only. Drafts, mutations, model/service transitions, raw-port changes, autostart, `.env`, database, model, and user-data changes remained out of scope.
- Preserved A's operational branch by merging `codex/admin-control` into `codex/admin-control-a-deploy` instead of replacing it. The pushed and deployed A merge is `1dffc7a`, descended from A's prior `6ee537f`; recovery branch `backup/pre-admin-control-20260921` points to the prior SHA.
- Deployed exact source `f0f0555` to B at `/home/jetson2/mediflow-ai/control/releases/f0f0555`. The original lifecycle cwd and manager metadata were left in place.
- Generated the dedicated management credential on B and transferred it directly from B to A. It never passed through the development Mac or command arguments and was not printed. Both copies are owner-only mode 0600. The one-time transfer identity and temporary A authorization were removed after a no-output digest comparison.
- Verified B's ED25519 host fingerprint before adding it to A. Installed a dedicated A-to-B tunnel identity restricted to port forwarding and `permitopen="127.0.0.1:8090"`.
- Started the B controller manually on `127.0.0.1:8090` as PID 35999 with `AI_CONTROL_DRAFTS_ENABLED=0` and `AI_CONTROL_MUTATIONS_ENABLED=0`. It has an exact private PID/start-tick record and no autostart entry.
- Started the A tunnel manually on `127.0.0.1:18090` as PID 1947132, forwarding only to B `127.0.0.1:8090`. It has an exact private PID/start-tick record and no autostart entry.
- Installed A's separate mode-0600 `admin-control-readonly.env`; the existing `.env` was not edited. A's same-origin admin route reached B through the tunnel while `model_manager` remained unloaded.
- A's kiosk processes were stopped before deployment and remained stopped. There was no running web process to restart, so no new kiosk daemon was started.

### Device evidence

- A deployment merge: 144 runnable tests passed, one skipped. B control suites: 11 passed. A read-only client/admin/generation/receipt suites: 9 passed.
- Authenticated B GETs for state, capabilities, models, current config, and events all returned successfully. GET capabilities reported drafts false, mutations false, and an empty operations list.
- B's managed general LLM retained PID 9205 and the same process start tick across deployment; port 8080 health stayed ready. MedGemma stayed stopped and port 8081 stayed free.
- B controller port 8090 and A tunnel port 18090 were loopback-only. The A same-origin overview returned chat-only/ready without loading the vision classifier.
- SHA comparisons confirmed A's `.env` and `database/database.db` were unchanged. A and B deployment checkouts were clean.
- A proposed POST-to-disabled-endpoints check was rejected by automatic approval review because the approval allowed authenticated GET verification only. No POST was sent; the device evidence uses GET capabilities plus existing mock tests.

No LLM or VLM was started, stopped, restarted, or switched. No cloud fallback, medical-quality evaluation, real-user-data test, or unverified co-residency test was performed.

## 2026-09-21 — C4 controller-authoritative ingress code/mock

- Continued from pushed `6fa9e91` on `codex/admin-control` with the existing
  read-only A/B deployment untouched. The repository had moved to
  `/Users/hajoonpark/자율설계/mediflow-kiosk-core`; the uncommitted C4 work was
  present there and was preserved.
- Added a private durable managed-ingress journal. Admission requires verified
  raw-bypass closure and the expected deployment generation. Active leases drain;
  transport loss after forwarding becomes `unknown`, closes admission, survives
  restart, and requires positive backend-completion evidence before reconciliation.
- Added a fixed loopback forwarder for the chat and VLM raw runtimes. It keeps
  their separate inference credentials, exposes only the two fixed API paths,
  strips control-only expectation fields, bounds bodies/responses, and emits an
  E3 receipt only after matching the applied runtime. Chat receipts are bound to
  the actual system-prompt digest received by ingress.
- Added sequential lifecycle adapters. The existing general LLM reuses
  `local_llm_service` exact PID ownership. The MedGemma adapter validates a
  private PID record against live UID/executable/argv/cwd/boot-id/start-tick
  evidence and never passes a mismatched or reused PID to its stop callback.
  Unmanaged engines and unverified co-residency block before any stop.
- Added one shared owner-only lifecycle-lock implementation for controller and
  CLI. It rejects relative paths, unsafe directories/files and final symlinks;
  a real cross-entrypoint flock-contention mock proves that a CLI action cannot
  enter while the controller owns the lock.
- Kept the general LLM default on port 8080 while adding strict, opt-in
  `LOCAL_LLM_HOST`/`LOCAL_LLM_PORT` support needed for an approved future raw
  loopback migration. No device environment was changed.
- Completed E3 runtime expectation/receipt persistence. Pinned runs send the
  expected artifact/runtime/config generation through local chat, reject a
  missing or mismatched receipt before success, and store the closed receipt in
  `explanations.runtime_receipt_json`. Existing databases migrate forward from
  schema version 3 to 4; no operational DB was opened or altered.
- Corrected operation commit order: the applied state is durable before admission
  reopens with the new generation. If reopening fails, rollback restores the
  previous actual and applied states or enters manual intervention.
- Added the review-only migration plan and configuration delta in
  `C4_MAINTENANCE_MIGRATION.md` and `C4_MAINTENANCE_MIGRATION.diff`.

### Tests

- Focused C4/E3 suite: 67 passed, then 31 passed after the final prompt/config
  receipt hardening.
- Available integrated local suite: 157 passed, 1 skipped, 0 failed after updating
  the expected research schema version to 4.
- `python -m py_compile`, `bash -n scripts/run_local_llm_candidate.sh`, and
  `git diff --check` passed.
- Committed the C4 implementation as `b870500` on `codex/admin-control`.
- The pre-existing Mac dependency exclusions remain: the two modules requiring
  unavailable `pytorch_grad_cam` and `qrcode` were not included. No package was
  installed and no medical-quality or real-device inference claim is made.

### Device and data scope

- No SSH/device command was run for this C4 task. A/B ports, services, processes,
  models, keys, private environment files, databases, and user data were not
  changed.
- Managed ingress activation, raw-port migration, process-manager bootstrap,
  synthetic device receipt verification, draft/mutation enablement, and a real
  apply/restore operation remain `BLOCKED_GATE` for a separate maintenance window.

## 2026-09-21 — approved C4 device maintenance

- Received explicit approval for the reviewed C4 maintenance sequence. Fixed two
  pre-device defects before changing inference: managed controller observation
  had to separate the ingress port from the raw runtime port (`29000e8`), and
  direct lifecycle CLI execution needed the repository import root (`6c2d9b1`).
  Local runnable regression reached 159 passed, one skipped before migration.
- Verified the existing general LLM PID 9205 against its mode-0600 record: PID,
  UID, executable, argv, cwd, boot-id and start-tick all matched. Port 8080 had
  zero established inference connections. B private state/config directories
  were owner-only, controller mutations were off, and there was no autostart.
- Deployed detached B releases without replacing the prior rollback releases.
  The final deployed runtime source is `c1e84bb`; B controller and ingress run from
  that release. The raw LLM manager/runtime cwd is the compatible `6c2d9b1`
  release because controller observation must match the exact process cwd.
- Created owner-only C4 and rollback environment files, the shared lifecycle
  lock, ingress journal, bootstrap applied state, and runtime receipt. Existing
  inference/admin credentials remained in their original owner-only mode-0600
  files and were never printed, logged, passed in argv, or copied to the Mac.
- Proved real shared-lock contention before lifecycle mutation: a second CLI
  action was rejected and PID/start-tick stayed unchanged.
- Stopped only exact-owned PID 9205 and restarted the same pinned Qwen artifact as
  PID 37141 on `127.0.0.1:18080`. A verified B:8080 reachable only through the
  managed ingress while B:8081/18080/18081 were unreachable from the network.
- Started ingress closed, verified sockets, then opened generation 1. A local B
  synthetic chat returned 200 with a matching closed runtime receipt and journal
  `open:0:0`. The bootstrap applied state is revision/generation `1/1`, profile
  `chat_only`.
- Restarted the B controller through exact PID validation. Final controller PID
  is 37652 on loopback 8090; final ingress PID is 37550 on network port 8080. A's
  existing tunnel PID 1947132 remained loopback-only on 18090.
- Changed only A's private `VLM_BASE_URL` to B:8080 after saving an owner-only
  backup. A's non-VLM `.env` digest stayed identical, `LLM_PROVIDER=local`, the
  general LLM URL stayed B:8080/v1, and no A web process was started.
- Found and fixed an inactive-upstream lease edge case (`c1e84bb`): connection
  refusal before an upstream request is sent now returns 503 and completes the
  lease instead of leaving it active. Actual A-to-B VLM-off verification returned
  `503 backend_unavailable` with journal `open:0:0`. Local runnable regression is
  now 160 passed, one skipped.
- Ran one approved actual synthetic apply/restore through `OperationCoordinator`.
  Operation `5adb27e4b8d74db0a3fa5768207f07c8` closed admission, drained, restarted
  exact-owned chat, received the injected verification failure, restored chat
  once, restored admission, and ended `rolled_back/synthetic_verify_failure`.
  Applied state remained `1:1:chat_only`; final chat PID is 37864, health is ready,
  and a post-restore A-to-B chat returned 200 with a matching receipt.

### Final device state and limits

- B sockets: ingress `0.0.0.0:8080`, raw chat `127.0.0.1:18080`, controller
  `127.0.0.1:8090`; 8081 and 18081 are closed. Admission is open with zero active
  and zero unknown leases.
- All key, C4 environment, applied receipt/state, lock, ingress DB and PID record
  files checked are owner-only mode 0600. No autostart entry was added.
- Controller capabilities still report drafts false, mutations false and zero
  operations. Permanent mutation was not enabled because the concrete MedGemma
  launcher/owner callback is not yet bound to controller bootstrap. MedGemma was
  not started, so no E1 device receipt or model-switch claim is made.
- No model file, key, operational/application DB, user data, CUDA/PyTorch setup,
  or medical-quality evaluation was changed or performed.
