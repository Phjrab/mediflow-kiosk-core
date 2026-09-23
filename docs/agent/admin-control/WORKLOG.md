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

## 2026-09-22 — approved C5 MedGemma lifecycle window and fail-closed recovery

- Implemented and pushed `8a9efa3` with the fixed MedGemma launcher, exact
  UID/executable/argv/cwd/boot-id/start-tick owner manager, controller mutation
  bootstrap, shared lifecycle lock, managed ingress binding, and private runtime
  receipt handling. Local runnable regression before deployment was 172 passed
  and one skipped; the focused clean detached B release suites passed 29 Admin
  Control, 13 MedGemma, and 10 local-LLM tests.
- Deployed the clean detached release at
  `/home/jetson2/mediflow-ai/control/releases/8a9efa3`. Added only the owner-only
  C5 path configuration needed by the manager. Existing keys, models, `.env`,
  CUDA/PyTorch, application DB, user data, rollback files, ingress, A tunnel, and
  raw chat configuration were preserved.
- Passed the identity, private-file mode, model-manifest, real shared-lock,
  zero-active/zero-unknown lease, raw-bypass, exact applied-receipt, and
  no-co-residency gates. Restarted only the exact-owned controller into the new
  release, then temporarily enabled drafts/mutations for the approved single
  sequence.
- Operation `3f0dd84d4d5b4e4d89c74e16449cedd9` completed the exact-owned
  chat→MedGemma switch. Applied state reached `2:2:vlm_only`; chat was stopped,
  MedGemma was ready on loopback `127.0.0.1:18081`, and the two heavy engines
  were never resident together.
- The synthetic VLM request was rejected with HTTP 409 before ingress created a
  lease or MedGemma began generation. This is not E1/E2 inference evidence and
  no medical-quality claim is made. The A and B role-prompt SHA-256 values were
  identical. The successful operation had stored an extra `observed_profile`
  field in its applied receipt while the E3 expectation schema requires exactly
  seven fields; this receipt-boundary defect explains the pre-admission 409.
- The requested MedGemma→chat operation
  `e287c3094eb740ae8332a92d822de76f` entered
  `manual_intervention_required/rollback_failed`. Device evidence showed no
  chat start log and no second MedGemma start log, making the VLM stop/port-release
  boundary the strongest failure location. The deployed code recorded only the
  generic rollback code, so the exact primary exception cannot be claimed.
- Followed the approved fail-safe immediately: admission remained closed while
  both engines and both raw ports were confirmed stopped; an exact, locked
  recovery restored the original receipt and applied state to `1:1:chat_only`,
  started only the pinned general LLM (PID 42774), and reopened admission with
  zero active and zero unknown leases. The controller was then restarted in the
  same `8a9efa3` release with drafts/mutations disabled (PID 42828).
- Final A-side verification passed: capabilities report drafts false, mutations
  false, managed ingress true and no operations; current state is
  `1:1:chat_only`; synthetic chat returned 200 with an exact receipt; only B:8080
  is network-reachable while 8081/18080/18081 are not.

### Postmortem code and tests

- Locally removed `observed_profile` from the runtime receipt and now validates
  the exact closed expectation schema before persistence.
- Locally made the MedGemma owner manager wait for actual loopback port release
  after exact process termination, preventing an immediate stopped-process/open-
  socket race from being interpreted as an unmanaged runtime.
- Locally added non-sensitive primary and rollback error codes to future
  `manual_intervention_required` audit results. Raw exception text, prompts, and
  credentials are not persisted.
- Added a local, explicit reconciliation endpoint that never changes a process or
  applied configuration. It acquires the shared lifecycle lock and will preserve
  the failed row as `reconciled` only after exact applied revision/generation/
  profile, engine receipt, open admission, closed raw bypass, and zero active/
  unknown lease evidence all match. Unsafe evidence leaves the row unchanged.
- Focused postmortem suite: 29 passed before the reconciliation addition; its
  focused Admin Control suite passed 28. Full runnable local suite: 176 passed,
  one skipped, zero failures/errors. The two pre-existing unavailable optional
  modules (`pytorch_grad_cam`, `qrcode`) remain excluded; no dependency was
  installed. `git diff --check` passed.
- These postmortem changes have not been deployed to either Jetson and the
  synthetic transition was not retried. The historical manual-intervention row
  remains in B's owner-only operation journal for audit and blocks a future
  operation until the new evidence-backed reconciliation code is separately
  approved, deployed, and explicitly invoked.
- Committed and pushed the postmortem code/mock baseline as `30f3ee4` on
  `codex/admin-control`.

No model file, key, operational/application DB, user data, CUDA/PyTorch setup,
cloud fallback, real-user-data inference, or medical-quality evaluation was
changed or performed.

## 2026-09-22 — approved reconciliation deployment and single VLM retry

- Revalidated local/remote HEAD `27c5da9`, a clean worktree, exact-owned chat PID
  42774 and controller PID 42828, `1:1:chat_only`, open admission, raw-bypass
  closure, zero active/unknown leases, exact seven-field receipt, and the
  preserved manual-intervention row before deployment.
- Created the clean detached B release
  `/home/jetson2/mediflow-ai/control/releases/27c5da9`. B release tests passed 31
  Admin Control, 15 MedGemma, and 10 local-LLM tests. The real shared lifecycle
  lock rejected a competing CLI action and no model process changed during
  bootstrap.
- Restarted only the exact-owned controller in `27c5da9` with temporary
  drafts/mutations. Through the authenticated A tunnel, the new reconciliation
  API rechecked the actual `1:1:chat_only` state and changed operation
  `e287c3094eb740ae8332a92d822de76f` from
  `manual_intervention_required` to `reconciled`. The original
  `rollback_failed` error and row identity remain preserved; no row was deleted
  or overwritten and the applied state did not change.
- The one approved retry operation `2059f3ef40e049509cb688d8105d194d`
  successfully switched chat→MedGemma. Applied state reached `2:2:vlm_only`
  with an exact seven-field receipt. Chat was stopped, MedGemma PID 43386 was
  exact-owned and ready on loopback 18081, admission was open at generation 2,
  and active/unknown leases were zero. No GPU-heavy co-residency occurred.
- The 16×16 synthetic-image request then ran through managed ingress for about
  72 seconds. Its generation-2 VLM lease was durably `completed`, proving the
  request passed ingress and reached the backend, but the endpoint returned HTTP
  400 `invalid_request`. This is not a successful VLM receipt or E1/E2 result.
  No user image, medical data, or medical-quality evaluation was used.
- Followed the approved failure branch without retry: closed admission, confirmed
  zero active/unknown leases, stopped exact-owned MedGemma, waited for loopback
  18081 to be released, restored the original seven-field receipt and
  `1:1:chat_only`, then started only the pinned general LLM as PID 43513.
- Restarted only the controller into read-only mode in the same `27c5da9` release
  as PID 43566. Final A verification reports drafts false, mutations false, no
  operations, managed ingress true, chat HTTP 200 with matching receipt, and only
  B:8080 reachable from the network. Final B audit reports open admission at
  generation 1, zero active/unknown leases, MedGemma stopped, no active
  operation, the historical row reconciled, and the retry forward operation
  preserved as succeeded.

### HTTP 400 postmortem code/mock

- The completed 72-second lease and request path show that the second failure
  occurred after backend generation began, unlike the earlier pre-admission 409.
  The deployed service collapses a strict JSON parse failure into the same 400
  used for client validation and logs no response content, so the exact generated
  text cannot and should not be claimed.
- Verified without inference that the pinned `llama-mtmd-cli` supports
  `--log-disable`. Locally added that flag so CLI diagnostics cannot contaminate
  the captured JSON channel.
- Added a distinct `ModelOutputError` response: completed generation that does
  not yield one contract JSON object now returns HTTP 502
  `invalid_model_output`, while actual malformed client requests remain HTTP
  400. Raw model output is never logged or persisted.
- Focused postmortem tests passed 33. Full runnable local suite passed 177 with
  one skipped and zero failures/errors. The two pre-existing optional modules
  requiring unavailable `pytorch_grad_cam` and `qrcode` remain excluded; no
  dependency was installed.
- This HTTP-output postmortem code is not deployed to either Jetson, and no
  further model start, controller mutation window, or synthetic inference was
  attempted after fail-closed recovery.
- Committed and pushed the HTTP-output postmortem baseline as `f6e428d` on
  `codex/admin-control`.

Existing model files, key contents, `.env`, application/user databases, user
data, CUDA/PyTorch, A tunnel, managed ingress, and cloud provider behavior were
preserved. Only the explicitly approved Admin Control operation journal
reconciliation was written.

## 2026-09-22 — approved output-channel deployment and single VLM retry

- Revalidated clean local/remote HEAD `14d7dc3` and the complete final device
  gate: exact `1:1:chat_only`, chat health, open admission, raw-bypass closure,
  zero active/unknown leases, exact seven-field receipt, reconciled historical
  operation, both successful forward-operation rows, and read-only controller.
- Created clean detached B release
  `/home/jetson2/mediflow-ai/control/releases/14d7dc3`. B tests passed 31 Admin
  Control, 16 MedGemma, and 10 local-LLM tests. Mutation bootstrap, preserved
  audit rows, and real shared-lock contention passed without changing a model.
- Restarted only the exact-owned controller in `14d7dc3` with temporary
  drafts/mutations. The one approved operation
  `37fdb2ca80f64fd88b73d915ee29e38e` successfully switched chat→MedGemma.
  Applied state reached `2:2:vlm_only` with an exact seven-field receipt; chat
  was stopped, MedGemma PID 43861 was exact-owned and ready, active/unknown
  leases were zero, and no co-residency occurred.
- Sent one 16×16 synthetic request through managed ingress. The generation-2 VLM
  lease ran from `2026-09-22T02:21:10Z` to `02:22:20Z` and ended `completed`.
  The deployed output-channel hardening returned HTTP 502
  `invalid_model_output`, with only the non-sensitive warning
  `model output rejected without response content`. Raw output was not logged or
  persisted. This is not an E1/E2 success or medical-quality result.
- Followed the approved failure branch immediately and did not retry: closed
  admission, confirmed zero active/unknown leases, stopped exact-owned MedGemma,
  verified loopback 18081 release, restored the original receipt and
  `1:1:chat_only`, and started only pinned chat as PID 43988.
- Restarted only the controller into read-only mode in `14d7dc3` as PID 44037.
  Final A verification reports drafts false, mutations false, no operations,
  managed ingress true, chat HTTP 200 with matching receipt, and only B:8080
  network-reachable. Final B audit reports open generation 1, zero active/unknown
  leases, MedGemma stopped, no active operation, and all historical rows intact.

### Generation-budget postmortem code/mock

- The maintenance fixture requested only 64 new tokens, while the closed analysis
  schema requires seven fields and the production `VLMConfig` default is 512.
  The earlier direct custom-API synthetic probe returned a valid contract object
  in 73.253 seconds. The similar 70-second completed lease plus the too-small
  maintenance budget is the strongest available configuration explanation; raw
  generated text was intentionally unavailable, so truncation is not claimed as
  directly observed fact.
- Locally added `MIN_ANALYSIS_NEW_TOKENS=256`. Requests below the minimum now fail
  before generation as client HTTP 400; production's 512-token default remains
  unchanged. This prevents an impossible budget from consuming a full model run
  and later appearing as a backend output failure.
- Focused postmortem tests passed 34. Full runnable local suite passed 178 with
  one skipped and zero failures/errors. The two pre-existing optional modules
  requiring unavailable `pytorch_grad_cam` and `qrcode` remain excluded; no
  dependency was installed.
- The minimum-budget change is not deployed to either Jetson. No additional
  model start, controller mutation window, or synthetic inference was attempted
  after fail-closed recovery.
- Committed and pushed the generation-budget guard as `8f2b62b` on
  `codex/admin-control`.

Model files, key contents, `.env`, application/user databases, user data,
CUDA/PyTorch, managed ingress, A tunnel, and cloud provider behavior were
preserved. No medical-quality evaluation or real-user-data inference occurred.

## 2026-09-22 — approved 512-token managed VLM verification and fail-closed recovery

- Revalidated clean local/remote HEAD `1eb41c2` and the complete maintenance
  gate before changing a process: exact-owned healthy chat, exact
  `1:1:chat_only`, open admission, raw-bypass closure, zero active/unknown
  leases, the exact seven-field runtime receipt, all prior operation rows, and
  a read-only controller.
- Created the clean detached B release
  `/home/jetson2/mediflow-ai/control/releases/1eb41c2`. Its focused suites passed
  31 Admin Control, 17 MedGemma, and 10 local-LLM tests. Mutation bootstrap and
  real shared-lock contention also passed without changing a model process.
- Restarted only the exact-owned controller in `1eb41c2` with temporary
  drafts/mutations. The single approved operation
  `851d43b10e16474295d03ea8aaeb69fc` successfully switched
  chat→MedGemma. Applied state reached exact `2:2:vlm_only`; chat was stopped,
  MedGemma PID 44300 was exact-owned and ready, admission was open with zero
  active/unknown leases, and the two GPU-heavy engines were never resident
  together.
- Sent exactly one managed request using a generated 224×224 split red/blue PNG
  and `max_new_tokens=512`. Its generation-2 VLM lease ran from
  `2026-09-22T02:38:03Z` to `02:39:17Z` and ended `completed`, but the endpoint
  returned HTTP 502 `invalid_model_output`. The service logged only
  `model output rejected without response content`; raw model output, the image,
  and the prompt were not logged or persisted.
- The same output-contract failure at 512 tokens rules out the earlier 64-token
  budget as the sole cause. The 256-token lower bound remains a useful early
  request guard, but it does not make managed output valid. Because raw output
  was deliberately unavailable, the exact generation/parser mismatch remains
  unknown and no stronger cause is claimed.
- Followed the approved failure branch immediately and made no inference retry:
  closed admission, confirmed zero active/unknown leases, stopped exact-owned
  MedGemma, verified loopback 18081 release, restored the original receipt and
  exact `1:1:chat_only`, and started only the pinned general LLM as PID 44429.
- Restarted only the exact-owned controller into read-only mode in the same
  `1eb41c2` release as PID 44478. Final A verification reports drafts false,
  mutations false, no operations, managed ingress true, chat HTTP 200 with a
  matching receipt, and only B:8080 network-reachable. Final B audit reports
  open generation 1, zero active/unknown leases, MedGemma stopped, no active
  operation, the historical reconciled row and all three successful forward
  operation rows preserved.

E1/E2 remains incomplete because the managed request did not return HTTP 200,
`vision_ingested=true`, a schema-valid analysis object, and a matching runtime
receipt. Existing model files, keys, owner-only environment and rollback files,
application/user databases, user data, CUDA/PyTorch, A tunnel, cloud fallback,
and autostart configuration were unchanged. No real-user-data inference or
medical-quality evaluation was performed.

### Post-window structural diagnostics (local code and mock only)

- Commit `6d522da` classifies a rejected llama.cpp channel as only `empty`,
  `no_object_start`, `invalid_json`, `non_object`, or `trailing_data`. The HTTP
  contract remains 502 `invalid_model_output` and still never logs generated
  text, prompts, images, credentials, or raw response bytes.
- Added mocks proving that private generated text is absent from the diagnostic
  and that a harmless preamble followed by exactly one JSON object remains
  accepted.
- Focused MedGemma suites passed 19/19. The full runnable local suite passed
  180 with one skipped. Complete discovery attempted 182 and had only the two
  pre-existing unavailable optional imports, `pytorch_grad_cam` and `qrcode`;
  no package was installed.
- This diagnostic commit was not deployed to either Jetson. No additional model
  start, controller restart, mutation, or inference occurred after fail-closed
  recovery.

## 2026-09-22 — approved bounded-output deployment and single verification

- Revalidated clean local/remote HEAD `c821ec7`, exact `1:1:chat_only`, healthy
  exact-owned chat, open admission, raw-bypass closure, zero active/unknown
  leases, the exact seven-field receipt, a read-only controller, and every
  preserved operation row before deployment.
- Created clean detached B release
  `/home/jetson2/mediflow-ai/control/releases/c821ec7`. B release tests passed
  31 Admin Control, 19 MedGemma, and 10 local-LLM tests. Mutation bootstrap and
  real shared-lock contention passed without changing a model process.
- Restarted only the exact-owned controller into temporary mutations as PID
  44756. Operation `2d1b2db5abaf4b0c911c4b3e15551549` successfully switched
  chat→MedGemma. Applied state reached exact `2:2:vlm_only`; MedGemma PID 44797
  was exact-owned and ready, chat was stopped, admission was open with zero
  active/unknown leases, and no GPU-heavy co-residency occurred.
- Sent exactly one 224×224 split red/blue synthetic request with
  `max_new_tokens=512`. Its generation-2 lease ran from
  `2026-09-22T03:06:24Z` to `03:07:39Z` and ended `completed`, but the response
  was HTTP 502 `invalid_model_output`. The newly deployed bounded diagnostic was
  `stdout=empty,stderr=empty`; no model text, prompt, image, credentials, or
  response bytes were logged or persisted.
- Closed admission immediately. The first close audit accidentally loaded the
  prior `1eb41c2` code root and therefore reported a cwd metadata mismatch while
  admission was already closed and leases were zero. No process action was taken
  from that result. Re-running the audit against `c821ec7` proved PID 44797 was
  exact-owned before the recovery continued.
- Stopped exact-owned MedGemma, verified port 18081 release, restored the
  original receipt and exact `1:1:chat_only`, and started only pinned chat as PID
  44953. Restarted only the controller into read-only `c821ec7` as PID 45002.
  Final A verification reports chat HTTP 200 with matching receipt, drafts and
  mutations false, no operations, and only B:8080 network-reachable. Final B
  audit reports open generation 1, zero active/unknown leases, VLM stopped, no
  active operation, and all historical and forward operation rows preserved.

### Confirmed logger cause and local-only fix

- Read-only inspection of pinned llama.cpp source commit
  `391fac16460f15233a7740550d858ac96df3419d` shows that `mtmd-cli` emits every
  generated token through `LOG(...)`, while `--log-disable` pauses the entire
  common logger. This exactly explains a successful process exit with empty
  stdout and stderr; it is no longer only a hypothesis.
- Local commit `70774a5` removes `--log-disable` and selects
  `--verbosity 0 --log-colors off --no-log-prefix --no-log-timestamps` instead.
  At this pinned revision, verbosity 0 preserves only generic `LOG(...)` output
  while excluding error, warning, info, trace, and debug diagnostics from the
  captured JSON channel.
- Focused MedGemma suites passed 19/19 and the runnable local suite passed 180
  with one skipped. This fix was not deployed and no further controller restart,
  model start, or inference was attempted after recovery.

E1/E2 remains incomplete. Existing model files, keys, environment and rollback
files, application/user databases, user data, CUDA/PyTorch, A tunnel, cloud
fallback, and autostart configuration were unchanged. No real-user-data
inference or medical-quality evaluation was performed.

## 2026-09-22 — approved logger-fix deployment and managed VLM success

- Revalidated clean local/remote HEAD `ee7e03e`, exact `1:1:chat_only`, healthy
  exact-owned chat, open admission, raw-bypass closure, zero active/unknown
  leases, the exact seven-field receipt, a read-only controller, and all
  preserved operation rows before deployment.
- Created clean detached B release
  `/home/jetson2/mediflow-ai/control/releases/ee7e03e`. B release suites passed
  31 Admin Control, 19 MedGemma, and 10 local-LLM tests. Mutation bootstrap and
  real shared-lock contention passed without changing a model process.
- Restarted only the exact-owned controller into temporary mutations as PID
  45817. Operation `01e9eaf212064800becdce1c6f2a1d6f` successfully switched
  chat→MedGemma. Applied state reached exact `2:2:vlm_only`; MedGemma PID 45858
  was exact-owned and ready, chat was stopped, admission was open with zero
  active/unknown leases, and no GPU-heavy co-residency occurred.
- Sent exactly one 224×224 split red/blue synthetic request with
  `max_new_tokens=512`. It returned HTTP 200 in 74.62 seconds with
  `vision_ingested=true`, a strict-schema `abstain` analysis, and a matching
  runtime receipt. The generation-2 lease ran from `2026-09-22T03:34:15Z` to
  `03:35:30Z` and ended `completed`. The client emitted only contract-validation
  metadata; model text, prompt, image, credentials, and response bytes were not
  printed, logged, or persisted.
- Closed admission after the single success, confirmed zero active/unknown
  leases, stopped exact-owned MedGemma, verified port 18081 release, restored
  the original receipt and exact `1:1:chat_only`, and started only pinned chat as
  PID 45982. Restarted only the controller into read-only `ee7e03e` as PID 46032.
- Final A verification reports chat HTTP 200 with a matching receipt, drafts and
  mutations false, no operations, and only B:8080 network-reachable. Final B
  audit reports open generation 1, zero active/unknown leases, VLM stopped, no
  active operation, and all historical and forward operation rows preserved.

The Admin Control managed VLM contract gate is now complete for one synthetic
engineering image. This is image-ingestion, response-contract, receipt, and
sequential lifecycle evidence only. It is not real-data, E2 survey-worker, load,
thermal, accuracy, or medical-quality evidence. Existing model files, keys,
environment and rollback files, application/user databases, user data,
CUDA/PyTorch, A tunnel, cloud fallback, and autostart configuration were
unchanged.

## 2026-09-22 — approved managed-ingress E2 attempt and fail-closed recovery

- Revalidated the approved preconditions before mutation: B release `ee7e03e`,
  exact-owned healthy chat, exact `1:1:chat_only`, open admission, closed raw
  bypass, zero active/unknown leases, and the exact seven-field runtime receipt.
- Created a new private research store at
  `/home/jetson_orin_nano/mediflow-ai/research/admin-e2-managed-20260922-c11`
  with mode 0700 and owner-only files. It reused only the existing normalized
  224x224 red/blue engineering fixture and created new identifiers: sample
  `c69d553984774e7e92103db399a3a86d`, run
  `93efe0ad577942ad888022b2261b08e8`, and job
  `109efdbfb7a34ef0a3756db9828d9d9b`.
- Froze one bounded `eye-survey-1.0` record with digest
  `6ec89117c833a9d5e2cfc6397f6c23971b3e55e25f148371db39f133ef08f150`.
  The isolated database contained one sample and survey before execution; no
  prior research row or operational database row was reused or overwritten.
- Temporarily enabled controller mutations and performed the one approved
  chat-to-MedGemma transition. Operation
  `4b289618a6a740359653a74d566091e7` succeeded, reaching exact
  `2:2:vlm_only` with no chat/VLM co-residency and zero leases.
- Invoked the E2 worker exactly once. The worker terminally marked the isolated
  job `failed` with bounded error `misconfigured` before any managed-ingress VLM
  lease or backend generation began. It persisted no prediction and did not
  emit model output, prompt, image, response bytes, or key material. Per the
  approved stop condition, no retry was attempted.
- Immediately closed admission, stopped exact-owned MedGemma, confirmed raw VLM
  port release, restored the original receipt and exact `1:1:chat_only`, and
  disabled drafts/mutations. Final B audit recorded read-only controller PID
  46468, healthy exact-owned chat PID 46419, VLM stopped, open admission, zero
  active/unknown leases, and every prior operation row plus the new successful
  transition row preserved.
- Final isolated-store audit found one sample, one survey, one run, one failed
  job, and zero predictions. The survey digest matched, the private tree stayed
  owner-only, and SHA-256 baselines for A's `.env`, operational database, and
  previous research database were unchanged.

### Root cause and source evidence

- Read-only diagnosis showed worker-mode validation passed while
  `VLMConfig.from_env` returned `misconfigured`. The endpoint, model, numeric
  limits, and owner-only key file independently validated.
- A's deployed branch is at `1ec6f31` and its `utils/ai_config.py` reads only
  inline `VLM_API_KEY`. It therefore cannot consume the approved
  `VLM_API_KEY_FILE` without violating the no-inline-key constraint.
- Current `codex/admin-control` already contains the safe file-secret path and
  regression test from `8a9efa3`: `VLMConfig.from_env` calls
  `secret(env, 'VLM')`, which accepts an owner-only file while preserving the
  same bounded `misconfigured` error externally. Focused local tests passed: 22
  AI-client, 6 experiment-worker, and 6 survey/hybrid tests.
- This diagnosis did not change A or B. Deploying the existing safe client code
  to A and attempting a new isolated E2 run both require new explicit scope.
- Prepared the review-only two-file delta in `A_VLM_KEYFILE_CLIENT.diff` and its
  gated device procedure in `A_VLM_KEYFILE_CLIENT_MIGRATION.md`. Neither was
  applied to a Jetson.

The managed-ingress E2 survey-worker gate remains incomplete because the job did
not succeed and no analysis or matching runtime receipt was persisted. This was
an engineering integration attempt only; no real-user-data inference, accuracy
measurement, or medical-quality evaluation was performed.

## 2026-09-22 — approved Jetson A owner-only VLM key-file client deployment

- Started from clean A branch `codex/admin-control-a-deploy` at exact head
  `1ec6f31`. Recorded content-free hashes for `.env`, the operational database,
  both research databases, and the owner-only VLM key file. The key file was
  owned by the device user with mode 0600. No A web process was running.
- Revalidated B before applying source: release `ee7e03e`, exact
  `1:1:chat_only`, healthy exact-owned chat PID 46419, controller PID 46468,
  VLM stopped, open admission, raw bypass closed, zero active/unknown leases,
  exact seven-field receipt, and drafts/mutations disabled.
- Transferred the review-only patch to an A temporary path and verified its
  digest matched the repository artifact. `git apply --check` passed. Applied
  exactly `utils/ai_config.py` and `tests/test_ai_clients.py`; no other tracked
  file changed.
- A focused tests passed: 22 AI-client, 6 experiment-worker, and 6
  survey/hybrid tests. The first configuration-only check sourced the unchanged
  operational `.env`, which intentionally has no VLM block, and stopped at the
  backend precondition before reading the key. A corrected no-network check used
  the existing managed-ingress endpoint/model values plus the owner-only key
  file and passed with no inline key and no request.
- Committed the exact two-file change on A as `f53a1c6` (`fix: load VLM
  credential from owner-only file`) and pushed
  `codex/admin-control-a-deploy`. The A working tree and remote tracking branch
  were clean and equal afterward.
- No web process existed before or after deployment, so no process was started
  or restarted. Post-apply hashes for `.env`, the operational database, both
  research databases, and the key file matched their preflight values. Key mode
  remained 0600 and the temporary transferred patch was removed.
- Final B verification again passed unchanged at `ee7e03e`, exact
  `1:1:chat_only`, with chat PID 46419, controller PID 46468, VLM stopped, open
  admission, zero active/unknown leases, and drafts/mutations disabled.

No E2 job or inference request ran in this deployment. No model process,
controller mutation, port, key, environment file, database, user data, model
file, CUDA/PyTorch, cloud fallback, or medical-quality status changed. A future
E2 attempt still requires a new isolated store and identifiers plus separate
approval; the prior failed job remains immutable.

## 2026-09-22 — second approved E2 window stopped by conservative readiness audit

- Began from clean source HEAD `4a68a6c`, A deployment `f53a1c6`, and B release
  `ee7e03e`. A's owner-only VLM key file loaded without an inline key. B passed
  exact owner, healthy chat, exact `1:1:chat_only`, open admission, raw-bypass
  closure, zero active/unknown leases, seven-field receipt, mutation bootstrap,
  and real shared-lock contention gates.
- Created private mode-0700 store
  `/home/jetson_orin_nano/mediflow-ai/research/admin-e2-managed-20260922-c12`.
  It contains new synthetic sample `a8c20e405ac04c1f841056af802ae187`
  and one frozen `eye-survey-1.0` record with digest
  `6ec89117c833a9d5e2cfc6397f6c23971b3e55e25f148371db39f133ef08f150`.
  The 224x224 fixture digest remained
  `e85c72bc93d05149bac9be4d0d03f5ffcb2240b294d9305c818a8cad92f2f911`.
- Restarted only the exact-owned controller with temporary mutations as PID
  46742. Forward operation `dd35e4c05ae74279bb38a0e710ae9492` stopped chat
  and started exact-owned MedGemma without co-residency, then recorded
  `succeeded` at `2:2:vlm_only`.
- The independent pre-worker audit used the generic unauthenticated health probe
  against MedGemma's protected `/readyz` route and returned
  `vlm_ready=false`. Process ownership, applied state, receipt, admission,
  raw-bypass closure, and zero leases all matched. Because the bounded check was
  treated as a mandatory gate, no C12 run or job was created, no worker or
  inference request ran, and no retry followed.
- Closed admission immediately. Recovery operation
  `88a4afb4ce81463fa1ffcabe27cd1431` stopped exact-owned MedGemma and restored
  healthy chat. It advanced the controller metadata to `3:3:chat_only`, so the
  preserved receipt from reconciled operation `e287c3094eb740ae8332a92d822de76f`
  was used under the shared lifecycle lock to restore the original exact
  `1:1:chat_only` metadata and ingress generation without another model restart.
- Restarted only the controller as read-only PID 46899. Final B audit passed with
  healthy chat PID 46810, VLM stopped and port released, open admission, zero
  active/unknown leases, the exact seven-field receipt, drafts/mutations false,
  no active operation, and all historical plus both new operation rows preserved.
- Final A audit found exactly one sample and survey and zero runs, jobs, and
  predictions in C12. The previous failed job
  `109efdbfb7a34ef0a3756db9828d9d9b` remained unchanged. A's `.env`, operational
  DB, source research DB, A source HEAD, and all private modes remained unchanged.

### Local authenticated readiness hardening

- Post-recovery source inspection established that MedGemma `/readyz` requires
  its owner-only bearer credential. The unauthenticated audit result cannot
  establish that the service was unready. The existing MedGemma manager had
  already passed its authenticated readiness loop before the forward operation
  completed.
- Added an optional readiness probe to the exact-owned process adapter. The
  MedGemma bootstrap now supplies `medgemma_service.ready`, which reads the
  owner-only credential and checks the fixed loopback `/readyz` route without
  exposing the key. A start with a false authenticated probe raises
  `start_not_ready`; the exact-owned process remains represented as running so
  operation rollback can stop it before restoring chat. A running-but-not-ready
  snapshot withholds its receipt, so later verification also fails closed.
- Added a regression proving a not-ready MedGemma start fails and remains safely
  stoppable by exact PID ownership. Local Admin Control tests passed 32 and
  MedGemma tests passed 19; source compilation and `git diff --check` passed.
- This readiness fix is local only. It was not deployed to A or B, and no further
  device mutation or inference was attempted after recovery.

This window produced lifecycle/readiness evidence only. E2 remains incomplete:
there is no C12 job, HTTP response, analysis, prediction, or runtime receipt to
score. No model output, prompt, image, response bytes, or key was printed or
persisted, and no medical-quality evaluation was performed.

## 2026-09-22 — authenticated readiness hardening deployed read-only on B

- Revalidated B release `ee7e03e` before deployment: controller PID 46899 was
  exact-owned and read-only, chat PID 46810 was healthy, MedGemma was stopped,
  applied state and the private seven-field receipt were exact
  `1:1:chat_only`, admission was open, raw bypass was closed, active/unknown
  leases were zero, and all nine operation audit rows were present.
- Created the independent detached release
  `/home/jetson2/mediflow-ai/control/releases/86bebb6` at exact source
  `86bebb6d1fd10984a48f8fd401e5c483f8499244`. The prior `ee7e03e` release and
  all rollback material remain intact.
- In the new release, all 32 Admin Control tests and all 19 MedGemma tests
  passed. Source compilation, release-diff checks, exact-owner observation,
  the read-only bootstrap, an authenticated no-network
  `medgemma_service.ready` mock, the not-ready rollback regression, and real
  shared lifecycle-lock contention also passed. The owner-only key was neither
  displayed nor copied.
- Restarted only the exact-owned controller from PID 46899 to PID 47037 in the
  new release, with drafts and mutations disabled. Chat PID 46810 was unchanged;
  neither chat nor MedGemma was started, stopped, or restarted, and no profile
  transition occurred.
- The final audit passed at release `86bebb6`: exact `1:1:chat_only`, healthy
  chat, stopped VLM with loopback 18081 closed, open admission, raw-bypass
  closure, zero active/unknown leases, the exact seven-field receipt,
  drafts/mutations false, and all nine operation rows preserved. Managed ingress
  remained on 8080, while controller 8090 and raw chat 18080 remained loopback
  only.

No E2 worker, inference request, sample, run, job, or model-profile mutation was
performed. Model files, keys, environment files, ports, databases, user data,
CUDA/PyTorch, cloud fallback, and medical-quality status were unchanged.

## 2026-09-22 — C13 managed-ingress E2 succeeded; final admission fail-closed

- Began from source `3f5d863`, A deployment `f53a1c6`, and B release `86bebb6`.
  B passed exact-owner chat health, exact `1:1:chat_only`, open admission,
  raw-bypass closure, zero active/unknown leases, the seven-field receipt,
  stopped VLM, and read-only controller gates. A loaded the owner-only mode-0600
  VLM key file without an inline key. A-to-B port checks exposed only managed
  ingress 8080; controller 8090 and raw 18080/18081 remained network-blocked.
- The operation database contained 11 pre-existing rows, rather than the nine
  stated in the previous summary. All 11 identifiers and states were captured
  as the immutable baseline and remained present at final audit.
- Created private C13 store
  `/home/jetson_orin_nano/mediflow-ai/research/admin-e2-managed-20260922-c13`
  using the existing 224x224 red/blue fixture digest
  `e85c72bc93d05149bac9be4d0d03f5ffcb2240b294d9305c818a8cad92f2f911`.
  New sample `6c68ba3fc1f441c0a93d4b7ccf3a455e` froze the existing
  `eye-survey-1.0` digest
  `6ec89117c833a9d5e2cfc6397f6c23971b3e55e25f148371db39f133ef08f150`.
- Restarted only the exact-owned controller as mutable PID 69830. Forward
  operation `91ac1878b65c45fdb0217bee5c3b005c` succeeded at exact
  `2:2:vlm_only`. Chat was stopped, MedGemma was exact-owned PID 69851, its
  authenticated readiness check passed, the receipt matched, and no heavy-model
  co-residency or active/unknown lease existed.
- Created new run `e2276b4707c54b72b30459a8aa19e3fd` and job
  `dd95e9c0413e49719188076289f67f69` with the verified generation-2 receipt.
  The normal CLI exited at import before claiming the job because A's system
  Python lacks `python-dotenv`; the job remained queued and B recorded no lease.
  No package was installed. The same existing `process_one` worker was then
  invoked directly exactly once, so no inference retry occurred.
- The single generation-2 VLM lease ran from `2026-09-22T06:39:29Z` to
  `06:40:44Z` and completed. The C13 job succeeded in 75138.51 ms with one
  prediction. The worker's enforced HTTP-success and `vision_ingested=true`
  checks passed, analysis was strict schema 1.0 with status `abstain`, and the
  frozen survey digest, seven-field runtime expectation, and receipt prompt
  digest all matched. Model output, prompt, image, response bytes, and keys were
  not printed or added to these logs.
- Reverse operation `0f0a7732fd4b4307b0008c101d39e755` succeeded, stopped
  MedGemma, released 18081, and restored healthy exact-owned chat PID 69924.
  Controller-authoritative revisions therefore advanced normally to
  `3:3:chat_only`.
- A proposed shared-lock rewrite of applied metadata, ingress generation, and
  receipt back to `1:1` was rejected by automatic approval review before
  execution because directly decreasing the controller-authoritative generation
  could create state and security drift. No such rewrite occurred and it was
  not retried through another path. Per the approved fail-closed rule, managed
  ingress admission was closed with zero active/unknown leases, then only the
  controller was restarted read-only as PID 69967 from `86bebb6`.
- Final B state is internally consistent `3:3:chat_only`, healthy chat, stopped
  VLM, closed admission, raw bypass closed, zero active/unknown leases, matching
  seven-field receipt, and drafts/mutations false. All 11 original operations
  plus the two successful C13 transition operations are preserved. From A,
  only port 8080 is network-reachable; its closed admission prevents inference.
- Final A audit found exactly one sample, survey, run, succeeded job, and
  prediction in the owner-only C13 store. A HEAD, `.env`, both operational DBs,
  the key file and mode, and the C11/C12 database hashes were unchanged.

This is synthetic integration evidence only. No model, key, environment file,
operational DB, user data, CUDA/PyTorch, or cloud fallback was changed, and no
medical-quality evaluation was performed. Reopening admission requires a new
explicit decision to accept monotonic `3:3:chat_only` as the safe baseline or a
separately implemented controller-authoritative reconciliation mechanism.

## 2026-09-22 — monotonic 3:3 baseline accepted and admission reopened

- Under a separate explicit approval, accepted controller-authoritative
  `3:3:chat_only` as the new safe baseline. Before mutation, exact-owned
  read-only controller PID 69967, healthy chat PID 69924, stopped MedGemma,
  closed admission, raw-bypass closure, zero active/unknown leases, matching
  seven-field receipt, disabled drafts/mutations, and all 13 operation rows
  matched the recorded state.
- Acquired the existing shared lifecycle lock, repeated every gate, and opened
  managed ingress admission at unchanged deployment generation 3. No applied
  state, receipt, generation, operation row, controller capability, model
  process, port, environment, or key was rewritten.
- Post-open verification passed at `3:3:chat_only`: admission open, zero
  active/unknown leases, raw bypass closed, exact same controller and chat PIDs,
  VLM stopped with no 18081 listener, drafts/mutations false, and all 13
  operation rows preserved. Controller 8090 and raw chat 18080 remain loopback;
  managed ingress remains on 8080.
- Applied-state and receipt file hashes after verification were
  `c127b3de434504924e97c86e1c3bb93511be7673d808d8f2c037589b827bf156`
  and `cff246d0bf0b8b43f9e8cb8d1fbb12ce3ab26981e86d278e360547e90101b709`.
  The admin, VLM, and chat key files remained owner-only mode 0600.

No chat or VLM inference request, E2 worker, model start/stop/restart, profile
transition, controller restart, or mutation enablement occurred in this action.
No model, key, environment file, port, database, user data, CUDA/PyTorch, cloud
fallback, or medical-quality status changed.

## 2026-09-23 — explicit environment mode for the research CLI

- C13 showed that A's system Python lacks `python-dotenv`: the standard
  `run_ai_experiments.py` entrypoint exited before claiming the queued job even
  though its settings were supplied in the process environment. The worker
  itself then completed exactly one direct invocation.
- Added `--explicit-env` to the research CLI. This opt-in mode uses the supplied
  process environment and does not import `python-dotenv` or read the project
  `.env`. The default mode still loads `.env`; if `python-dotenv` is missing,
  it returns bounded `missing_dotenv` before opening an experiment store.
- Added focused tests for isolated-store initialization and an empty E2 worker
  queue without `python-dotenv`, plus default-mode fail-closed behavior. The new
  three tests, six experiment-worker tests, and six survey/hybrid tests pass.
  `git diff --check` and source compilation without writing bytecode pass.
- Updated the research protocol and Admin Control handoff to reflect the
  completed C13 E2 gate and current open `3:3:chat_only` admission. This source
  change remains local to `codex/admin-control`; A's deployed commit is still
  `f53a1c6` and B's deployed release is still `86bebb6`.

No device command, worker, inference request, process change, research data
change, or medical-quality evaluation was performed for this source update.

### Jetson A exact two-file deployment

- A began clean at `f53a1c6`. Baseline SHA-256 digests for `.env`, both
  operational DBs, the owner-only VLM key file, and C11/C12/C13 research DBs
  were captured. The key remained owner-only mode 0600. No web or research
  worker process was running.
- Applied only `scripts/run_ai_experiments.py` and
  `tests/test_run_ai_experiments_cli.py` from the reviewed local change. Patch
  SHA-256 was
  `d6971aac86de7712b7096baff9a6bd366f028eb1aea89372a92b68f728b8ebe2`;
  the two deployed source/test hashes matched the local pushed files.
- A system Python passed the three new CLI tests and six survey/hybrid tests.
  One of six experiment-worker tests failed because its E0 path imports the
  existing OpenCV build against incompatible NumPy 2.2.6. The project’s
  existing virtualenv then passed all three CLI, six experiment-worker, and six
  survey/hybrid tests. No package or runtime was changed.
- Committed exactly those two files on A as `265e545` and pushed
  `codex/admin-control-a-deploy`. A's local and remote heads matched and its
  working tree was clean. Post-deployment hashes of `.env`, operational DBs,
  VLM key, and C11/C12/C13 research DBs matched the baselines.

No E2 job, inference request, model/profile transition, controller mutation,
web process restart, key/environment/DB/user-data change, or medical-quality
evaluation occurred during this deployment. B was not changed.
