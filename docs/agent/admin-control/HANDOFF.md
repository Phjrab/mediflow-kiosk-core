# Admin Control Handoff

Current phase: C0-C4 and controller-authoritative ingress are complete. Clean
detached release `14d7dc3` is deployed on Jetson B. The approved single
output-channel retry proved exact sequential chat→MedGemma activation and proper
`502 invalid_model_output` classification, then fail-closed recovery restored the
original `1:1:chat_only` state. Controller mutations are disabled. E1/E2 remains
incomplete because no managed VLM response has returned a valid analysis object
with a matching runtime receipt.

## Final verified device state

- B controller is exact-owned PID 44037 from release `14d7dc3`, loopback-only on
  8090. Capabilities report drafts false, mutations false, managed ingress true,
  and no operations.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. From A, only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 43988 and healthy on B loopback
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

## Local source after the window

The branch contains an undeployed generation-budget guard after `14d7dc3`:

- `MIN_ANALYSIS_NEW_TOKENS=256` rejects budgets below the complete seven-field
  response contract before starting generation;
- production `VLMConfig.max_new_tokens=512` remains unchanged;
- the failed maintenance fixture used 64 tokens, while an earlier direct custom
  API probe produced a valid contract object in 73.253 seconds. This makes the
  too-small maintenance budget the strongest configuration explanation, though
  raw-output truncation was not directly observed;
- focused tests pass 34/34 and the runnable suite passes 178 with one skipped.

The two existing optional local dependencies `pytorch_grad_cam` and `qrcode`
remain unavailable, so their modules were not run. No package was installed.
The minimum-budget change is not deployed to A or B.

## Remaining gates

- Commit and push the minimum-generation-budget guard, then review it before any
  future detached B release.
- A further synthetic VLM attempt requires a new explicit maintenance approval
  and must use at least 256 tokens; 512 matches the production default and prior
  successful direct-probe configuration class.
- Preserve `14d7dc3`, exact `1:1:chat_only`, every existing audit row, owner-only
  files, and all rollback material. Stop at the first drift, ownership, lease,
  port, receipt, output-contract, or rollback failure.
- E1/E2 remains incomplete until managed ingress returns HTTP 200 with
  `vision_ingested=true`, a schema-valid analysis object, and a matching closed
  receipt. Real-user-data validation and medical-quality evaluation remain
  `NOT_RUN`.
