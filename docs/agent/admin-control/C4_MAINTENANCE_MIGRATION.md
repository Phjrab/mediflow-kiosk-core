# C4 Managed Ingress Maintenance Migration

Status: `REVIEW_ONLY / NOT_APPLIED / BLOCKED_GATE`.

This runbook separates the code/mock work from the device maintenance window. No
Jetson port, process, model, key, environment file, database, or user data was
changed while preparing it. The proposed private configuration delta is in
`C4_MAINTENANCE_MIGRATION.diff`; it contains paths and ports but no credentials.

## Intended topology

- B managed ingress becomes the only network-reachable inference endpoint on
  port 8080. It keeps the existing Bearer credentials and the existing
  `/v1/chat/completions` and `/v1/analyze-eye` request contracts.
- The general LLM raw server moves to fixed loopback `127.0.0.1:18080`.
- The MedGemma service uses fixed loopback `127.0.0.1:18081` when its sequential
  profile is selected. Port 8081 is closed rather than left as a raw bypass.
- A keeps its general LLM URL and changes only the private VLM base URL from
  B:8081 to B:8080. Provider selection and the no-cloud-fallback rule remain.
- Controller, general-LLM CLI, and the future MedGemma launcher use one owner-only
  `device-lifecycle.lock`. The controller stays outside both model processes.

## Preconditions

1. Pin the pushed source SHA and record A/B deployed SHAs, process identities,
   listening sockets, current applied state, and file digests without displaying
   credentials.
2. Confirm the B state and lock directories are owner-only and that key files
   are regular non-symlink files with mode 0600 or stricter.
3. Confirm the current general LLM is managed by its exact PID/UID/executable/
   argv/cwd/boot-id/start-tick record. Treat mismatch or an unrecorded listener as
   `unmanaged_process`; do not signal it.
4. Keep drafts and mutations disabled. Pause new research claims and confirm no
   active or unknown inference. Do not cancel or rewrite queued jobs.
5. Prepare the exact rollback environment before stopping the general LLM. This
   maintenance requires a brief approved inference outage.

## Migration sequence

1. Close admission and verify the durable ingress journal has zero active and
   zero unknown leases. A client timeout or disconnect is not completion.
2. Acquire the shared lifecycle lock. A second controller, CLI, or worker must
   fail closed without starting or stopping a process.
3. Stop only the exact-owned general LLM. Start the same pinned artifact on
   loopback 18080 with its existing credential, model, and launch settings.
4. Start the managed ingress on B:8080 with raw-bypass verification still false.
   Verify the raw ports are loopback-only and B:8081 is closed, then set the
   verified bootstrap flag and open admission for the current deployment
   generation. Never infer this flag from a successful health check alone.
5. Run authenticated synthetic chat through ingress. Verify a full response,
   lease completion, matching runtime receipt, and no direct raw reachability.
6. Change only A's private VLM base URL to B:8080. Run the existing synthetic E1
   request only if the VLM profile is separately selected through the owned
   adapter; do not force simultaneous GPU residency.
7. Keep admin drafts and mutations disabled until the ingress, shared-lock,
   adapter identity, receipt, and rollback checks have passed. Enabling them is
   the last gate, followed by one synthetic apply-and-restore operation.

## Failure and rollback

- Before the applied receipt is durable, close admission, stop only processes
  whose exact owner records still match, restore the previous actual profile,
  and restore the previous applied record.
- If the previous profile was stopped, restore stopped. Do not start an old model
  merely because a new start failed.
- If completion is unknown, leave admission closed and require positive backend
  idle evidence before reconciling the lease.
- If rollback cannot prove the prior state, record
  `manual_intervention_required` and do not retry in a loop.
- To return to the pre-migration topology during the approved window, stop the
  exact-owned ingress and loopback raw process, restore the recorded general LLM
  environment on port 8080, restore A's VLM URL to 8081, and verify the original
  exact-owned general LLM receipt. Do not alter models, keys, DBs, or user data.

## Evidence to capture

- Source/deployment SHAs and clean-tree status.
- Redacted socket ownership before, during, and after migration.
- Shared-lock contention, exact PID identity, drain and unknown-lease behavior.
- Synthetic request status plus receipt fields/digests, without prompt, image,
  credential, or patient content.
- Applied and restored generations, operation ID, rollback outcome, and proof
  that cloud fallback did not occur.

Actual device migration, model switching, and medical-quality evaluation remain
unexecuted until the user supplies the explicit maintenance approval recorded in
the handoff.
