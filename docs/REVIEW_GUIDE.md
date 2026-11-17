# Explaining Greenworks to your TL

## Your opening

> Greenworks is an offline electricity-bill analysis application. The browser uploads a PDF to a local Flask API. A background worker runs a page-by-page extraction pipeline. It reads embedded text or uses Tesseract OCR, then uses layout rules for known formats and a pretrained model through Ollama for unfamiliar formats. Results are checked against typed fields and supporting evidence, stored locally, and shown beside the original page. Savings and emissions are calculated separately from reviewed inputs using explicit formulas.

## The five layers to remember

1. **Frontend:** `web/index.html`, `style.css`, `app.js` — upload, progress, page preview, results and scenario form.
2. **API and worker:** `dashboard.py`, `jobs.py`, `cli.py` — accept requests, queue work and run processing without blocking the upload request.
3. **Extraction:** `extraction.py`, `documents.py`, `rules.py`, `ollama_client.py` — orchestrate pages, read/OCR documents, match known layouts and call the local model.
4. **Validation and output:** `schema.py`, `exports.py`, `evaluation.py` — type/evidence checks, downloadable reports and comparison with reviewed labels.
5. **Analytics:** `analytics.py` — calculate energy mix, cost savings and emissions scenarios from reviewed inputs.

Open [ARCHITECTURE.md](ARCHITECTURE.md) for the diagram, complete file map, API list and code walkthrough order. Use [DASHBOARD.md](DASHBOARD.md) for the live demo.

## Answers you should be able to give

**Where does execution start?**
`START_DASHBOARD.cmd` calls `scripts/start_dashboard.ps1`. That starts `python -m billintel.dashboard`, which builds the Flask app using `create_app()` and serves the frontend at `127.0.0.1:8791`.

**What happens when Analyze is clicked?**
JavaScript sends a multipart upload. Flask checks the PDF and creates a job. A background thread runs a CLI subprocess. The pipeline saves results after each page; JavaScript polls every two seconds and displays the latest progress.

**Where is the AI model?**
The pretrained model is managed by the local Ollama installation, outside this Git repository. `ollama_client.py` sends local API requests; `extraction.py` supplies the prompt and expected JSON schema. `schema.py` defines the data format, not model weights.

**Did you train a model?**
No. This version uses pretrained `llama3.1:8b`, prompts, OCR and parsing rules. Training/fine-tuning is a future decision after labeled evaluation identifies the errors and enough suitable examples are available.

**Does every upload use the LLM?**
No. In Automatic mode, recognized page layouts use rules. Unknown layouts fall back to Ollama. Quick mode uses only rules; model-only mode uses Ollama. On a recognized page, missing fields remain null rather than automatically invoking the LLM for each missing field.

**Why not use only the LLM?**
It made errors such as treating an HSN commodity code as consumption and choosing an early-payment amount as normal payable. Known-layout parsing improves selected examples. Valid JSON does not mean the values are correct.

**Why OCR and an LLM?**
OCR converts scanned images into text. Extraction interprets that text as fields. Errors can occur at either stage, so the original image and supporting text remain available for review.

**What is validated?**
Allowed units, numeric ranges and output structure; whether numeric quotes occur in text; whether the number and relevant source label appear in their quote. Unsupported text/OCR numeric model candidates are quarantined. These checks do not catch every incorrect label/value association.

**Where is the database?**
There is no database yet. PDFs, logs and results are local files under `output/dashboard/<job-id>/`. Job state lives in server memory; sidebar history lives in browser memory. Files survive restart, but job/history recovery is not implemented.

**Why a background worker?**
OCR and model inference are slow. The upload returns a job ID promptly while processing continues. One extraction subprocess runs at a time; this is a simple local worker, not Celery or a distributed queue.

**What does complete mean?**
Every PDF page processed without a page error. It does not mean human-verified or accurate. A successful first-two-page preview can finish while the document remains incomplete.

**How are reports produced?**
The browser displays page JSON. `exports.py` creates HTML, CSV and JSON downloads. These exports do not automatically aggregate repeated totals or merge invoices.

**How do savings work?**
Renewable energy used × avoided marginal grid rate − all-in renewable cost + export credit. The user supplies reviewed values for one site and period. The invoice alone may not contain losses, delivered renewable energy or all costs.

**How do emissions work?**
Renewable energy used × (grid factor − renewable factor). Factors need an approved source/year/accounting method. The example uses illustrative values and is not a certified carbon claim.

**What is your accuracy?**
The historical model-only baseline matched 4 of 8 selected fields on one grid page. Revised rules matched 8 of those 8 fields on the same development example. This is not held-out or dataset-wide accuracy. The 26 software tests check program behavior, not overall model accuracy.

**What dataset coverage do you have?**
The earlier inventory found 101 PDFs and 595 pages. Text-only layout recognition matched 199 pages; 280 text pages were unmatched and 116 needed OCR or blank-page review. Recognition is not complete extraction or proof of correctness.

**How is it offline?**
The frontend assets, Flask API, PDF processing, OCR and Ollama inference run locally. Models/dependencies need internet for initial installation. The Ollama client uses loopback and rejects cloud-model metadata. This has not been certified through a full network-isolation audit.

**Can it process procurement invoices?**
Not reliably. The current schema and rules are for electricity and renewable-energy invoices. General invoices need their own fields and evaluation.

**What comes next?**
Representative manually reviewed labels; document-level train/validation/test splits; measurement of OCR and extraction errors; stronger layout coverage/model comparisons; invoice grouping and grid/renewable reconciliation. Fine-tune only if measured results justify it.

## Concepts to remember

- kWh = energy; kW = power; kVA = apparent power; kVAh = apparent energy. Never silently substitute one unit for another.
- Solar supplied is not necessarily solar used after losses, exports and banking.
- Payable amount can include adjustments, arrears and taxes; it is not automatically an avoidable energy cost.
- Peak surcharge units can overlap base consumption. Adding every units row double-counts energy.
- Null means unknown, absent or rejected. It does not mean zero.
- A PDF can contain multiple invoices and repeated amounts. A file hash identifies bytes, not duplicate commercial invoices.

## Before the walkthrough

1. Open the dashboard and test the selected examples.
2. Open `docs/ARCHITECTURE.md` and follow the code order at its end.
3. Be clear that scenario numbers are fictional unless inputs were actually reviewed.
4. Be transparent about using AI coding assistance; explain the parts you understand and the measured limitations.
5. Ask the TL for priority fields, representative verified labels, a tariff/emissions methodology and an acceptance threshold.
