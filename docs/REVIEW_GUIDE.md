# Tomorrow's review guide - 17 November 2026

Read this once tonight, then rehearse the opening and demo aloud. You do not need to memorize every function. Understand the data flow, why numbers can be wrong, and how the project detects and handles uncertainty.

## Your 90-second opening

> My project is an offline electricity-bill intelligence pipeline. The objective is to turn grid and renewable-energy bills into structured, traceable data, then use reviewed data to estimate cost and environmental benefits.
>
> I inventoried 101 PDFs containing 595 pages. They include both text PDFs and scans, and some files contain several invoices. I use PyMuPDF for embedded text and Tesseract for local OCR. Ollama runs a pretrained model locally for unfamiliar layouts. For recognized layouts, explicit parsing rules are more reliable for numeric fields.
>
> The first model-only baseline made serious numeric mistakes. On one page it matched four of eight manually checked fields. I added typed units, evidence checks and layout rules. The revised parser matches all eight fields on that same development example. That is not a claim of overall accuracy.
>
> I can demonstrate consumption extraction, scanned solar supply calculations and payable amounts with source evidence. Savings and emissions are calculated with deterministic formulas after reconciliation, rather than asking the language model to invent them. The next priority is a representative labeled evaluation set and monthly reconciliation across grid and renewable invoices.

## Live upload dashboard

For the interactive review, launch `START_DASHBOARD.cmd` and follow [the dashboard walkthrough](DASHBOARD.md). You can upload a PDF and generate a report. The static report below remains a fallback.

## Five-minute demonstration

1. Double-click `RUN_REVIEW_DEMO.cmd` from the project folder. It rebuilds the local report using rules and OCR. It does not need Ollama or internet. If Python is not found, use the exact Python executable documented below.
2. Show the dataset counts and explain the three routes: embedded text, OCR, and model fallback.
3. On the grid header, point out the normal payable amount versus early-payment and late-payment amounts. Explain why choosing the largest or first number is unsafe.
4. On the consumption page, point to the kWh and kVAh columns. Explain that they are not interchangeable.
5. On the scanned solar invoice, show the original page, the two supply quantities, and the computed sum. Each line passes quantity × rate ≈ line amount. Explain that the HSN code identifies the commodity and is not consumption.
6. Show the review notes and evidence. Missing values are unknown, not zero. Every result remains reviewable.
7. Show the synthetic scenario: 40% renewable share, INR 80,000 estimated net savings and 26 tonnes estimated avoided CO2e. Explicitly say these are fictional teaching inputs, not measured company savings.
8. Finish with the limitations and the next milestone. Open GitHub to show version history if internet is available; keep the local repo available as backup.

Do not run the full dataset through Ollama during the review. Inference latency and accuracy are not yet suitable for that demonstration. The report is reproducible output, not a live LLM run; say so directly.

## What each component does

| Component | Purpose | What it does not prove |
|---|---|---|
| PyMuPDF | Extract embedded PDF text and render pages | Correct reading order or interpretation |
| Tesseract OCR | Turn scanned page images into text locally | Perfect digit recognition |
| Ollama | Run downloaded language models locally | It is not itself the trained model |
| llama3.1:8b | Pretrained model used for structured extraction | Bill-specific accuracy or training on these invoices |
| Layout rules | Find known labels, units and table patterns | Generalization to unseen utility formats |
| Pydantic schema | Enforce field types, allowed units and numeric constraints | Whether a plausible value is semantically correct |
| Evidence validation | Check quoted text and reported number | Correct label-to-number association in every table |
| SHA-256 | Identify the exact source PDF | Semantic invoice deduplication |
| Evaluation | Compare selected fields with reviewed labels | Overall accuracy unless the sample is representative |
| Analytics | Apply explicit arithmetic to reviewed inputs | Verified realized savings or certified emissions reductions |
| Git | Track source changes and push updates | A backup of private input bills; those are deliberately excluded |

The architecture is: PDF → text/OCR → recognized-layout rules, otherwise Ollama → typed fields and evidence → review and reconciliation → calculation → report.

The CLI defaults to `--engine hybrid`: rules for recognized pages, Ollama for other pages. `--engine rules` is the fast demo mode; unknown layouts return an explicit error. `--engine llm` runs the model-only route for comparisons. Rules leave unmatched fields null; hybrid does not automatically fill every missing field from the LLM on recognized pages.

For text/OCR LLM results, a numeric candidate with a missing quote, a number absent from the quote, or an absent source label for grid/solar/wind/export is moved to `rejected_candidates`; its accepted field becomes null. That still cannot catch every semantic error. Vision results require visual review because there is no extracted text to match against.

## Electricity concepts you should know

- **kWh:** electrical energy used over time. A 1 kW load running for one hour consumes 1 kWh. In ordinary electricity billing, one energy unit usually refers to 1 kWh; always check the bill.
- **kW:** real power at a point in time or an average over a demand interval. It is not monthly energy.
- **kVA:** apparent power; often used for industrial contract or maximum demand.
- **kVAh:** apparent energy. Do not label it kWh or multiply by an unrelated power-factor value.
- **Power factor:** real power divided by apparent power under the applicable measurement definition. Low power factor can contribute to higher apparent-power demand. Tariff effects must be checked for the specific utility.
- **Contract demand:** agreed capacity. **Recorded maximum demand:** observed demand. **Billed demand:** tariff-defined chargeable demand; these can differ.
- **Grid imports:** energy received from the grid. **Exports:** energy sent out. **Solar supply/generation:** not automatically the energy consumed at the factory after losses, exports and banking.
- **Time-of-day charges:** different charges or rebates for different periods. Peak surcharge units may overlap base energy units; adding them would double-count consumption.
- **Current charges versus payable:** payable can include arrears, adjustments, taxes, credits and deductions. Payment discounts are separate.
- **Open-access/PPA renewable purchase:** renewable electricity purchased through a supply arrangement. Wheeling, banking, losses, taxes and adjustments may affect delivered units and actual cost.

Use the term "solar energy supplied or consumed in kWh," not "current from solar," unless the task really requires electrical current in amperes.

## Explain the calculations

All inputs must refer to the same site, meter boundary and period, and must be mutually exclusive.

1. Accounted consumption = grid import + solar used + wind used.
2. Renewable share = (solar used + wind used) / accounted consumption × 100.
3. Estimated savings = renewable energy used × avoided marginal grid rate − all-in renewable cost + export credit.
4. Estimated avoided CO2e = renewable energy used × (grid emission factor − renewable emission factor).

Example: 60,000 kWh grid + 30,000 solar + 10,000 wind = 100,000 kWh. Renewable share is 40%. At an illustrative avoided grid rate of INR 8/kWh and renewable cost of INR 240,000, estimated savings are 40,000 × 8 − 240,000 = INR 80,000. At illustrative factors of 0.70 and 0.05 kg CO2e/kWh, estimated avoided emissions are 26,000 kg = 26 tonnes.

Do not use total bill / kWh as the avoided rate without checking fixed charges and demand charges. Do not claim all solar energy is consumed on-site. Emissions factors need an approved source, year, geography and accounting method. The calculation is a scenario estimate, not a corporate carbon inventory or a carbon-credit claim.

Environmental value: identify waste, compare energy per unit of production, evaluate load shifting, and assess renewable substitution. Lower bills do not automatically imply lower energy use or emissions. Production changes, tariff changes and billing days can explain differences.

## Questions the TL may ask

**Did you train an AI model?**
No. This version uses a pretrained model through Ollama, with prompting, a schema and deterministic parsers. I have not fine-tuned it. Fine-tuning requires labeled examples, an evaluation split and evidence that it addresses the measured errors.

**Why Ollama?**
It provides a local inference runtime and API for downloaded models, fitting the offline requirement. Model quality, speed and hardware needs still need evaluation. Initial dependency and model downloads require internet; processing can run locally afterward.

**Why not just use regex?**
Known layouts benefit from predictable label-based parsing, but the dataset has many layouts and scans. The model offers a fallback for unfamiliar layouts. Both routes need evidence, validation and measured evaluation. The current demo is deliberately clear about using rules.

**Why not use only the LLM?**
The baseline confused money with energy, HSN codes with quantities and early-payment amounts with normal payable amounts. Valid JSON does not imply a correct answer. A hybrid approach reduces avoidable numeric errors on recognized formats.

**What is your accuracy?**
The previous model-only baseline matched 4/8 selected fields on one grid page. The rule-based revision matches 8/8 on the same development example. These are not held-out results. The software test suite checks arithmetic, validation, evidence rejection, parser behavior and offline rules execution; use the latest test run for its current count. I will report dataset accuracy only after independently labeled, representative evaluation.

**How much of the dataset is supported?**
The text-only coverage scan recognized layout patterns on 199/595 pages: 133 MSEDCL headers, 42 MSEDCL consumption pages and 24 TANGEDCO headers. Another 280 text pages were not matched, and 116 pages need OCR or blank-page review. Recognition is not complete field coverage. The selected solar OCR example is additional demo evidence, not part of the text-only count.

**Why are some values null?**
The value is missing, ambiguous, unsupported or rejected. Null is safer and more honest than guessing zero. Review is still necessary.

**Can it calculate actual savings now?**
It can calculate scenarios from reviewed inputs. Actual savings need reconciled delivered energy, the avoidable tariff, renewable costs, losses, taxes and a defensible baseline. The demo does not claim measured company savings.

**How do you avoid double counting?**
The prototype keeps results per page and does not automatically aggregate them. Next we need invoice grouping, account/site/period matching, duplicate detection and reconciliation of utility adjustments with supplier invoices. A PDF may contain many bills, and several pages may repeat the same total.

**How will you evaluate properly?**
Manually label fields, values, units and evidence across utilities, suppliers, scans and low-quality pages. Keep pages from the same invoice in the same split. Hold out whole documents and preferably some templates/suppliers. Measure numeric-and-unit accuracy, missing-value handling, field coverage, false positives, processing failures and latency. Include abstentions instead of hiding failures.

**How is data kept private?**
Input bills and outputs stay local and are ignored by Git. Ollama requests go to 127.0.0.1, proxying is disabled for those requests, and cloud-model metadata is rejected. The report embeds private source pages, so it also stays out of Git. This is not a formal network-isolation audit.

**Can we deploy it?**
It is an internship prototype. Before production: broader evaluation, review controls, invoice reconciliation, security/access controls, logging and operational testing are needed. Do not promise a production accuracy number tomorrow.

**What code did you write, and did you use AI assistance?**
Explain the modules you can walk through and be transparent that you used an AI coding assistant. Say you are validating the code, understanding its behavior and measuring its limitations. Do not claim you personally implemented or trained something you cannot explain.

## What to ask your TL

- Which three output fields and which bill types should be prioritized first?
- Is the renewable data supplied, injected, adjusted, banked or delivered energy? Who can confirm the reconciliation rules?
- Can we get a small set of accountant/engineer-verified labels and an acceptance threshold?
- Which tariff baseline, renewable costs and emission-factor source should be used?
- Is the expected deliverable a CLI, dashboard, API, batch report or integration?
- Which hardware will run the offline system, and what turnaround time is acceptable?

## Proposed next milestone (agree scope, do not promise blindly)

1. Establish labels and evaluation split for representative invoices.
2. Expand supported layouts and benchmark the local model/OCR alternatives.
3. Implement reviewed invoice grouping and grid/solar/wind reconciliation.
4. Add monthly trends, energy intensity and review/export workflows.
5. Validate on unseen documents and document failures before deployment.

## Tonight and tomorrow morning

- Run the demo once and keep the generated HTML open as a backup.
- Read the source evidence on the demo pages and rehearse the 90-second opening twice.
- Know which examples are real extractions and which numbers are synthetic scenarios.
- Rehearse the honest answers about training, accuracy, offline behavior and limitations.
- Charge the laptop, keep the dataset local, and do not depend on a model download tomorrow.
- If a live model call is slow or wrong, show the review workflow and saved report; do not hide it.

## Commands and troubleshooting

From the project folder:

```powershell
python -m scripts.prepare_review
Start-Process 'output/review/review-demo.html'
python -m pytest -q
python -m billintel.cli models
python -m billintel.cli extract 'path\to\bill.pdf' --engine hybrid --ocr --max-pages 1
python -m billintel.cli analyze examples/scenario.json
```

Known Python executable on this machine:

```powershell
& 'C:/Users/Johan Paul/anaconda3/python.exe' -m scripts.prepare_review
```

If the report already exists, opening it needs no Python, OCR or Ollama. If model listing fails, start Ollama; the rules demo still works without it. If OCR fails, check the Tesseract installation and English language data. Unsupported layouts are expected to abstain in rules mode.

## References to understand, not memorize

- Ollama structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- Ollama local/offline configuration: https://docs.ollama.com/faq
- GHG Protocol Scope 2 Guidance: https://ghgprotocol.org/scope-2-guidance

These references inform the design. No official emissions factor is embedded in this prototype.
