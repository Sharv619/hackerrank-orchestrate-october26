"""Typed boundaries for deterministic auditing."""
from dataclasses import dataclass, field
from datetime import datetime
import unicodedata
import re


def norm(value):
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def phone(value):
    return re.sub(r'[^0-9]', '', str(value or ''))


@dataclass(frozen=True)
class DeletionCase:
    case_id: str
    email: str
    requested_at: str
    reported_status: str
    reported_at: str
    audit_at: str
    request_text: str


@dataclass
class IdentitySet:
    user_id: str
    emails: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    names: set = field(default_factory=set)
    email_hashes: set = field(default_factory=set)

    @property
    def keys(self):
        return {self.user_id} | self.emails | self.phones | self.email_hashes


@dataclass(frozen=True)
class EvidenceSource:
    file_id: str
    file_path: str
    origin: str
    captured_at: str


@dataclass
class SnapshotScope:
    """Authoritative snapshot metadata for negative evidence."""
    evidence_id: str
    captured_at: str
    system_id: str
    resource_type: str  # e.g., 'USER_PROFILE'
    observed_resource_ids: frozenset  # resource_ids present in this snapshot

    def is_authoritative_for(self, system_id: str, resource_type: str) -> bool:
        return self.system_id == system_id and self.resource_type == resource_type


@dataclass
class EvidenceFact:
    evidence_id: str
    system_id: str
    resource_id: str
    category: str
    state: str
    observed_at: str
    captured_at: str
    identifiers: set
    fields: dict
    locator: str = ''
    strength: int = 2
    # Provenance: what kind of evidence this is
    evidence_kind: str = 'state'  # 'state' | 'linkage' | 'negative'

    def available(self, cutoff):
        return timestamp(self.observed_at) <= timestamp(cutoff) and timestamp(self.captured_at) <= timestamp(cutoff)


@dataclass
class ResourceState:
    fact: EvidenceFact
    conflicts: list = field(default_factory=list)


@dataclass(frozen=True)
class DeletionRule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


@dataclass
class PolicyDecision:
    fact: EvidenceFact
    rule_id: str
    action: str
    expected: str
    compliant: bool


@dataclass
class Violation:
    decision: PolicyDecision
    finding: str
    remediation: str


@dataclass
class OutputStep:
    step_no: int
    phase: str
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str


@dataclass
class ResourceLink:
    """Explicit subject→resource edge with provenance."""
    subject_user_id: str
    system_id: str
    resource_id: str
    category: str
    provenance: str  # 'user_id' | 'email' | 'phone' | 'hash' | 'LINK_RESOURCE_IDENTITY' | 'reference' | 'event_correlation'
    evidence_id: str
    established_at: str  # when this link was established/known
