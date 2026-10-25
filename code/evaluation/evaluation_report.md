# Final evaluation and submission-blocker review

## Measured public evaluation

The before column is the user-supplied starting baseline. The after column is the actual final public evaluator run across all 32 requests. No hidden evaluation labels or organizer files were used. Public answers are read only by the evaluator, after predictions.

| Metric | Before | After |
|---|---:|---:|
| status_accuracy | 90.62% | 90.62% |
| exact_case_accuracy | 34.38% | 28.12% |
| step_accuracy | 63.21% | 57.95% |
| field_accuracy | 74.24% | 69.60% |
| sequence_accuracy | 34.38% | 28.12% |
| mismatched cases | 21/32 | 23/32 |

Step/field scores use positional comparisons with max(predicted steps, expected steps) as the per-case denominator. Field accuracy scores all seven fields. Sequence accuracy compares complete ordered step arrays. Unresolved requests remain in every metric denominator: case_01, case_02, case_04. `UNRESOLVED` appears only in evaluation diagnostics, never in submission CSVs. The evaluator writes metrics and diagnostics, not an invalid sample prediction file.

The score decrease is accepted. Capture-time gating now prevents later-captured facts from establishing earlier ownership/verification obligations. For example, case_09/account_3960 in evidence_06 was observed on September 16 at 08:57:34Z, before the 09:00Z audit, but was not captured until September 18 at 11:55:24Z; it cannot establish a link at that earlier audit. Screenshot evidence also establishes `object_19` via `activity_4007` for its subject, including the later public request `case_07`; the public answer does not list that object. Neither behavior is suppressed to match public answers. Remaining mismatches are not all asserted to be underivable: this task did not establish that exhaustive claim. Missing resources are not supplied from sample labels.

## Root cause and eight-case trace

All eight requests explicitly authorize deletion. Temporal identity resolution succeeded. Each subject had an explicit catalog link at or before audit_at, but PNG files had no adapter even with media enabled. Their state observations never entered retrieval. The empty decision list hit the fallback `INCOMPLETE, []`, bypassing the planner. This is a missing evidence-adapter defect combined with an invalid fallback, not eight case-specific errors. For the connector and backup, the omitted observations were specifically data-flow and restore risks.

The new adapter extracts explicit console rows with local Tesseract OCR. It does not correct resource IDs or infer ownership from nearby text. Screenshot facts have no subject identifiers: exact catalog ownership and exact resource/state joins determine applicability. The object-storage record uses the literal filename in its catalog link; no filename-number-to-resource-number inference is used. Existing identity-bearing document references retain their exact catalog joins. No image facts, IDs or case answers are hardcoded.

| Case | Resolved subject | audit_at | Resource | Ownership + finding evidence | Old → new steps | Grounded reason |
|---|---|---|---|---|---:|---|
| case_35 | user_13 | 2026-09-02T08:00:00Z | search_428 | activity_4001 + evidence_09 | 0 → 3 | Search result still present |
| case_39 | user_14 | 2026-08-08T10:00:00Z | data_flow_1121 | activity_4002 + evidence_14 | 0 → 3 | Continuous connector active |
| case_50 | user_20 | 2026-07-14T12:00:00Z | analytics_7438 | activity_4003 + evidence_19 | 0 → 3 | Analytics profile still identifiable |
| case_52 | user_18 | 2026-06-19T14:00:00Z | export_1260 | activity_4004 + evidence_23 | 0 → 3 | Export ready for download |
| case_53 | user_22 | 2026-05-25T09:00:00Z | support_1034 | activity_4005 + evidence_28 | 0 → 3 | Support conversation exposes identifiers |
| case_55 | user_16 | 2026-04-30T11:00:00Z | backup_9287 | activity_4006 + evidence_32 | 0 → 3 | Subject archive remains available for restore |
| case_61 | user_07 | 2026-02-14T10:00:00Z | object_19 | activity_4007 + evidence_46 | 0 → 3 | Catalog-linked support attachment still stored |
| case_63 | user_09 | 2026-09-17T09:20:00Z | marketing_001 | activity_4008 + evidence_60 | 0 → 3 | Catalog-linked marketing profile remains live |

All eight statuses remain `INCOMPLETE`. Each now has a finding citing the screenshot, the policy-required remediation, and the matching future verification. Remediation and future verification cite no evidence. The historical phone aliases for user_20 were both resolved; no fuzzy matching was needed. Later observations remained excluded.

If a request truly has no grounded state observations, production raises `InsufficientEvidenceError`; it never guesses COMPLETE, fabricates findings, or writes an empty INCOMPLETE row. The three unresolved public samples are handled as explicit evaluation failures only.

## Output invariants and production fixes

- NOT_APPLICABLE has exactly an empty array. COMPLETE/INCOMPLETE require nonempty steps.
- INCOMPLETE requires findings, remediation and future verification; every finding has its appropriate remedy and every remedy has its corresponding check.
- Findings and COMPLETE proofs cite participant-visible evidence available by audit_at.
- Remediation and INCOMPLETE future verification have empty evidence IDs.
- COMPLETE contains only evidence-backed verification.
- Exact seven-field schema, string types, integer consecutive numbering, valid operation/state pairs, unique steps, canonical operation/phase order, exact sorted case coverage.
- Every policy decision contributes verification, including resources reached through activity or filename mappings.
- Ownership availability uses both observation and capture time; latest audit lookup also requires both.
- Explicit catalog edges in resource collection are subject-scoped.
- Snapshot-derived negative observations stay request-local; retrieval does not mutate corpus facts/indexes.
- Null result/state/timestamp values normalize without crashing valid records; nullable source references are safe.
- Parsing failures stop the run; validation completes before atomically replacing output.csv.

## Working directory and dependencies

Tests resolve imports and dataset paths from __file__. Production defaults were already based on __file__; Pipeline now also accepts a string dataset path. Root commands are documented in README. Pillow is declared; Tesseract 5 with English data and Poppler are explicit external prerequisites, not bundled machine-local binaries. This environment used downloaded Ubuntu OCR packages in /tmp because sudo requires an interactive password; no temporary path is embedded in production code.

## Two original failing tests

### test_7_unrelated_delete_record_cannot_enter_subject_graph

Classification: OUTDATED TEST EXPECTATION.
Failing assertion: `assert has_direct` (the test assumed the event must identify the case subject).
Actual record: activity_3342, account_001, SUCCESS; details: "Deletion worker reported the requested operation as completed. Target resource: account_001."
Expected record: an imagined identity-bearing version of activity_3342. No such user/email detail is present.
Relevant functions: Pipeline._get_event_correlation_links and _has_direct_identity_in_details.
Action: assert that actual identity-free activity produces no link. Production ownership logic changed to satisfy this test: NO.

### test_8_partial_and_success_unrelated_users_rejected

Classification: OUTDATED TEST EXPECTATION.
Failing assertion: `len(grounded) == 1`; actual result was zero.
Actual records: activity_3595/account_010, activity_3598/account_4842 and activity_3599/account_5334. All report generic deletion operations and contain no matching subject identity.
Expected record: an imagined identity-bearing activity_3595/account_010.
Relevant functions: Pipeline._get_event_correlation_links and _has_direct_identity_in_details.
Action: controlled participant-created events verify rejection of identity-free and unrelated SUCCESS/PARTIAL results, plus acceptance of an exact subject identifier. Production ownership logic changed to satisfy this test: NO.

## Participant-created evaluation cases

These are automated fixtures in code/tests/test_submission_contract.py, independent of public canonical answers.

| Custom case | Expected result | Result |
|---|---|---|
| Missing phases, malformed schema, empty finding evidence, planned checks citing evidence, bad numbering/order, future citation (14 variants) | Validator rejects every invalid plan | Pass |
| Decision resource omitted from collection | Matching future verification is still emitted | Pass |
| Future-captured account lookup with an earlier observation | No ownership link before capture | Pass |
| Repeated snapshot absence query | Corpus remains unchanged and later requests inherit no synthetic facts | Pass |
| Screenshot with multiple subjects and disabled/active rows | Only explicit active row state; no image-wide ownership | Pass |
| Object filename mapped by exact subject catalog entry | Correct object joined; unrelated subject and suffix matches rejected | Pass |
| Identity-bearing document with identity-free catalog mapping | Existing exact reference join preserved | Pass |
| Null state/result/time with explicit 404 | ABSENT normalized using evidence timestamp | Pass |
| Catalog edge belongs to a different subject | Resource excluded | Pass |

## Regression and static review

Root pytest: 48 passed. code/ pytest: 48 passed. Both locations initially differed (root: 7 failed/14 passed; code/: 2 failed/19 passed).

Final generation: 518 rows; 355 INCOMPLETE, 153 COMPLETE, 10 NOT_APPLICABLE. Only the 10 NOT_APPLICABLE rows have empty arrays. All statuses are unchanged from the starting full output; 145 rows have corrected step arrays. Standalone validator passes. Runtime LLM calls: zero.

BLOCKER: none remaining in the final 518-row output and packaging checks.
HIGH: fixed omitted media evidence, empty-plan fallback, missing verification, cross-request negative-fact mutation, future-capture linkage and subject scoping.
MEDIUM: OCR remains limited to explicit supported console schemas; unsupported/unreadable evidence is not converted into guessed ownership or completion. Three public samples remain unresolved and count as failures. Hidden accuracy is not measured.
LOW: cosmetic legacy formatting/refactoring intentionally deferred.

Manual/AST review found no literal sample/case/resource IDs in production modules, no absolute workstation paths, no organizer-data access, and no runtime API client. Set iteration affecting emitted plans is sorted; canonical planning remains deterministic. All local production imports are included in the archive. Setup does require the documented OCR/PDF tools.

Output SHA-256: `231dd42a2a300efaf8cc1cf496bac84b7565a0847ff63b38875dac5ebcf57e0b`.

## Contract recheck and archive-layout correction

Re-read problem_statement.md after the initial packaging approval. Its Evaluation and Token Usage sections require evaluation/evaluation_report.md and evaluation/usage_report.md at the ZIP root. The previous archive only contained code/evaluation/ copies, so the earlier packaging approval was incorrect. The corrected packaging script includes byte-identical root copies and verifies both exact paths; source reports remain under code/evaluation/.

All 518 rows pass the plan, citation, numbering and phase checks. Operation ranks were independently extracted from the statement and matched exactly against the planner and every emitted row. Historical identity, claim-versus-proof handling, active flow/restore risks and tombstone treatment were rechecked in the implementation and regression tests. This is structural and implementation verification, not a guarantee of complete discovery or hidden-answer accuracy. Scoring logic, predictions and measured metrics are unchanged by this packaging correction.
