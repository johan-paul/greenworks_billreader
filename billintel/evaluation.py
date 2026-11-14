"""Compare a saved extraction with independently reviewed per-page labels."""
import math

def evaluate(extraction: dict, labels: dict):
    if extraction['sha256'] != labels['sha256']:
        raise ValueError('Labels and extraction refer to different source PDFs')
    pages = {p['page']:p for p in extraction['pages']}
    checks = []
    for label in labels['pages']:
        page = pages.get(label['page'], {})
        for field, expected in label['fields'].items():
            actual = page.get('data', {}).get(field)
            passed = page.get('status') == 'needs_review' and field in page.get('data', {})
            if isinstance(expected, dict):
                passed = passed and isinstance(actual, dict) and actual.get('unit') == expected['unit']
                passed = bool(passed and math.isclose(actual['value'], expected['value'], rel_tol=0, abs_tol=0.01))
            else:
                passed = bool(passed and actual == expected)
            checks.append({'page':label['page'], 'field':field, 'expected':expected, 'actual':actual, 'passed':passed})
    count = len(checks)
    return {'evaluated_fields':count, 'correct_fields':sum(c['passed'] for c in checks),
            'field_accuracy':sum(c['passed'] for c in checks)/count if count else None,
            'scope':'Only labeled fields; not a dataset-wide accuracy estimate', 'checks':checks}
