from dataclasses import asdict
from corpus import Corpus, read_csv
from models import DeletionCase, SnapshotScope, ResourceLink
from identity import IdentityResolver
from intent import classify
from resolver import resolve
from policy import Policy
from planner import plan, plan_with_verification_coverage
from datetime import timedelta
import re


class InsufficientEvidenceError(ValueError):
    """No permitted status can be established from grounded state evidence."""


class Pipeline:
    def __init__(self, dataset, media=False):
        from pathlib import Path
        dataset = Path(dataset)
        self.corpus = Corpus(dataset, media)
        self.identities = IdentityResolver(read_csv(dataset / 'user_identities.csv'), read_csv(dataset / 'user_audit_log.csv'))
        self.policy = Policy(read_csv(dataset / 'deletion_rules.csv'))

    def audit(self, case):
        intent, route, reason = classify(case.request_text)
        diagnostic = dict(case_id=case.case_id, intent=intent, route=route, reason=reason, warnings=[])
        if intent == 'NON_DELETE':
            return dict(case_id=case.case_id, deletion_status='NOT_APPLICABLE', steps=[]), diagnostic
        if intent == 'AMBIGUOUS':
            diagnostic['warnings'].append('Unresolved request intent')
        identity = self.identities.resolve(case.email, case.audit_at)
        diagnostic['user_id'] = identity.user_id

        # Task 1: ONLY grounded event-correlation links (direct identity in event details)
        event_correlation_links = self._get_event_correlation_links(identity, case, intent)

        # Task 2: Request-local audit lookup links (never mutates Corpus.resource_links)
        audit_lookup_links = self._get_audit_lookup_links(identity, case.audit_at)

        facts, links, future = self.corpus.retrieve(identity, case.audit_at, event_correlation_links + audit_lookup_links)
        states = resolve(facts, case.audit_at)
        decisions = [self.policy.evaluate(s, case.audit_at) for s in states]

        # Collect all subject resources for verification coverage
        all_subject_resources = self._collect_subject_resources(identity, case.audit_at, event_correlation_links + audit_lookup_links)

        if decisions:
            status, steps = plan_with_verification_coverage(decisions, all_subject_resources)
        else:
            raise InsufficientEvidenceError(f'{case.case_id}: no grounded state evidence; cannot establish a contract-valid deletion status')

        diagnostic.update(resources=len(states), future_observations_ignored=future, conflicts=sum(bool(s.conflicts) for s in states), evidence=sorted({f.evidence_id for f in facts}))
        return dict(case_id=case.case_id, deletion_status=status, steps=steps), diagnostic

    def _get_event_correlation_links(self, identity, case, intent):
        """
        Get event-correlation resource links ONLY when DELETE_RECORD event
        contains grounded identity correlation in its details.
        
        Allowed grounded correlation:
        - exact user_id
        - exact current/historical email
        - exact normalized phone
        - exact email_hash
        - explicit subject/customer reference matching identity
        - explicit LINK_RESOURCE_IDENTITY reference
        """
        from models import timestamp, ResourceLink
        if intent != 'DELETE':
            return []
        
        from models import timestamp as ts_func
        case_reported = ts_func(case.reported_at)
        window_start = case_reported - timedelta(hours=1)
        window_end = case_reported + timedelta(hours=1)
        
        links = []
        for event in self.corpus.activity:
            if event['event_type'] == 'DELETE_RECORD' and event['reported_result'] in ('SUCCESS', 'PARTIAL'):
                res_id = event.get('resource_id', '')
                if not (res_id and res_id.startswith('account_')):
                    continue
                
                event_time = ts_func(event['event_time'])
                if not (window_start <= event_time <= window_end):
                    continue
                
                # ONLY grounded correlation: direct identity in event details
                if not self._has_direct_identity_in_details(event.get('details', ''), identity):
                    continue  # No grounded correlation - reject
                
                link = ResourceLink(
                    subject_user_id=identity.user_id,
                    system_id=event['target_system'],
                    resource_id=res_id,
                    category='USER_PROFILE',
                    provenance='event_correlation',
                    evidence_id=event['activity_id'],
                    established_at=event['event_time']
                )
                links.append(link)
        return links

    def _has_direct_identity_in_details(self, details, identity):
        """Check if event details contain grounded identity correlation."""
        # Check for user_id
        user_match = re.search(r'\b(user_\d+)\b', details)
        if user_match and user_match.group(1) == identity.user_id:
            return True
        # Check for email
        email_match = re.search(r'([\w.+-]+@[\w.-]+\.[a-zA-Z]{2,})', details)
        if email_match and email_match.group(1).lower() in identity.keys:
            return True
        # Check for phone
        phone_match = re.search(r'(\+?[\d ()-]{8,25})', details)
        if phone_match:
            phone_norm = re.sub(r'[^0-9]', '', phone_match.group(1))
            if phone_norm in identity.keys:
                return True
        # Check for email hash (64 hex chars)
        hash_match = re.search(r'\b([0-9a-f]{64})\b', details, re.I)
        if hash_match and hash_match.group(1).lower() in identity.keys:
            return True
        # Check for explicit subject/customer reference matching identity
        if ('subject_reference' in details or 'customer_reference' in details) and identity.user_id in details:
            return True
        return False

    def _get_audit_lookup_links(self, identity, audit_at):
        """
        Request-local audit lookup linkage.

        Searches all USER_PROFILE facts where lookup_key exactly matches a
        resolved identity key and observed_at <= audit_at. Selects the
        latest observation overall (across all resource IDs). If two
        different resource IDs share the same maximum timestamp, fails
        closed and returns no link.

        Does NOT mutate Corpus.resource_links — returns a request-local
        list of ResourceLink objects only.

        Returns: list of ResourceLink (0 or 1 items)
        """
        from models import timestamp, ResourceLink

        candidates = []
        for fact in self.corpus.facts:
            if fact.system_id != 'account_service':
                continue
            if fact.category != 'USER_PROFILE':
                continue
            lookup_key = fact.fields.get('lookup_key', '')
            if not lookup_key:
                continue
            if lookup_key not in identity.keys:
                continue
            if not fact.available(audit_at):
                continue
            candidates.append({
                'resource_id': fact.resource_id,
                'observed_at': fact.observed_at,
                'evidence_id': fact.evidence_id,
            })

        if not candidates:
            return []

        max_ts = max(timestamp(c['observed_at']) for c in candidates)
        tied = [c for c in candidates if timestamp(c['observed_at']) == max_ts]
        tied_resources = {c['resource_id'] for c in tied}

        # Fail closed on ties: different resource IDs with same max timestamp
        if len(tied_resources) > 1:
            return []

        winner = tied[0]
        return [ResourceLink(
            subject_user_id=identity.user_id,
            system_id='account_service',
            resource_id=winner['resource_id'],
            category='USER_PROFILE',
            provenance='audit_lookup',
            evidence_id=winner['evidence_id'],
            established_at=winner['observed_at'],
        )]

    def _collect_subject_resources(self, identity, audit_at, event_correlation_links):
        """Collect all known subject resources with their expected actions."""
        from models import timestamp
        resources = []

        # From corpus resource_links
        for link in self.corpus.resource_links:
            subject_match = False
            if link.provenance == 'user_id' and link.subject_user_id == identity.user_id:
                subject_match = True
            elif link.provenance in ('email', 'hash', 'phone') and link.subject_user_id in identity.keys:
                subject_match = True
            elif link.provenance == 'LINK_RESOURCE_IDENTITY':
                subject_match = link.subject_user_id == identity.user_id or link.subject_user_id in identity.keys

            if subject_match and timestamp(link.established_at) <= timestamp(audit_at):
                expected_action = self._expected_action_for_category(link.category)
                if expected_action and link.category:
                    resources.append((link.system_id, link.resource_id, link.category, expected_action))

        # From case-specific event-correlation links
        for link in event_correlation_links:
            subject_match = link.subject_user_id == identity.user_id
            if subject_match and timestamp(link.established_at) <= timestamp(audit_at):
                expected_action = self._expected_action_for_category(link.category)
                if expected_action and link.category:
                    resources.append((link.system_id, link.resource_id, link.category, expected_action))

        # From facts that have subject identifiers
        for fact in self.corpus.facts:
            if not fact.available(audit_at):
                continue
            subject_match = False
            if fact.fields.get('user_id') == identity.user_id:
                subject_match = True
            elif any(ident in identity.keys for ident in fact.identifiers):
                subject_match = True

            if subject_match and fact.category:
                expected_action = self._expected_action_for_category(fact.category)
                if expected_action:
                    resources.append((fact.system_id, fact.resource_id, fact.category, expected_action))

        # ONE-HOP resource-reference traversal:
        # From each owned resource, follow exactly one explicit resource-reference
        # edge (e.g., source_resource_id) to a target resource.
        # Direction is source -> target only, never bidirectional.
        # The source fact must be available at audit_at.
        owned = {(r[0], r[1]) for r in resources}
        for system_id, resource_id in sorted(owned):
            for fact in self.corpus.facts:
                if (fact.system_id, fact.resource_id) != (system_id, resource_id):
                    continue
                if not fact.available(audit_at):
                    continue
                ref_target = (fact.fields.get('source_resource_id') or '').strip()
                if not ref_target:
                    continue
                # Only resource-to-resource references count
                if not re.fullmatch(r'\b(account|search|audit_record|support|backup|data_flow|export|tombstone|connector|analytics)_\d+\b', ref_target):
                    continue
                # Account targets only for this patch
                if not ref_target.startswith('account_'):
                    continue
                expected_action = self._expected_action_for_category('USER_PROFILE')
                if expected_action:
                    resources.append(('account_service', ref_target, 'USER_PROFILE', expected_action))

        seen = set()
        unique = []
        for r in resources:
            key = (r[0], r[1])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    def _expected_action_for_category(self, category):
        if category == 'USER_PROFILE': return 'DELETE'
        elif category == 'SECONDARY_IDENTIFIER': return 'DELETE'
        elif category == 'SEARCH_INDEX_ENTRY': return 'DELETE'
        elif category == 'CACHE_ENTRY': return 'DELETE'
        elif category == 'SUPPORT_MESSAGE': return 'REDACT'
        elif category == 'SUPPORT_ATTACHMENT': return 'DELETE'
        elif category == 'ANALYTICS_PROFILE': return 'ANONYMIZE'
        elif category == 'PRODUCT_TELEMETRY': return 'ANONYMIZE'
        elif category == 'USER_EXPORT': return 'DELETE'
        elif category == 'MARKETING_PROFILE': return 'DELETE'
        elif category == 'EMAIL_DELIVERY_LOG': return 'REDACT'
        elif category == 'SECURITY_AUDIT_LOG': return 'RETAIN'
        elif category == 'LEGAL_HOLD_RECORD': return 'RETAIN'
        elif category == 'BACKUP_ARCHIVE': return 'BLOCK'
        elif category == 'ACCOUNT_TOMBSTONE': return 'REDACT'
        elif category == 'DATA_FLOW': return 'DISABLE'
        return None

    def run(self, path):
        results = []
        diagnostics = []
        for row in sorted(read_csv(path), key=lambda r: r['case_id']):
            result, diagnostic = self.audit(DeletionCase(**row))
            results.append(result)
            diagnostics.append(diagnostic)
        return results, diagnostics
