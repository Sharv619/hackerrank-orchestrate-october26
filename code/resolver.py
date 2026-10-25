"""Latest direct observations; conservative equal-time conflict handling."""
from collections import defaultdict
from models import ResourceState, timestamp

UNSAFE = {'PRESENT', 'PII', 'ACTIVE'}


def resolve(facts, cutoff):
    groups = defaultdict(list)
    for fact in facts:
        if fact.available(cutoff):
            groups[(fact.system_id, fact.resource_id)].append(fact)
    states = []
    for key, items in sorted(groups.items()):
        newest = max(timestamp(f.observed_at) for f in items)
        current = [f for f in items if timestamp(f.observed_at) == newest]
        # Same-snapshot replica drift remains a violation if any copy survives.
        current.sort(key=lambda f: (f.state in UNSAFE, f.strength, f.evidence_id, f.locator), reverse=True)
        chosen = current[0]
        conflicts = [f for f in current[1:] if f.state != chosen.state]
        states.append(ResourceState(chosen, conflicts))
    return states
