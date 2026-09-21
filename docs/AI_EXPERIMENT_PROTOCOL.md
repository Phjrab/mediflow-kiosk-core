# AI experiment protocol

The research store is separate from `database/database.db`, user result pages,
PDF reports, and Kakao sharing. Research features default to off. The initial
usable image comparison is E0 versus E1 on the same approved isolated
`sample_id`. E3 separately explains a completed E0 JSON result with the selected
local general LLM; it is not an image-analysis arm.

## Arms and implementation state

| Arm | Input | Purpose | State |
| --- | --- | --- | --- |
| E0 | Canonical eye ROI | Existing EfficientNet baseline, optional Grad-CAM | Implemented; synthetic Jetson A run and Grad-CAM artifact verified |
| E1 | Same canonical eye ROI | Independent MedGemma image analysis | Implemented; same-sample synthetic A-to-B worker run verified |
| E2 | ROI plus frozen bounded survey | Survey-conditioned VLM analysis | Implemented; synthetic A-to-B worker run verified |
| E3 | Completed E0 result JSON, no image | Local-LLM result explanation | Implemented; synthetic A-to-B local-LLM run verified |
| E4 | Completed same-sample E0 and E1/E2 results | Deterministic hybrid review rule | Implemented; synthetic device workflow verified, no model generation |

E0 does not run MediaPipe again. The sample manifest records source size, ROI
coordinates, laterality basis, crop/preprocessing versions, and input digests.
An administrator may explicitly register one selected-eye ROI from operational
history after recording authorization, retention policy, retention expiry, and
research split. The bridge never auto-enqueues and never copies the full frame,
stored prediction, score, disease name, Grad-CAM, or survey.

## Storage and flags

Choose an absolute private directory outside the repository's public assets:

```dotenv
EXPERIMENT_DATA_DIR=<ABSOLUTE_PRIVATE_DIRECTORY_OUTSIDE_WEB_STATIC>
EXPERIMENT_QUEUE_MAX=16
EXPERIMENT_ALLOW_REAL_DATA=0
EXPERIMENT_STORE_RAW_OUTPUT=0
AI_EXPERIMENTS_ENABLED=1
BASELINE_EXPERIMENTS_ENABLED=1
EXPLANATION_EXPERIMENTS_ENABLED=0
SURVEY_VLM_EXPERIMENTS_ENABLED=0
HYBRID_REVIEW_EXPERIMENTS_ENABLED=0
AI_EXPERIMENT_AUTO_ENQUEUE=0
AI_EXPERIMENT_MODE=shadow
```

Initialize the schema:

```bash
python3 scripts/run_ai_experiments.py init
```

Directories and files are created with private permissions. Images, SQLite data,
reports, and Grad-CAM artifacts are ignored by Git. Raw model text is not stored.
Retention deletion is restricted to explicitly selected expired research copies
and never includes the operational DB or operational source images.

## Engineering dry run

Register a synthetic image. This command always marks the sample as both
`engineering_fixture` and `synthetic`; it cannot register patient data.

```bash
python3 scripts/run_ai_experiments.py register-fixture \
  --image <SYNTHETIC_JPEG_OR_PNG> \
  --patient-group-id fixture-group-001 \
  --capture-id fixture-capture-001 \
  --source-asset-ref synthetic-fixture-001 \
  --selected-eye L
```

Create separate run snapshots for E0 and E1. The JSON config and model manifest
must contain the frozen preprocessing, prompt, model revision/hash, runtime,
dtype/quantization, and generation parameters. Secret-like fields are removed
before persistence.

```bash
python3 scripts/run_ai_experiments.py create-run \
  --arm E0_baseline \
  --model-manifest <EFFICIENTNET_MANIFEST_JSON> \
  --config <E0_CONFIG_JSON> \
  --engineering-fixture

python3 scripts/run_ai_experiments.py create-run \
  --arm E1_vlm_image \
  --model-manifest <MEDGEMMA_MANIFEST_JSON> \
  --config <E1_CONFIG_JSON> \
  --engineering-fixture
```

Enqueue the same sample once for each run. Repeating the same sample/run pair is
idempotent. An intentional repeat uses a new run and `repeat_index`.

```bash
python3 scripts/run_ai_experiments.py enqueue --sample-id <SAMPLE_ID> --run-id <E0_RUN_ID>
python3 scripts/run_ai_experiments.py enqueue --sample-id <SAMPLE_ID> --run-id <E1_RUN_ID>
```

Run E0 manually on the host that has the existing compatible classifier stack:

```bash
python3 scripts/run_ai_experiments.py baseline-once
```

Run one E1 job or a persistent manual worker while the VLM profile is active:

```bash
python3 scripts/run_ai_experiments.py worker --once
python3 scripts/run_ai_experiments.py worker
```

No worker starts with the kiosk. E0 and E1 workers claim only their own arms.
Interrupted running jobs are marked failed on persistent VLM worker startup;
there is no unbounded retry.

## E3 local result explanation

E3 is disabled independently and uses only `LLM_PROVIDER=local`. It does not
invoke OpenAI or Gemini and never falls back to them. First complete the E0 job
for a sample. Then create an E3 config file containing only:

```json
{
  "source_run_id": "<COMPLETED_E0_RUN_ID>",
  "question_id": "explain-result-ko-v1"
}
```

Enable the worker explicitly and create/enqueue a separate E3 run:

```dotenv
EXPLANATION_EXPERIMENTS_ENABLED=1
LLM_PROVIDER=local
AI_DEPLOYMENT_PROFILE=chat_only
```

```bash
python3 scripts/run_ai_experiments.py create-run \
  --arm E3_result_explanation \
  --model-manifest <LOCAL_LLM_MANIFEST_JSON> \
  --config <E3_CONFIG_JSON> \
  --engineering-fixture
python3 scripts/run_ai_experiments.py enqueue \
  --sample-id <SAMPLE_ID> --run-id <E3_RUN_ID>
python3 scripts/run_ai_experiments.py explanation-once
```

The source must be a succeeded E0 prediction for the same sample. The worker
allowlists the status, suggested class, limitations, brief explanation,
confidence, probabilities, and backend. It omits the sample image, Grad-CAM,
reference label, paths, and arbitrary provenance. The prompt states that no image
was supplied. Output is stored in `explanations`, separate from `predictions`, and
the evaluator returns `EXPLANATION_REVIEW_REQUIRED` without classification
accuracy. The admin page renders the text with `textContent`.

## E2 bounded survey-conditioned VLM

E2 uses the same canonical ROI as E1 plus one immutable, closed survey object.
Free text, diagnosis, label, existing prediction, confidence, Grad-CAM, and
reference-label fields are rejected. The `eye-survey-1.0` object has exactly:

```json
{
  "schema_version": "eye-survey-1.0",
  "symptoms": ["redness", "itching"],
  "duration_bucket": "1_3d",
  "contact_lens_use": "unknown",
  "trauma_or_chemical_exposure": "no",
  "prior_eye_surgery": "no"
}
```

Allowed symptoms are `redness`, `pain`, `itching`, `discharge`,
`blurred_vision`, `photophobia`, and `foreign_body_sensation`. Duration is one
of `lt_24h`, `1_3d`, `4_7d`, `gt_7d`, or `unknown`; the remaining fields are
`yes`, `no`, or `unknown`. Freeze the survey before enqueueing:

```bash
python3 scripts/run_ai_experiments.py add-survey \
  --sample-id <SAMPLE_ID> --responses <SURVEY_JSON> --source <SURVEY_SOURCE_REF>
python3 scripts/run_ai_experiments.py create-run \
  --arm E2_vlm_survey --model-manifest <MEDGEMMA_MANIFEST_JSON> \
  --config <E2_CONFIG_JSON> --engineering-fixture
```

The E2 config is exactly `{"survey_schema_version":"eye-survey-1.0"}`. A
different survey cannot overwrite a frozen one. Enable
`SURVEY_VLM_EXPERIMENTS_ENABLED=1` only for an approved E2 run; the VLM worker
then sends the bounded survey under `context.survey` and records its digest.

## E4 deterministic hybrid review

E4 reads completed same-sample E0 plus E1 or E2 records. It reads no image,
performs no model generation, creates no replacement diagnosis, and never
changes a user result. Its fixed `paired-review-v1` rule reports `agreement`,
`disagreement`, or `not_comparable`, a manual-review flag, and always records
`agreement_is_accuracy=false` and `user_result_action=none`. Configure a run as:

```json
{
  "baseline_run_id": "<COMPLETED_E0_RUN_ID>",
  "vlm_run_id": "<COMPLETED_E1_OR_E2_RUN_ID>",
  "rule_id": "paired-review-v1"
}
```

```bash
python3 scripts/run_ai_experiments.py create-run \
  --arm E4_hybrid_review --model-manifest <RULE_MANIFEST_JSON> \
  --config <E4_CONFIG_JSON> --engineering-fixture
python3 scripts/run_ai_experiments.py enqueue \
  --sample-id <SAMPLE_ID> --run-id <E4_RUN_ID>
HYBRID_REVIEW_EXPERIMENTS_ENABLED=1 \
  python3 scripts/run_ai_experiments.py hybrid-once
```

The store rechecks both source run IDs, arms, sample identity, result digests,
and the deterministic review before commit. E4 evaluation returns
`HYBRID_REVIEW_ONLY` with no classification metrics.

## Approved real data

Real data registration requires all of the following:

1. a documented permission reference,
2. a retention policy reference and ISO expiry date,
3. `EXPERIMENT_ALLOW_REAL_DATA=1` and `AI_EXPERIMENTS_ENABLED=1`,
4. a valid stored bbox for the selected eye,
5. patient-level train/validation/test/holdout/prospective split assignment.

Use the administrator page `/admin/ai-experiments`, section “승인된 운영 이력
ROI 등록”. The state-changing endpoint is
`POST /api/admin/ai-experiments/samples/from-history`; it requires the existing
admin session and CSRF token. The operational SQLite connection is query-only,
the asset must resolve below the configured capture root, and a recorded asset
digest is checked when present. The source patient hash becomes the private
patient-group key, while paths and existing analysis content are not copied.

The operation is idempotent by source session/asset, eye, and preprocessing
version. A repeated request returns the existing sample only when source digest,
permission, retention, expiry, and split still match. An expired sample cannot be
registered or enqueued. The public CLI has no real-data registration command.
Images are sent to a VLM as validated bytes, never as an arbitrary URL.

Review expired copies without mutation:

```bash
python3 scripts/run_ai_experiments.py retention-status
```

The command reports opaque sample IDs and active-job conflicts and always returns
`mutation_performed=false`. It does not delete data.

After reviewing that output, delete only individually selected expired copies by
repeating `--sample-id` and supplying the exact confirmation string:

```bash
python3 scripts/run_ai_experiments.py retention-purge \
  --sample-id <EXPIRED_SAMPLE_ID> \
  --confirm DELETE_EXPIRED_RESEARCH_COPIES
```

The purge rechecks expiry and rejects the complete batch before mutation if a
sample is missing, unexpired, synthetic/engineering-only, or has a queued,
running, or cancellation-pending job. It removes the research ROI, that sample's
Grad-CAM artifacts, jobs, predictions, E2 survey, E3 explanations, E4 hybrid
reviews, reference label, and its `operational_import` audit link. It preserves runs because another sample may
share them, preserves unrelated audit records, never opens the operational DB,
and performs SQLite `VACUUM`. At most 100 unique sample IDs may be supplied in
one invocation. This command was verified only with temporary mock data; it has
not been run against device or real research data.

## Monitoring, comparison, and evaluation

Check a job without exposing its image:

```bash
python3 scripts/run_ai_experiments.py status --job-id <JOB_ID>
```

The admin page `/admin/ai-experiments` lists job and analysis states separately.
Its E0/E1 comparison uses only common sample IDs and calls the result agreement,
not accuracy. Model output is rendered as text. Existing user pages and reports
do not read from this store.

Add independently reviewed reference labels only when their provenance is known:

```bash
python3 scripts/run_ai_experiments.py add-reference-label \
  --sample-id <SAMPLE_ID> --label <0_TO_4> --source <REVIEW_SOURCE_REF>
```

Before evaluation, the tool rejects a patient group that appears in multiple
splits. Export private JSON, CSV, and Markdown reports:

```bash
python3 scripts/evaluate_ai_experiments.py \
  --run-id <RUN_ID> \
  --output-dir <ABSOLUTE_PRIVATE_REPORT_DIRECTORY>
```

Reports state attempted, labelled, assessed, abstained, and technical-failure
denominators. Accuracy is limited to the answered subset and is accompanied by
coverage and end-to-end correct fraction. Synthetic engineering fixtures always
return `ENGINEERING_FIXTURE_NO_MEDICAL_METRICS`. Missing labels return
`NO_REFERENCE_LABELS`.

The source-attested E1 custom API completed one synthetic request on Jetson B in
73.253 seconds with the text model on CUDA and the vision projector on CPU. This
single engineering fixture is image-ingestion evidence only. Sustained latency,
throughput, thermal behavior, OOM recovery, real-data behavior, and medical
quality remain `N/A` until evaluated under an approved protocol and dataset.
