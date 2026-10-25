"""Evaluate the supplied policy table; no case-dependent rules."""
from models import DeletionRule,PolicyDecision

EXPECTED={'DELETE':'ABSENT','REDACT':'REDACTED','ANONYMIZE':'ANONYMIZED','RETAIN':'PRESENT','DISABLE':'DISABLED','BLOCK':'BLOCKED'}


class Policy:
    def __init__(self,rows):self.rules={r['data_category']:DeletionRule(**r) for r in rows}

    def evaluate(self,state,cutoff):
        fact=state.fact
        if fact.category=='DATA_FLOW':return PolicyDecision(fact,'challenge_active_flow','DISABLE','DISABLED',fact.state=='DISABLED')
        rule=self.rules.get(fact.category)
        if rule is None:raise ValueError(f'No supplied policy for category {fact.category}')
        action=rule.required_action
        if fact.category=='BACKUP_ARCHIVE':action='BLOCK'
        expected=EXPECTED[action]
        # Supplied structured collections establish shared support context and subject-owned attachments.
        # Retention dates and hold flags, when explicit, must satisfy the conditional rule.
        if action=='RETAIN':
            until=fact.fields.get('retention_until')
            if until and until<cutoff:raise ValueError(f'Expired retention needs a supplied fallback rule: {fact.resource_id}')
            if fact.fields.get('legal_hold_active') is False:raise ValueError('Inactive legal hold has no fallback rule')
        return PolicyDecision(fact,rule.rule_id,action,expected,fact.state==expected)
