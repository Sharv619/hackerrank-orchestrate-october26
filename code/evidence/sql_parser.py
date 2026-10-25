"""Read each supplied SQL snapshot in an isolated in-memory SQLite database."""
import json
import sqlite3
from evidence.normalize import normalize, schema, parse_snapshot_scope
from models import SnapshotScope


def parse(path, source):
    facts = []
    scopes = []
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    forbidden = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
    conn.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in forbidden else sqlite3.SQLITE_OK)
    try:
        conn.executescript(path.read_text())
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]

        # Parse all tables
        for table in tables:
            if table == 'snapshot_scope':
                continue
            rows = [dict(r) for r in conn.execute('SELECT * FROM "' + table.replace('"', '""') + '"')]
            system, category = schema(table)
            if category == 'USER_PROFILE':
                resource_ids = {r['resource_id'] for r in rows if r.get('resource_id')}
                # Legacy scope tuple
                scopes.append((source, system, source.captured_at, resource_ids, table))
                # Create SnapshotScope for negative evidence
                scope = SnapshotScope(
                    evidence_id=source.file_id,
                    captured_at=source.captured_at,
                    system_id=system,
                    resource_type=category,
                    observed_resource_ids=frozenset(resource_ids)
                )
                scopes.append(scope)
            for row in rows:
                if 'record_json' in row:
                    record = json.loads(row['record_json'])
                    system = row['origin_system']
                    collection = row['collection_name']
                else:
                    record = row
                    collection = table
                fact = normalize(record, source, system, collection, source.captured_at, table)
                if fact:
                    facts.append(fact)

        # Parse snapshot_scope table if present (for explicit scope metadata)
        if 'snapshot_scope' in tables:
            scope_rows = [dict(r) for r in conn.execute('SELECT * FROM "snapshot_scope"')]
            by_system_type = {}
            for row in scope_rows:
                system_id = row.get('system_id', row.get('system', ''))
                resource_type = row.get('resource_type', row.get('category', ''))
                resource_id = row.get('resource_id', '')
                if system_id and resource_type and resource_id:
                    key = (system_id, resource_type)
                    if key not in by_system_type:
                        by_system_type[key] = set()
                    by_system_type[key].add(resource_id)

            for (system_id, resource_type), resource_ids in by_system_type.items():
                scope = SnapshotScope(
                    evidence_id=source.file_id,
                    captured_at=source.captured_at,
                    system_id=system_id,
                    resource_type=resource_type,
                    observed_resource_ids=frozenset(resource_ids)
                )
                scopes.append(scope)

        # Generic replicas expose profiles as JSON rows; retain their declared table scope.
        if any('record_json' in [r[1] for r in conn.execute('PRAGMA table_info("' + t + '")')] for t in tables):
            for table in tables:
                if table.startswith('customer_data_'):
                    ids = {f.resource_id for f in facts if f.locator == table and f.category == 'USER_PROFILE'}
                    scopes.append((source, 'account_service', source.captured_at, ids, table))
    finally:
        conn.close()
    return facts, scopes
