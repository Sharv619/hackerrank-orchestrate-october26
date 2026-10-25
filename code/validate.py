"""Validate participant-visible schema, plan coverage, citations and cutoffs."""
import json
from pathlib import Path
from corpus import read_csv
from models import timestamp
from planner import OPS, sort_key, FIX, VERIFY

FIELDS = {'step_no', 'phase', 'system_id', 'resource_id', 'operation', 'state', 'evidence_id'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_steps(status, steps, dates, cutoff):
    require(status in {'COMPLETE', 'INCOMPLETE', 'NOT_APPLICABLE'}, 'Invalid status')
    require(isinstance(steps, list), 'steps_json must be an array')
    if status == 'NOT_APPLICABLE':
        require(not steps, 'NOT_APPLICABLE must have no steps')
        return
    require(bool(steps), f'{status} requires evidence-backed steps')
    seen = set()
    for n, step in enumerate(steps, 1):
        require(isinstance(step, dict) and set(step) == FIELDS, 'Malformed step schema')
        require(type(step['step_no']) is int and step['step_no'] == n, 'Non-consecutive step_no')
        require(all(isinstance(step[k], str) for k in FIELDS - {'step_no'}), 'Step fields must be strings')
        require(bool(step['system_id']) and bool(step['resource_id']), 'Empty resource or system')
        phase = step['phase']
        require(phase in OPS, 'Invalid phase')
        require((step['operation'], step['state']) in OPS[phase], 'Invalid operation/state')
        key = (phase, step['system_id'], step['resource_id'], step['operation'])
        require(key not in seen, 'Duplicate step')
        seen.add(key)
        future = phase == 'REMEDIATION' or (status == 'INCOMPLETE' and phase == 'VERIFICATION')
        if future:
            require(step['evidence_id'] == '', 'Planned remediation/verification must have empty evidence')
        else:
            require(bool(step['evidence_id']) and step['evidence_id'] in dates, 'Missing or unknown evidence')
            require(timestamp(dates[step['evidence_id']]) <= timestamp(cutoff), 'Evidence after audit_at')
        if status == 'COMPLETE':
            require(phase == 'VERIFICATION', 'COMPLETE allows only current-state verification')
    require(steps == sorted(steps, key=sort_key), 'Invalid phase or canonical operation ordering')
    if status == 'INCOMPLETE':
        require({s['phase'] for s in steps} == set(OPS), 'INCOMPLETE needs FINDING, REMEDIATION and VERIFICATION')
        for action, (finding, remediation) in FIX.items():
            found = {(s['system_id'], s['resource_id']) for s in steps if s['operation'] == finding}
            fixed = {(s['system_id'], s['resource_id']) for s in steps if s['operation'] == remediation}
            # REDACT and ANONYMIZE share REPORT_EXPOSED_PII; accept either treatment.
            if finding == 'REPORT_EXPOSED_PII':
                found = {r for r in found if r in fixed}
            require(found <= fixed, 'Finding has no appropriate remediation')
            require(fixed <= {(s['system_id'], s['resource_id']) for s in steps if s['operation'] == finding}, 'Remediation has no grounded finding')
            verified = {(s['system_id'], s['resource_id']) for s in steps if s['operation'] == VERIFY[action]}
            require(fixed <= verified, 'Remediation has no future verification')
        exposed = {(s['system_id'], s['resource_id']) for s in steps if s['operation'] == 'REPORT_EXPOSED_PII'}
        treated = {(s['system_id'], s['resource_id']) for s in steps if s['operation'] in {'REDACT_RECORD', 'ANONYMIZE_RECORD'}}
        require(exposed <= treated, 'Exposed PII has no treatment')


def validate(path, requests, dataset):
    dataset = Path(dataset)
    rows = read_csv(path)
    cases = {r['case_id']: r for r in read_csv(requests)}
    require(len(rows) == len(cases), 'Row count mismatch')
    require([r.get('case_id') for r in rows] == sorted(cases), 'Missing, duplicate or unsorted cases')
    dates = {r['file_id']: r['captured_at'] for r in read_csv(dataset / 'evidence_files.csv')}
    dates.update({r['activity_id']: r['event_time'] for r in read_csv(dataset / 'system_activity.csv')})
    dates.update({r['audit_id']: r['event_time'] for r in read_csv(dataset / 'user_audit_log.csv')})
    for row in rows:
        require(list(row) == ['case_id', 'deletion_status', 'steps_json'], 'Wrong columns')
        try:
            validate_steps(row['deletion_status'], json.loads(row['steps_json']), dates, cases[row['case_id']]['audit_at'])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{row['case_id']}: {exc}") from exc
    return len(rows)


if __name__ == '__main__':
    import argparse
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--samples', action='store_true')
    args = parser.parse_args()
    name = 'sample_deletion_requests.csv' if args.samples else 'deletion_requests.csv'
    output = root / ('sample_output.generated.csv' if args.samples else 'output.csv')
    print('Validated', validate(output, root / 'dataset' / name, root / 'dataset'), 'rows')
