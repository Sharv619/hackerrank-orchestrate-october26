"""Parse common structured/plain log dialects and correlate trace start/readback."""
import json
import re
from evidence.normalize import normalize

PAIRS=re.compile(r'(\w+)=(?:"([^"]*)"|([^\s|]+))')

def decode(line):
    time=line[:20]
    if line[21:22]=='{':return time,json.loads(line[21:])
    plain=line.replace('\\"','"')
    row={k:a if a else b for k,a,b in PAIRS.findall(plain)}
    if 'function' in row:row['service']=row['function'];row['trace_id']=row.get('requestId','')
    m=re.match(r'\S+ \[\w+\] \[([^]]+)\] \[([^]]+)\] (\w+):',plain)
    if m:row.update(service=m[1],trace_id=m[2],event=m[3])
    if ' | ' in plain:
        parts=plain.split(' | ')
        if len(parts)>=6:row.update(service=parts[2],trace_id=parts[3],event=parts[4])
    m=re.match(r'\S+ <\d+>1 \S+ (\S+) (\S+) - - ',plain)
    if m:row.update(service=m[1],trace_id=m[2])
    return time,row


def parse(path,source):
    facts=[];traces={}
    for lineno,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip():continue
        time,row=decode(line);trace=row.get('trace_id','');event=row.get('event','')
        if event.endswith('_started') and trace:
            # Record that this trace has a lookup-start with its lookup_key
            has_lookup_key = 'lookup_key' in row
            has_resource_id = 'resource_id' in row
            traces[trace] = {**traces.get(trace, {}), **row, '_has_lookup_started': True, '_start_had_lookup_key': has_lookup_key, '_start_had_resource_id': has_resource_id}
            continue
        merged={**traces.get(trace,{}),**row} if trace else row
        rid=merged.get('resource_id')
        if not rid:continue
        service=merged.get('system',merged.get('service',''))
        if service=='support_replica':service='support_platform'
        category='';state=''
        if event=='record_lookup':category=merged.get('record_type','');state=merged.get('result','')
        elif event in {'profile_lookup_completed'}:
            category='USER_PROFILE'
            state='ABSENT' if merged.get('rows')=='0' or merged.get('http_status')=='404' else 'PRESENT'
        elif event=='index_query_completed':category='SEARCH_INDEX_ENTRY';state='PRESENT' if merged.get('result')=='hit' else 'ABSENT'
        elif event=='attachment_pii_scan':category='SUPPORT_ATTACHMENT';state='PRESENT'
        elif event in {'contact_query_completed','contact_lookup_completed'}:
            category='SECONDARY_IDENTIFIER'
            state='PRESENT' if merged.get('rows')!='0' else 'ABSENT'
        elif event=='attachment_pii_scan':category='SUPPORT_ATTACHMENT';state='PRESENT'
        elif event=='message_pii_scan':category='SUPPORT_MESSAGE';state='PII'
        elif event=='message_read':category='SUPPORT_MESSAGE';state='REDACTED' if merged.get('message_text')=='[REDACTED]' else 'PII'
        elif event in {'support_ticket_read_completed'}:category='SUPPORT_MESSAGE'
        elif event=='analytics_identity_scan':category='ANALYTICS_PROFILE';state='PII'
        elif event in {'analytics_profile_read','analytics_profile_read_completed'}:
            category='ANALYTICS_PROFILE'
            if merged.get('direct_identifiers')=='0':state='ANONYMIZED'
        elif event=='audit_record_read_completed':category='SECURITY_AUDIT_LOG';state='PRESENT' if merged.get('rows')!='0' else 'ABSENT'
        elif event in {'connector_heartbeat','connector_config_loaded','connector_config_read_completed'}:category='DATA_FLOW'
        elif event=='restore_candidate_evaluated':category='BACKUP_ARCHIVE';state='ACTIVE' if merged.get('eligible')=='true' and merged.get('deletion_block')=='false' else 'BLOCKED'
        elif event=='restore_authorization_completed':category='BACKUP_ARCHIVE';state='BLOCKED' if merged.get('decision')=='deny' else 'ACTIVE'
        elif event=='restore_policy_read_completed':category='BACKUP_ARCHIVE'
        elif event in {'export_download_check_completed','export_metadata_read_completed'}:category='USER_EXPORT';state='PRESENT' if merged.get('available')=='true' else 'ABSENT'
        else:continue
        merged={**merged,'system':service,'record_type':category,'state':state,'observed_at':time}
        # A start-event lookup key is provenance, not a retained identifier field.
        fact=normalize(merged,source,service,observed=time,locator=f'line:{lineno}',strength=3)
        if fact:
            # Trace-aware negative lookup handling
            # Preserve identifiers ONLY for NEGATIVE lookups that have a correlated start event
            # WITH a lookup_key AND WITHOUT resource_id (identity-based lookup).
            # Clear for:
            # 1. Uncorrelated negative probes (no matching lookup-start event)
            # 2. Targeted probes (start event has resource_id - verifying known resource, not identity lookup)
            if event in {'profile_lookup_completed', 'contact_lookup_completed', 'contact_query_completed'}:
                merged_state = merged.get('state', '').upper()
                if merged_state in {'ABSENT', 'NOT_FOUND'} or merged.get('rows') == '0' or merged.get('http_status') == '404':
                    lookup_key = merged.get('lookup_key')
                    if lookup_key:
                        fact.fields['lookup_key'] = lookup_key
                    # Check if this trace has a matching lookup-start event with a lookup_key
                    has_correlated_start = merged.get('_has_lookup_started', False)
                    start_had_lookup_key = merged.get('_start_had_lookup_key', False)
                    start_had_resource_id = merged.get('_start_had_resource_id', False)
                    # Identity lookup: correlated start WITH lookup_key AND WITHOUT resource_id
                    # Targeted probe: correlated start WITH resource_id (verifying known resource)
                    # Uncorrelated probe: no start event at all
                    if not has_correlated_start or not start_had_lookup_key or start_had_resource_id:
                        # Uncorrelated negative probe OR targeted probe: don't add lookup_key to identifiers
                        fact.identifiers = set()
                    # If has_correlated_start AND start_had_lookup_key AND NOT start_had_resource_id: preserve lookup_key in identifiers for identity matching
            facts.append(fact)
    return facts,[]