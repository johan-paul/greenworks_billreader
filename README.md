# Greenworks Bill Reader

Offline electricity-bill extraction with Ollama and transparent energy analysis.

## What this version does

- Inventories PDF datasets without sending them to a cloud service.
- Extracts grid, solar and wind bill fields into validated JSON with page numbers and supporting quotes.
- Reads embedded PDF text with a local language model; optionally renders scans for a local vision model.
- Separates kWh, kVAh, kW and kVA and flags suspicious units and missing text evidence.
- Calculates renewable share, scenario savings and avoided emissions from reviewed, reconciled inputs.
- Saves progress after each page and records failures instead of silently skipping them.

This is an initial extraction and analysis pipeline, not a trained or accuracy-certified model. Ollama runs a pretrained model locally. Fine-tuning should only follow creation of a labeled evaluation dataset and measurement of baseline errors.

## Setup (PowerShell)

Python 3.11+ and Ollama are required. Dependency installation and model downloads require internet once; processing uses the loopback Ollama API only.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
ollama pull llama3.1:8b
# For scans, download a compatible local vision model, for example:
ollama pull qwen2.5vl:3b
```

Run Ollama locally. For an offline deployment, disable Ollama cloud features with `OLLAMA_NO_CLOUD=1` in the server environment and restart Ollama; use network isolation if offline operation must be enforced beyond this application. The application hardcodes `127.0.0.1`, bypasses HTTP proxies and rejects model metadata indicating a cloud model. It makes no runtime model downloads.

```powershell
.\.venv\Scripts\python -m billintel.cli models
.\.venv\Scripts\python -m billintel.cli inventory 'EB bills'
.\.venv\Scripts\python -m billintel.cli extract 'path\to\bill.pdf' --max-pages 1
.\.venv\Scripts\python -m billintel.cli extract 'path\to\scanned-bill.pdf' --vision-model qwen2.5vl:3b
# Use vision for complex tables even if the PDF has a text layer:
.\.venv\Scripts\python -m billintel.cli extract 'path\to\bill.pdf' --vision-model qwen2.5vl:3b --force-vision
.\.venv\Scripts\python -m billintel.cli analyze examples/scenario.json
.\.venv\Scripts\python -m pytest -q
```

Outputs are local under `output/`. A nonzero extraction exit code indicates page failures. `complete=false` also indicates intentionally limited runs. `complete=true` means every page was processed, not that values have been verified. Rerunning the same PDF replaces its extraction output; copy reviewed work before rerunning.

## Dataset findings

Initial local inventory: 101 electricity PDFs, 595 pages; 479 pages have at least 80 extracted text characters. The remaining 116 pages need scan/blank-page review. This heuristic does not establish readability or extraction accuracy. Some PDFs contain multiple bills, so PDF-level aggregation would be unsafe. Procurement invoices are outside this initial scope.

## Review and reconciliation

Every extracted page is marked `needs_review`. Check numeric values, units, billing period, account and supplier against the original document. Text quotes can be verified mechanically, but that does not prove the model matched a value to the right label. Vision quotes require visual review.

Group pages into invoices using invoice/account identifiers and the energy billing period. Deduplicate repeated invoices and reconcile solar/wind supply with utility adjustments before entering scenario inputs. Do not sum page totals, historical graphs, supplier energy and grid totals indiscriminately. No automatic page or invoice aggregation is implemented yet.

The schema covers consumption, grid imports, solar and wind energy, exports, current charges, payable balance, tariff, demand, power factor and penalties. Missing fields stay null; printed kVAh is not treated as kWh. Electricity energy (kWh) is different from electrical current (amperes).

## Calculations

The sample scenario is synthetic, with illustrative rates and emission factors. Copy it to `output/my-scenario.json` and replace every value with reviewed inputs for one site and billing period. `reviewed=true` is a user attestation, not automated verification. Specify the source of rates and emission factors in `assumptions_source`.

- Accounted consumption = grid imports + delivered solar used + delivered wind used.
- Renewable share = renewable energy used / accounted consumption.
- Estimated net savings = renewable energy used x avoided marginal grid rate - all-in renewable cost + export credit.
- Estimated avoided kg CO2e = renewable energy used x (grid factor - renewable factor).

All-in renewable cost should include applicable purchase, wheeling, banking, losses, taxes and incremental operational costs. Do not deduct the full average bill rate when fixed/demand charges remain payable. Capital expenditure and financing need a separate payback model. Emissions factors must have a cited geography, year and accounting methodology; this project does not supply official factors or claim certified carbon reductions. Recommendations are screening suggestions, not engineering designs.

## Validation and next milestones

1. Label representative pages from each utility, supplier and scan quality; record values, units and evidence.
2. Use separate documents for development and held-out testing. Keep pages from the same invoice together to avoid leakage.
3. Measure field exact match, numeric/unit accuracy, missing-value precision and document coverage; report failures as well as successes.
4. Validate scan extraction on a locally downloaded vision model; compare OCR if handwriting or tables perform poorly.
5. Add reviewed invoice grouping and monthly site reconciliation, then a review dashboard and trend charts.
6. Consider fine-tuning only when measured errors justify it; evaluate on unseen suppliers/templates.

Current unit tests validate scenario arithmetic, invalid inputs, review requirements, unit/evidence flags and missing-vision errors. They do not establish real-bill extraction accuracy. The default 600-second per-page timeout and local hardware may limit throughput.

## Data protection and Git

Original bills, procurement documents, extracted results, images, environment files and local environments are ignored by Git. Commit source code, tests and synthetic examples only. Check `git status` before each commit. Never commit customer account information or bank details in examples.

```powershell
git add billintel tests examples README.md pyproject.toml .gitignore
git commit -m "Describe the change"
git push origin main
```

## API references

- https://docs.ollama.com/capabilities/structured-outputs
- https://docs.ollama.com/capabilities/vision
- https://docs.ollama.com/faq

## Evaluate against reviewed labels

Create a local labels file with the source PDF SHA-256 and page-specific expected fields:

```json
{"sha256":"HASH_FROM_EXTRACTION", "pages":[{"page":1,"fields":{
  "total_consumption":{"value":125,"unit":"kWh"},
  "solar_energy":null
}}]}
```

```powershell
python -m billintel.cli evaluate 'output/extractions/result.json' 'output/labels.json'
```

Only label fields that can be established from that page. Numeric comparisons require matching units and use an absolute tolerance of 0.01. Missing/error pages count as failures. Keep labels and evaluation reports in `output/` to avoid committing private data.

Initial smoke test: the installed `llama3.1:8b` returned valid JSON on one grid-bill page but matched only 4 of 8 manually checked fields, including errors in consumption and payable amount. This tiny sample is not a dataset accuracy estimate. Do not use its output for unattended reporting. Field-specific units and quote checks expose some failures; they cannot guarantee semantic correctness. Scanned-page validation is a separate requirement.
