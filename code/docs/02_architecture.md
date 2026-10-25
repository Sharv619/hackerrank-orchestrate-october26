# Architecture

This design adapts the local-first principles supplied by the user about Launchpad. Launchpad source has not been inspected or copied. The implementation is a terminal Python pipeline, not a multi-agent runtime.

## Execution path

```text
Input/configuration fingerprints
  -> load identities, history, manifest, policies and activity
  -> bounded parse/cache -> normalize -> index -> coverage audit
  -> per request: intent route -> time-valid identity resolution
  -> retrieve exact identifier/resource links
  -> filter availability and observation times
  -> reconstruct per-copy resource state -> apply policy
  -> detect violations/risks -> plan all required verification
  -> canonical output steps -> validated result + CaseAudit/checkpoint
  -> whole-run validation -> atomic output.csv publication
  -> extractive explanation and evaluation/usage reports
```

## Explicit boundaries

1. **Observed evidence**: immutable parser facts, raw locators, source metadata, quality and capture times.
2. **Normalized state**: scoped resource/copy state reconstructed from facts and identity links; includes conflicts and unknowns.
3. **Policy requirements**: rules loaded from the CSV with condition evaluations and expected states.
4. **Findings**: supported violations derived from observed state versus policy.
5. **Remediation**: future actions generated from violations and recreation dependencies.
6. **Verification**: expected final state of every relevant resource, including retained records.

Only typed, validated decisions enter output generation. Neither parser prose nor model explanations become CSV steps directly.

## Modules and responsibilities

| Modules | Responsibility |
|---|---|
| `main.py`, `config.py`, `pipeline.py` | CLI, immutable run configuration and orchestration |
| `models.py`, `identity.py`, `intent.py` | Typed contracts, temporal identity graph and authorization routing |
| `evidence/{registry,csv_parser,json_parser,sql_parser,log_parser,text_parser,pdf_parser,image_parser,normalize,cache}.py` | Format adapters, extraction bounds and content-addressed facts |
| `retrieval/{index,search,coverage}.py` | Exact inverted indices, resource expansion and completeness audit |
| `state/{temporal,resolver}.py` | Cutoffs, precedence, copy scopes and conflict detection |
| `policy/{rules,evaluate,planner}.py` | Conditional policy, findings and deterministic action planning |
| `output/{steps,sort,validate}.py` | Exact operation/state schema, canonical ordering and publication gates |
| `audit/{manifest,explain}.py` | Decision provenance and local extractive explanations |
| `runtime/{atomic,checkpoint,usage,model_gateway}.py` | Durable artifacts, resume and accounted optional model access |
| `evaluation/{main,metrics,custom_cases}.py`, `tests/` | Sample comparison, synthetic cases and regression tests |

## Intent routes

The routing enum is `DETERMINISTIC`, `LOCAL_SEMANTIC`, `MODEL_ESCALATION`, `NOT_APPLICABLE`. Keep it distinct from intent (`DELETE`, `NON_DELETE`, `AMBIGUOUS`) and final deletion status. Store route, reason, confidence basis and classifier version in each audit.

Run explicit authorization/negation rules first. Add local semantic processing only if measured unresolved cases justify it. Confidence is a rule/model-specific indication of uncertainty, not an invented generic security score or a calibrated probability without validation. Optional generative escalation may propose structured intent/extraction candidates; validation and policy logic still determine output. Unresolved ambiguity blocks a publishable decision rather than defaulting to deletion.

## Retrieval and coverage integrity

Build indices once over user IDs, emails, phones, hashes, resource IDs and systems. Exact matching is the primary retrieval method. Lexical retrieval may discover candidates, but does not prove identity. Do not add embeddings without evidence of improved recall. Keep time-bounded links so identifiers removed in a later readback do not make a known resource disappear.

`CoverageReport` lists expected files, parsed files, failed files with reasons, skipped files, unsupported formats, normalized record counts and indexed identifier counts. Include per-file accounting and parser versions. A parser reporting success must account for recognized records and unexplained leftovers; returning zero facts cannot silently mean success.

During structured-only development, media is explicitly marked skipped and the evaluator reports coverage and unresolved cases. Missing files with unknown scope are potentially material to every relevant case. A narrow exemption needs positive scope evidence, which is recorded. Final publication requires all material gaps resolved; incomplete coverage cannot support `COMPLETE` simply because retrieval returned no violations.

## State precedence and scope

Filter future source captures and observations before using facts or links. Latest direct evidence wins within the same copy scope; timestamps and directness are both retained. Explicitly distinguish observed state from update timestamps and activity claims. Multiple copies must all satisfy policy. Equal-time contradictory observations remain conflicts. Do not infer cross-replica absence from a primary-only readback.

SQL snapshots run in an isolated in-memory SQLite connection with extension loading disabled, an authorizer rejecting filesystem access/ATTACH and nonessential operations, input-size limits and execution interruption. Preserve table/copy labels. Only complete, declared snapshots can establish scoped absence, and only for previously grounded resource identities.

## Bounded media extraction

Implement and measure structured parsing first. Use sample failures to prioritize local PDF text extraction and OCR. Cache each file once; never process it per case. Initial configurable bounds: 25 MiB per input file, 50 PDF pages, 40 million image pixels, 60 seconds per extraction process, one extraction worker by default. Report limit violations as failures with materiality consequences. Reject oversized dimensions before decoding; do not truncate silently.

Run media extraction in child processes with timeouts and process cleanup; apply memory/CPU limits where supported and document platform limitations. Extract text/positions, then validate resource IDs, timestamps, booleans and identity fields. Low-confidence OCR identifiers require corroboration or an unresolved decision. An OCR model is local ML, not a generative model call, and its engine/version/invocations/latency still belong in telemetry.

## Atomic writes and resume

Use a temporary file in the destination directory, UTF-8 deterministic serialization, flush, `fsync`, `os.replace`, and parent-directory `fsync` where supported. Apply this to parser caches, audit manifests, checkpoints and final CSV. A failed run must not overwrite the previous validated output. Write a completion manifest identifying the exact final CSV hash and run fingerprints so an older output is not mistaken for this run's result.

Cache key: SHA-256 of file contents, parser/normalizer version, relevant configuration, extraction backend/model version. Case checkpoint key: case content, complete participant input fingerprint, decision-engine version/configuration and cached extraction fingerprints. Store result, result hash and audit hash. Validate all before reuse; corruption or any dependency change causes recomputation. Include skipped files and parsing configuration in fingerprints. No process/PID recovery framework is needed.

## Accounted optional models and explanations

Default `GHOST_USE_CLOUD_EXPLAINER=0`. The default explanation is assembled locally from selected facts, citations and rule decisions after output steps are fixed. Explainer failure cannot change status, steps or citations. Keep explanation APIs read-only over a finalized result.

Any optional generative backend must use one `ModelGateway`, recording provider, exact model, purpose, call ID, latency, input/output tokens, cost estimate and pricing basis, success/failure and escalation reason. Include retries and failed calls; unknown usage is unknown, not zero. No unrelated network APIs or automatic provider activation. Do not introduce a provider dependency unless unresolved cases demonstrate a need.

Usage reports distinguish actual calls in the final invocation, inherited cached model work, local OCR work, and development-agent work outside the submitted pipeline. A cached result must retain its original extraction/model provenance. Report zero LLM calls only when verified by the ledger. Full-run reporting includes total/per-request token and cost values and stage timings.

## Acceptance gates

- Structured baseline and its incomplete-media coverage report are reproducible before media implementation.
- Synthetic tests cover intent, identity, temporal/replica behavior, policy and ordering.
- Sample metrics and every mismatch are reported; improve general logic without hardcoding samples.
- Final run resolves every case, validates the exact 518-row contract and has no material coverage failures.
- Cold and warm/resumed executions produce identical output bytes under identical inputs/configuration.
- Package contains runnable code, setup, reports and interview notes, with no dataset, secrets or caches.
