# Validation record - 17 November 2026

## Automated checks

`python -m pytest -q`: **26 passed**. Tests cover scenario arithmetic, invalid inputs, units, quote evidence, quarantined numeric candidates, source-label requirements, local OCR routing, page provenance, partial runs, evaluation behavior, supported rule patterns, arithmetic mismatches, unsupported layouts, and rules execution without an Ollama server.

Software test success is not model extraction accuracy.

## Real-data development checks

- Source dataset inventory: 101 PDFs, 595 pages, 479 text-readable pages under the 80-character heuristic; 116 need OCR or blank-page review.
- Text-only rule recognition: 133 MSEDCL headers, 42 MSEDCL consumption pages, 24 TANGEDCO headers; 280 text pages unmatched. Recognition is not field completeness or correctness.
- Original grid-page labels: revised rules match 8 of 8 selected fields, versus the historical model-only baseline of 4 of 8. The same example was used during development; this is not held-out evaluation.
- Five selected real pages across four PDFs processed through rules/OCR with source evidence. Source images were inspected for the targeted values. These outputs and their private source pages remain under `output/review/` and are not committed.
- Scanned solar invoice: two quantity/rate/amount lines pass arithmetic checks; their quantity sum is represented as a derived supply quantity. It is not automatically treated as delivered self-consumption.
- No cross-page, cross-invoice or cross-site aggregation was performed.

## Local inference check

The installed local `llama3.1:8b` processed a synthetic PDF through the model-only route. It returned the printed consumption and payable amount correctly, but also inferred grid imports without an explicit grid label. A subsequent validation rule flags and quarantines that unsupported source classification for text/OCR model output. This rule has an automated regression test; the live inference was not rerun after that validation-only change.

## Demonstration and privacy checks

- Earlier static review outputs remain under `output/review/`. Their obsolete generator has been removed; the upload dashboard is the maintained workflow.
- The report is self-contained HTML with embedded source images and no external scripts/styles. Its opening layout was rendered in headless Edge and inspected.
- The static report is a rules/OCR demonstration, not a live model run or a production dashboard.
- The scenario is synthetic and calculates 40% renewable share, INR 80,000 estimated net savings and 26,000 kg estimated avoided CO2e. Its rates and factors are illustrative.
- Raw input data, report images, labels and extracted results are excluded by `.gitignore`.

## Outstanding validation

Representative independent labels, held-out document testing, unseen template testing, OCR robustness, model comparisons, measured latency, invoice deduplication and reconciliation, approved tariffs and emissions factors, and production operational/security review remain outstanding.

## Architecture cleanup validation

After separating the Ollama client, document helpers, background worker and export renderer, all 26 tests passed. Frontend files were expanded with Prettier; Python was formatted with Black. Unused imports and undefined names were checked with Ruff. No model retraining or new accuracy claim is part of this refactor.
