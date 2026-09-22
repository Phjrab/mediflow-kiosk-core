# Admin Control Handoff

Current phase: C0-C6 and the direct managed VLM contract gate are complete.
Clean detached release `ee7e03e` remains deployed on Jetson B. The subsequent
one-time managed-ingress E2 survey-worker attempt failed before ingress with
bounded error `misconfigured` because A's deployed client cannot read the
owner-only VLM key file. A's exact two-file key-file client fix is now deployed
as `f53a1c6`; no E2 retry followed. B remains exact `1:1:chat_only` with
controller drafts and mutations disabled.

## Final verified device state

- B controller is exact-owned PID 46468 from release `ee7e03e`, loopback-only on
  8090. Capabilities report drafts false, mutations false, managed ingress true,
  and no operations.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. From A, only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 46419 and healthy on B loopback
  18080. MedGemma is stopped, has no PID record, and loopback 18081 is closed.
  No heavy model co-residency occurred.
- Applied state and the private ingress receipt are exact `1:1:chat_only` with
  the closed seven-field schema. A-to-B synthetic chat returned HTTP 200 with a
  matching receipt.
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

- Preserve `ee7e03e`, exact `1:1:chat_only`, every existing audit row, owner-only
  files, and all rollback material. Stop at the first drift, ownership, lease,
  port, receipt, output-contract, or rollback failure.
- The direct managed VLM contract gate needs no additional synthetic retry. The
  E2 survey-worker gate is incomplete. The minimal A client deployment is now
  complete at `f53a1c6`; any later E2 rerun requires separately reviewed scope,
  a new isolated store and identifiers, and the failed job must remain immutable.
- A future device mutation, sustained load/thermal evaluation, or real-data
  protocol requires its own reviewed scope.
- Real-user-data validation and medical-quality evaluation remain `NOT_RUN`.
