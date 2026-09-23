# Controller Identity Recovery Gate

Status: **blocked; read-only diagnosis only**. The current controller remains
healthy, and no controller process or identity record was changed.

## Observed mismatch

- Live B controller: PID 69967, UID 1000, executable `/usr/bin/python3.10`,
  cwd `/home/jetson2/mediflow-ai/control/releases/86bebb6`, argv
  `python3 -m services.ai_control.app`, start tick 9144933.
- Existing owner-only mode-0600 identity record:
  `/home/jetson2/.local/state/mediflow-ai/admin-control-runtime/controller.pid`
  records PID 47037 and start tick 8757518. PID 47037 is absent.
- Authenticated controller GETs pass, but they do **not** repair the separate
  process ownership record. The mismatch prevents a proven exact-owned stop
  or restart, which is mandatory before enabling B drafts/mutations.

## Required next gate

1. In a separately reviewed maintenance scope, identify the process launcher
   and verify the live PID's UID, boot ID, executable, argv, cwd, start tick,
   listener ownership, and release SHA against independent records. Preserve
   the old identity file and every existing operation row.
2. Establish an owner-validated controller stop/restart or a reviewed atomic
   identity adoption procedure under the shared lifecycle lock. Test it with
   mock stale-PID, PID reuse, boot-ID drift, and interrupted-write cases. Do
   not overwrite the old record merely because `/readyz` returns HTTP 200.
3. Recheck A/B source revisions, A's private submission state, research job
   counts, B raw bypass, exact chat/VLM ownership, zero active/unknown leases,
   admission, seven-field receipt, and rollback material. Verify read-only
   service restart and rollback to the previous controller state before
   considering permanent flags.
4. If any check fails, leave B on the current read-only `86bebb6` release,
   healthy `3:3:chat_only`, open admission, and drafts/mutations disabled.

No model transition, inference request, key rotation, `.env` change, DB edit,
operation deletion, or medical-quality evaluation is needed for this diagnosis.
