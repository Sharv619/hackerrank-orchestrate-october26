"""The problem statement's operation order is the serialization contract."""
from dataclasses import asdict
from models import OutputStep, PolicyDecision

OPS = {
    'FINDING': [
        ('REPORT_REMAINING_RECORD', 'PRESENT'),
        ('REPORT_EXPOSED_PII', 'PRESENT'),
        ('REPORT_ACTIVE_DATA_FLOW', 'ACTIVE'),
        ('REPORT_RESTORE_RISK', 'ACTIVE'),
    ],
    'REMEDIATION': [
        ('DISABLE_DATA_FLOW', 'DISABLED'),
        ('BLOCK_RESTORE', 'BLOCKED'),
        ('DELETE_RECORD', 'ABSENT'),
        ('REDACT_RECORD', 'REDACTED'),
        ('ANONYMIZE_RECORD', 'ANONYMIZED'),
    ],
    'VERIFICATION': [
        ('VERIFY_RECORD_ABSENT', 'ABSENT'),
        ('VERIFY_RECORD_PRESENT', 'PRESENT'),
        ('VERIFY_RECORD_REDACTED', 'REDACTED'),
        ('VERIFY_RECORD_ANONYMIZED', 'ANONYMIZED'),
        ('VERIFY_DATA_FLOW_DISABLED', 'DISABLED'),
        ('VERIFY_RESTORE_BLOCKED', 'BLOCKED'),
    ],
}

ORDER = {op: (p, i) for p, (phase, ops) in enumerate(OPS.items()) for i, (op, _) in enumerate(ops)}
STATES = {op: state for ops in OPS.values() for op, state in ops}
VERIFY = {
    'DELETE': 'VERIFY_RECORD_ABSENT',
    'REDACT': 'VERIFY_RECORD_REDACTED',
    'ANONYMIZE': 'VERIFY_RECORD_ANONYMIZED',
    'RETAIN': 'VERIFY_RECORD_PRESENT',
    'DISABLE': 'VERIFY_DATA_FLOW_DISABLED',
    'BLOCK': 'VERIFY_RESTORE_BLOCKED',
}
FIX = {
    'DELETE': ('REPORT_REMAINING_RECORD', 'DELETE_RECORD'),
    'REDACT': ('REPORT_EXPOSED_PII', 'REDACT_RECORD'),
    'ANONYMIZE': ('REPORT_EXPOSED_PII', 'ANONYMIZE_RECORD'),
    'DISABLE': ('REPORT_ACTIVE_DATA_FLOW', 'DISABLE_DATA_FLOW'),
    'BLOCK': ('REPORT_RESTORE_RISK', 'BLOCK_RESTORE'),
}

EXPECTED_FINAL_STATES = {
    'DELETE': 'ABSENT',
    'REDACT': 'REDACTED',
    'ANONYMIZE': 'ANONYMIZED',
    'RETAIN': 'PRESENT',
    'DISABLE': 'DISABLED',
    'BLOCK': 'BLOCKED',
}


def sort_key(step):
    return (*ORDER[step['operation']], step['system_id'], step['resource_id'])


def plan(decisions):
    """Original planner for backward compatibility."""
    if not decisions:
        raise ValueError('Cannot plan without grounded state evidence')
    violations = [d for d in decisions if not d.compliant]
    status = 'INCOMPLETE' if violations else 'COMPLETE'
    steps = []

    def add(phase, op, d, evidence):
        f = d.fact
        steps.append(asdict(OutputStep(0, phase, f.system_id, f.resource_id, op, STATES[op], evidence)))

    for d in violations:
        if d.action not in FIX:
            raise ValueError(f'Missing mandatory retained record has no allowed restoration operation: {d.action}')
        finding, fix = FIX[d.action]
        add('FINDING', finding, d, d.fact.evidence_id)
        add('REMEDIATION', fix, d, '')

    for d in decisions:
        add('VERIFICATION', VERIFY[d.action], d, d.fact.evidence_id if status == 'COMPLETE' else '')

    steps.sort(key=sort_key)
    for n, step in enumerate(steps, 1):
        step['step_no'] = n
    return status, steps


def plan_with_verification_coverage(decisions, all_subject_resources):
    """
    Extended planner that ensures complete verification coverage per Fix 4.

    all_subject_resources: list of (system_id, resource_id, category, expected_action)
    """
    if not decisions:
        raise ValueError('Cannot plan without grounded state evidence')
    violations = [d for d in decisions if not d.compliant]
    status = 'INCOMPLETE' if violations else 'COMPLETE'
    steps = []

    def add(phase, op, d, evidence):
        f = d.fact
        steps.append(asdict(OutputStep(0, phase, f.system_id, f.resource_id, op, STATES[op], evidence)))

    # 1. Findings from violations
    for d in violations:
        if d.action not in FIX:
            raise ValueError(f'Missing mandatory retained record has no allowed restoration operation: {d.action}')
        finding, fix = FIX[d.action]
        add('FINDING', finding, d, d.fact.evidence_id)
        add('REMEDIATION', fix, d, '')

    # 2. Build verification coverage
    verified = set()  # (system_id, resource_id, verify_op)

    # Evidence-backed verification for violations (only for COMPLETE cases)
    if status == 'COMPLETE':
        for d in decisions:
            if not d.compliant:
                verify_op = VERIFY[d.action]
                verified.add((d.fact.system_id, d.fact.resource_id, verify_op))
                add('VERIFICATION', verify_op, d, d.fact.evidence_id)

    # Build resource_expected from all_subject_resources
    resource_expected = {}
    for sys_id, res_id, cat, action in all_subject_resources:
        if (sys_id, res_id) not in resource_expected:
            resource_expected[(sys_id, res_id)] = action

    # Every decision, including resources reached through activity, needs verification.
    for d in decisions:
        resource_expected[(d.fact.system_id, d.fact.resource_id)] = d.action

    # For COMPLETE cases: evidence-backed verification for ALL decisions
    if status == 'COMPLETE':
        for d in decisions:
            verify_op = VERIFY[d.action]
            if (d.fact.system_id, d.fact.resource_id, verify_op) not in verified:
                add('VERIFICATION', verify_op, d, d.fact.evidence_id)
    else:
        # INCOMPLETE: future verification for ALL known subject resources
        # For INCOMPLETE cases, all VERIFICATION steps must have empty evidence_id
        for (sys_id, res_id), action in resource_expected.items():
            verify_op = VERIFY[action]
            if (sys_id, res_id, verify_op) not in verified:
                # Find matching decision or create synthetic
                matching_decision = None
                for d in decisions:
                    if d.fact.system_id == sys_id and d.fact.resource_id == res_id:
                        matching_decision = d
                        break
                if matching_decision:
                    add('VERIFICATION', verify_op, matching_decision, '')
                else:
                    from models import PolicyDecision, EvidenceFact
                    synthetic_fact = EvidenceFact(
                        evidence_id='',
                        system_id=sys_id,
                        resource_id=res_id,
                        category='',
                        state='',
                        observed_at='',
                        captured_at='',
                        identifiers=set(),
                        fields={},
                        locator='',
                        strength=1,
                        evidence_kind='verification'
                    )
                    synthetic_decision = PolicyDecision(
                        fact=synthetic_fact,
                        rule_id='',
                        action=action,
                        expected=EXPECTED_FINAL_STATES[action],
                        compliant=True
                    )
                    add('VERIFICATION', VERIFY[action], synthetic_decision, '')

    steps.sort(key=sort_key)
    for n, step in enumerate(steps, 1):
        step['step_no'] = n
    return status, steps
