"""Focused regression tests for the four fixes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
DATASET = Path(__file__).resolve().parents[1] / 'dataset'
from corpus import Corpus, read_csv
from identity import IdentityResolver
from models import EvidenceFact, SnapshotScope, ResourceLink, timestamp
from datetime import timedelta


def test_1_known_account_missing_from_snapshot_resolves_absent():
    """Fix 1: Known account missing from authoritative snapshot → ABSENT fact."""
    corpus = Corpus(DATASET, media=False)
    identities = read_csv(DATASET / 'user_identities.csv')
    audit_log = read_csv(DATASET / 'user_audit_log.csv')
    resolver = IdentityResolver(identities, audit_log)
    
    identity = resolver.for_user('user_01', '2026-09-03T11:30:00Z')
    
    # Add event-correlation link for account_001 (from case_01)
    link = ResourceLink(
        subject_user_id='user_01',
        system_id='account_service',
        resource_id='account_001',
        category='USER_PROFILE',
        provenance='event_correlation',
        evidence_id='activity_3342',
        established_at='2026-08-20T16:41:43Z'
    )
    corpus.resource_links.append(link)
    
    facts, _, _ = corpus.retrieve(identity, '2026-09-03T11:30:00Z', [link])
    
    # Should find ABSENT fact for account_001 from evidence_54 snapshot
    absent_facts = [f for f in facts if f.resource_id == 'account_001' and f.state == 'ABSENT' and f.evidence_kind == 'negative']
    assert len(absent_facts) == 1, f"Expected 1 ABSENT fact for account_001, got {len(absent_facts)}"
    assert absent_facts[0].evidence_id == 'evidence_54', f"Expected evidence_54, got {absent_facts[0].evidence_id}"
    print("✓ Test 1 passed: Known account missing from snapshot → ABSENT")


def test_2_unknown_resource_missing_from_snapshot_no_absent():
    """Fix 1: Unknown/random resource missing from snapshot does NOT create ABSENT."""
    corpus = Corpus(DATASET, media=False)
    identities = read_csv(DATASET / 'user_identities.csv')
    audit_log = read_csv(DATASET / 'user_audit_log.csv')
    resolver = IdentityResolver(identities, audit_log)
    
    identity = resolver.for_user('user_01', '2026-09-03T11:30:00Z')
    
    # Do NOT add any resource link for account_9999 (unknown)
    facts, _, _ = corpus.retrieve(identity, '2026-09-03T11:30:00Z')
    
    absent_facts = [f for f in facts if f.resource_id == 'account_9999' and f.evidence_kind == 'negative']
    assert len(absent_facts) == 0, f"Expected 0 ABSENT facts for unknown account_9999, got {len(absent_facts)}"
    print("✓ Test 2 passed: Unknown resource missing from snapshot → no ABSENT")


def test_3_delete_record_links_but_not_proves_absent():
    """Fix 3: DELETE_RECORD SUCCESS links resource but doesn't prove ABSENT alone."""
    corpus = Corpus(DATASET, media=False)
    identities = read_csv(DATASET / 'user_identities.csv')
    audit_log = read_csv(DATASET / 'user_audit_log.csv')
    resolver = IdentityResolver(identities, audit_log)
    
    identity = resolver.for_user('user_01', '2026-09-03T11:30:00Z')
    
    # Add event-correlation link (simulating DELETE_RECORD)
    link = ResourceLink(
        subject_user_id='user_01',
        system_id='account_service',
        resource_id='account_001',
        category='USER_PROFILE',
        provenance='event_correlation',
        evidence_id='activity_3342',
        established_at='2026-08-20T16:41:43Z'
    )
    corpus.resource_links.append(link)
    
    facts, _, _ = corpus.retrieve(identity, '2026-09-03T11:30:00Z', [link])
    
    # Should have the link but ABSENT must come from snapshot, not from DELETE_RECORD
    absent_facts = [f for f in facts if f.resource_id == 'account_001' and f.state == 'ABSENT' and f.evidence_kind == 'negative']
    
    assert len(absent_facts) == 1, f"Expected 1 negative ABSENT fact from snapshot, got {len(absent_facts)}"
    assert absent_facts[0].evidence_id == 'evidence_54', f"ABSENT must cite snapshot evidence_54, got {absent_facts[0].evidence_id}"
    print("✓ Test 3 passed: DELETE_RECORD links resource, ABSENT comes from snapshot")


def test_4_other_email_cannot_enter_subject_graph():
    """Fix 2: Resource belonging to another email cannot enter subject graph."""
    corpus = Corpus(DATASET, media=False)
    identities = read_csv(DATASET / 'user_identities.csv')
    audit_log = read_csv(DATASET / 'user_audit_log.csv')
    resolver = IdentityResolver(identities, audit_log)
    
    # user_01 = amina.elmasri@gmail.com
    identity = resolver.for_user('user_01', '2026-09-03T11:30:00Z')
    
    # account_005 belongs to leila.haddad@yahoo.com (user_05), not user_01
    facts, _, _ = corpus.retrieve(identity, '2026-09-03T11:30:00Z')
    
    # Should NOT have account_005 in facts for user_01
    account_005_facts = [f for f in facts if f.resource_id == 'account_005']
    assert len(account_005_facts) == 0, f"Expected 0 facts for account_005 (belongs to user_05), got {len(account_005_facts)}"
    print("✓ Test 4 passed: Other user's resource not in subject graph")


def test_5_incomplete_verification_includes_compliant_companions():
    """Fix 4: INCOMPLETE verification includes compliant companion resources."""
    from planner import plan_with_verification_coverage
    from models import PolicyDecision, EvidenceFact, ResourceState
    from resolver import resolve
    
    corpus = Corpus(DATASET, media=False)
    identities = read_csv(DATASET / 'user_identities.csv')
    audit_log = read_csv(DATASET / 'user_audit_log.csv')
    resolver = IdentityResolver(identities, audit_log)
    
    identity = resolver.for_user('user_06', '2026-09-10T09:15:00Z')  # CORRECT audit_at for case_06
    
    # Add event-correlation links for account_006 and search_001
    event_links = []
    for rid, sys, cat in [('account_006', 'account_service', 'USER_PROFILE'), ('search_001', 'search_service', 'SEARCH_INDEX_ENTRY')]:
        link = ResourceLink(
            subject_user_id='user_06',
            system_id=sys,
            resource_id=rid,
            category=cat,
            provenance='event_correlation',
            evidence_id=f'activity_xxx',
            established_at='2026-08-30T17:08:20Z'
        )
        corpus.resource_links.append(link)
        event_links.append(link)
    
    facts, _, _ = corpus.retrieve(identity, '2026-09-10T09:15:00Z', event_links)
    states = resolve(facts, '2026-09-10T09:15:00Z')
    
    # Build all_subject_resources
    all_subject_resources = [
        ('account_service', 'account_006', 'USER_PROFILE', 'DELETE'),
        ('search_service', 'search_001', 'SEARCH_INDEX_ENTRY', 'DELETE'),
    ]
    
    from policy import Policy
    policy = Policy(read_csv(DATASET / 'deletion_rules.csv'))
    decisions = [policy.evaluate(s, '2026-09-10T09:15:00Z') for s in states]
    
    status, steps = plan_with_verification_coverage(decisions, all_subject_resources)
    
    # Should have VERIFICATION for BOTH resources (even compliant ones)
    verify_steps = [s for s in steps if s['phase'] == 'VERIFICATION']
    verify_resources = {(s['system_id'], s['resource_id']) for s in verify_steps}
    
    assert ('account_service', 'account_006') in verify_resources, "Missing VERIFY for account_006"
    assert ('search_service', 'search_001') in verify_resources, "Missing VERIFY for search_001"
    
    # For INCOMPLETE, evidence_id should be empty
    for s in verify_steps:
        assert s['evidence_id'] == '', f"INCOMPLETE verification should have empty evidence_id, got {s['evidence_id']}"
    print("✓ Test 5 passed: INCOMPLETE includes compliant companion resources with empty evidence_id")


def test_6_complete_verification_requires_evidence():
    """Fix 4: COMPLETE verification requires actual evidence."""
    from planner import plan_with_verification_coverage
    from models import PolicyDecision, EvidenceFact
    
    # Create a mock COMPLETE decision with evidence
    fact = EvidenceFact(
        evidence_id='evidence_54',
        system_id='account_service',
        resource_id='account_001',
        category='USER_PROFILE',
        state='ABSENT',
        observed_at='2026-09-02T23:00:00Z',
        captured_at='2026-09-02T23:00:00Z',
        identifiers=set(),
        fields={},
        locator='snapshot:evidence_54',
        strength=3,
        evidence_kind='negative'
    )
    
    from models import PolicyDecision
    decision = PolicyDecision(
        fact=fact,
        rule_id='rule_01',
        action='DELETE',
        expected='ABSENT',
        compliant=True
    )
    
    all_subject_resources = [
        ('account_service', 'account_001', 'USER_PROFILE', 'DELETE'),
    ]
    
    status, steps = plan_with_verification_coverage([decision], all_subject_resources)
    
    assert status == 'COMPLETE', f"Expected COMPLETE, got {status}"
    
    verify_steps = [s for s in steps if s['phase'] == 'VERIFICATION']
    assert len(verify_steps) == 1, f"Expected 1 VERIFICATION step, got {len(verify_steps)}"
    assert verify_steps[0]['evidence_id'] == 'evidence_54', f"COMPLETE verification must cite evidence, got {verify_steps[0]['evidence_id']}"
    print("✓ Test 6 passed: COMPLETE verification requires actual evidence")


def test_7_unrelated_delete_record_cannot_enter_subject_graph():
    """Activity success without subject identifiers cannot establish ownership."""
    from pipeline import Pipeline
    from models import DeletionCase
    pipeline = Pipeline(DATASET, media=False)
    case = DeletionCase(**read_csv(DATASET / 'sample_deletion_requests.csv')[0])
    identity = pipeline.identities.resolve(case.email, case.audit_at)
    events = [e for e in pipeline.corpus.activity
              if e['event_type'] == 'DELETE_RECORD'
              and abs((timestamp(e['event_time']) - timestamp(case.reported_at)).total_seconds()) <= 3600]
    assert events, 'Fixture must exercise a real activity record'
    assert all(not pipeline._has_direct_identity_in_details(e['details'], identity) for e in events)
    assert pipeline._get_event_correlation_links(identity, case, 'DELETE') == []


def test_8_partial_and_success_unrelated_users_rejected():
    """Both outcomes need exact subject provenance; success is not ownership."""
    from pipeline import Pipeline
    from models import DeletionCase, IdentitySet
    from types import SimpleNamespace
    pipeline = Pipeline.__new__(Pipeline)
    identity = IdentitySet('user_90001', {'owner@example.test'})
    case = DeletionCase('fixture', 'owner@example.test', '2026-06-01T00:00:00Z',
                        'COMPLETE', '2026-06-01T00:00:00Z', '2026-06-02T00:00:00Z',
                        'Please delete my account')
    for outcome in ('SUCCESS', 'PARTIAL'):
        event = dict(event_type='DELETE_RECORD', reported_result=outcome,
                     resource_id='account_90001', event_time=case.reported_at,
                     details='Deletion worker received the final result.',
                     target_system='account_service', activity_id='fixture-event')
        pipeline.corpus = SimpleNamespace(activity=[event])
        assert pipeline._get_event_correlation_links(identity, case, 'DELETE') == []
        event['details'] = 'Deletion result for other@example.test and user_90002'
        assert pipeline._get_event_correlation_links(identity, case, 'DELETE') == []
        event['details'] = 'Deletion result for owner@example.test'
        assert len(pipeline._get_event_correlation_links(identity, case, 'DELETE')) == 1


if __name__ == '__main__':
    test_1_known_account_missing_from_snapshot_resolves_absent()
    test_2_unknown_resource_missing_from_snapshot_no_absent()
    test_3_delete_record_links_but_not_proves_absent()
    test_4_other_email_cannot_enter_subject_graph()
    test_5_incomplete_verification_includes_compliant_companions()
    test_6_complete_verification_requires_evidence()
    test_7_unrelated_delete_record_cannot_enter_subject_graph()
    test_8_partial_and_success_unrelated_users_rejected()
    print("\n✓ All 8 regression tests passed!")
