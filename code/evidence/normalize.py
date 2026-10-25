"""Schema-level normalization shared by every evidence adapter."""
import re
from models import EvidenceFact, SnapshotScope, norm, phone

COLLECTIONS = {
    'customer_profiles': ('account_service','USER_PROFILE'),
    'profile_lookups': ('account_service','USER_PROFILE'),
    'customer_search_documents': ('search_service','SEARCH_INDEX_ENTRY'),
    'search_documents': ('search_service','SEARCH_INDEX_ENTRY'),
    'index_queries': ('search_service','SEARCH_INDEX_ENTRY'),
    'customer_analytics_profiles': ('analytics_platform','ANALYTICS_PROFILE'),
    'customer_analytics_reports': ('analytics_platform','ANALYTICS_PROFILE'),
    'profiles': ('analytics_platform','ANALYTICS_PROFILE'),
    'support_records': ('support_platform','SUPPORT_MESSAGE'),
    'support_conversations': ('support_platform','SUPPORT_MESSAGE'),
    'tickets': ('support_platform','SUPPORT_MESSAGE'),
    'customer_exports': ('export_service','USER_EXPORT'),
    'customer_export_jobs': ('export_service','USER_EXPORT'),
    'exports': ('export_service','USER_EXPORT'),
    'connector_subscriptions': ('integration_service','DATA_FLOW'),
    'connectors': ('integration_service','DATA_FLOW'),
    'backup_restore_entries': ('backup_service','BACKUP_ARCHIVE'),
    'restore_entries': ('backup_service','BACKUP_ARCHIVE'),
    'security_audit_records': ('security_service','SECURITY_AUDIT_LOG'),
    'security_audit_events': ('security_service','SECURITY_AUDIT_LOG'),
    'audit_records': ('security_service','SECURITY_AUDIT_LOG'),
    'deleted_customer_references': ('identity_service','ACCOUNT_TOMBSTONE'),
    'support_attachments': ('support_platform','SUPPORT_ATTACHMENT'),
    'secondary_identifiers': ('identity_service','SECONDARY_IDENTIFIER'),
    'ticket_attachments': ('support_platform','SUPPORT_ATTACHMENT'),
    'connector_configurations': ('integration_service','DATA_FLOW'),
    'connectors': ('integration_service','DATA_FLOW'),
    'backup_restore_entries': ('backup_service','BACKUP_ARCHIVE'),
    'restore_entries': ('backup_service','BACKUP_ARCHIVE'),
    'security_audit_records': ('security_service','SECURITY_AUDIT_LOG'),
    'security_audit_events': ('security_service','SECURITY_AUDIT_LOG'),
    'audit_records': ('security_service','SECURITY_AUDIT_LOG'),
    'deleted_customer_references': ('identity_service','ACCOUNT_TOMBSTONE'),
    'support_attachments': ('support_platform','SUPPORT_ATTACHMENT'),
    'secondary_identifiers': ('identity_service','SECONDARY_IDENTIFIER'),
    'ticket_attachments': ('support_platform','SUPPORT_ATTACHMENT'),
    'connector_configurations': ('integration_service','DATA_FLOW'),
    'connectors': ('integration_service','DATA_FLOW'),
    'backup_catalog': ('backup_service','BACKUP_ARCHIVE'),
    'retained_order_records': ('legal_service','LEGAL_HOLD_RECORD'),
}
SYSTEM_CATEGORY = dict(COLLECTIONS.values())
SYSTEM_CATEGORY.update(account_service='USER_PROFILE', support_platform='SUPPORT_MESSAGE', marketing_platform='MARKETING_PROFILE', object_storage='SUPPORT_ATTACHMENT')

EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')
IDENTIFIER = re.compile(r'(?<![\w])user_\d+(?![\w])|(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', re.I)

# Resource ID patterns for extraction
RESOURCE_PATTERNS = {
    'account': re.compile(r'\baccount_\d+\b'),
    'analytics': re.compile(r'\banalytics_\d+\b'),
    'audit_record': re.compile(r'\baudith_record_\d+\b'),
    'search': re.compile(r'\bsearch_\d+\b'),
    'support': re.compile(r'\bsupport_\d+\b'),
    'backup': re.compile(r'\bbackup_\d+\b'),
    'data_flow': re.compile(r'\bdata_flow_\d+\b'),
    'export': re.compile(r'\bexport_\d+\b'),
    'tombstone': re.compile(r'\btombstone_\d+\b'),
    'connector': re.compile(r'\bconnector_\d+\b'),
}

NULLS = {'', 'null', 'none', '[redacted]', 'redacted', 'no direct identifier'}

# Snapshot scope table name
SNAPSHOT_SCOPE_TABLE = 'snapshot_scope'


def scalar_values(value):
    if isinstance(value, dict):
        for k,v in value.items():
            if k not in {'integrity_seal','checksum','file_name','object_key','archive_key'}:
                yield from scalar_values(v)
    elif isinstance(value, list):
        for v in value: yield from scalar_values(v)
    elif value is not None: yield str(value)


def identifiers(value):
    found = set()
    for s in scalar_values(value):
        found.update(norm(x) for x in EMAIL.findall(s))
        found.update(norm(x) for x in IDENTIFIER.findall(s))
        if re.fullmatch(r'\+?[\d ()-]{8,25}', s) and len(phone(s)) >= 8:
            found.add(phone(s))
    return found


def extract_resource_ids(value) -> set[str]:
    """Extract all resource IDs from a string value."""
    found = set()
    for s in scalar_values(value):
        for pattern_name, pattern in RESOURCE_PATTERNS.items():
            found.update(pattern.findall(s))
    return found


def flattened(row):
    result = dict(row)
    for key in ('document','profile','payload','identifiers'):
        if isinstance(row.get(key), dict):
            result.update(row[key])
    hits = row.get('hits', {})
    if isinstance(hits, dict) and hits.get('documents'):
        result.update(hits['documents'][0])
    return result


def schema(collection, system=''):
    for name in sorted(COLLECTIONS, key=len, reverse=True):
        if collection == name or collection.startswith(name + '_'):
            s, c = COLLECTIONS[name]
            return system if system in SYSTEM_CATEGORY else s, c
    return system, SYSTEM_CATEGORY.get(system, '')


def present(value):
    return norm(value) not in NULLS


def has_pii(row, include_reference=False):
    fields = ('email','phone','name','full_name','display_name','email_hash',
              'requester_name','requester_email','requester_phone',
              'owner_email','owner_phone','customer_email')
    if any(present(row.get(k)) for k in fields):
        return True
    if include_reference and any(present(row.get(k)) for k in ('user_id','customer_reference','subject_reference')):
        return True
    if any(identifiers(row.get(k, '')) for k in ('message_text','message_excerpt','body')):
        return True
    return False


def normalize(row, source, system='', collection='', observed='', locator='', strength=2, evidence_kind='state'):
    row = flattened(row)
    system, category = schema(collection, row.get('system', row.get('origin_system', system)))
    category = row.get('record_type', row.get('data_category', category))
    rid = row.get('resource_id', '')
    if not rid or not category or not system:
        return None
    time = row.get('observed_at') or row.get('recorded_at') or observed or source.captured_at
    state = str(row.get('result') or row.get('state') or '').upper()
    state = {'NOT_FOUND':'ABSENT','FOUND':'PRESENT','IDENTIFIABLE':'PII','HIT':'PRESENT'}.get(state, state)
    if state not in {'ABSENT','PRESENT','PII','REDACTED','ANONYMIZED','ACTIVE','DISABLED','BLOCKED'}:
        if category == 'DATA_FLOW':
            state = 'ACTIVE' if norm(row.get('enabled')) in {'true','1'} else 'DISABLED'
        elif category == 'BACKUP_ARCHIVE':
            state = 'ACTIVE' if norm(row.get('restore_allowed')) in {'true','1'} else 'BLOCKED'
        elif category in {'SUPPORT_MESSAGE','ACCOUNT_TOMBSTONE','EMAIL_DELIVERY_LOG'}:
            state = 'PII' if has_pii(row) else 'REDACTED'
        elif category in {'ANALYTICS_PROFILE','PRODUCT_TELEMETRY'}:
            state = 'PII' if has_pii(row, True) else 'ANONYMIZED'
        elif row.get('status_code') == 404 or row.get('http_status') in (404,'404') or row.get('rows') in (0,'0'):
            state = 'ABSENT'
        elif isinstance(row.get('hits'), dict) and row['hits'].get('total') == 0:
            state = 'ABSENT'
        else:
            state = 'PRESENT'
    return EvidenceFact(
        source.file_id, system, rid, category, state, time,
        source.captured_at, identifiers(row), row, locator, strength,
        evidence_kind=evidence_kind
    )


def parse_snapshot_scope(source, captured_at, system_id, resource_type, resource_ids: set[str]) -> SnapshotScope:
    """Create snapshot scope metadata from parsed resource IDs."""
    return SnapshotScope(
        evidence_id=source.file_id,
        captured_at=captured_at,
        system_id=system_id,
        resource_type=resource_type,
        observed_resource_ids=frozenset(resource_ids)
    )


def extract_resource_ids_from_row(row) -> set[str]:
    """Extract all resource IDs from a row's scalar values."""
    found = set()
    for s in scalar_values(row):
        for pattern_name, pattern in RESOURCE_PATTERNS.items():
            found.update(pattern.findall(s))
    return found
