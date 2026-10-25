"""Exact identity lookup with time-filtered historical aliases."""
from collections import defaultdict
import hashlib
from models import IdentitySet, norm, phone, timestamp


class IdentityResolver:
    def __init__(self, identities, history):
        self.current = {r['user_id']: r for r in identities}
        self.history = defaultdict(list)
        self.email_users = defaultdict(set)
        for row in identities:
            self.email_users[norm(row['email'])].add(row['user_id'])
        for row in history:
            self.history[row['user_id']].append(row)
            if row['field_name'] == 'email':
                for key in ('old_value', 'new_value'):
                    self.email_users[norm(row[key])].add(row['user_id'])

    def for_user(self, uid, cutoff):
        row = self.current[uid]
        values = {k: {norm(row[k])} for k in ('email', 'phone', 'name', 'email_hash')}
        # Undo future changes before expanding aliases known by the cutoff.
        for event in sorted(self.history[uid], key=lambda r:r['event_time'], reverse=True):
            field = event['field_name']
            if timestamp(event['event_time']) > timestamp(cutoff):
                values.setdefault(field, set()).discard(norm(event['new_value']))
                values[field].add(norm(event['old_value']))
        for event in self.history[uid]:
            if timestamp(event['event_time']) <= timestamp(cutoff):
                values.setdefault(event['field_name'], set()).update([norm(event['old_value']), norm(event['new_value'])])
        emails = values['email'] - {''}
        hashes = values['email_hash'] - {''}
        hashes.update(hashlib.sha256(e.encode()).hexdigest() for e in emails)
        return IdentitySet(uid, emails, {phone(p) for p in values['phone']} - {''}, values['name'] - {''}, hashes)

    def resolve(self, email, cutoff):
        matches = [self.for_user(uid, cutoff) for uid in self.email_users[norm(email)]]
        matches = [m for m in matches if norm(email) in m.emails]
        if len(matches) != 1:
            raise ValueError(f'Identity lookup is not unique: {len(matches)} matches')
        return matches[0]
