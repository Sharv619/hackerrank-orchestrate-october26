"""Parse once, then retrieve by exact identifiers and grounded resource links."""
from collections import defaultdict, Counter
from pathlib import Path
import csv
import re
from models import EvidenceSource, EvidenceFact, SnapshotScope, ResourceLink, timestamp
from evidence import json_parser, sql_parser, log_parser, text_parser
from evidence.normalize import identifiers, extract_resource_ids, RESOURCE_PATTERNS


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


class Corpus:
    def __init__(self, dataset, media=True):
        self.dataset = Path(dataset)
        self.activity = read_csv(self.dataset / 'system_activity.csv')
        self.sources = [EvidenceSource(**r) for r in read_csv(self.dataset / 'evidence_files.csv')]
        self.facts = []
        self.scopes = []
        self.snapshot_scopes = []
        self.coverage = []
        parsers = {'.json': json_parser.parse, '.sql': sql_parser.parse, '.log': log_parser.parse, '.txt': text_parser.parse}
        if media:
            from evidence.pdf_parser import parse as pdf_parse
            parsers['.pdf'] = pdf_parse
            from evidence.image_parser import parse as image_parse
            parsers['.png'] = image_parse

        # Build resource links with explicit provenance (initialize early)
        self.resource_links = []

        for source in self.sources:
            path = self.dataset / source.file_path
            parser = parsers.get(path.suffix)
            if parser is None:
                self.coverage.append(dict(file_id=source.file_id, status='skipped', format=path.suffix, reason='adapter not enabled'))
                continue
            try:
                # JSON parser now returns (facts, scopes, ref_links)
                result = parser(path, source)
                if isinstance(result, tuple) and len(result) == 3:
                    facts, scopes, ref_links = result
                else:
                    # Backward compatibility
                    facts, scopes = result
                    ref_links = []
            except Exception as exc:
                raise ValueError(f'{source.file_id}: evidence parsing failed: {exc}') from exc
            self.facts.extend(facts)
            # Add reference links from explicit structured references
            self.resource_links.extend(ref_links)
            for s in scopes:
                if isinstance(s, SnapshotScope):
                    self.snapshot_scopes.append(s)
                else:
                    self.scopes.append(s)
            self.coverage.append(dict(file_id=source.file_id, status='parsed', records=len(facts)))

        # Build indexes
        self.by_identifier = defaultdict(set)
        self.by_resource = defaultdict(list)
        for i, fact in enumerate(self.facts):
            self.by_resource[(fact.system_id, fact.resource_id)].append(i)
            for key in fact.identifiers:
                self.by_identifier[key].add(i)

        # Build resource links with explicit provenance
        self._build_resource_links()

        # Links from system_activity (for identity-based expansion)
        self.links = defaultdict(list)
        for event in self.activity:
            keys = identifiers(event['details'])
            for key in keys:
                self.links[key].append(event)

        # Reference links from explicit catalog
        self.reference_links = []
        for event in self.activity:
            if event['event_type'] == 'LINK_RESOURCE_IDENTITY':
                self.reference_links.append(event)

    def _build_resource_links(self):
        """Build explicit subject→resource edges with provenance."""
        # 1. From facts with user_id (provenance: 'user_id')
        for fact in self.facts:
            user_id = fact.fields.get('user_id')
            if user_id and fact.category in {'USER_PROFILE', 'SECONDARY_IDENTIFIER', 'ACCOUNT_TOMBSTONE'}:
                self.resource_links.append(ResourceLink(
                    subject_user_id=user_id,
                    system_id=fact.system_id,
                    resource_id=fact.resource_id,
                    category=fact.category,
                    provenance='user_id',
                    evidence_id=fact.evidence_id,
                    established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                ))

        # 2. From facts with email/phone/hash (provenance: 'email'/'phone'/'hash')
        for fact in self.facts:
            for ident in sorted(fact.identifiers):
                if '@' in ident:
                    self.resource_links.append(ResourceLink(
                        subject_user_id=ident,
                        system_id=fact.system_id,
                        resource_id=fact.resource_id,
                        category=fact.category,
                        provenance='email',
                        evidence_id=fact.evidence_id,
                        established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                    ))
                elif ident.startswith('user_') and len(ident) > 5:
                    self.resource_links.append(ResourceLink(
                        subject_user_id=ident,
                        system_id=fact.system_id,
                        resource_id=fact.resource_id,
                        category=fact.category,
                        provenance='user_id',
                        evidence_id=fact.evidence_id,
                        established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                    ))
                elif re.fullmatch(r'\+?[\d ()-]{8,25}', ident) and len(ident) >= 8:
                    self.resource_links.append(ResourceLink(
                        subject_user_id=ident,
                        system_id=fact.system_id,
                        resource_id=fact.resource_id,
                        category=fact.category,
                        provenance='phone',
                        evidence_id=fact.evidence_id,
                        established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                    ))
                elif len(ident) == 64 and all(c in '0123456789abcdef' for c in ident.lower()):
                    self.resource_links.append(ResourceLink(
                        subject_user_id=ident,
                        system_id=fact.system_id,
                        resource_id=fact.resource_id,
                        category=fact.category,
                        provenance='hash',
                        evidence_id=fact.evidence_id,
                        established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                    ))

        # 3. From explicit LINK_RESOURCE_IDENTITY events
        for event in self.activity:
            if event['event_type'] == 'LINK_RESOURCE_IDENTITY':
                email_match = re.search(r'([\w.+-]+@[\w.-]+\.[a-zA-Z]{2,})', event['details'])
                user_match = re.search(r'\buser_\d+\b', event['details'])
                if email_match or user_match:
                    subject_id = user_match.group(0) if user_match else email_match.group(0)
                    self.resource_links.append(ResourceLink(
                        subject_user_id=subject_id,
                        system_id=event['target_system'],
                        resource_id=event['resource_id'],
                        category='',
                        provenance='LINK_RESOURCE_IDENTITY',
                        evidence_id=event['activity_id'],
                        established_at=event['event_time']
                    ))

        # 4. From reference relationships in facts
        for fact in self.facts:
            if fact.fields.get('external_reference'):
                self.resource_links.append(ResourceLink(
                    subject_user_id='',
                    system_id=fact.system_id,
                    resource_id=fact.resource_id,
                    category=fact.category,
                    provenance='reference',
                    evidence_id=fact.evidence_id,
                    established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                ))

    def _get_snapshot_scope(self, system_id: str, resource_type: str, cutoff: str):
        """Get the most recent authoritative snapshot scope for a system/resource_type at or before cutoff."""
        from models import timestamp
        cutoff_ts = timestamp(cutoff)
        candidates = [
            s for s in self.snapshot_scopes
            if s.is_authoritative_for(system_id, resource_type)
            and timestamp(s.captured_at) <= cutoff_ts
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: timestamp(s.captured_at))

    def retrieve(self, identity, cutoff, event_correlation_links=None):
        from models import timestamp
        selected = set()
        for key in sorted(identity.keys):
            selected.update(self.by_identifier.get(key, ()))
        accepted = {i for i in selected if self.facts[i].available(cutoff)}
        resources = {(self.facts[i].system_id, self.facts[i].resource_id) for i in accepted}
        links = []
        for key in sorted(identity.keys):
            for event in self.links.get(key, ()):
                if timestamp(event['event_time']) <= timestamp(cutoff):
                    resources.add((event['target_system'], event['resource_id']))
                    links.append(event)

        # Also add resources linked via explicit resource links
        for link in self.resource_links:
            subject_match = False
            if link.provenance == 'user_id' and link.subject_user_id == identity.user_id:
                subject_match = True
            elif link.provenance in ('email', 'hash', 'phone') and link.subject_user_id in identity.keys:
                subject_match = True
            elif link.provenance == 'LINK_RESOURCE_IDENTITY':
                if link.subject_user_id == identity.user_id or link.subject_user_id in identity.keys:
                    subject_match = True

            if subject_match and timestamp(link.established_at) <= timestamp(cutoff):
                resources.add((link.system_id, link.resource_id))

        # Add case-specific event-correlation links
        if event_correlation_links:
            for link in event_correlation_links:
                if link.subject_user_id == identity.user_id and timestamp(link.established_at) <= timestamp(cutoff):
                    resources.add((link.system_id, link.resource_id))

        reference_facts = []
        from dataclasses import replace
        for fact in self.facts:
            if not fact.fields.get('external_reference') or not fact.available(cutoff):
                continue
            matches = [e for e in self.reference_links
                       if timestamp(e['event_time']) <= timestamp(cutoff)
                       and re.search(r'(?<![\w.-])' + re.escape(fact.resource_id) + r'(?![\w.-])', e['details'])
                       and ((e['target_system'], e['resource_id']) in resources
                            or bool(identity.keys.intersection(fact.identifiers)))]
            targets = {(e['target_system'], e['resource_id']) for e in matches}
            if len(targets) == 1:
                system, resource = next(iter(targets))
                reference_facts.append(replace(fact, system_id=system, resource_id=resource))

        for resource in sorted(resources):
            accepted.update(i for i in self.by_resource.get(resource, ()) if self.facts[i].available(cutoff))

        # NEGATIVE EVIDENCE: Infer ABSENT for known subject resources in authoritative snapshots
        # Get all subject-linked resources from resource_links + event_correlation_links
        subject_resource_ids = set()
        link_category_map = {}
        for link in self.resource_links:
            subject_match = False
            if link.provenance == 'user_id' and link.subject_user_id == identity.user_id:
                subject_match = True
            elif link.provenance in ('email', 'hash', 'phone') and link.subject_user_id in identity.keys:
                subject_match = True
            elif link.provenance == 'LINK_RESOURCE_IDENTITY':
                if link.subject_user_id == identity.user_id or link.subject_user_id in identity.keys:
                    subject_match = True

            if subject_match and timestamp(link.established_at) <= timestamp(cutoff):
                subject_resource_ids.add((link.system_id, link.resource_id))
                if link.category:
                    link_category_map[(link.system_id, link.resource_id)] = link.category

        # Also from event-correlation links
        if event_correlation_links:
            for link in event_correlation_links:
                if link.subject_user_id == identity.user_id and timestamp(link.established_at) <= timestamp(cutoff):
                    subject_resource_ids.add((link.system_id, link.resource_id))
                    if link.category:
                        link_category_map[(link.system_id, link.resource_id)] = link.category

        # Build set of resources already present as PRESENT facts
        present_resources = set()
        for i in accepted:
            fact = self.facts[i]
            if fact.state == 'PRESENT':
                present_resources.add((fact.system_id, fact.resource_id))

        # For each known subject resource, check if there's an authoritative snapshot showing it ABSENT
        negative_facts = []
        for system_id, resource_id in sorted(subject_resource_ids):
            if (system_id, resource_id) in present_resources:
                continue

            category = link_category_map.get((system_id, resource_id), '')
            if not category:
                for fact in self.facts:
                    if fact.system_id == system_id and fact.resource_id == resource_id:
                        if fact.available(cutoff):
                            category = fact.category
                            break

            if not category:
                continue

            scope = self._get_snapshot_scope(system_id, category, cutoff)
            if scope and resource_id not in scope.observed_resource_ids:
                neg_fact = EvidenceFact(
                    evidence_id=scope.evidence_id,
                    system_id=system_id,
                    resource_id=resource_id,
                    category=category,
                    state='ABSENT',
                    observed_at=scope.captured_at,
                    captured_at=scope.captured_at,
                    identifiers=set(),
                    fields={},
                    locator=f'snapshot:{scope.evidence_id}',
                    strength=3,
                    evidence_kind='negative'
                )
                if neg_fact.available(cutoff):
                    negative_facts.append(neg_fact)

        facts = []
        from dataclasses import replace
        for i in sorted(accepted):
            fact = self.facts[i]
            if fact.fields.get('external_reference'):
                continue
            facts.append(fact)
        return facts + negative_facts + reference_facts, links, len(selected - accepted)

    def summary(self):
        return dict(
            expected_files=len(self.sources),
            files=dict(Counter(r['status'] for r in self.coverage)),
            normalized_records=len(self.facts),
            indexed_identifiers=len(self.by_identifier),
            snapshot_scopes=len(self.snapshot_scopes),
            resource_links=len(self.resource_links)
        )
