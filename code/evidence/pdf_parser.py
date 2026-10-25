"""Local PDF text extraction for supported business-record semantics."""
import re
import subprocess
from evidence.normalize import normalize,identifiers


def parse(path,source):
    text=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,check=True,timeout=20).stdout
    facts=[]
    # References are read from the document body, never inferred from its filename.
    for rid in sorted(set(re.findall(r'\b(?:support|audit_record|export)_\d+\b',text))):
        if rid.startswith('support_') and re.search(r'attachment|uploader customer',text,re.I):
            system,category='support_platform','SUPPORT_ATTACHMENT'
        elif rid.startswith('audit_record_') and re.search(r'retain until|journal entry',text,re.I):
            system,category='security_service','SECURITY_AUDIT_LOG'
        elif rid.startswith('export_'):
            system,category='export_service','USER_EXPORT'
        else:continue
        row=dict(resource_id=rid,system=system,record_type=category,state='PRESENT',document_text=text)
        fact=normalize(row,source,observed=source.captured_at,locator='pdf:text')
        if fact:facts.append(fact)
    # A statement code can be linked to a resource through a time-valid catalog entry.
    # Preserve the document as a reference-only fact for that join, without inventing IDs.
    for reference in sorted(set(re.findall(r'\bNST-\d{4}-\d{4}-\d+\b',text))):
        row=dict(resource_id=reference,system='export_service',record_type='USER_EXPORT',state='PRESENT',document_text=text,external_reference=True)
        facts.append(normalize(row,source,observed=source.captured_at,locator='pdf:statement'))
    return facts,[]
