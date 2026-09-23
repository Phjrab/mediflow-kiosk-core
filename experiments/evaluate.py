"""Metrics with explicit denominators and engineering-fixture safeguards."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any

import sqlite3

from experiments.store import ExperimentStore


LABELS = ('0', '1', '2', '3', '4')


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _rows(store: ExperimentStore, run_id: str) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(store.db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            '''SELECT s.sample_id, s.patient_group_id, s.split, s.engineering_fixture,
                      r.arm_id,
                      j.state AS job_state, j.error_code,
                      p.analysis_status, p.suggested_label, p.duration_ms,
                      l.label AS reference_label,
                      e.explanation_text, e.source_result_digest,
                      h.review_json
               FROM jobs j
               JOIN samples s ON s.sample_id = j.sample_id
               JOIN runs r ON r.run_id = j.run_id
               LEFT JOIN predictions p ON p.job_id = j.job_id
               LEFT JOIN explanations e ON e.job_id = j.job_id
               LEFT JOIN hybrid_reviews h ON h.job_id = j.job_id
               LEFT JOIN reference_labels l ON l.sample_id = s.sample_id
               WHERE j.run_id = ? ORDER BY s.sample_id''',
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def evaluate_run(store: ExperimentStore, run_id: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    store.validate_patient_splits()
    rows = _rows(store, run_id)
    states = Counter(row['job_state'] for row in rows)
    analysis_states = Counter(row['analysis_status'] for row in rows if row['analysis_status'])
    result: dict[str, Any] = {
        'run_id': run_id,
        'arm_id': run['arm_id'],
        'N_attempted': len(rows),
        'job_states': dict(sorted(states.items())),
        'analysis_states': dict(sorted(analysis_states.items())),
        'technical_failures': sum(
            states[state] for state in ('failed', 'timed_out')
        ),
        'engineering_fixture': bool(rows) and all(row['engineering_fixture'] for row in rows),
        'clinical_metrics': None,
    }

    if run['arm_id'] == 'E4_hybrid_review':
        reviews = [json.loads(row['review_json']) for row in rows if row['review_json']]
        outcomes = Counter(review['outcome'] for review in reviews)
        result['N_labelled'] = sum(row['reference_label'] in LABELS for row in rows)
        result['N_reviews'] = len(reviews)
        result['review_outcomes'] = dict(sorted(outcomes.items()))
        result['N_manual_review_required'] = sum(
            review['manual_review_required'] is True for review in reviews
        )
        result['evaluation_status'] = 'HYBRID_REVIEW_ONLY'
        result['hybrid_review_is_classification_metric'] = False
        result['agreement_is_accuracy'] = False
        return result

    if run['arm_id'] == 'E3_result_explanation':
        result['N_labelled'] = sum(row['reference_label'] in LABELS for row in rows)
        result['N_explanations'] = sum(bool(row['explanation_text']) for row in rows)
        result['evaluation_status'] = 'EXPLANATION_REVIEW_REQUIRED'
        result['explanation_is_classification_metric'] = False
        return result

    labelled = [row for row in rows if row['reference_label'] in LABELS]
    result['N_labelled'] = len(labelled)
    if not labelled:
        result['evaluation_status'] = 'NO_REFERENCE_LABELS'
        return result
    if result['engineering_fixture']:
        result['evaluation_status'] = 'ENGINEERING_FIXTURE_NO_MEDICAL_METRICS'
        return result

    assessed = [
        row for row in labelled
        if row['job_state'] == 'succeeded'
        and row['analysis_status'] == 'assessed'
        and row['suggested_label'] in LABELS
    ]
    correct = sum(row['suggested_label'] == row['reference_label'] for row in assessed)
    confusion = {actual: {predicted: 0 for predicted in LABELS} for actual in LABELS}
    for row in assessed:
        confusion[row['reference_label']][row['suggested_label']] += 1

    per_class = {}
    f1_values = []
    total = len(labelled)
    for label in LABELS:
        tp = confusion[label][label]
        fn = sum(confusion[label][other] for other in LABELS if other != label)
        fp = sum(confusion[other][label] for other in LABELS if other != label)
        tn = len(assessed) - tp - fn - fp
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        specificity = _ratio(tn, tn + fp)
        f1_denominator = 2 * tp + fp + fn
        f1 = (2 * tp) / f1_denominator if f1_denominator else None
        if f1 is not None:
            f1_values.append(f1)
        per_class[label] = {
            'support': sum(row['reference_label'] == label for row in labelled),
            'precision': precision,
            'recall_answered_subset': recall,
            'specificity_answered_subset': specificity,
            'f1': f1,
        }

    result['evaluation_status'] = 'REFERENCE_METRICS_AVAILABLE'
    result['clinical_metrics'] = {
        'N_eligible': len(labelled),
        'N_assessed': len(assessed),
        'N_correct': correct,
        'N_abstain': sum(row['analysis_status'] == 'abstain' for row in labelled),
        'N_technical_failure': sum(row['job_state'] in ('failed', 'timed_out') for row in labelled),
        'coverage': _ratio(len(assessed), len(labelled)),
        'answered_accuracy': _ratio(correct, len(assessed)),
        'end_to_end_correct_fraction': _ratio(correct, len(labelled)),
        'macro_f1_answered_subset': sum(f1_values) / len(f1_values) if f1_values else None,
        'confusion_matrix_answered_subset': confusion,
        'per_class': per_class,
    }
    return result


def compare_runs(store: ExperimentStore, left_run_id: str, right_run_id: str) -> dict[str, Any]:
    store.get_run(left_run_id)
    store.get_run(right_run_id)
    left = {row['sample_id']: row for row in _rows(store, left_run_id)}
    right = {row['sample_id']: row for row in _rows(store, right_run_id)}
    paired_ids = sorted(set(left) & set(right))
    comparable = []
    for sample_id in paired_ids:
        left_row, right_row = left[sample_id], right[sample_id]
        if (
            left_row['job_state'] == right_row['job_state'] == 'succeeded'
            and left_row['analysis_status'] == right_row['analysis_status'] == 'assessed'
        ):
            comparable.append((left_row, right_row))
    agreements = sum(a['suggested_label'] == b['suggested_label'] for a, b in comparable)
    return {
        'left_run_id': left_run_id,
        'right_run_id': right_run_id,
        'N_left_attempted': len(left),
        'N_right_attempted': len(right),
        'N_paired_attempted': len(paired_ids),
        'N_paired_assessed': len(comparable),
        'agreement_rate_paired_assessed': _ratio(agreements, len(comparable)),
        'agreement_is_accuracy': False,
    }


def export_report(store: ExperimentStore, run_id: str, output_dir: str | Path) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = evaluate_run(store, run_id)
    rows = _rows(store, run_id)
    json_path = output_dir / f'{run_id}.json'
    csv_path = output_dir / f'{run_id}.csv'
    markdown_path = output_dir / f'{run_id}.md'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    fieldnames = list(rows[0]) if rows else ['sample_id']
    with csv_path.open('w', encoding='utf-8', newline='') as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    metrics = report.get('clinical_metrics') or {}
    markdown_path.write_text(
        '# AI experiment report\n\n'
        f'- Run: `{run_id}`\n'
        f'- Arm: `{report["arm_id"]}`\n'
        f'- Evaluation status: `{report["evaluation_status"]}`\n'
        f'- Engineering fixture: `{report["engineering_fixture"]}`\n'
        f'- Attempted: `{report["N_attempted"]}`\n'
        f'- Eligible: `{metrics.get("N_eligible", "N/A")}`\n'
        f'- Assessed: `{metrics.get("N_assessed", "N/A")}`\n'
        f'- Coverage: `{metrics.get("coverage", "N/A")}`\n'
        '\nEngineering fixture outputs are software evidence, not medical performance. '
        'E3 explanations and E4 hybrid reviews are separate review outputs, not image-classification metrics.\n',
        encoding='utf-8',
    )
    for path in (json_path, csv_path, markdown_path):
        os.chmod(path, 0o600)
    return {'json': json_path, 'csv': csv_path, 'markdown': markdown_path}
