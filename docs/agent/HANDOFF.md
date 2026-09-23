# Handoff — local AI and shadow research

## Repository state

- Path: `/Users/hajoonpark/자율설계/mediflow-kiosk-core`
- Branch: `codex/local-ai-shadow-experiments`
- Base: `2877e65f99bb1a3f9837b56c0736de57a4f66902`
- Feature commit `5c81b8d` is pushed as `origin/codex/local-ai-shadow-experiments`.
- No `AGENTS.md` exists. Preserve `.env`, `HASH_PEPPER`, CUDA/PyTorch,
  operational DB, weights, user data, and current changes.

## Stage status

| Stage | State | Evidence / limit |
| --- | --- | --- |
| P0 | DONE | Code, baseline, branch, and two devices inspected read-only |
| P1 | DEVICE_VERIFIED | Strict provider, bounded transport, A-to-B authenticated generation |
| P2 | OPERATIONAL_DEVICE_VERIFIED | Minimal local-chat overlay promoted on A with recovery point; exact route, outage/no-fallback, and recovery checks passed |
| P3 | SYNTHETIC_DEVICE_VERIFIED | Isolated same-sample store plus Jetson A E0 and private Grad-CAM artifact |
| P4 | SYNTHETIC_A_TO_B_DEVICE_VERIFIED | Source-attested MedGemma E1 and bounded-survey E2 workers succeeded on the same synthetic sample |
| P5 | SYNTHETIC_DEVICE_VERIFIED | Durable E0/E1 jobs, one paired sample, comparison, and private exports verified |
| P6 | SYNTHETIC_DEVICE_VERIFIED | E0/E1/E2/E3/E4 all succeeded; 15 private reports exported |
| P7 | PARTIAL / SOURCE_ATTESTED_Q4_DEVICE_VERIFIED | Official source and derived Q4 artifacts verified; BF16 full-CUDA is blocked by memory and medical evaluation remains unrun |
| P8 | DONE for current code scope | Runbooks, evidence, handoff updated |

## Implemented contracts

- `/api/chat` dispatches once to explicitly selected `openai`, `gemini`, or
  `local`; local failure does not fall back to cloud.
- `/api/chat/status` performs no generation.
- `/api/chat` and `/api/chat/status` bypass baseline model initialization. A
  private mode-0600 `LOCAL_LLM_API_KEY_FILE` can replace the inline token; both
  forms at once fail closed.
- Research defaults off and is separate from operational results.
- E0 and E1 can use the same private research sample. E0 is existing
  EfficientNet; E1 is independent image-only VLM. Arm-filtered workers do not
  require simultaneous GPU residency.
- E2 adds only a frozen `eye-survey-1.0` enumerated survey to the same ROI. It
  rejects free text, labels, prior predictions, confidence and Grad-CAM; its flag
  is independent and defaults off.
- E3 explains a completed same-sample E0 JSON using only the explicitly selected
  local LLM. It receives no image/reference label/Grad-CAM, stores output apart
  from predictions, and is excluded from image-classification metrics.
- E4 deterministically compares completed same-sample E0 and E1/E2 records. It
  reads no image, invokes no model, stores separately, reports agreement as not
  accuracy, requires manual review on disagreement/non-comparable input, and has
  no user-result action.
- Admin comparison reports paired agreement and says it is not accuracy.
- `GRADCAM_MODE` defaults to `always`; `on_demand` and `off` are explicit.
- The approved operational bridge copies only a selected-eye ROI through a
  query-only DB connection. It requires admin CSRF, permission and retention
  references, expiry, split, and `EXPERIMENT_ALLOW_REAL_DATA=1`. Expired samples
  cannot be enqueued. `retention-status` is read-only. The separately authorized
  `retention-purge` requires explicit expired sample IDs and the fixed confirmation
  string, preserves shared runs and operational sources, and was tested only on
  temporary mock data.

## Test state

- Targeted tests pass: local lifecycle manager 6, local client 21, experiments 27, MedGemma service 6,
  operational import 5, E3 explanation/migration 5, Jetson compatibility 5, Grad-CAM 4,
  retention purge 4, chat prompt 5, existing Jetson scripts 4, artifact pinning 5.
- Full discovery: 123 attempted, 120 pass, 1 Linux-only skip, 2 existing dependency
  errors (`pytorch_grad_cam`, `qrcode`) on macOS.
- AST 73 files, verified JSON 5 files, and `git diff --check` pass.
- Container evidence: `docs/agent/evidence/jetson-b-pytorch-25.05-compat-2026-09-21.json`
  (SHA-256 `8bfd31a3ab78bebd56c2afe035bb41fbfbf32fda2ca0bd4ef7795b92a7fa48c2`) reports `READY_CORE`.
- A staging additionally passes the 21 client and 5 artifact tests. Actual
  general-LLM generation and single-request timing were verified. A synthetic
  VLM image-ingestion/GPU probe also passed; no real-data or medical quality
  evaluation occurred.

## Device state

- A's operational branch `codex/local-llm-operational` merged the feature
  commit and is pushed at `ab6f840`. Recovery branch
  `backup/pre-shadow-ai-20260921-1600` preserves the pre-deployment `f4f0972`
  state, and a private mode-0600 `.env` backup exists. A's actual virtualenv ran
  all 141 discovered tests successfully. Pre/post hashes confirmed `.env` and the
  operational DB were unchanged; models, user data, HASH_PEPPER and CUDA/PyTorch
  were also preserved.
- B's root filesystem has 127 GiB available (42% used) after pulling the exact
  NVIDIA PyTorch 25.05 Linux/arm64 digest. Its 63 compressed layers total
  4,975,299,603 bytes; Docker inspection matched image ID and repo digest
  `sha256:c7a797978bfcdd5b9046b448c5defa290e7662be0f4c63497599c8428d3d6efb`.
- B's host Python remains unchanged and incompatible for this path. Inside the
  pinned container, the no-network/no-model report returned `READY_CORE` with
  L4T 36.5.2, PyTorch `2.8.0a0+5228986c39.nv25.05`, CUDA 12.9 available, and one
  Orin device. The processor probe succeeded, while full BF16 Transformers loading later failed from the measured memory limit.
- `config/ai_artifact_candidates.json` pins the deployment artifacts. B has the
  hash-verified Qwen file, exact llama.cpp commit, official pinned MedGemma source
  shards, and source-derived BF16, Q4_K_M, and F16 projector GGUF files. The
  source-attested Q4 path passed one synthetic custom-API request. The BF16
  Transformers path remains `BLOCKED_MEMORY`, and the older Ollama artifact is
  excluded from E1 because its conversion provenance is unattested.
- B's pinned general LLM is owned by the verified manual
  `local_llm_service.py` manager. It installs no autostart and validates a private
  process identity record before signalling. Each MedGemma operation stopped it
  through that manager and restored it in a trap. After the successful API probe,
  PID 8244 was managed on port 8080 and `/health` returned `{"status":"ok"}`.
- B has a private mode-0600 Hugging Face token. Browser acceptance for the
  HAI-DEF terms was completed, the exact pinned source returned HTTP 200, and both
  safetensor shards were downloaded and verified by byte size and SHA-256. Token
  contents were never written to repository evidence.
- The pinned Ollama 0.32.15 Linux/arm64 image and `medgemma1.5:4b` Q4_K_M
  artifacts are downloaded in B's isolated probe directory and verified by
  digest. With the general LLM stopped, the CUDA runner correctly classified
  generated red/blue fixtures and was then removed. It remains
  `BLOCKED_PROVENANCE` for E1 because its manifest does not attest the exact
  Google source revision/conversion lineage.
- On A, a mode-0700 research directory contains one generated 224x224 fixture,
  a mode-0600 isolated research DB, the E0 Grad-CAM artifact, and 15 mode-0600
  JSON/CSV/Markdown exports for E0-E4. All five jobs succeeded. E1/E2 abstained,
  E3 is marked explanation-review-required, and E4 recorded `not_comparable` with
  manual review and `agreement_is_accuracy=false`. No reference label was added.
- The dedicated VLM key was transferred directly from B to A after explicit user
  authorization and stored as an owned mode-0600 single-line file. It never
  passed through the development Mac, command arguments, logs, or Git.
- Credentials are not in repository files or command output. Dedicated API-key
  files on A and B are owned by their service users and mode 0600.
- The approved temporary deployment clone/archive cleanup is complete. A's
  operational checkout, existing staging tree, recovery branch and private
  recovery backup were explicitly rechecked and preserved.

## Resume from here

1. Review the two pushed branches before merging to `main`: feature commit
   `5c81b8d` and A deployment merge `ab6f840`. Keep A recovery branch
   `backup/pre-shadow-ai-20260921-1600` and its private `.env` backup.
2. B remains manual and sequential: the general LLM is the normal service on
   port 8080; MedGemma is stopped and port 8081 is free. Simultaneous residency
   on B is neither required nor verified.
3. The implementation and synthetic device workflow are complete. Remaining
   validation requires separately approved real research data, independent
   reference labels, governance records, and a medical-quality protocol.
4. Sustained load, thermal behavior, timeout/OOM recovery, and optional
   co-residency remain unverified. Do not infer them from the single-fixture run.
5. Review `retention-status` before any explicitly authorized purge. No
   operational record was imported or purged during this deployment.
