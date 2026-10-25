# Problem analysis

Design status: written before production implementation. The current task is plan review; implementation milestones are tracked in `04_wbs.md`.

## Contract and inspected inputs

Only participant-facing `dataset/` supplies prediction inputs. The inspected checkout contains 518 evaluation requests, 32 public sample requests, 850 current identity rows, 306 identity-history rows, 4,011 activity rows, 15 deletion rules and 94 manifest entries. Evidence comprises 28 JSON files, 26 logs, 24 SQL snapshots, four PDFs, eleven PNG images and one text document. Counts are discovery observations, not constants used for resource discovery or prediction.

Read requests from `deletion_requests.csv`; use `sample_deletion_requests.csv` and `sample_output.csv` only in the development evaluator. Never import sample answers into the decision pipeline. Resolve file paths using `evidence_files.csv`, inspect contents, and load policy dynamically from `deletion_rules.csv`.

The submitted root `output.csv` has exactly `case_id,deletion_status,steps_json`, one row per evaluation case (518 for the supplied dataset), lexically sorted by case ID. Each step has exactly `step_no`, `phase`, `system_id`, `resource_id`, `operation`, `state`, `evidence_id`. Serialize JSON deterministically and number steps after sorting. Internal provenance, coverage and explanations belong in separate artifacts.

## Authorization and status

- `NOT_APPLICABLE`: the request does not authorize deletion or deletion verification; output `[]`. Access, correction, export, marketing opt-out and account-support requests alone do not authorize deletion. Mixed requests require clause-level interpretation.
- `INCOMPLETE`: grounded evidence establishes a remaining record, prohibited identifiers, active data flow or unsafe restore path. Output findings, all required remediation and verification of the entire relevant final state, including already compliant retained records.
- `COMPLETE`: every relevant copy meets policy, mandatory retained records are available, and no relevant active flow or restore path can recreate prohibited data. Output evidence-backed verification only.

Ambiguity or a parser failure is not evidence of a violation. Internally represent `NEEDS_REVIEW`/unresolved decisions separately; this is never a fourth submission label. Do not fabricate a finding or mark `COMPLETE` from missing evidence. An unresolved material case blocks publication of the final submission until resolved. A diagnostic partial run may still produce audit manifests, coverage and evaluation results without publishing final `output.csv`.

## Identity and evidence

Use exact Unicode-normalized identifiers: stable user ID, current/historical emails, phones and hashes. Names can corroborate but must not establish identity alone. Do not fuzzy-match a similar email to the subject. Keep identity edges and their provenance/time bounds; a future identity change cannot silently create a historical link. Derive normalized-email SHA-256 values only as a documented transformation and retain the source edge.

Evidence may identify a resource without retaining subject identifiers. Follow earlier grounded resource links so anonymized analytics records, absent accounts and redacted support records can still be retrieved. Resource IDs and systems are separate keys; filenames, numeric suffixes and manifest ordering never establish subject membership.

Normalize observations without discarding raw source locators, replica/table identity, timestamps or identity-link provenance. Activities are claims unless their content establishes an actual observation. A successful delete/anonymize operation alone cannot prove absence/anonymization. A correlated readback with zero rows or HTTP 404 can prove absence within its declared scope. A missing row only proves absence in a documented complete snapshot for the queried resource; absence from a partial export does not.

## Time and conflicts

Every accepted observation and identity link must be available at or before `audit_at`. Track observation time, source capture time and update time separately. Apply the manifest availability cutoff as well as the observation cutoff. An old timestamp inside a later-captured file cannot bypass the cutoff. Record rejected future sources in `CaseAudit` with the reason.

Prefer the latest applicable direct observation within the same resource/copy scope. Keep primary and replica states separate: absence from the primary cannot erase a surviving replica. Treat equal-time contradictory direct observations as a conflict; do not break semantic ties by filename. Record the conflict and require resolution when material. Preserve explicit absence scope and any uncertainty from incomplete parsing.

## Policy and risks

Apply each category's supplied condition, not just its action name. Preserve security records within retention and legal-hold records while the hold applies. Expired or unknown retention conditions must not be silently converted into an unsupported deletion rule. Support conversation context may require redaction, while subject-owned attachments require deletion. Analytics and telemetry must be irreversibly unlinked where attributable.

An account tombstone may retain its stable internal subject reference, while name, email, phone, email hash and prohibited direct identifiers must be absent. The stable reference alone is not exposed PII under this rule. An anonymized analytics record has stricter unlinkability requirements than a tombstone.

Processes are first-class resources. Active syncs, imports, connectors or indexers may recreate data even when account deletion succeeded. Report/disable/verify these flows. Retain backups when required, but report and block unsafe restore access; do not substitute backup deletion for restore blocking.

## Ordering and citations

Use the exact table order in `problem_statement.md`:

| Phase | Operations in order |
|---|---|
| FINDING | REPORT_REMAINING_RECORD, REPORT_EXPOSED_PII, REPORT_ACTIVE_DATA_FLOW, REPORT_RESTORE_RISK |
| REMEDIATION | DISABLE_DATA_FLOW, BLOCK_RESTORE, DELETE_RECORD, REDACT_RECORD, ANONYMIZE_RECORD |
| VERIFICATION | VERIFY_RECORD_ABSENT, VERIFY_RECORD_PRESENT, VERIFY_RECORD_REDACTED, VERIFY_RECORD_ANONYMIZED, VERIFY_DATA_FLOW_DISABLED, VERIFY_RESTORE_BLOCKED |

Then sort by system ID and resource ID. The mandatory output ordering takes precedence over alternative execution orders. Internally describe dependencies and flag any tension between operational prerequisites and this serialization contract rather than silently changing array order.

Findings and `COMPLETE` verification cite participant-visible file/activity/audit IDs that support the assertion at the cutoff. Future remediation and all `INCOMPLETE` verification use empty evidence IDs. Validate semantic citation support, not only ID existence.

## Likely hidden-test failures

1. Negated or mixed multilingual intent mistaken for authorization.
2. Historical identifiers missed, future aliases leaked, or decoys joined fuzzily.
3. Clean records lost after identifiers are removed; unrelated resource IDs conflated.
4. Workflow success accepted as state; partial-snapshot absence overclaimed.
5. Later capture used to rewrite history; replica drift collapsed away.
6. Stable tombstone reference treated as forbidden; analytics reference wrongly allowed.
7. Retained records deleted, retention conditions ignored, or backup restore risk missed.
8. Verification covers only violations and omits required retained/compliant resources.
9. Parser/OCR failure silently interpreted as a clean corpus.
10. Stale checkpoint/cache reuse after evidence, rules, configuration or code changes.
11. Correct actions serialized in the wrong order or with incorrect citations.
12. Explanatory/model prose allowed to change the scored decision.
