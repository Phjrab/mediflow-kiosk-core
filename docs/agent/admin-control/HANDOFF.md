# Admin Control Handoff

Latest repository integration: PR #5 merged into `main` as `1da439b` on
2026-09-23. A's latest deployment branch is `e78003d` with the F1 fix and
gated admin apply code, but its web process remains stopped and A's Admin
Control mutation flags have not been enabled. B's latest verified controller
release remains `86bebb6` in read-only mode.

Current phase: C0-C6 and the direct managed VLM contract gate are complete.
Authenticated readiness hardening is deployed on Jetson B as clean detached
release `86bebb6`; `ee7e03e` remains preserved as rollback material. The subsequent
one-time managed-ingress E2 survey-worker attempt failed before ingress with
bounded error `misconfigured` because A's deployed client cannot read the
owner-only VLM key file. A's exact two-file key-file client fix was deployed as
`f53a1c6`; A now runs its descendant `265e545` with the explicit research CLI
environment option. A second approved window stopped before job creation because an
unauthenticated audit probe could not verify the protected MedGemma readiness
route. Before C13, B had been recovered to exact
`1:1:chat_only` with controller drafts and mutations disabled. A new C13 E2
worker run subsequently succeeded. Its controller-authoritative restore advanced
the device to internally consistent `3:3:chat_only`; an unsafe direct generation
rewind was blocked before execution. A later explicit approval accepted monotonic
`3:3:chat_only` as the safe baseline and reopened admission without changing the
controller, model processes, receipt, generation, or operation history.

## Final verified device state

- B controller is exact-owned PID 69967 from release `86bebb6`, loopback-only on
  8090. Capabilities report drafts false, mutations false, managed ingress true,
  and no operations.
- B managed ingress remains on network port 8080. Its journal is at generation
  3 with zero active and zero unknown leases, and admission is open. From A,
  only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 69924 and healthy on B loopback
  18080. MedGemma is stopped, has no PID record, and loopback 18081 is closed.
  No heavy model co-residency occurred.
- Applied state and the private ingress receipt match at `3:3:chat_only` with
  the closed seven-field schema. Inference admission is open at unchanged
  generation 3.
- A's Admin Control tunnel and private VLM URL are unchanged. Keys, environment
  files, rollback releases, model files, CUDA/PyTorch, application/user DBs, and
  user data are unchanged. No autostart was added.

## Preserved audit evidence

- Historical operation `e287c3094eb740ae8332a92d822de76f` remains
  `reconciled` with its original `rollback_failed` error preserved.
- First retry forward operation `2059f3ef40e049509cb688d8105d194d` remains
  `succeeded`; its synthetic request produced a completed generation-2 lease and
  HTTP 400 under the older output classification.
- Output-channel retry operation `37fdb2ca80f64fd88b73d915ee29e38e` remains
  `succeeded`; it reached `2:2:vlm_only` with exact-owned MedGemma PID 43861 and
  the correct seven-field receipt.
- Its single 16×16 synthetic request created a generation-2 VLM lease from
  `2026-09-22T02:21:10Z` to `02:22:20Z`; the lease ended `completed`, then the
  endpoint returned HTTP 502 `invalid_model_output`. Raw generated output was
  not logged or persisted.
- No retry followed the 502. Admission closed, zero active/unknown leases were
  confirmed, MedGemma stopped with port release, exact chat-only was restored,
  and the controller returned to read-only.

- The 512-token forward operation `851d43b10e16474295d03ea8aaeb69fc`
  remains `succeeded`; it reached exact `2:2:vlm_only` with MedGemma PID 44300
  and no chat/VLM co-residency.
- Its one 224×224 split red/blue synthetic request used
  `max_new_tokens=512`. The generation-2 lease ran from
  `2026-09-22T02:38:03Z` to `02:39:17Z` and ended `completed`, but the response
  was HTTP 502 `invalid_model_output`. Raw generated output was neither logged
  nor persisted. No inference retry followed.

- Bounded-output operation `2d1b2db5abaf4b0c911c4b3e15551549` remains
  `succeeded`; it reached exact `2:2:vlm_only` with MedGemma PID 44797 and no
  chat/VLM co-residency.
- Its one 224×224, 512-token request created a completed lease from
  `2026-09-22T03:06:24Z` to `03:07:39Z` and returned HTTP 502. The diagnostic
  was exactly `stdout=empty,stderr=empty`; no raw output was retained. Recovery
  then restored chat-only and no request was retried.

- Logger-fix operation `01e9eaf212064800becdce1c6f2a1d6f` remains
  `succeeded`; it reached exact `2:2:vlm_only` with MedGemma PID 45858 and no
  chat/VLM co-residency.
- Its single 224×224, 512-token request returned HTTP 200 in 74.62 seconds with
  `vision_ingested=true`, strict-schema `analysis_status=abstain`, and a matching
  runtime receipt. The lease from `2026-09-22T03:34:15Z` to `03:35:30Z` ended
  `completed`. Only validation metadata was emitted; no model response content
  was logged or persisted.

## Source and deployed release after the window

Deployed release `ee7e03e` includes the generation-budget guard from `8f2b62b`,
bounded structural diagnostics from `6d522da`, and logger fix `70774a5`:

- `MIN_ANALYSIS_NEW_TOKENS=256` rejects budgets below the complete seven-field
  response contract before starting generation;
- production `VLMConfig.max_new_tokens=512` remains unchanged;
- `c821ec7` diagnosed the previous failure as `stdout=empty,stderr=empty`
  without exposing raw model output;
- source inspection showed `--log-disable` suppressed generated tokens;
- `70774a5` preserves verbosity-0 generic output while disabling colors,
  prefixes, timestamps, and higher diagnostic levels;
- the managed request now returns a valid response through ingress.

The two existing optional local dependencies `pytorch_grad_cam` and `qrcode`
remain unavailable, so their modules were not run. No package was installed.
These changes are deployed only as part of B's detached `ee7e03e` release. A was
not changed.

The bounded diagnostic from `6d522da` identified both process output channels as
empty in the preceding release. Read-only inspection of pinned
llama.cpp commit `391fac16460f15233a7740550d858ac96df3419d` confirms the cause:
`mtmd-cli` emits generated tokens via `LOG(...)`, and `--log-disable` pauses that
logger entirely.

Commit `70774a5`, deployed as part of `ee7e03e`, replaces `--log-disable` with
verbosity 0 and disables colors, prefixes, and timestamps. This preserves only
generic generated output at the pinned runtime while suppressing diagnostic log
levels. Focused MedGemma tests pass 19/19 and the runnable local suite passes 180
with one skipped. The successful device request confirms the corrected output
path under managed ingress.

## Managed-ingress E2 attempt

- Isolated store:
  `/home/jetson_orin_nano/mediflow-ai/research/admin-e2-managed-20260922-c11`
- New sample/run/job:
  `c69d553984774e7e92103db399a3a86d` /
  `93efe0ad577942ad888022b2261b08e8` /
  `109efdbfb7a34ef0a3756db9828d9d9b`
- Frozen survey digest:
  `6ec89117c833a9d5e2cfc6397f6c23971b3e55e25f148371db39f133ef08f150`
- B transition operation: `4b289618a6a740359653a74d566091e7`, preserved as
  `succeeded`.
- Worker result: one terminal `failed/misconfigured` job, zero predictions, and
  no ingress VLM lease. No retry occurred.

At the failed attempt, A's deployed `codex/admin-control-a-deploy` head
`1ec6f31` read only inline `VLM_API_KEY`. The exact review artifacts were
`A_VLM_KEYFILE_CLIENT.diff` and `A_VLM_KEYFILE_CLIENT_MIGRATION.md`. They were
applied as only two source/test files and committed on A as `f53a1c6`. Focused
tests passed 22+6+6, and a no-network check loaded the existing owner-only file
without an inline key. A had no running web process, so none was restarted.
Post-apply protected-file hashes and key mode 0600 were unchanged.

## Remaining gates

- Preserve current controller release `86bebb6`, rollback release `ee7e03e`,
  current internally consistent `3:3:chat_only`, every existing audit row, owner-only
  files, and all rollback material. Stop at the first drift, ownership, lease,
  port, receipt, output-contract, or rollback failure.
- The direct managed VLM contract gate needs no additional synthetic retry. The
  E2 survey-worker gate completed in C13. The minimal A client deployment is at
  `f53a1c6`; the existing failed C11 job remains immutable. Do not repeat E2
  without a new, separately reviewed objective.
- A future device mutation, sustained load/thermal evaluation, or real-data
  protocol requires its own reviewed scope.
- Real-user-data validation and medical-quality evaluation remain `NOT_RUN`.

## Second E2 window and readiness finding

- Private C12 store:
  `/home/jetson_orin_nano/mediflow-ai/research/admin-e2-managed-20260922-c12`
- New sample: `a8c20e405ac04c1f841056af802ae187`; frozen survey digest:
  `6ec89117c833a9d5e2cfc6397f6c23971b3e55e25f148371db39f133ef08f150`.
- Forward operation `dd35e4c05ae74279bb38a0e710ae9492` reached exact-owned
  `2:2:vlm_only`. The independent audit then used a generic unauthenticated
  probe against protected `/readyz` and observed `vlm_ready=false`; this does
  not prove the authenticated service was unready.
- No C12 run/job was allocated and no worker, lease, HTTP inference, prediction,
  or retry occurred. C12 remains one sample, one survey, zero runs/jobs/results.
- Recovery operation `88a4afb4ce81463fa1ffcabe27cd1431` restored chat; the
  preserved original receipt then restored exact `1:1:chat_only` under the
  shared lock. Both new operations remain preserved as `succeeded` audit rows.
- Local source now requires MedGemma's authenticated owner-only `/readyz` probe
  during start and verification. Admin Control tests pass 32 and MedGemma tests
  pass 19. Authenticated no-network readiness, not-ready rollback, exact-owner,
  read-only bootstrap, and shared-lock gates passed on B before the controller
  alone moved to `86bebb6`.

The readiness deployment, C13 E2 worker gate, and safe admission recovery are
complete. Do not run another E2 request or directly rewrite applied metadata,
ingress generation, or the receipt.

## C13 successful E2 evidence and admission recovery

- C13 sample/run/job:
  `6c68ba3fc1f441c0a93d4b7ccf3a455e` /
  `e2276b4707c54b72b30459a8aa19e3fd` /
  `dd95e9c0413e49719188076289f67f69`.
- Forward and reverse operations:
  `91ac1878b65c45fdb0217bee5c3b005c` and
  `0f0a7732fd4b4307b0008c101d39e755`, both preserved as `succeeded`.
- The single VLM lease completed. The job succeeded with HTTP-success and
  `vision_ingested=true` enforced by the worker, strict schema 1.0
  `analysis_status=abstain`, matching frozen survey digest, and matching
  generation-2 runtime receipt.
- Automatic approval review rejected a direct shared-state rewind from
  generation 3 to generation 1 before it executed, citing possible controller
  authority and security drift. Admission at that window's end was closed at
  consistent `3:3:chat_only`; controller drafts/mutations are disabled.
- A later explicit approval accepted monotonic `3:3:chat_only`. After all
  read-only gates passed, admission alone reopened under the shared lifecycle
  lock at unchanged generation 3. Controller PID 69967, chat PID 69924, stopped
  VLM, zero leases, seven-field receipt, disabled drafts/mutations, and all 13
  operation rows remained unchanged. No inference request ran.

## Research CLI deployment on A

- On A, the first C13 CLI launch stopped before job claim because the system
  Python lacks `python-dotenv`. The existing worker function then processed the
  queued job exactly once. Local source now offers an explicit `--explicit-env`
  CLI mode for already supplied process settings, with tests for missing
  `python-dotenv`, an isolated store, and an empty E2 queue. Exactly the CLI and
  its new test were applied to A and pushed as `265e545` on
  `codex/admin-control-a-deploy`. A's existing project virtualenv passed all
  15 focused CLI, worker, and survey tests. A's system Python passed the CLI
  and survey tests but its E0 worker test hit the pre-existing NumPy 2/OpenCV
  ABI mismatch; no package was changed. Protected file and C11/C12/C13 DB
  hashes stayed fixed. No E2 run, inference request, or web process restart
  occurred.

## Current source-only F1 correction

- `codex/admin-control` is pushed at `4ff21a2` with a two-file Macro-F1 fix:
  `experiments/evaluate.py` now uses `2*TP/(2*TP+FP+FN)`. A class with assessed
  errors and no true positives contributes `0.0`; a class absent from both
  assessed actuals and predictions remains undefined and is excluded.
- Five new evaluation regressions cover perfect classification, one missed
  class, a balanced five-class counterexample (hand-calculated Macro-F1 0.2),
  absent classes, and all-wrong predictions (Macro-F1 0.0). All 10 evaluation
  tests pass. E3/E4 and experiment-store tests also pass. Of 189 locally
  importable tests, 188 pass and one is skipped. The other two test modules
  cannot import because this Mac Python lacks `pytorch_grad_cam` and `qrcode`.
- The exact two-file fix is deployed on A as `a8257f9`, with 173 virtualenv
  tests passing and protected file/DB hashes unchanged. It is not deployed to
  B, which does not run the evaluator. Existing stored evaluation reports were
  not rewritten. See `A_F1_EVALUATOR_MIGRATION.md` for the gate and result.

## A admin apply source under review

- A's `/admin/config` source now has a gated apply action and an owner-only
  client submission journal. A records the plan and idempotency key before
  forwarding; an uncertain response blocks a new plan. Browser refresh can
  resume known operation status without starting another model transition.
- The code is merged through PR #5 and deployed to A as `e78003d` with all
  179 A virtualenv tests passing. A's `admin-client` submission directory is
  owner-only mode 0700. Its web process remained stopped and no A mutation
  flag, `.env`, DB, or key changed. A and B remain read-only for Admin Control.
- The local route/client tests and 195 locally importable tests passed (one
  skipped); the admin page's inline JavaScript passed syntax check.
- A read-only B audit still showed `3:3:chat_only`, open admission, no active or
  unknown leases, healthy chat, stopped VLM, a matching seven-field receipt,
  and all 13 existing operation rows. No model or controller transition ran.

## Permanent activation blocked by controller identity

- B's running controller is PID 69967 from release `86bebb6`, UID 1000,
  `/usr/bin/python3.10`, expected argv and cwd, start tick 9144933. The
  owner-only controller identity file instead records PID 47037, start tick
  8757518; that PID no longer exists. This mismatch was independently read
  from `/proc` and the identity file without signalling either process.
- Activation stopped before touching B's environment or restarting its
  controller. Repeated authenticated status showed `3:3:chat_only`, admission
  open, zero active/unknown leases, seven-field receipt match, no active
  operation, healthy chat, stopped VLM, 13 preserved operation rows, and both
  draft/mutation flags false. Protected B env, key, and applied-state hashes
  remained unchanged. B mock suites passed 32 Admin Control and 19 MedGemma
  tests. See `CONTROLLER_IDENTITY_RECOVERY.md` before any new write attempt.
