# Admin Control Handoff

Current phase: C0-C4 and controller-authoritative ingress are complete. Clean
detached release `1eb41c2` is deployed on Jetson B. The approved single
224×224, 512-token managed request again returned `502 invalid_model_output`,
then fail-closed recovery restored exact `1:1:chat_only`. Controller mutations
are disabled. E1/E2 remains incomplete because no managed VLM response has
returned a valid analysis object with a matching runtime receipt.

## Final verified device state

- B controller is exact-owned PID 44478 from release `1eb41c2`, loopback-only on
  8090. Capabilities report drafts false, mutations false, managed ingress true,
  and no operations.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. From A, only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 44429 and healthy on B loopback
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

## Source and deployed release after the window

Pushed and deployed HEAD `1eb41c2` includes generation-budget guard commit
`8f2b62b`:

- `MIN_ANALYSIS_NEW_TOKENS=256` rejects budgets below the complete seven-field
  response contract before starting generation;
- production `VLMConfig.max_new_tokens=512` remains unchanged;
- an earlier failed maintenance fixture used 64 tokens, but the approved 512-token
  managed request now failed with the same output classification. The old budget
  is therefore not the sole cause. The exact model-output/parser mismatch is
  unknown because raw output is intentionally unavailable;
- focused tests pass 34/34 and the runnable suite passes 178 with one skipped.

The two existing optional local dependencies `pytorch_grad_cam` and `qrcode`
remain unavailable, so their modules were not run. No package was installed.
The minimum-budget change is deployed only as part of B's detached `1eb41c2`
release. A was not changed.

Local commit `6d522da`, which is not deployed, adds bounded output-structure
diagnostics for a future approved run. It can distinguish empty channels, no
JSON object start, invalid JSON, non-object JSON, and trailing data without
recording generated text, prompts, images, or response bytes. Focused MedGemma
tests pass 19/19 and the runnable local suite passes 180 with one skipped. Full
discovery has only the two pre-existing missing optional imports
`pytorch_grad_cam` and `qrcode`.

## Remaining gates

- Review undeployed structural-diagnostic commit `6d522da`. A future approved
  run can use it to distinguish channel contamination, trailing data, and
  missing/invalid JSON while preserving the no-raw-output rule.
- A further synthetic VLM attempt requires a new explicit maintenance approval.
  Do not infer that a larger token budget will resolve the failure.
- Preserve `1eb41c2`, exact `1:1:chat_only`, every existing audit row, owner-only
  files, and all rollback material. Stop at the first drift, ownership, lease,
  port, receipt, output-contract, or rollback failure.
- E1/E2 remains incomplete until managed ingress returns HTTP 200 with
  `vision_ingested=true`, a schema-valid analysis object, and a matching closed
  receipt. Real-user-data validation and medical-quality evaluation remain
  `NOT_RUN`.
