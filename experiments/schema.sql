PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS samples (
    sample_id TEXT PRIMARY KEY,
    patient_group_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    capture_time TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (modality = 'external_eye_webcam'),
    selected_eye TEXT NOT NULL CHECK (selected_eye IN ('L', 'R', 'unknown')),
    laterality_basis TEXT NOT NULL,
    source_asset_ref TEXT NOT NULL,
    canonical_roi_ref TEXT NOT NULL UNIQUE,
    source_digest TEXT NOT NULL,
    roi_digest TEXT NOT NULL,
    source_size_json TEXT NOT NULL,
    roi_bbox_json TEXT NOT NULL,
    orientation TEXT NOT NULL,
    mirrored INTEGER NOT NULL CHECK (mirrored IN (0, 1)),
    crop_version TEXT NOT NULL,
    preprocessing_version TEXT NOT NULL,
    quality_state TEXT NOT NULL,
    quality_reasons_json TEXT NOT NULL,
    permission_ref TEXT,
    retention_policy_ref TEXT,
    retention_until TEXT,
    source_system TEXT,
    source_record_ref TEXT,
    split TEXT NOT NULL,
    engineering_fixture INTEGER NOT NULL CHECK (engineering_fixture IN (0, 1)),
    synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    arm_id TEXT NOT NULL CHECK (arm_id IN (
        'E0_baseline', 'E1_vlm_image', 'E2_vlm_survey',
        'E3_result_explanation', 'E4_hybrid_review'
    )),
    repeat_index INTEGER NOT NULL CHECK (repeat_index >= 0),
    config_json TEXT NOT NULL,
    config_digest TEXT NOT NULL,
    model_manifest_json TEXT NOT NULL,
    prompt_digest TEXT,
    engineering_fixture INTEGER NOT NULL CHECK (engineering_fixture IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL REFERENCES samples(sample_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN (
        'queued', 'running', 'succeeded', 'failed', 'timed_out',
        'cancel_requested', 'cancelled', 'skipped'
    )),
    lease_token TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_state_created_idx ON jobs(state, created_at);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
    analysis_status TEXT NOT NULL CHECK (
        analysis_status IN ('assessed', 'abstain', 'unsupported_input')
    ),
    suggested_label TEXT,
    result_json TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    duration_ms REAL,
    created_at TEXT NOT NULL,
    CHECK (
        (analysis_status = 'assessed' AND suggested_label IS NOT NULL) OR
        (analysis_status != 'assessed' AND suggested_label IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS explanations (
    explanation_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
    source_prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    source_result_digest TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    explanation_text TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider = 'local'),
    model TEXT NOT NULL,
    runtime_receipt_json TEXT,
    duration_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS survey_inputs (
    sample_id TEXT PRIMARY KEY REFERENCES samples(sample_id),
    schema_version TEXT NOT NULL CHECK (schema_version = 'eye-survey-1.0'),
    response_json TEXT NOT NULL,
    response_digest TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hybrid_reviews (
    review_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(job_id),
    baseline_prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    baseline_result_digest TEXT NOT NULL,
    vlm_prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    vlm_result_digest TEXT NOT NULL,
    input_digest TEXT NOT NULL,
    review_json TEXT NOT NULL,
    duration_ms REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_labels (
    sample_id TEXT PRIMARY KEY REFERENCES samples(sample_id),
    label TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO schema_metadata(key, value) VALUES ('schema_version', '4')
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
