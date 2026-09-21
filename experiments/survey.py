"""Closed E2 survey schema; no free text, diagnosis, label, or model result fields."""
from __future__ import annotations

from typing import Any

from utils.ai_config import AIError


SURVEY_SCHEMA_VERSION = 'eye-survey-1.0'
SURVEY_KEYS = {
    'schema_version', 'symptoms', 'duration_bucket', 'contact_lens_use',
    'trauma_or_chemical_exposure', 'prior_eye_surgery',
}
ALLOWED_SYMPTOMS = {
    'redness', 'pain', 'itching', 'discharge', 'blurred_vision',
    'photophobia', 'foreign_body_sensation',
}
DURATION_BUCKETS = {'lt_24h', '1_3d', '4_7d', 'gt_7d', 'unknown'}
TRISTATE = {'yes', 'no', 'unknown'}


def validate_survey(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SURVEY_KEYS:
        raise AIError('invalid_survey')
    if value.get('schema_version') != SURVEY_SCHEMA_VERSION:
        raise AIError('invalid_survey')
    symptoms = value.get('symptoms')
    if (
        not isinstance(symptoms, list) or len(symptoms) > len(ALLOWED_SYMPTOMS)
        or any(not isinstance(item, str) or item not in ALLOWED_SYMPTOMS for item in symptoms)
        or len(set(symptoms)) != len(symptoms)
    ):
        raise AIError('invalid_survey')
    duration = value.get('duration_bucket')
    contact = value.get('contact_lens_use')
    exposure = value.get('trauma_or_chemical_exposure')
    surgery = value.get('prior_eye_surgery')
    if duration not in DURATION_BUCKETS or any(
        item not in TRISTATE for item in (contact, exposure, surgery)
    ):
        raise AIError('invalid_survey')
    return {
        'schema_version': SURVEY_SCHEMA_VERSION,
        'symptoms': sorted(symptoms),
        'duration_bucket': duration,
        'contact_lens_use': contact,
        'trauma_or_chemical_exposure': exposure,
        'prior_eye_surgery': surgery,
    }


def validate_run_config(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {'survey_schema_version'}:
        raise ValueError('invalid E2 configuration')
    if value.get('survey_schema_version') != SURVEY_SCHEMA_VERSION:
        raise ValueError('invalid E2 survey schema')
    return {'survey_schema_version': SURVEY_SCHEMA_VERSION}
