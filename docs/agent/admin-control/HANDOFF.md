# Admin Control Handoff

Current phase: C0-C4 implementation and the controller-authoritative ingress are
complete. The C5 fixed MedGemma owner manager was deployed from pushed commit
`8a9efa3`, but the approved synthetic chat→MedGemma→chat window exposed a receipt
contract defect and then a rollback failure. The device was safely returned to
the original `1:1:chat_only` state and mutations were disabled. C5 VLM receipt
verification remains incomplete.

## Final verified device state

- B controller runs the clean detached `8a9efa3` release as exact-owned PID
  42828 on `127.0.0.1:8090`. Capabilities report drafts false, mutations false,
  managed ingress true, and an empty operations list.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. Network checks from A
  show only B:8080 reachable; 8081, 18080, and 18081 are not exposed.
- The pinned general LLM is exact-owned PID 42774, healthy on B loopback
  `127.0.0.1:18080`. MedGemma is stopped and loopback 18081 is closed. No heavy
  model co-residency occurred.
- Durable applied state and the private ingress receipt are restored to
  `1:1:chat_only`. A-to-B synthetic chat returned 200 with an exact E3 receipt.
- A's existing loopback Admin Control tunnel and private VLM URL remain in their
  prior C4 state. Existing keys and environment/rollback files remain
  owner-only. No autostart was added.
- Operation `e287c3094eb740ae8332a92d822de76f` remains
  `manual_intervention_required/rollback_failed` in B's owner-only journal. Do
  not delete or rewrite it. It deliberately blocks another apply until the local
  evidence-backed reconciliation path is reviewed, deployed, and invoked.

## What the device window proved

- Exact-owned sequential chat→MedGemma switching worked once. Operation
  `3f0dd84d4d5b4e4d89c74e16449cedd9` reached `2:2:vlm_only`; MedGemma was ready
  on loopback and chat was stopped.
- The synthetic VLM request returned HTTP 409 before ingress created a lease and
  before generation. A/B role-prompt hashes match. The operation receipt stored
  eight fields because `observed_profile` leaked into the closed seven-field E3
  expectation, so this window does not provide an E1/E2 VLM receipt or inference
  result.
- The reverse operation failed before a chat start was logged, then its single
  rollback attempt also failed. Both engines were stopped, admission was closed,
  and no active/unknown inference remained when manual recovery began. The old
  code did not preserve the two underlying exception codes, so the precise
  rollback exception is not asserted.
- The approved exact recovery restored only the original chat runtime and then
  locked the controller read-only. No further transition or model restart was
  attempted.

## Local source after the window

The branch contains an undeployed postmortem fix after `8a9efa3`:

- lifecycle verification returns and persists only the exact seven-field runtime
  expectation;
- the MedGemma owner manager waits until loopback port 18081 is actually released
  after exact process termination;
- future manual-intervention records contain safe primary and rollback error
  codes in addition to the stable `rollback_failed` status;
- an explicit reconciliation endpoint preserves the historical row and changes
  no process/configuration; it succeeds only when exact applied state, runtime
  receipt, ownership, admission, raw-bypass, and zero-lease evidence all match;
- focused tests pass and the runnable suite passes 176 with one skipped.

The two pre-existing optional local dependencies `pytorch_grad_cam` and `qrcode`
are unavailable, so their modules were not run. No package was installed. The
pushed postmortem source must be reviewed before any future device window; it is
not present on A or B yet.

## Remaining gates

- Review the postmortem and reconciliation diff and deploy it to a new detached B
  release only in a new approved maintenance window. Preserve the current
  `8a9efa3` release and all rollback material. Invoke reconciliation only after
  it re-verifies exact `1:1:chat_only`, open admission, zero active/unknown
  leases, exact-owned healthy chat, stopped VLM, and closed raw bypass.
- A second synthetic chat→MedGemma→chat attempt requires new explicit approval.
  It must stop after the first drift, ownership, lease, port-release, receipt, or
  rollback failure. Do not claim E1/E2 until the managed-ingress VLM response is
  200, `vision_ingested` is true, and its closed receipt matches.
- Real-user-data validation and medical-quality evaluation remain `NOT_RUN`.

Models, key contents, application/operational DBs, user data, CUDA/PyTorch, and
cloud provider behavior remain unchanged.
