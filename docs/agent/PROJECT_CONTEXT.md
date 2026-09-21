# Verified context — 2026-09-21

Local development host: macOS, Python 3.13. The minimal general-LLM chat
overlay is deployed in A's operational checkout on local branch
`codex/local-llm-operational` at commit `f4f0972`, rebased onto current
`origin/main` (`2877e65`), with a clean working tree, recovery branches, and
private pre-change `.env` backup. It has not been pushed.
Repository path is `/Users/hajoonpark/자율설계/mediflow-kiosk-core`; branch
`codex/local-ai-shadow-experiments`, initial HEAD
`2877e65f99bb1a3f9837b56c0736de57a4f66902`. Initial worktree was clean. No
`AGENTS.md` exists. The supplied integrated specification is under `docs/agent`.

Baseline: MediaPipe eye ROI is resized to 224x224 using INTER_AREA in detector;
bilateral/upload paths apply INTER_CUBIC before classifier's PIL BILINEAR and
ImageNet normalization. Iris removal belongs to analyzer, not classifier.
Classifier uses inference_mode only for forward and a separate Grad-CAM lock.
Class IDs from config.py: 0 conjunctivitis, 1 eyelid, 2 cataract, 3 normal,
4 uveitis. Checkpoint contract unchanged; real model inference NOT_RUN.
Bilateral/upload results have confidence in percent with `class`; legacy diagnose
uses fractional confidence with `disease_class`. Browser results are untrusted.

`/api/chat` receives `user_message` and `diagnosis_result`. The implementation now
preserves OpenAI/Gemini and adds an exact local provider without cloud fallback.
The widget uses generation-free status and no canned error answer. Research data
uses a separate private store and is not read by operational DB/PDF/user results.
Chat routes bypass baseline model initialization, and the local credential can be
read from an owned mode-0600 file instead of `.env`.
With explicit user authorization, an admin-only bridge may copy one selected-eye
ROI from operational history. It uses a query-only DB connection, does not copy
the full frame or existing analysis fields, and requires permission, retention,
expiry, and split metadata. No real operational record has been imported in tests.

Expired research-copy cleanup is an explicit two-step operation. A read-only
inventory is separate from a confirmed purge of named sample IDs. The purge is
confined to the research store, preserves shared runs and unrelated audit records,
and never opens the operational DB. Only temporary mock copies have been purged
during verification.

Devices A and B are reachable and both are Orin Nano 8 GB class systems. A reports
L4T R36.4.7 and B R36.5.2. B's existing host PyTorch remains unchanged and
incompatible with its driver, while the exact NVIDIA PyTorch 25.05 Linux/arm64
container reports CUDA `READY_CORE`. The official pinned MedGemma source is now
accessible and its two safetensor shards were downloaded and hash verified on B.
The full BF16 Transformers load exhausted the available 8 GB unified-memory
budget, so that path remains `BLOCKED_MEMORY`.

B also has an exact commit `391fac16460f15233a7740550d858ac96df3419d`
CUDA architecture-87 llama.cpp build and official-source-derived Q4_K_M text and
F16 projector GGUF artifacts with recorded hashes. With the general LLM stopped,
the text model ran on CUDA and the projector on CPU. A synthetic custom API request
returned HTTP 200, `vision_ingested=true`, and a contract-valid abstention in
73.253 seconds. The general LLM was then restored and `/health` returned OK.
This is synthetic engineering evidence only. Consented data, independent labels,
clinical evaluation, sustained load, thermal behavior, and OOM recovery remain
unverified. Concurrent residency is optional; research flags default off.

The immutable candidates are recorded in
`config/ai_artifact_candidates.json`: NVIDIA PyTorch 25.05 iGPU by NGC digest,
llama.cpp v0.4.1 by commit, Qwen2.5 3B Q4_K_M by revision/SHA-256, official
MedGemma source shards by revision/SHA-256, and the derived Q4_K_M/F16 GGUF files
by SHA-256. The general LLM and the source-attested MedGemma custom API have both
completed separate device smokes. The older Ollama artifact remains historical
probe evidence and is still excluded from E1 because its conversion provenance
is unattested. BF16 full-CUDA loading, real-data inference, and medical evaluation
remain unverified.

E2 and E4 are code-complete and mock verified. E2 accepts only a frozen,
enumerated `eye-survey-1.0` record and keeps prior predictions, labels, confidence,
Grad-CAM, and free text out of VLM context. E4 is a deterministic same-sample
E0-versus-E1/E2 review with no image/model call and no user-result action. Both
features have independent default-off flags and their records are included in
research retention purge. Their hardware workflow has not been run.
