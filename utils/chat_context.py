"""Allowlisted browser result summary. Browser claims are never authenticated facts."""
import math


def summarize_result(value):
    def eye(raw):
        if not isinstance(raw, dict):
            return None
        out = {}
        disease = raw.get('disease')
        if isinstance(disease, str) and len(disease) <= 100:
            out['disease'] = disease
        for key in ('class', 'disease_class'):
            item = raw.get(key)
            if type(item) is int and 0 <= item <= 4:
                out[key] = item
        # Actual current API contracts: class=>percent; disease_class=>fraction.
        # Ambiguous legacy confidence is omitted, never guessed by magnitude.
        confidence = raw.get('confidence')
        unit = 'percent' if 'class' in out else 'fraction' if 'disease_class' in out else None
        if unit and type(confidence) in (int, float) and math.isfinite(confidence):
            if 0 <= confidence <= (100 if unit == 'percent' else 1):
                out['confidence'] = confidence
                out['confidence_unit'] = unit
        return out or None

    result = {'source': 'unverified_browser_result'}
    if not isinstance(value, dict):
        result['availability'] = 'unavailable'
        return result
    for side in ('left_eye', 'right_eye'):
        if side in value:
            result[side] = eye(value[side])
    if not any(result.get(side) for side in ('left_eye', 'right_eye')):
        result['single_eye'] = eye(value)
    result['availability'] = 'provided' if any(result.get(k) for k in ('left_eye', 'right_eye', 'single_eye')) else 'unavailable'
    return result
