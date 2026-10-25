"""Read explicit console records with local OCR; ownership comes from exact catalog links.

Screen text is state evidence only. It never creates subject ownership from a
search box, another table row, activity history, or OCR-corrected identifiers.
"""
import io
import os
import re
import subprocess
from PIL import Image
from evidence.normalize import normalize


def extract_text(path, page_mode=3):
    with Image.open(path) as image:
        image = image.convert('RGB')
        image = image.resize((image.width * 2, image.height * 2))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
    result = subprocess.run(
        ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', str(page_mode)],
        input=buffer.getvalue(), capture_output=True, check=True, timeout=90,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    return result.stdout.decode('utf-8')


def parse_text(text, source):
    facts = {}

    def add(resource, system, category, state, reference=False):
        row = dict(resource_id=resource, system=system, record_type=category, state=state)
        if reference:
            row['external_reference'] = True
        fact = normalize(row, source, observed=source.captured_at, locator='image:console', strength=2)
        # A console can contain unrelated users, search input and activity history.
        fact.identifiers = set()
        facts[(system, resource)] = fact

    # Explicit result rows / selected raw document, never global string co-occurrence.
    if 'Search Console' in text and 'Raw document' in text:
        for match in re.finditer(r'Raw document\s*[·—-]\s*(search_\d+)\b', text):
            add(match[1], 'search_service', 'SEARCH_INDEX_ENTRY', 'PRESENT')
    if 'BridgeOps' in text and 'Topology' in text:
        for line in text.splitlines():
            match = re.search(r'\b(data_flow_\d+)\b.*\bContinuous\b', line)
            if match:
                add(match[1], 'integration_service', 'DATA_FLOW', 'ACTIVE')
    if 'Pulse Analytics' in text and 'Event timeline' in text:
        for line in text.splitlines():
            match = re.search(r'\b(analytics_\d+)\b', line)
            if match and re.search(r'\buser_\d+\b|[\w.+-]+@[\w.-]+', line):
                add(match[1], 'analytics_platform', 'ANALYTICS_PROFILE', 'PII')
    if 'Customer Download Center' in text and 'All exports' in text:
        for line in text.splitlines():
            match = re.search(r'(?<![\w])(export_\d+)\b.*\bReady\b', line)
            if match:
                add(match[1], 'export_service', 'USER_EXPORT', 'PRESENT')
    if 'Helpline Console' in text and 'Conversation' in text and 'Email' in text:
        resources = set(re.findall(r'\bsupport_\d+\b', text))
        if len(resources) == 1 and re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', text):
            add(next(iter(resources)), 'support_platform', 'SUPPORT_MESSAGE', 'PII')
    if 'Vault Recovery Manager' in text and 'Archives' in text:
        for line in text.splitlines():
            match = re.search(r'\b(backup_\d+)\b.*\bArchive\b', line)
            if match:
                add(match[1], 'backup_service', 'BACKUP_ARCHIVE', 'ACTIVE')
    if 'Nimbus Object Storage' in text and ('support-attachments' in text or re.search(r'Uploader\s+support-service', text)):
        for line in text.splitlines():
            # Object names are references, not resource IDs. Only an explicit,
            # time-valid catalog edge may turn these into a subject-owned object.
            match = re.search(r'\b([\w.-]+\.pdf)\b.*\b\d+(?:\.\d+)?\s*(?:KB|MB)\b', line)
            if match:
                add(match[1], 'object_storage', 'SUPPORT_ATTACHMENT', 'PRESENT', True)
    if 'Audience Operations' in text and 'Live profile fields updated' in text:
        resources = set(re.findall(r'\bmarketing_\d+\b', text))
        if len(resources) == 1:
            add(next(iter(resources)), 'marketing_platform', 'MARKETING_PROFILE', 'PRESENT')
    if 'Customer Operations' in text and 'Customer details' in text:
        resources = set(re.findall(r'\baccount_\d+\b', text))
        if len(resources) == 1:
            add(next(iter(resources)), 'account_service', 'USER_PROFILE', 'PRESENT')
    if 'Sentinel' in text and 'Raw event' in text:
        for match in re.finditer(r'\b(audit_record_\d+)\s*[·—-]\s*Raw event', text):
            add(match[1], 'security_service', 'SECURITY_AUDIT_LOG', 'PRESENT')
    return list(facts.values()), []


def parse(path, source):
    facts, scopes = parse_text(extract_text(path), source)
    if not facts:
        # Uniform-block segmentation preserves table rows when automatic page
        # segmentation reads columns separately. Identifiers remain unmodified.
        facts, scopes = parse_text(extract_text(path, page_mode=6), source)
    return facts, scopes
