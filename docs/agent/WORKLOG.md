# Work log

## 2026-09-20 — P0 investigation

- Read the complete integrated specification and inspected the target repository.
  No `AGENTS.md` exists in this checkout.
- Continued in `/Users/hajoonpark/자율설계/mediflow-kiosk-core` on branch
  `codex/local-ai-shadow-experiments`, base
  `2877e65f99bb1a3f9837b56c0736de57a4f66902`.
- Initial worktree was clean. Current uncommitted changes belong to this task.
  No `.env`, `HASH_PEPPER`, operational DB, model, user asset, or CUDA/PyTorch
  installation was changed.
- Baseline discovery ran 35 tests: 32 passed, 1 Linux-only skip, and two existing
  import errors (`pytorch_grad_cam`, `qrcode`) on macOS.
- Read-only SSH inspection succeeded after connectivity was restored. A: Orin
  Nano 8 GB class, L4T R36.4.7, Python 3.10.12, about 52 GB root storage free;
  system Python had no torch. B: Orin Nano 8 GB class, L4T R36.5.2, Python
  3.10.12, about 155 GB root storage free.
- B has user-local PyTorch `2.11.0+cu130`, but its CUDA probe reports the driver
  is too old for that build and CUDA is unavailable. Status is
  `BLOCKED_COMPATIBILITY`; no runtime package was altered.
- No general LLM server, MedGemma model, or relevant listening service was found
  in the limited read-only inspection.

## 2026-09-20 — P1/P2 local chat path

- Added exact `openai`, `gemini`, and `local` provider selection. Unknown
  providers are rejected and local failure never invokes a cloud provider.
- Added a bounded OpenAI-compatible local client with literal private-IP exact
  allowlist, no redirect/proxy use, auth, request limits, single-flight admission,
  deadlines, and conservative recovering state after unknown remote completion.
- Added an allowlisted browser-result summary that excludes images, patient IDs,
  arbitrary HTML/instructions, and ambiguous confidence units.
- Integrated local chat into `/api/chat`; added generation-free
  `/api/chat/status`; removed hidden widget generation and canned fallback.
- Added local settings to the admin page, masked secrets, atomic `.env` update
  after validation, and HTML escaping for persisted settings.
- Added read-only preflight and non-sensitive chat smoke tools.

## 2026-09-20 — P3–P6 research path

- Preserved the MediaPipe/EfficientNet contract and added explicit
  `GRADCAM_MODE=always|on_demand|off`; default `always` preserves behavior.
- Added a separate private SQLite research store with sample lineage, finite
  durable jobs, idempotency, cancellation/recovery, predictions, labels, and audit.
- Synthetic fixture registration is supported. Real samples require an allow flag
  and permission reference; the CLI has no real-data import command.
- Added E0 EfficientNet baseline and E1 VLM workers that claim only their arm. E0
  can save a private Grad-CAM artifact for the same isolated sample used by E1.
- Added an independent MedGemma service/client with validated image bytes,
  prompt hash, forbidden-context checks, strict schema, auth, single-flight,
  local-only model loading, and mandatory CUDA placement.
- Added admin research APIs/page, run evaluation, E0/E1 paired comparison, and
  safe text rendering. Research output is not consumed by user results, the
  operational DB, PDF, Kakao, or chat.
- Added explicit-denominator evaluation and private JSON/CSV/Markdown export.
  Engineering fixtures cannot emit medical accuracy and patient split leakage
  stops evaluation. E2/E4 remain explicitly unimplemented.
- Added the minimum-scope E3 worker for a completed same-sample E0 result. It is
  local-provider-only, reads no image, omits Grad-CAM/reference labels/paths,
  snapshots a fixed question and prompt digest, and stores text in a separate
  explanations table. E3 evaluation requires explanation review and never emits
  image-classification metrics. Five focused mock/migration tests pass; no LLM
  was run.

## Verification

- Local LLM/VLM client contract: 19 tests passed with loopback HTTP mock.
- Experiment store/evaluator/E0-E1 workers/admin surface: 21 tests passed.
- Approved operational ROI import, authorization, retention and path controls:
  5 tests passed.
- MedGemma service: 3 tests; Grad-CAM policy: 4; chat prompt: 5; existing Jetson
  deployment scripts: 4. All passed.
- Full discovery: 101 attempted; 98 passed, 1 skipped, and the same two existing
  dependency import errors (`pytorch_grad_cam`, `qrcode`).
- AST parse 65 files, JSON parse 3 files, and `git diff --check` passed.
  Credential literal scan found no supplied device credentials.
- macOS AI preflight correctly returned `NOT READY` because CUDA is unavailable.
  No cloud request was made. See `evidence/verification-2026-09-20.txt`.

## Unfinished and blocked work

- A-to-B general LLM generation is `NOT_RUN`; no model/server is installed on B.
- MedGemma access, approved revision/hash, compatible runtime, real image
  ingestion, and device memory/latency/OOM/load tests are `NOT_RUN`; B is
  `BLOCKED_COMPATIBILITY`.
- No approved medical data or independent reference labels were supplied.
  Medical quality evaluation is `BLOCKED_DATA` and was not claimed.
- Automatic approval review initially rejected an operational-history bridge
  because the sensitive transfer lacked specific authorization. The user then
  explicitly approved that transfer. The implemented admin/CSRF path copies only
  the selected-eye ROI through a query-only DB connection and requires
  `permission_ref`, `retention_policy_ref`, `retention_until`, and split. It is
  idempotent, audited, path-confined, and refuses expired data. Synthetic tests
  verified ROI-only copying and no operational DB mutation; no real record was
  imported during verification.
- A destructive expired-data purge was rejected by automatic approval review
  because import authorization did not authorize irreversible bulk deletion.
  The safer `retention-status` command was added first and expired samples were
  blocked from new enqueue operations. The user later supplied the exact requested
  authorization for implementation and mock testing only.
- Added `retention-purge` with explicit sample IDs and the fixed confirmation
  `DELETE_EXPIRED_RESEARCH_COPIES`. It revalidates expiry and blocks active jobs,
  unexpired data, synthetic fixtures, unknown IDs, duplicates, and batches over
  100 before mutation. Files are staged for rollback until the research DB
  transaction commits.
- The purge removes only research ROI/Grad-CAM files and linked jobs,
  predictions, E3 explanations, reference labels, and `operational_import` audit
  links. Shared run rows, unrelated audit rows, operational DB/source files, and
  nonexpired samples remain. SQLite `VACUUM` runs after file deletion. Four
  temporary-data tests pass; no device or real-data purge was run.

## 2026-09-20 — B compatibility evidence

- Rechecked B over SSH without changing packages or files. It reports L4T
  R36.5.2, CUDA toolkit 12.6.11, PyTorch `2.11.0+cu130`, CUDA build 13.0, and
  `torch.cuda.is_available() == False`; the warning reports driver level 12060.
- NVIDIA's current official material maps Jetson Linux 36.5 to JetPack 6.2.2 and
  CUDA 12.6. Its Jetson PyTorch matrix lists 2.7/2.8 development releases for
  JetPack 6.2 and PyTorch 2.11 for JetPack 7.1. B remains
  `BLOCKED_COMPATIBILITY`; no replacement package was selected or installed.
- Added `scripts/jetson_ai_compat_report.py` and pure classification helpers. The
  report is read-only, bounded, JSON-formatted, performs no network/model load,
  and distinguishes core CUDA visibility from model readiness. Five new unit
  tests pass, including a fixture for B's observed mismatch. After E3 and the
  retention purge were added, full discovery attempts 101 tests: 98 pass, one
  Linux-only test skips, and the same two development-host dependency imports
  fail (`pytorch_grad_cam`, `qrcode`).

## 2026-09-20 — immutable deployment candidate selection

- Selected, without pulling or installing, NVIDIA's signed
  `nvcr.io/nvidia/pytorch:25.05-py3-igpu` as the isolated MedGemma PyTorch
  candidate. NVIDIA's Jetson matrix maps framework release 25.05/PyTorch 2.8 to
  JetPack 6.2. Recorded registry manifest digest
  `sha256:774bbc5cbedfd5d432129e2ae79a7f6de6f267afa8e1f4b3b44dead00f790c79`
  and its Linux/arm64 child digest.
- Selected `llama.cpp` v0.4.1 commit
  `391fac16460f15233a7740550d858ac96df3419d` plus the official
  `Qwen/Qwen2.5-3B-Instruct-GGUF` Q4_K_M file at revision
  `7dabda4d13d513e3e842b20f0d435c732f172cbe` as the first general-LLM
  candidate. Recorded its 2,104,932,768-byte file SHA-256 in
  `config/ai_artifact_candidates.json`.
- Pinned `google/medgemma-1.5-4b-it` revision
  `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b` and both official weight-shard
  SHA-256 values. The gated files were not downloaded. Their repository file
  total is about 8.6 GB; Google's published static BF16 estimate is 6.4 GB before
  runtime/KV overhead. The implemented BF16 service is explicitly
  `BLOCKED_MEMORY` for B until measured or a supported four-bit vision path is
  selected and proven. No CPU fallback is accepted.
- Added an offline verifier and a pinned `llama.cpp` foreground launcher. The
  launcher rejects revision/file changes and unsafe key-file permissions, uses
  one CUDA-offloaded slot, and disables prompt cache, slots, and the web UI.
  Five focused tests pass. Full discovery now attempts 106 tests: 103 pass, one
  Linux-only test skips, and the same two pre-existing
  dependency imports fail (`pytorch_grad_cam`, `qrcode`). AST parsing covers 68
  Python files, three pinned JSON files parse, `git diff --check` passes, and
  `.env` remains unchanged.
- At candidate-selection time, recorded an Ollama 0.32.15 Linux/arm64 container
  and `medgemma1.5:4b` Q4_K_M model layer by registry digest as a possible
  low-memory hardware probe. The later synthetic probe is documented below. It
  is not approved for E1: the serving manifest does not attest the exact
  originating Google revision or conversion lineage, so it remains
  `BLOCKED_PROVENANCE`.
- A noninteractive SSH key probe for B was unavailable in this turn. No password
  was placed in a command, file, or process argument, and no remote change was
  made. Device installation, model download, generation, image ingestion, memory
  measurement, and medical evaluation remain `NOT_RUN`.

## 2026-09-20 — general LLM device deployment and A-to-B verification

- Reconnected to B and preserved its existing user PyTorch/CUDA installation.
  Created only private directories under `/home/jetson2/mediflow-ai`, cloned
  `llama.cpp` at exact commit `391fac16460f15233a7740550d858ac96df3419d`,
  and built `llama-server` natively against CUDA 12.6 for architecture 87. The
  initial generic configuration exposed `compute_90` compiler commands and was
  stopped; the final cache records `CMAKE_CUDA_ARCHITECTURES=87` and
  `GGML_CUDA_FA=OFF`. No system packages were installed.
- Downloaded the pinned Qwen2.5 3B Q4_K_M artifact on B. Both the manual check
  and repository verifier confirmed 2,104,932,768 bytes and SHA-256
  `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`.
  The runtime reports `0.4.1-dev`, build 10969, commit `391fac164`, Linux aarch64,
  and `CUDA0: Orin (7607 MiB)`; dynamic links resolve to the CUDA 12.6 runtime,
  cuBLAS, driver, and the built CUDA ggml library.
- Created a dedicated key in a B-owned mode-0600 file and transferred it by SCP
  to an A-owned mode-0600 file without printing its contents. The local transfer
  copy was deleted immediately. The B server rejects unauthenticated model
  access with 401 and accepts the dedicated key with 200.
- B-local deterministic smoke returned `MEDIFLOW_LOCAL_OK` in 0.699 seconds and
  logged 14.20 output tokens/s for six tokens. A-to-B direct chat returned
  `MEDIFLOW_A_TO_B_OK` in 0.553 seconds. After restarting through the repository
  verification launcher, the A client returned `MEDIFLOW_RESTART_OK` in 0.700
  seconds. The manual server remains running on B port 8080; it is not installed
  as an autostart service.
- Added strict `LOCAL_LLM_API_KEY_FILE` support. It rejects relative paths,
  symlinks, non-regular files, wrong ownership, group/other permissions, large or
  multiline content, and ambiguous simultaneous inline/file credentials. The
  local LLM/VLM client suite now passes 21 tests.
- Copied source only into A's private `/home/jetson_orin_nano/mediflow-ai/staging`
  tree; operational `.env`, DB, models, user data, and the clean operational Git
  checkout were untouched. The first status smoke found that the global Flask
  hook initialized EfficientNet for chat requests. Chat routes now bypass that
  initialization, and the completion flag is set only after successful model
  loading. In staging, `/api/chat/status` returned configured/local and
  `/api/chat` returned `MEDIFLOW_API_ROUTE_OK`; `models_initialized` stayed false.
- After launcher restart B showed approximately 2.75 GiB server RSS, 2.9 GiB
  available system memory, and 443 MiB swap used. These are single-request
  general-LLM engineering smokes only. The later synthetic MedGemma probe is
  documented below. No load/soak/OOM recovery, real-data experiment, actual
  purge, or medical-quality evaluation was run.
- Final local discovery attempted 108 tests: 105 passed, one Linux-only test
  skipped, and the same two development-host dependency imports failed
  (`pytorch_grad_cam`, `qrcode`). Local and A staging both pass the 21 client and
  5 artifact tests. AST parsing covers 68 Python files; three pinned JSON files,
  launcher shell syntax, `git diff --check`, and the empty `.env` diff pass.


## 2026-09-20 — MedGemma synthetic GPU hardware probe

- Pulled the pinned Ollama 0.32.15 multi-architecture image on B by digest
  `sha256:57d60e686821ea81a7748a3ec8141308c8b8f95b27105713954abf7a6529e700`.
  Docker selected Linux/arm64. The container reported Ollama 0.32.15 and detected
  CUDA 12.6, compute capability 8.7, and the Orin GPU. It ran manually with no
  restart policy and was removed after the probe.
- Stopped the general LLM before starting the VLM container. Pulled
  `medgemma1.5:4b` only into `/home/jetson2/mediflow-ai/ollama-probe`. Direct
  checks confirmed the 3,338,928,384-byte model layer SHA-256
  `a051c2bd4ab8d5b7f4df8eec344f2fdd603efb2d098da799dc16c95e9e8bc838`
  and serving-manifest SHA-256
  `433252621ab154668b5d8be6aff6c1b771bacba045e46e6193da8d6ad1630f2c`.
  The API reported a 4.3B Q4_K_M GGUF model with `completion` and `vision`
  capabilities.
- Used only two generated 224x224 solid-color PNG fixtures. The GPU-backed
  multimodal runner returned `red` for the red fixture and `blue` for the blue
  fixture. Cold request latency was 20.605 seconds including 14.946 seconds of
  load; the warm request was 5.456 seconds. Logs show 34/35 layers offloaded to
  CUDA, a 2,309.91 MiB CUDA model buffer, and one image batch decoded per request.
- The running container used about 4.897 GiB of the 7.429 GiB system-memory
  limit; available memory fell to about 1.1 GiB and swap use reached 911 MiB.
  This supports sequential scheduling on this 8 GB device and does not justify
  simultaneous LLM/VLM residency or production load claims.
- Stopped and removed the VLM container, then restarted the exact pinned
  llama.cpp launcher. B health returned OK and the A repository client returned
  a 29-character recovery response in 906.5 ms; a subsequent direct assertion confirmed exact `MEDIFLOW_POST_VLM_EXACT_OK`.
  Earlier invalid-key and outage tests returned unauthorized/connection failure
  without cloud fallback, and the baseline models stayed uninitialized on A.
- This is a synthetic engineering hardware/image-ingestion probe only. The
  Ollama serving manifest still does not attest the exact Google source revision
  and conversion lineage, so this artifact remains `BLOCKED_PROVENANCE` for E1.
  The gated official source/BF16 path remains blocked by access and memory.
  No operational image, real research record, medical label, clinical metric,
  or real-data purge was used or evaluated.


## 2026-09-20 — Jetson A operational local-LLM promotion

- Rechecked A's operational repository before mutation: clean `main` at
  `f5368550230e37238c7a7930e6b39c4e0ec11cde`, with no kiosk Flask process or
  matching systemd service running. The two newer upstream commits affect only
  kiosk browser startup and Naver result links, so they do not overlap the
  promoted local-chat files.
- Built a minimal deployment candidate from exact A commit `f536855`; it contains
  only local/OpenAI/Gemini chat dispatch, bounded local transport, safe browser
  result summary, generation-free status, protected admin configuration, widget
  behavior, and chat-route model-initialization bypass. Research/VLM routes and
  experiment code were not copied into the operational checkout.
- The candidate passed 15 loopback HTTP/configuration/UI tests on macOS and again
  under A's operational virtualenv. A candidate Flask test returned configured
  local status and exact `MEDIFLOW_OPERATIONAL_CANDIDATE_OK` while
  `models_initialized` remained false. An invalid-key candidate request returned
  HTTP 503 `unauthorized` with no cloud fallback.
- Created recovery branch `backup/pre-local-llm-20260920-2335` at the original A
  commit and a private recovery directory at
  `/home/jetson_orin_nano/mediflow-ai/backups/pre-local-llm-20260920-2335`.
  It contains a mode-0600 pre-change `.env`, its SHA-256, the base commit, and a
  tracked-file archive. No secret value was printed.
- Applied the minimal overlay and atomically updated only the AI settings in the
  existing mode-0600 `.env`. The dedicated local-LLM key remains in its separate
  owned mode-0600 file. OpenAI/Gemini configuration was retained; selection is
  `local`, and local failures never dispatch to either cloud provider.
- The operational checkout passed the same 15 tests, Python compilation, and
  `git diff --check`. Its test client returned exact
  `MEDIFLOW_OPERATIONAL_DEPLOY_OK` with `models_initialized=False` and used a
  staging DB path rather than the operational DB.
- Stopped only B's general LLM and ran A's operational smoke with dummy cloud
  credentials present. It failed `connection_failed` with exit 1 and made no
  fallback. Restarted the exact pinned launcher; B health returned OK and A
  directly asserted exact `MEDIFLOW_OPERATIONAL_RECOVERY_OK`.
- A had no running kiosk service before deployment, so no operational daemon was
  started or restarted. The nine-file minimal overlay is committed locally on
  `codex/local-llm-operational` as
  `dd3afd7b0a4297a918a1d346d29f397173528d7e`; the working tree is clean and no
  push was performed. Operational DB, model files, user assets, HASH_PEPPER,
  CUDA/PyTorch, and MedGemma residency were not changed. No purge or real-data
  research operation ran.


## 2026-09-20 — approved deployment-candidate cleanup

- After explicit user authorization, deleted only the task-created local
  `/Users/hajoonpark/Documents/자율설계/mediflow-a-deploy` clone and
  `/private/tmp/mediflow-local-llm-a-overlay-20260920.tgz` archive.
- Deleted only A's task-created
  `/home/jetson_orin_nano/mediflow-ai/staging/operational-local-llm-candidate`
  directory and matching staging archive.
- Verified all four targets are absent. The actual local source repository, A's
  existing `staging/kiosk-core`, operational checkout, clean deployment branch,
  recovery branch, and private recovery backup remain present. No DB, model,
  user data, `.env`, credential, B artifact, or runtime process was deleted.


## 2026-09-21 — Jetson A upstream reconciliation

- Fetched A's GitHub `origin/main`, advancing its stale remote-tracking ref from
  `f536855` to `2877e65`. Created recovery branch
  `backup/local-llm-pre-rebase-20260920` at the original deployment commit
  `dd3afd7`, then rebased `codex/local-llm-operational` onto `origin/main` without
  conflicts. The new local deployment commit is
  `f4f0972c9a565ca49bfb5b11f44792f8f962c75f`; no push was performed.
- Verified `origin/main` is an ancestor of the deployment branch and that the
  working tree is clean. The ignored mode-0600 `.env` and dedicated mode-0600
  key file retained their ownership and permissions.
- Post-rebase checks passed: 15 local-LLM deployment tests, the upstream Naver
  navigation test, `bash -n start_services.sh`, and an exact operational
  `/api/chat` response `MEDIFLOW_REBASE_OK`. `models_initialized` stayed false.
  The first pytest invocation was blocked before collection by an unrelated ROS
  `launch_testing` plugin requiring absent `lark`; rerunning the same test with
  standard `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` passed 1/1 without installing or
  changing dependencies.
- `mediflow-kiosk status` remained stopped for both eye_server and kakao_app, as
  it was before deployment. No daemon was started, no cloud fallback was used,
  and no operational DB, model, user data, CUDA/PyTorch or B artifact changed.


## 2026-09-21 — Jetson B manual lifecycle hardening

- Kept the repository's explicit no-autostart policy. Added
  `scripts/local_llm_service.py` with manual `start`, `stop`, `restart`, `status`
  and `logs` actions; it installs no systemd/cron/desktop entry and downloads no
  artifact.
- Startup still delegates to `run_local_llm_candidate.sh`, preserving the pinned
  llama.cpp revision, artifact digest and protected key-file checks. The manager
  records a private JSON identity and validates user, executable, complete argv,
  working directory, boot ID and process start ticks before signalling only that
  PID. It refuses an unmanaged listener on port 8080.
- Mock verification passed 6 lifecycle safety tests. The existing 21 AI-client,
  5 artifact-manifest and 4 Jetson-deployment tests also passed; Python compile,
  launcher bash syntax and `git diff --check` passed. The first sandboxed
  AI-client run could not bind a loopback test port; the approved loopback rerun
  passed all 21 tests.
- Copied only the manager to B's existing private control tree and verified its
  Python compilation and mode 0755. Read-only `status` correctly reported the
  existing PID 2686054 listener as `unmanaged process detected on port 8080`;
  no JSON PID record was fabricated, no signal was sent, and the running service
  was not restarted. The one-time cutover remains pending explicit service-stop
  approval.


## 2026-09-21 — Jetson B managed-manual cutover and recovery

- With explicit user authorization for the brief interruption, revalidated the
  existing legacy PID 2686054 against the exact expected owner, executable,
  complete argv and working directory. It stopped cleanly on SIGTERM; no
  SIGKILL or broad process match was used. Port 8080 closed, and the old
  mode-0600 PID record was preserved as `llama-server.pid.pre-manager-20260921`.
- Started the same pinned Qwen/llama.cpp candidate through
  `local_llm_service.py`. The manager wrote mode-0600 PID JSON and log files,
  reported health ready, rejected unauthenticated `/v1/models` with 401, and
  accepted the dedicated protected key with 200. A returned exact
  `MEDIFLOW_MANAGED_OK` through the repository local client.
- Exercised managed stop/status and confirmed port 8080 closed. While stopped,
  A returned `connection_failed` with exit 1 even when dummy OpenAI and Gemini
  keys were present; no cloud fallback occurred. Managed start restored ready
  state under new PID 2738092 and A again returned exact
  `MEDIFLOW_MANAGED_OK`.
- A's `eye_server` and `kakao_app` remained stopped before and after this work.
  No kiosk daemon, systemd/cron/autostart entry, operational DB, model artifact,
  CUDA/PyTorch package, user data, `.env`, HASH_PEPPER or research result was
  changed. No real-data purge or medical-quality evaluation ran.


## 2026-09-21 — post-lifecycle full verification

- Re-ran complete unittest discovery after adding the lifecycle manager: 114
  attempted, 111 passed, one Linux `/proc` test skipped on macOS, and the same
  two development-host import errors remained (`pytorch_grad_cam`, `qrcode`).
  The new lifecycle tests all passed; no new regression was found.
- Parsed all 70 repository Python files outside virtual environments and all
  three pinned JSON files. `git diff --check` passed and `.env` still has no diff.
- Scanned the repository for the supplied device passwords and common API-token
  prefixes; none were present. Matches for `1234` were existing example phone
  numbers only.
- Removed accidental literal patch-marker `+` prefixes from
  `PROJECT_CONTEXT.md`, updated the B managed-manual state, and refreshed the
  full-suite and AST counts in `HANDOFF.md`.


## 2026-09-21 — official MedGemma access probe

- Checked B without stopping the managed general LLM. A Hugging Face token file
  exists, is owned by `jetson2`, and is mode 0600; `huggingface_hub` is installed.
  No official MedGemma cache directory exists.
- Sent authenticated metadata and access-only requests to the official pinned
  revision without persisting a response body. The revision API returned 200
  and exact SHA match; metadata reported `gated=auto` and no
  `userAccessRequestStatus`. Both HEAD and one-byte range GET for pinned
  `config.json` returned 403.
- Recorded `BLOCKED_ACCESS_TERMS`. No config, processor, model weight, container,
  package or token was downloaded or changed; the general LLM remained ready.


## 2026-09-21 — B capacity and pinned container manifest preflight

- Without stopping the managed LLM, confirmed B's root filesystem has 143 GiB
  available at 34% use. The private AI tree uses 5.7 GiB and the Hugging Face
  cache uses 25 MiB.
- Inspected, but did not pull, the pinned NVIDIA PyTorch 25.05 Linux/arm64 image
  manifest. Its exact digest resolves to 63 layers totaling 4,975,299,603
  compressed bytes (4.634 GiB). Extracted Docker storage will be larger.
- The general LLM remained managed and ready. No image, package, model or model
  response body was downloaded; no service or host runtime was changed.

## 2026-09-21 — pinned NVIDIA PyTorch container core compatibility on B

- After explicit authorization, pulled only
  `nvcr.io/nvidia/pytorch@sha256:c7a797978bfcdd5b9046b448c5defa290e7662be0f4c63497599c8428d3d6efb`.
  Docker inspection reported the same image ID and repo digest, `linux/arm64`,
  and 4,975,365,491 bytes. Root free space changed from 143 GiB to 127 GiB.
- Kept the managed Qwen/llama.cpp service running throughout the pull. For the
  compatibility run only, stopped it with the verified lifecycle manager,
  confirmed port 8080 closed, and ran the pinned container with NVIDIA runtime,
  no network, no model/token mount, read-only root and code mount, dropped
  capabilities, `no-new-privileges`, and automatic container removal.
- The first invocation reached no project code because the private control-tree
  bind mount was unreadable to the container. The manager's exit trap restored
  the LLM. Copied only the two report source modules into a dedicated readable,
  read-only probe mount and repeated the bounded test. No dependency or host
  runtime was modified.
- The successful report returned `READY_CORE`: L4T 36.5.2, aarch64, Python
  3.12.3, NVIDIA PyTorch `2.8.0a0+5228986c39.nv25.05`, built CUDA 12.9,
  `torch.cuda.is_available() == true`, one `Orin` device, and `model_loaded=false`.
  The JSON evidence SHA-256 is
  `8bfd31a3ab78bebd56c2afe035bb41fbfbf32fda2ca0bd4ef7795b92a7fa48c2`.
  This verifies the container's PyTorch/CUDA core only; it does not verify a
  MedGemma load, memory fit, inference, provenance, or medical quality.
- Each bounded interruption recovered the same pinned general LLM under a new
  validated PID. Final status was ready on port 8080. A's repository client
  passed generation in 854.9 ms and an exact
  `MEDIFLOW_CONTAINER_RECOVERY_OK` assertion. A's `eye_server` and `kakao_app`
  remained stopped. The Hugging Face cache stayed 25,346,198 bytes; no official
  MedGemma config or weight was downloaded. The post-terms pinned-config access
  recheck still returned HTTP 403, so official source access remains blocked.
- Post-change verification passed 5 artifact-manifest, 5 Jetson-compatibility,
  and 6 lifecycle-manager tests. The 21 loopback AI-client tests passed when
  rerun with host loopback permission. Full discovery retains only the two known
  missing development dependencies (`pytorch_grad_cam`, `qrcode`) plus one
  Linux-only skip. AST parsing passed for 70 Python files, four JSON evidence/
  manifest files parsed, `git diff --check` passed, `.env` has no diff, and the
  supplied device passwords were absent from repository files.

## 2026-09-21 — E2 survey and E4 hybrid review implementation

- Rechecked official MedGemma access without downloading a response body. The
  protected token authenticates as `Supermassive111`, but the pinned revision's
  `config.json` HEAD still returns HTTP 403. The managed general LLM stayed ready.
- Froze `eye-survey-1.0` for E2 as enumerated fields only. The store rejects free
  text, labels, diagnosis, predictions, confidence and Grad-CAM, makes each
  sample's survey immutable, and requires it before E2 enqueue. The VLM worker
  includes it only when the independent default-off survey flag is enabled and
  records the survey digest.
- Added deterministic E4 `paired-review-v1` for completed same-sample E0 plus
  E1/E2 results. It reads no image, invokes no model, cannot update a user result,
  and stores `agreement`, `disagreement`, or `not_comparable` in a separate table.
  The store revalidates source identity/digests and recomputes the rule before
  commit. Evaluation returns `HYBRID_REVIEW_ONLY`, never classification accuracy.
- Migrated the private experiment schema to version 3 with `survey_inputs` and
  `hybrid_reviews`. Authorized retention purge now removes these sample-scoped
  records before their source predictions while preserving shared runs and the
  operational source. No real data or device purge was used.
- Added independent default-off flags, CLI commands, admin capability/report
  rendering, frozen profile metadata, and protocol/runbook instructions. Six new
  E2/E4 mock tests pass together with existing worker, evaluation, explanation,
  and retention tests. Hardware MedGemma inference and medical quality evaluation
  remain `NOT_RUN`/`BLOCKED_ACCESS`/`BLOCKED_DATA`.
- Full unittest discovery attempted 120 tests: 117 passed, one Linux-only test
  skipped, and the same two development-host dependencies were absent
  (`pytorch_grad_cam`, `qrcode`). AST parsing passed for 73 Python files, four
  JSON files parsed, `git diff --check` passed, `.env` has no diff, and the
  supplied device passwords are absent from repository files.
- Final read-only B verification at `2026-09-21T03:28:24Z` confirmed managed
  PID 3844752 still listening on port 8080 and `/health` returning
  `{"status":"ok"}`. The earlier silent SSH status session was terminated
  locally; the model process was not stopped or restarted.
- After the user replaced B's Hugging Face login, a no-download recheck at
  `2026-09-21T04:16:03Z` authenticated as `therabbit0302`. The pinned revision
  SHA still matched, but `config.json` HEAD returned HTTP 403 and access status
  remained unset. This account must accept the HAI-DEF terms in the browser;
  no model body or weight was downloaded. Jetson A does not require Hub login.

## 2026-09-21 — official MedGemma source, conversion, and custom API probe

- Completed HAI-DEF access acceptance in the browser. B's authenticated pinned
  revision check returned HTTP 200. Downloaded the two official safetensor shards
  into the isolated model directory and verified their recorded byte sizes and
  SHA-256 values. No token value was persisted in repository evidence.
- Kept B's host CUDA/PyTorch installation unchanged. In the exact pinned NVIDIA
  PyTorch 25.05 arm64 container, the processor loaded offline, but full BF16 CUDA
  model loading exceeded the 8 GB unified-memory budget. This path remains
  `BLOCKED_MEMORY`; it did not silently fall back to CPU.
- Built llama.cpp `391fac16460f15233a7740550d858ac96df3419d` for CUDA
  architecture 87 and converted only the verified official source. Recorded and
  verified the BF16 GGUF, Q4_K_M text GGUF, and F16 vision-projector GGUF hashes.
  An initial conversion while the general LLM was resident caused a device reboot;
  after recovery, the same conversion succeeded with exclusive scheduling and a
  temporary output file. The managed general LLM was restored.
- GPU offload of both text and projector exceeded memory. The successful bounded
  path keeps the Q4 text model on CUDA and the projector explicitly on CPU. A
  direct synthetic image prompt succeeded before the service integration.
- Added the source-attested `llama_cpp_cli` backend to the existing custom
  MedGemma API, including exact revision checks, absolute non-symlink paths,
  offline mode, single request bounds, JSON schema, private temporary images, and
  guaranteed image deletion. llama-mtmd may emit generation on either stream;
  the service validates each stream independently and never merges diagnostics
  into a response. Six focused service tests pass.
- With the general LLM stopped by its manager, B's `/readyz` reported the CUDA
  text/CPU projector placement. The custom `/v1/analyze-eye` returned HTTP 200,
  `vision_ingested=true`, and a strict-contract abstention for a generated
  224x224 red/blue fixture in 73.253 seconds. The fixture contained no medical or
  user data. The general LLM was restored afterward; its managed status and
  `/health` were ready on port 8080.
- This verifies source provenance, artifact integrity, image ingestion, and one
  synthetic API request only. No operational image, medical label, clinical
  metric, sustained load, thermal behavior, or OOM-recovery quality was evaluated.
- Final verification attempted 123 unit tests: 120 passed, one Linux-only test
  skipped, and the same two development-host imports were unavailable
  (`pytorch_grad_cam`, `qrcode`). The six MedGemma service and five artifact
  manifest tests pass. AST parsing passed for 73 Python files, five JSON files
  parsed, relevant shell syntax and `git diff --check` passed, and `.env` has no
  diff. Final B state had managed general LLM PID 8244 healthy on port 8080,
  no MedGemma service process, and no listener on port 8081.
