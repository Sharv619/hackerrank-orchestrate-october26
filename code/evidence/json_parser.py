import json
from evidence.normalize import normalize
from models import ResourceLink, timestamp


REFERENCE_FIELDS = ('customer_reference', 'subject_reference', 'subject_ref', 'subject_selector', 'user_id')


def parse(path, source):
    data = json.loads(path.read_text(encoding='utf-8'))
    facts = []
    scopes = []
    ref_links = []  # ResourceLink objects from explicit references

    def records(rows, system, collection, observed, locator):
        if collection == 'customer_profiles':
            scopes.append((source, system or 'account_service', observed, {r['resource_id'] for r in rows}, locator))
        for i, row in enumerate(rows):
            fact = normalize(row, source, system, collection, observed, f'{locator}/{i}')
            if fact:
                facts.append(fact)
                # Extract explicit reference links from this record
                for ref_field in REFERENCE_FIELDS:
                    ref_value = row.get(ref_field)
                    if ref_value and fact.resource_id and fact.category:
                        # Normalize reference value (same as identifiers)
                        from evidence.normalize import norm
                        ref_norm = norm(ref_value)
                        ref_links.append(ResourceLink(
                            subject_user_id=ref_norm,
                            system_id=fact.system_id,
                            resource_id=fact.resource_id,
                            category=fact.category,
                            provenance='reference',
                            evidence_id=fact.evidence_id,
                            established_at=max((fact.observed_at, fact.captured_at), key=timestamp)
                        ))

    if isinstance(data, list):
        records(data, source.origin, '', source.captured_at, 'records')
    elif 'service_exports' in data:
        for system, groups in data['service_exports'].items():
            for collection, rows in groups.items():
                records(rows, system, collection, data['exported_at'], collection)
    elif 'snapshots' in data:
        for i, snapshot in enumerate(data['snapshots']):
            records(snapshot['records'], snapshot['data_store'], snapshot['collection'], snapshot['captured_at'], f'snapshots/{i}')
    else:
        records(data.get('records', []), source.origin, data.get('collection', ''), data.get('captured_at', data.get('exported_at', source.captured_at)), 'records')
    return facts, scopes, ref_links
