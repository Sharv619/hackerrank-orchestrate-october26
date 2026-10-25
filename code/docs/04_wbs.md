# Work breakdown — core pipeline first

Latest user priority overrides the optional hardening in the earlier architecture draft. No cloud gateway, embeddings, frontend, API or checkpoint system is on the immediate path.

| ID | Task / files | Dependencies | Validation and completion criterion | Status |
|---|---|---|---|---|
| W01 | Discover contract/data; docs | None | All formats inspected, contract understood | Done |
| W02 | Intent; `intent.py` | W01 | Multilingual authorization and negative requests tested | Pending |
| W03 | Identity; `identity.py` | W01 | Exact current/history matching, no similar-email merges | Pending |
| W04 | Structured parsers; `evidence/` | W01 | JSON, SQL, log, text and CSV tests | Pending |
| W05 | Normalize/index; `models.py`, `corpus.py` | W03,W04 | Identifier and resource retrieval; coverage counts | Pending |
| W06 | Temporal state; `resolver.py` | W05 | Future evidence excluded; claims never prove state | Pending |
| W07 | Policy; `policy.py` | W06 | Dynamic rules, retention, tombstone and risks tested | Pending |
| W08 | Remediation/verification/order; `planner.py` | W07 | Exact phase/operation ordering and full verification | Pending |
| W09 | Sample evaluator; `evaluation/main.py`, `metrics.py` | W08 | Print five required metrics for all 32 samples | Pending |
| W10 | Diagnose and fix general logic | W09 | Record mismatches; no answer/case shortcuts | Pending |
| W11 | PDF/image adapters only for demonstrated gaps | W10 | Required media evidence parsed and evaluated | Pending |
| W12 | Custom tests; `tests/` | W02–W11 | Historical identity, tombstone, active flow, time, decoy cases | Pending |
| W13 | Full run; `main.py`, root `output.csv` | W10,W11 | Exactly 518 sorted rows | Pending |
| W14 | Validator; `validate.py` | W08,W13 | Schema, IDs, citations/time, ordering and coverage pass | Pending |
| W15 | Evaluation/usage Markdown | W09,W12–W14 | Actual metrics, failures, costs and runtime recorded | Pending |
| W16 | README/interview/package review | W15 | Runnable archive; no dataset, caches or secrets | Pending |

First milestone: `python3 code/main.py --samples` generates sample output and prints evaluation. Second: `python3 code/main.py` produces and validates root `output.csv`.
