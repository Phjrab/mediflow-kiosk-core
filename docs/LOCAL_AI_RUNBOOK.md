# Local AI runbook

> Current-reading note (2026-09-24): the table and direct B:8080 examples below
> record the 2026-09-21 local-AI integration checkpoint. The later
> [Admin Control handoff](agent/admin-control/HANDOFF.md) records A deployment
> `9cc410a`, B controller release `86bebb6`, managed ingress on B:8080,
> controller loopback 8090, and raw model runtime on B loopback 18080/18081.
> On that later checkpoint, chat is active, MedGemma is stopped, and no new live
> Apply/model transition was performed during Admin activation. Revalidate
> exact deployed versions and ownership before using any historical command
> below as a current operating procedure.

This runbook separates the kiosk host (A) from the general LLM and research VLM
host (B). A third VLM host (C) is optional. No step requires the LLM and VLM to
remain resident on the same GPU.

## 2026-09-21 integration checkpoint (historical)

| Host | Intended role | Read-only observation | Status |
| --- | --- | --- | --- |
| A | Existing kiosk, `/api/chat` client, E0 baseline | Orin Nano 8 GB class, L4T R36.4.7, Python 3.10 | `ab6f840` deployed and pushed; 141 tests plus synthetic E0-E4 workflow passed |
| B | General LLM or MedGemma service | Orin Nano 8 GB class, L4T R36.5.2, CUDA toolkit 12.6.11, Python 3.10 | General LLM managed on port 8080; official-source Q4 MedGemma custom API passed one synthetic request under sequential scheduling |
| C | Optional VLM host | Not supplied | `NOT_RUN` |

The pinned Qwen model was downloaded to B, verified by byte size and SHA-256,
and run through the pinned native CUDA `llama.cpp` build. Dedicated mode-0600
LLM and VLM keys are stored on A without printing their contents. A's operational
branch `codex/local-llm-operational` is deployed and pushed at `ab6f840`; all 141
device tests passed. Recovery branch `backup/pre-shadow-ai-20260921-1600` and a
private pre-change `.env` backup exist. Hash checks confirmed that deployment and
the synthetic workflow did not change A's `.env` or operational DB.

B's general-LLM service remains owned by the repository's manual lifecycle
manager, not an installed boot service. Official MedGemma source shards and the
source-derived Q4_K_M/F16 GGUF files are hash verified. E1 and E2 completed under
sequential scheduling; MedGemma was then stopped and the general LLM restored.

## Same-sample synthetic device integration

On 2026-09-21, A generated one 224x224 red/blue engineering fixture and stored
it only in a private research directory. E0 used A's existing CUDA EfficientNet
and saved a Grad-CAM artifact. B then stopped its managed general LLM and served
the source-attested MedGemma Q4 endpoint for E1 and E2 sequentially. Both VLM
arms returned valid abstentions. B stopped MedGemma and restored the general LLM;
E3 then generated one local explanation from E0 JSON only, and E4 produced a
deterministic `not_comparable` review with manual review required.

All five jobs succeeded. The E0/E1 comparison recorded one paired attempt and
zero paired assessed results, so agreement is `N/A` and explicitly not accuracy.
Five JSON, CSV, and Markdown report sets were saved with mode 0600. Evidence is
`docs/agent/evidence/jetson-a-synthetic-e0-e4-2026-09-21.json`. This is software
integration evidence from a generated fixture, not medical-quality evidence.

## Pinned first-deployment candidates

`config/ai_artifact_candidates.json` records the immutable metadata gathered
from the official registries on 2026-09-20. The general LLM entry also records
the completed B verification; the MedGemma entries remain candidates:

- General chat: `Qwen/Qwen2.5-3B-Instruct-GGUF` Q4_K_M at revision
  `7dabda4d13d513e3e842b20f0d435c732f172cbe`, served by `llama.cpp` release
  `v0.4.1` at commit `391fac16460f15233a7740550d858ac96df3419d`.
- Isolated MedGemma runtime: NVIDIA's signed
  `nvcr.io/nvidia/pytorch:25.05-py3-igpu` manifest
  `sha256:774bbc5cbedfd5d432129e2ae79a7f6de6f267afa8e1f4b3b44dead00f790c79`.
  NVIDIA's Jetson matrix lists framework release 25.05/PyTorch 2.8 for JetPack
  6.2. The exact Linux/arm64 digest is pulled on B. A no-network, no-model,
  read-only probe returned `READY_CORE` with CUDA available on one Orin device.
  Evidence is in
  `docs/agent/evidence/jetson-b-pytorch-25.05-compat-2026-09-21.json`.
- MedGemma source: `google/medgemma-1.5-4b-it` revision
  `91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b`. The HAI-DEF terms were accepted,
  the pinned source returned HTTP 200, and both BF16 safetensor shards were
  downloaded on B. Their combined size is 8,600,277,880 bytes and their individual
  SHA-256 values are recorded in `config/ai_artifact_candidates.json`.
- Source-derived llama.cpp artifacts: Q4_K_M text model SHA-256
  `c39d76e3cb4678bec663cab92b39ac45ad86378c26c978c023b4f6d81ce0f45c`
  and F16 projector SHA-256
  `77bcbe7f2847d5f6c098c02ca99aeb4defadd3482469928fbf5e5924acb78733`.
  The exact runtime commit is `391fac16460f15233a7740550d858ac96df3419d`.

The full BF16 Transformers load was attempted in the pinned NVIDIA container
after stopping the general LLM and failed because the 8 GB unified-memory budget
was insufficient. That path remains `BLOCKED_MEMORY`. The source-derived Q4_K_M
text model runs on CUDA while the F16 vision projector stays on CPU; GPU projector
offload also exceeded the memory budget. This mixed placement is explicit and is
not a silent text-model CPU fallback. llama.cpp labels the mtmd CLI experimental,
so the result is an engineering research baseline rather than a production or
medical-quality claim.

An Ollama probe candidate is also pinned: official image `0.32.15` by multi-arch
and Linux/arm64 digests, plus `medgemma1.5:4b` Q4_K_M by serving-manifest and
3,338,928,384-byte model-layer digests. Google's FAQ links Ollama as a local
MedGemma option and Ollama's Docker documentation supplies `JETSON_JETPACK=6`.
The serving manifest does not attest the exact originating Google model commit or
conversion procedure. It is therefore `BLOCKED_PROVENANCE` for E1 research and
was used only for a non-sensitive hardware/image-ingestion probe. With the
general LLM stopped, Ollama detected CUDA 12.6/compute 8.7, offloaded 34/35
layers, and returned the correct dominant color for generated red and blue PNGs.
The container used about 4.897 GiB and was removed after the probe. This confirms
hardware and image ingestion only; it remains excluded from E1 until the exact
source revision and conversion mapping are established. Do not mix its results
into a run whose manifest claims the pinned Google source revision.

After files have been acquired into a private directory, verify them offline
before any model load:

```bash
python3 scripts/verify_ai_artifacts.py \
  --component general_llm \
  --root <PRIVATE_QWEN_MODEL_DIRECTORY>

python3 scripts/verify_ai_artifacts.py \
  --component medgemma_source \
  --root <PRIVATE_MEDGEMMA_MODEL_DIRECTORY>

python3 scripts/verify_ai_artifacts.py \
  --component medgemma_gguf \
  --root <PRIVATE_MEDGEMMA_GGUF_DIRECTORY>
```

The verifier rejects missing files, size/digest mismatches, symlinks and path
escapes. It performs no download and writes nothing to the artifact directory.

## A: preserve the kiosk and select one chat provider

Keep the existing `.env`. Add only reviewed keys that are missing. Never replace
`HASH_PEPPER`, application secrets, database paths, or existing cloud keys.

```dotenv
LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://<B_LAN_IP>:8080/v1
LOCAL_LLM_MODEL=<SERVER_MODEL_ALIAS>
LOCAL_LLM_API_KEY_FILE=<ABSOLUTE_MODE_0600_KEY_FILE>
AI_ALLOWED_ENDPOINTS=http://<B_LAN_IP>:8080
AI_DEPLOYMENT_PROFILE=chat_only
```

Use exactly one of `LOCAL_LLM_API_KEY` and `LOCAL_LLM_API_KEY_FILE`. File mode
must deny all group/other access, the file must be regular rather than a symlink,
and it must be owned by the kiosk process user. The file form keeps the token out
of `.env` and process arguments.

`LLM_PROVIDER` accepts exactly `openai`, `gemini`, or `local`. The selected
provider receives one request. A local error is returned to the user and never
causes an automatic OpenAI or Gemini request. `/api/chat/status` checks
configuration without generating text. Both chat routes bypass baseline model
initialization, so checking or using remote chat does not load EfficientNet.

The local backend contract is OpenAI-compatible Chat Completions at
`POST /v1/chat/completions`. The v1 client accepts a literal private/loopback IP
whose exact origin appears in `AI_ALLOWED_ENDPOINTS`; it does not use redirects,
DNS names, or environment HTTP proxies.

Read-only configuration and CUDA preflight:

```bash
python3 scripts/ai_preflight.py
```

For a machine-readable Jetson stack report that does not use the network, load a
model, or alter packages:

```bash
python3 scripts/jetson_ai_compat_report.py > jetson-ai-compat.json
```

The command exits zero only for `READY_CORE`. This means the observed PyTorch
core can see CUDA; it does not mean an LLM, MedGemma, memory budget, or medical
quality has passed. Keep the JSON with the deployment evidence and do not include
credentials or model tokens in it.

The recorded B container probe stopped the managed general LLM only for the
bounded GPU check, confirmed port 8080 closed, and restored it through an exit
trap. The container used `--runtime nvidia`, `--network none`, a read-only root
and source mount, dropped capabilities, `no-new-privileges`, and `--rm`. No Hugging
Face token or model directory was mounted. `READY_CORE` is limited to PyTorch/CUDA
initialization; do not treat it as MedGemma inference or quality evidence.

After B is independently running, use non-sensitive text only:

```bash
python3 scripts/ai_smoke_test.py --question "연결 상태 확인용 문장입니다."
```

Build the pinned `llama.cpp` source in a separate directory on B with CUDA. Do
not replace the existing Python/PyTorch installation:

```bash
git clone https://github.com/ggml-org/llama.cpp.git <PRIVATE_LLAMA_CPP_DIR>
git -C <PRIVATE_LLAMA_CPP_DIR> checkout 391fac16460f15233a7740550d858ac96df3419d
cmake -S <PRIVATE_LLAMA_CPP_DIR> -B <PRIVATE_LLAMA_CPP_DIR>/build \
  -DGGML_CUDA=ON -DGGML_CUDA_FA=OFF \
  -DCMAKE_CUDA_ARCHITECTURES=87 -DCMAKE_BUILD_TYPE=Release
cmake --build <PRIVATE_LLAMA_CPP_DIR>/build --config Release \
  --target llama-server -j4
```

The explicit architecture is required for Orin. The first configure attempt on
B used the toolkit's generic architecture set and was stopped after `compute_90`
appeared in compiler commands. The verified build uses only architecture 87.
FlashAttention was disabled for this first 4096-context baseline; CUDA layer
offload remains enabled.

Create a separate mode-0600 API-key file outside the repository. After the
Qwen file passes `verify_ai_artifacts.py`, start the foreground service:

```bash
export LLAMA_CPP_DIR=<PRIVATE_LLAMA_CPP_DIR>
export LOCAL_LLM_MODEL_DIR=<PRIVATE_QWEN_MODEL_DIRECTORY>
export LOCAL_LLM_API_KEY_FILE=<PRIVATE_MODE_0600_KEY_FILE>
bash scripts/run_local_llm_candidate.sh
```

The launcher refuses a source revision mismatch, changed model bytes, symlinks,
or a broadly readable key file. It binds port 8080 with API-key authentication,
one request slot, a 4096-token context, full CUDA layer offload, no prompt cache,
no slot endpoint, and no web UI. The command remains foreground-only; it does
not install an autostart service.


For repeatable manual operation, use the lifecycle manager with the same three
protected path variables. `LOCAL_LLM_CONTROL_DIR` is optional; when set, it must
be an absolute private directory owned by the service user.

```bash
export LLAMA_CPP_DIR=<PRIVATE_LLAMA_CPP_DIR>
export LOCAL_LLM_MODEL_DIR=<PRIVATE_QWEN_MODEL_DIRECTORY>
export LOCAL_LLM_API_KEY_FILE=<PRIVATE_MODE_0600_KEY_FILE>
export LOCAL_LLM_CONTROL_DIR=<PRIVATE_STATE_DIRECTORY>

python3 scripts/local_llm_service.py start
python3 scripts/local_llm_service.py status
python3 scripts/local_llm_service.py logs
python3 scripts/local_llm_service.py restart
python3 scripts/local_llm_service.py stop
```

The manager always delegates startup to the pinned candidate launcher. It writes
a mode-0600 JSON record and validates the process user, executable, complete
argument vector, working directory, boot ID and process start ticks before it
sends a signal. It refuses an occupied unmanaged port and never uses broad
process matching. A stale record from an earlier boot is removed only when its
recorded process no longer exists. These commands remain manual: the manager
does not create a systemd unit, cron entry, desktop autostart or artifact download.
If a pre-existing hand-started server owns port 8080, `status` reports
`unmanaged process`; perform a reviewed one-time transition before using
`restart` or `stop` through the manager.

### Verified B baseline, 2026-09-20

- `llama-server` reports `0.4.1-dev`, build 10969, commit `391fac164`, Linux
  aarch64, and `CUDA0: Orin (7607 MiB)`.
- The Qwen file is 2,104,932,768 bytes and matches SHA-256
  `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`.
- Health returned 200. Unauthenticated `/v1/models` returned 401; the same call
  with the dedicated key returned 200 and the pinned alias.
- B-local deterministic smoke output was `MEDIFLOW_LOCAL_OK` in 0.699 seconds;
  measured generation was 14.20 tokens/s for six output tokens.
- A-to-B direct chat returned `MEDIFLOW_A_TO_B_OK` in 0.553 seconds. The repository
  client returned `MEDIFLOW_CLIENT_OK`; after launcher restart it returned
  `MEDIFLOW_RESTART_OK` in 0.700 seconds.
- A's isolated staging `/api/chat/status` returned configured/local and
  `/api/chat` returned `MEDIFLOW_API_ROUTE_OK`, while `models_initialized`
  remained false. The later minimal operational promotion returned exact
  `MEDIFLOW_OPERATIONAL_DEPLOY_OK`; a forced B outage failed locally without
  cloud fallback, and restart returned exact `MEDIFLOW_OPERATIONAL_RECOVERY_OK`.
- After the launcher restart, B showed about 2.75 GiB server RSS, 2.9 GiB system
  memory available, and 443 MiB swap used. This is a one-request smoke baseline,
  not a concurrency, soak, OOM-recovery, or medical-quality result.
- On 2026-09-21, the pre-manager PID 2686054 was accepted only after its
  owner, executable, full argv and working directory matched the reviewed
  deployment. It exited on SIGTERM; its mode-0600 PID file was preserved. The
  lifecycle manager then started and recorded the same pinned service. Managed
  stop produced an A-side `connection_failed` even with dummy cloud keys, with
  no fallback; managed start restored health, authenticated access and exact
  `MEDIFLOW_MANAGED_OK` generation. The final observed managed PID was 2738092.

Run the existing kiosk with its existing command:

```bash
mediflow-kiosk start
mediflow-kiosk status
mediflow-kiosk logs
```

The admin config page can change the provider and masked credentials. Saving is
staged into a temporary file and atomically replaces `.env` only after validation.
When `LOCAL_LLM_API_KEY_FILE` is active, the page reports a protected-file source
and disables inline local-token replacement/deletion to avoid ambiguous credentials.

A's pre-promotion recovery point is branch
`backup/pre-local-llm-20260920-2335`; the private backup directory is
`/home/jetson_orin_nano/mediflow-ai/backups/pre-local-llm-20260920-2335`.
Restore only during a reviewed rollback: stop the kiosk if it is running, restore
the tracked files from Git or the archive, restore `env.before` with mode 0600,
remove only the three added utility modules, smoke-test, then restart. Do not
restore or modify the operational DB, models, user assets or CUDA/PyTorch.

## B/C: MedGemma custom research service

The implemented service is a custom API, not an OpenAI-compatible endpoint:

```text
GET  /healthz
GET  /readyz
POST /v1/analyze-eye
```

It supports the pinned Transformers path and a `MEDGEMMA_RUNTIME=llama_cpp_cli`
path. Transformers loads only approved local files and requires CUDA placement.
The llama.cpp path verifies an absolute non-symlink binary and GGUF files, checks
the exact runtime commit, keeps the text model on CUDA, and uses the explicitly
recorded CPU vision-projector placement required by B's memory budget.
Acquisition of model files, licence/access acceptance, revision selection, and
hash verification happen before runtime setup and are not automated by this
repository. Record the approved revision and hashes by copying and completing
`services/medgemma/model_manifest.example.json` outside Git.

`services/medgemma/requirements-medgemma.in` is an input list, not a Jetson lock
file. Resolve versions only after the JetPack/L4T/driver/PyTorch compatibility
matrix is verified. On the currently inspected B, do not install another wheel
or alter CUDA until that mismatch has a reviewed remediation plan.

### B compatibility finding and safe remediation boundary

NVIDIA identifies Jetson Linux 36.5 as the JetPack 6.2.2 production line. Its
packaged compute stack uses CUDA 12.6. NVIDIA's current Jetson PyTorch matrix
lists the 2.7/2.8 development releases against JetPack 6.2, while 2.11 appears
against JetPack 7.1. The observed B combination (`R36.5.2`, toolkit 12.6.11,
PyTorch `2.11.0+cu130`) is therefore not a supported combination in that matrix,
which agrees with the live `cuda_available=False` result.

Do not repair this by upgrading the existing user installation in place. Preserve
it. The selected first container candidate is the pinned NVIDIA 25.05 iGPU image
above. Its exact Linux/arm64 digest is pulled and the isolated core compatibility
report passes. Keep using that digest and the no-network/no-model isolation for
future probes. The current matrix has no standalone NVIDIA wheel entry for its
JetPack 6.2 rows, so do not invent a wheel URL from a version pattern. General LLM serving uses the separate
`llama.cpp` candidate and does not depend on the user PyTorch installation. Start
only one GPU-heavy service at a time until memory and timeout recovery have been
measured.

For the BF16 Transformers path, the manual foreground command is:

```bash
export MEDGEMMA_MODEL_DIR=<APPROVED_LOCAL_MODEL_DIRECTORY>
export MEDGEMMA_MODEL_MANIFEST=<PRIVATE_MODEL_MANIFEST_JSON>
export MEDGEMMA_API_KEY=<DEDICATED_VLM_TOKEN>
export MEDGEMMA_HOST=0.0.0.0
export MEDGEMMA_PORT=8081
python3 services/medgemma/app.py
```

For B's source-attested Q4 path, use a private manifest based on
`services/medgemma/model_manifest.llama_cpp.example.json` and set:

```bash
export MEDGEMMA_RUNTIME=llama_cpp_cli
export MEDGEMMA_MODEL_MANIFEST=<PRIVATE_LLAMA_CPP_MANIFEST_JSON>
export MEDGEMMA_LLAMA_CPP_BIN=<PINNED_LLAMA_MTMD_CLI>
export MEDGEMMA_GGUF_MODEL=<VERIFIED_Q4_K_M_GGUF>
export MEDGEMMA_GGUF_MMPROJ=<VERIFIED_F16_PROJECTOR_GGUF>
export MEDGEMMA_API_KEY=<DEDICATED_VLM_TOKEN>
export MEDGEMMA_HOST=127.0.0.1
export MEDGEMMA_PORT=8081
python3 services/medgemma/app.py
```

The verified request used a synthetic 224x224 fixture, returned HTTP 200 with
`vision_ingested=true` in 73.253 seconds, and produced a strict-schema abstention.
It used no operational/user image and provides no medical-quality evidence.

The service is deliberately single-flight and has no autostart installer. Stop
the foreground process with `Ctrl-C`. Its request logs omit images and prompts.

The same B can run the local general LLM for `/api/chat` and E3 explanations.
E3 is a manual research worker and uses a completed E0 result JSON without an
image. Run `explanation-once` only under `chat_only`; stop the general LLM before
switching B to `vlm_only` for E1. This preserves sequential comparison without
requiring both models to remain on the GPU.

On A, enable research only after the service is ready:

```dotenv
AI_EXPERIMENTS_ENABLED=1
VLM_ENABLED=1
SURVEY_VLM_EXPERIMENTS_ENABLED=0
HYBRID_REVIEW_EXPERIMENTS_ENABLED=0
AI_EXPERIMENT_MODE=shadow
AI_EXPERIMENT_AUTO_ENQUEUE=0
AI_DEPLOYMENT_PROFILE=vlm_only
VLM_BACKEND=medgemma_custom_v1
VLM_BASE_URL=http://<B_OR_C_LAN_IP>:8081
VLM_MODEL=google/medgemma-1.5-4b-it
VLM_API_KEY=<DEDICATED_VLM_TOKEN>
AI_ALLOWED_ENDPOINTS=http://<B_OR_C_LAN_IP>:8081
EXPERIMENT_DATA_DIR=<ABSOLUTE_PRIVATE_DIRECTORY_OUTSIDE_WEB_STATIC>
```

Verify one explicitly non-sensitive image:

```bash
python3 scripts/vlm_smoke_test.py \
  --image <NON_SENSITIVE_JPEG_OR_PNG> \
  --confirm-non-sensitive
```

E2 and E4 remain separately disabled even when E1 is enabled. For E2, validate
and freeze an `eye-survey-1.0` JSON with `add-survey`, create an E2 run whose
config names that exact schema, then set `SURVEY_VLM_EXPERIMENTS_ENABLED=1` for
the manual VLM worker. The schema contains enumerated answers only and rejects
free text, diagnosis, labels, prior predictions, confidence, and Grad-CAM.

E4 runs on the experiment host after same-sample E0 and E1/E2 completion. Its
`paired-review-v1` rule is deterministic and requires
`HYBRID_REVIEW_EXPERIMENTS_ENABLED=1`; `hybrid-once` reads no image and starts no
model. It stores agreement/disagreement/not-comparable for research review and
never edits the operational result. See `docs/AI_EXPERIMENT_PROTOCOL.md` for the
closed schemas and commands.

`co_resident_verified` exists as an explicit profile but must be used only after
measured GPU memory, latency, timeout recovery, and load tests pass. The current
8 GB class B has no such verification. Switch between `chat_only` and `vlm_only`
by stopping the current model service, confirming its process/GPU allocation is
gone, starting the other service, and then changing A's profile. Do not treat a
client timeout as proof that remote generation stopped.

## Failure handling and rollback

- `unauthorized`: verify the dedicated token on both sides without printing it.
- `loading`: wait for `/readyz`; `/healthz` alone does not prove image readiness.
- `busy`: keep queue concurrency at one; do not start a second GPU request.
- `request_timeout`: consider the client recovering until remote idle is verified
  and the A process is restarted.
- OOM or non-CUDA placement: stop the owned research service and record the run as
  failed. Do not silently move MedGemma to CPU.
- Roll back research with `VLM_ENABLED=0`, `AI_EXPERIMENTS_ENABLED=0`,
  `BASELINE_EXPERIMENTS_ENABLED=0`, `SURVEY_VLM_EXPERIMENTS_ENABLED=0`, and
  `HYBRID_REVIEW_EXPERIMENTS_ENABLED=0`. Keep `LLM_PROVIDER` on the last explicitly
  selected provider. Existing screening and stored user results remain separate.
- Operational-history ROI registration also requires
  `EXPERIMENT_ALLOW_REAL_DATA=1`, an admin CSRF token, permission and retention
  references, a future retention date, and a research split. Turning either
  experiment flag off disables new imports without deleting existing data.
- Retention cleanup is a separate manual two-step operation: run
  `retention-status`, review each opaque ID and active-job state, then use
  `retention-purge` with explicit IDs and `DELETE_EXPIRED_RESEARCH_COPIES`.
  The command operates only inside `EXPERIMENT_DATA_DIR`; it does not open the
  operational database or delete shared run definitions.

Official references used for runtime assumptions:

- <https://developers.google.com/health-ai-developer-foundations/medgemma/model-card>
- <https://developers.google.com/health-ai-developer-foundations/medgemma/get-started>
- <https://huggingface.co/google/medgemma-1.5-4b-it>
- <https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform/index.html>
- <https://docs.nvidia.com/deeplearning/frameworks/install-pytorch-jetson-platform-release-notes/pytorch-jetson-rel.html>
- <https://catalog.ngc.nvidia.com/orgs/nvidia/-/containers/pytorch/25.05-py3-igpu>
- <https://developer.nvidia.com/embedded/jetpack-sdk-622>
- <https://docs.nvidia.com/jetson/archives/r36.5/ReleaseNotes/Jetson_Linux_Release_Notes_r36.5.pdf>
- <https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF>
- <https://github.com/ggml-org/llama.cpp/releases/tag/v0.4.1>
