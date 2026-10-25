"""Evaluate every public sample, counting evidence abstentions as failures.

UNRESOLVED is an evaluation diagnostic, never a submission CSV status.
"""
import json
from corpus import read_csv
from models import DeletionCase
from pipeline import Pipeline, InsufficientEvidenceError
from evaluation.metrics import evaluate, display


def run_samples(dataset, media, artifacts):
    pipeline = Pipeline(dataset, media)
    results, diagnostics, unresolved = [], [], []
    for row in sorted(read_csv(dataset / 'sample_deletion_requests.csv'), key=lambda r: r['case_id']):
        try:
            result, diagnostic = pipeline.audit(DeletionCase(**row))
        except InsufficientEvidenceError as exc:
            unresolved.append(row['case_id'])
            result = dict(case_id=row['case_id'], deletion_status='UNRESOLVED', steps=[])
            diagnostic = dict(case_id=row['case_id'], error=str(exc))
        results.append(result)
        diagnostics.append(diagnostic)
    report = evaluate(results, read_csv(dataset / 'sample_output.csv'))
    report['unresolved_cases'] = unresolved
    artifacts.mkdir(exist_ok=True)
    (artifacts / 'sample_metrics.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (artifacts / 'sample_diagnostics.json').write_text(json.dumps(diagnostics, indent=2), encoding='utf-8')
    display(report)
    print('Unresolved samples (counted as failures):', ', '.join(unresolved) or 'none')
    print('Evaluation only: no sample prediction CSV is written.')
    return report
