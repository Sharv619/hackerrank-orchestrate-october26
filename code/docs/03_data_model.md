# Core data model

The implementation uses dataclasses and plain dictionaries at parser boundaries.

| Model | Fields and purpose |
|---|---|
| DeletionCase | CSV request fields; `audit_at` is the exclusive source of the decision cutoff |
| IdentitySet | user ID, emails, phones, names and email hashes recovered from current and historical rows |
| EvidenceSource | file ID, path, capture time and format |
| EvidenceFact | source ID, system/resource, category, state, observation/capture times, identifiers, original normalized fields and scope |
| ResourceState | selected current facts for a resource plus conflicts |
| DeletionRule | rule ID, category, condition, required action |
| PolicyDecision | resource, applicable rule, expected state and observed compliance |
| Violation | resource, finding operation, remediation and supporting evidence |
| OutputStep | exactly the seven required submission fields |

JSON collections and SQL tables map to category-specific records. Logs correlate start/readback events by trace ID. TXT record rows map directly. CSV activity supports identity/resource links but operation success alone never establishes state. Media adapters will be added only for demonstrated missing evidence.

Keep source availability and observation time separately. Identity matches are exact; names alone are insufficient. Internal unresolved cases and parser gaps are diagnostics, never invented evidence.
