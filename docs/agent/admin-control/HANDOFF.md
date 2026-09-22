# Admin Control Handoff

Current phase: C0-C4 and the controller-authoritative ingress are complete. The
`27c5da9` reconciliation/lifecycle release is deployed on Jetson B. The approved
single retry proved exact sequential chat→MedGemma activation and fixed the E3
receipt boundary, but the synthetic VLM generation ended with HTTP 400 rather
than a valid analysis response. Fail-closed recovery returned the device to the
original `1:1:chat_only` state, and controller mutations are disabled.

## Final verified device state

- B controller is exact-owned PID 43566 from clean detached release `27c5da9`,
  loopback-only on 8090. Capabilities report drafts false, mutations false,
  managed ingress true, and no operations.
- B managed ingress remains on network port 8080. Its journal is open at
  generation 1 with zero active and zero unknown leases. From A, only B:8080 is
  reachable; 8081, 18080, and 18081 are not network-exposed.
- The pinned general LLM is exact-owned PID 43513 and healthy on B loopback
  18080. MedGemma is stopped, has no PID record, and loopback 18081 is closed.
  No heavy model co-residency occurred.
- Durable applied state and private ingress receipt are restored to
  `1:1:chat_only`. A-to-B synthetic chat returned HTTP 200 with the exact closed
  seven-field receipt.
- A's existing Admin Control tunnel and private VLM URL are unchanged. Existing
  keys, environment files, rollback material, model files, CUDA/PyTorch,
  application/user DBs, and user data are unchanged. No autostart was added.

## Audit and retry evidence

- Operation `e287c3094eb740ae8332a92d822de76f` is preserved as `reconciled`; its
  historical `rollback_failed` error remains. The reconciliation endpoint
  changed no process or applied configuration and succeeded only after exact
  recovery-state, receipt, ownership, admission, raw-bypass, and zero-lease
  evidence matched.
- Retry operation `2059f3ef40e049509cb688d8105d194d` succeeded in switching
  chat→MedGemma. Applied state reached `2:2:vlm_only` with an exact seven-field
  receipt; chat was stopped and exact-owned MedGemma PID 43386 was ready on
  loopback 18081.
- The 16×16 synthetic request created one generation-2 VLM lease from
  `2026-09-22T02:01:55Z` to `02:03:07Z`; the lease ended `completed`. The endpoint
  returned HTTP 400 `invalid_request`, so no VLM runtime receipt, E1/E2 result,
  or medical-quality result is claimed.
- After that first failure, admission was closed and no retry occurred. Exact
  recovery stopped MedGemma, verified port release, restored the original chat
  receipt/state, started only chat, and returned the controller to read-only.

## Local source after the window

The branch has an additional undeployed HTTP-output postmortem change after
`27c5da9`:

- the pinned, device-confirmed `llama-mtmd-cli --log-disable` option prevents CLI
  diagnostics from contaminating the captured JSON channel;
- completed generation with invalid contract JSON now returns HTTP 502
  `invalid_model_output` instead of being mislabeled as a client HTTP 400;
- raw generated text is neither logged nor persisted;
- focused tests pass 33/33 and the runnable suite passes 177 with one skipped.

The two existing optional local dependencies `pytorch_grad_cam` and `qrcode`
remain unavailable, so their modules were not run. No package was installed.
This latest local change is not deployed to A or B.

## Remaining gates

- Commit and push the HTTP-output postmortem change, then review it before any
  new detached B release.
- A further synthetic VLM attempt requires a new explicit maintenance approval.
  Preserve `27c5da9`, the current `1:1:chat_only` state, the reconciled historical
  row, the successful forward-operation row, and all rollback material.
- Any future attempt must stop at the first drift, ownership, lease, port,
  receipt, output-contract, or rollback failure and return to exact chat-only.
- E1/E2 remains incomplete until managed ingress returns HTTP 200 with
  `vision_ingested=true`, a schema-valid analysis object, and a matching closed
  runtime receipt. Real-user-data validation and medical-quality evaluation
  remain `NOT_RUN`.
