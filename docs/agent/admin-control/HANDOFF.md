# Admin Control Handoff

Current phase: C0-C4 and controller-authoritative ingress are complete. Clean
detached release `c821ec7` is deployed on Jetson B. Its single approved 224×224,
512-token request returned `502 invalid_model_output` with bounded diagnostic
`stdout=empty,stderr=empty`; fail-closed recovery restored exact
`1:1:chat_only`. Controller mutations are disabled. E1/E2 remains incomplete.

## Final verified device state

- B controller is exact-owned PID 45002 from release `c821ec7`, loopback-only on
  8090. Capabilities report drafts false, mutations false, managed ingress true,
  and no operations.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. From A, only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 44953 and healthy on B loopback
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

## Source and deployed release after the window

Deployed release `c821ec7` includes the generation-budget guard from `8f2b62b`
and bounded structural diagnostics from `6d522da`:

- `MIN_ANALYSIS_NEW_TOKENS=256` rejects budgets below the complete seven-field
  response contract before starting generation;
- production `VLMConfig.max_new_tokens=512` remains unchanged;
- 512-token managed requests proved the earlier 64-token budget was not the sole
  cause;
- the latest bounded result was `stdout=empty,stderr=empty`, without exposing
  raw model output.

The two existing optional local dependencies `pytorch_grad_cam` and `qrcode`
remain unavailable, so their modules were not run. No package was installed.
These changes are deployed only as part of B's detached `c821ec7` release. A was
not changed.

The bounded diagnostic from `6d522da` is now deployed as part of `c821ec7` and
identified both process output channels as empty. Read-only inspection of pinned
llama.cpp commit `391fac16460f15233a7740550d858ac96df3419d` confirms the cause:
`mtmd-cli` emits generated tokens via `LOG(...)`, and `--log-disable` pauses that
logger entirely.

Local commit `70774a5`, which is not deployed, replaces `--log-disable` with
verbosity 0 and disables colors, prefixes, and timestamps. This preserves only
generic generated output at the pinned runtime while suppressing diagnostic log
levels. Focused MedGemma tests pass 19/19 and the runnable local suite passes 180
with one skipped.

## Remaining gates

- Review undeployed logger fix `70774a5` before any new detached B release.
- A further synthetic VLM attempt requires a new explicit maintenance approval.
  Preserve the bounded structural diagnostic and never log model output.
- Preserve `c821ec7`, exact `1:1:chat_only`, every existing audit row, owner-only
  files, and all rollback material. Stop at the first drift, ownership, lease,
  port, receipt, output-contract, or rollback failure.
- E1/E2 remains incomplete until managed ingress returns HTTP 200 with
  `vision_ingested=true`, a schema-valid analysis object, and a matching closed
  receipt. Real-user-data validation and medical-quality evaluation remain
  `NOT_RUN`.
