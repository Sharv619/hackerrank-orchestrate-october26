"""Participant-authored contract regressions, independent of sample answers."""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from models import EvidenceSource, IdentitySet, ResourceLink, EvidenceFact, PolicyDecision
from evidence.image_parser import parse_text
from evidence.normalize import normalize
from pipeline import Pipeline
from planner import plan_with_verification_coverage
from validate import validate_steps
from corpus import Corpus

NOW = '2026-06-01T00:00:00Z'
LATER = '2026-07-01T00:00:00Z'
SOURCE = EvidenceSource('fixture-evidence', 'fixture.png', 'console', NOW)


def valid_plan():
    fact = normalize(dict(resource_id='record-z', state='PRESENT'), SOURCE, 'account_service')
    decision = PolicyDecision(fact, 'fixture-policy', 'DELETE', 'ABSENT', False)
    return plan_with_verification_coverage([decision], [])


def test_decision_resource_always_has_future_verification():
    status, steps = valid_plan()
    assert len(steps) == 3
    validate_steps(status, steps, {SOURCE.file_id: NOW}, NOW)


@pytest.mark.parametrize('mutation', [
    'empty', 'no_finding', 'no_fix', 'no_verify', 'empty_finding_evidence',
    'fix_evidence', 'verify_evidence', 'number', 'order', 'missing_field',
    'extra_field', 'wrong_type', 'unknown_operation', 'future_evidence',
])
def test_invalid_incomplete_is_rejected(mutation):
    status, steps = valid_plan()
    dates = {SOURCE.file_id: NOW}
    if mutation == 'empty': steps = []
    elif mutation.startswith('no_'):
        phase = {'no_finding': 'FINDING', 'no_fix': 'REMEDIATION', 'no_verify': 'VERIFICATION'}[mutation]
        steps = [s for s in steps if s['phase'] != phase]
        for n, step in enumerate(steps, 1): step['step_no'] = n
    elif mutation == 'empty_finding_evidence': steps[0]['evidence_id'] = ''
    elif mutation == 'fix_evidence': steps[1]['evidence_id'] = SOURCE.file_id
    elif mutation == 'verify_evidence': steps[2]['evidence_id'] = SOURCE.file_id
    elif mutation == 'number': steps[1]['step_no'] = 8
    elif mutation == 'order':
        steps.reverse()
        for n, step in enumerate(steps, 1): step['step_no'] = n
    elif mutation == 'missing_field': del steps[0]['state']
    elif mutation == 'extra_field': steps[0]['extra'] = 'x'
    elif mutation == 'wrong_type': steps[0] = None
    elif mutation == 'unknown_operation': steps[0]['operation'] = 'UNKNOWN'
    elif mutation == 'future_evidence': dates[SOURCE.file_id] = LATER
    with pytest.raises(ValueError): validate_steps(status, steps, dates, NOW)


def test_no_evidence_cannot_be_complete_or_incomplete():
    for status in ('COMPLETE', 'INCOMPLETE'):
        with pytest.raises(ValueError): validate_steps(status, [], {}, NOW)
    validate_steps('NOT_APPLICABLE', [], {}, NOW)
    with pytest.raises(ValueError): plan_with_verification_coverage([], [])


def test_null_result_and_state_fall_back_to_observed_fields():
    fact = normalize(dict(resource_id='record-z', result=None, state=None, observed_at=None,
                          status_code=404), SOURCE, 'account_service')
    assert fact.state == 'ABSENT' and fact.observed_at == NOW


def test_image_state_does_not_assign_screen_wide_ownership():
    text = ('BridgeOps Topology\n'
            'data_flow_901 warehouse someone@example.test Continuous 20\n'
            'data_flow_902 warehouse owner@example.test Disabled 0\n')
    facts, _ = parse_text(text, SOURCE)
    assert [(f.resource_id, f.state) for f in facts] == [('data_flow_901', 'ACTIVE')]
    assert facts[0].identifiers == set()


def test_image_ocr_does_not_correct_resource_ids():
    facts, _ = parse_text('Search Console Raw document - search 901', SOURCE)
    assert facts == []


def test_audit_lookup_future_capture_cannot_establish_link():
    from types import SimpleNamespace
    pipeline = Pipeline.__new__(Pipeline)
    fact = EvidenceFact('future', 'account_service', 'record-z', 'USER_PROFILE', 'ABSENT',
                        NOW, LATER, set(), {'lookup_key': 'owner@example.test'})
    pipeline.corpus = SimpleNamespace(facts=[fact])
    assert pipeline._get_audit_lookup_links(IdentitySet('user_90001', {'owner@example.test'}), NOW) == []


def test_snapshot_negative_facts_are_request_local():
    from collections import defaultdict
    from models import SnapshotScope
    corpus = Corpus.__new__(Corpus)
    corpus.facts = []; corpus.by_identifier = {}; corpus.by_resource = defaultdict(list)
    corpus.links = {}; corpus.resource_links = []; corpus.reference_links = []
    corpus.snapshot_scopes = [SnapshotScope('fixture', NOW, 'account_service', 'USER_PROFILE', frozenset())]
    link = ResourceLink('user_90001', 'account_service', 'record-z', 'USER_PROFILE',
                        'event_correlation', 'fixture-link', NOW)
    identity = IdentitySet('user_90001')
    before = deepcopy((corpus.facts, corpus.by_resource, corpus.resource_links))
    first = corpus.retrieve(identity, NOW, [link])[0]
    assert len(first) == 1 and first[0].state == 'ABSENT'
    assert (corpus.facts, corpus.by_resource, corpus.resource_links) == before
    assert corpus.retrieve(identity, NOW)[0] == []


def test_explicit_catalog_edge_is_subject_scoped():
    from types import SimpleNamespace
    pipeline = Pipeline.__new__(Pipeline)
    link = ResourceLink('user_90002', 'account_service', 'record-z', 'USER_PROFILE',
                        'LINK_RESOURCE_IDENTITY', 'fixture', NOW)
    pipeline.corpus = SimpleNamespace(facts=[], resource_links=[link])
    assert pipeline._collect_subject_resources(IdentitySet('user_90001'), NOW, []) == []


def test_reference_filename_requires_exact_subject_catalog_edge():
    from collections import defaultdict
    corpus = Corpus.__new__(Corpus)
    fact = normalize(dict(resource_id='receipt.pdf', record_type='SUPPORT_ATTACHMENT',
                          state='PRESENT', external_reference=True), SOURCE, 'object_storage')
    corpus.facts = [fact]; corpus.by_identifier = {}; corpus.by_resource = defaultdict(list)
    event = dict(event_type='LINK_RESOURCE_IDENTITY', event_time=NOW, target_system='object_storage',
                 resource_id='object-z', details='receipt.pdf belongs to user_90001')
    corpus.links = {'user_90001': [event]}; corpus.resource_links = []
    corpus.reference_links = [event]; corpus.snapshot_scopes = []
    facts, _, _ = corpus.retrieve(IdentitySet('user_90001'), NOW)
    assert [(f.resource_id, f.evidence_id) for f in facts] == [('object-z', SOURCE.file_id)]
    assert corpus.retrieve(IdentitySet('user_90002'), NOW)[0] == []
    event['details'] = 'other-receipt.pdf belongs to user_90001'
    assert corpus.retrieve(IdentitySet('user_90001'), NOW)[0] == []


def test_ownership_link_availability_includes_capture():
    corpus = Corpus.__new__(Corpus)
    fact = normalize(dict(resource_id='record-z', email='owner@example.test'),
                     EvidenceSource('future', 'future', 'account_service', LATER),
                     'account_service', observed=NOW)
    corpus.facts = [fact]; corpus.activity = []; corpus.resource_links = []
    corpus._build_resource_links()
    assert corpus.resource_links
    assert all(link.established_at == LATER for link in corpus.resource_links)


def test_backup_image_row_does_not_use_other_archive_restore_activity():
    facts, _ = parse_text('Vault Recovery Manager Archives\n'
                          'backup_90001 owner@example.test 2 GB Archive\n'
                          'backup_90002 restored - Completed\n', SOURCE)
    assert [(f.resource_id, f.state) for f in facts] == [('backup_90001', 'ACTIVE')]


def test_evaluation_abstention_is_counted_as_failure():
    import json
    from evaluation.metrics import evaluate
    report = evaluate([dict(case_id='fixture', deletion_status='UNRESOLVED', steps=[])],
                      [dict(case_id='fixture', deletion_status='COMPLETE', steps_json=json.dumps(valid_plan()[1]))])
    assert report['cases'] == 1 and report['status_accuracy'] == 0
    assert report['exact_case_accuracy'] == 0 and report['sequence_accuracy'] == 0
    with pytest.raises(ValueError): validate_steps('UNRESOLVED', [], {}, NOW)


def test_identity_bearing_document_keeps_exact_catalog_mapping():
    from collections import defaultdict
    corpus = Corpus.__new__(Corpus)
    fact = normalize(dict(resource_id='statement-z', record_type='USER_EXPORT',
                          state='PRESENT', external_reference=True, email='owner@example.test'),
                     SOURCE, 'export_service')
    corpus.facts = [fact]; corpus.by_identifier = {'owner@example.test': {0}}
    corpus.by_resource = defaultdict(list, {('export_service', 'statement-z'): [0]})
    corpus.links = {}; corpus.resource_links = []; corpus.snapshot_scopes = []
    corpus.reference_links = [dict(event_time=NOW, target_system='export_service',
                                  resource_id='export-z', details='statement-z maps to export-z')]
    facts, _, _ = corpus.retrieve(IdentitySet('user_90001', {'owner@example.test'}), NOW)
    assert [(f.resource_id, f.evidence_id) for f in facts] == [('export-z', SOURCE.file_id)]
