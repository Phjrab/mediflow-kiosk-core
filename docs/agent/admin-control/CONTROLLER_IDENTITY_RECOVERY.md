# Controller Identity Recovery Gate

Status: **recovered in the separately approved 2026-09-23 maintenance window**.
The mismatch below is historical evidence; the current controller identity is
exact at PID 94394. Drafts and mutations remain disabled.

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

## Gate used for this repair

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

## Executed recovery

- The clean B release was `86bebb6d1fd10984a48f8fd401e5c483f8499244`.
  Independently checked UID 1000, `/usr/bin/python3.10`, exact argv and cwd,
  boot ID, `/proc` start tick and `ps` start time, and PID 69967 ownership of
  loopback 8090. PID 47037 was absent. All protected files were owner-only
  mode 0600 and matched their prior hashes.
- Under the shared lifecycle lock, the read-only preflight checked the exact
  stale record, live process and socket inode, healthy exact chat PID 69924,
  closed raw VLM port, authenticated controller state, open admission, zero
  active/unknown leases, matching seven-field runtime receipt, disabled
  drafts/mutations, and a digest of all 13 operation rows. No write occurred
  during this preflight.
- The old identity bytes were retained as owner-only mode-0600
  `controller.pid.before-recovery-69967`. Only the exact controller was
  stopped via pidfd and restarted from the same clean release and read-only
  environment. The new identity atomically records PID 94394, start tick
  17692634, the same boot ID, UID, executable, argv and cwd.
- An independent post-restart check confirmed PID 94394 owns loopback 8090;
  authenticated GETs show healthy `3:3:chat_only`, open admission and disabled
  drafts/mutations. Chat PID 69924 and ingress PID 37550 did not change;
  VLM remains stopped. All 13 operation rows and protected hashes, including
  the operation database, are unchanged.
- Local one-window tool mock tests passed 8/8, including stale/reused PID,
  boot drift and interrupted atomic replacement. B's existing Admin Control
  32/32 and MedGemma 19/19 mock tests passed before restart. No model switch,
  inference request, key rotation, `.env` change, application DB edit,
  operation deletion, or medical-quality evaluation occurred.

Permanent draft/mutation activation is a separate gate. This recovery does not
authorize or perform that change.
