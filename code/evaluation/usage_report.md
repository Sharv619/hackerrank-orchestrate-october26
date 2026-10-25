# Final full-dataset runtime usage

This report covers the normal final 518-case pipeline run that produced root output.csv, with media adapters enabled. Actual recorded elapsed time: 205.131 seconds. Output SHA-256: `231dd42a2a300efaf8cc1cf496bac84b7565a0847ff63b38875dac5ebcf57e0b`.

| Runtime inference metric | Overall total |
|---|---:|
| Requests | 518 |
| LLM provider | none |
| LLM model names | none |
| Model/API calls | 0 |
| Input tokens | 0 |
| Output tokens | 0 |
| Total tokens | 0 |
| Average tokens/request | 0 |
| Estimated runtime model cost | $0 |
| Estimated runtime model cost/request | $0 |

There are no per-provider or per-model LLM subtotals because no LLM is invoked. No embeddings or external inference APIs are used. Local Tesseract 5.3.4 (English recognition data) performs screenshot OCR, and Poppler performs PDF text extraction. Those local tools produce no LLM input/output tokens or API charges; local CPU/installation costs are not estimated as model costs.

Development-time AI assistance is separate: Codex was used to inspect evidence, implement fixes and review tests. Its development token counts and costs are not available here and are not fabricated or included in the zero-runtime totals. Repeated development validation runs and public sample evaluation are also separate from the final 518-request run reported above.
