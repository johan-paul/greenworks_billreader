# Greenworks Bill Reader

An offline electricity-bill analysis prototype: upload a PDF, inspect extracted fields with source evidence, download a report, and calculate scenarios from reviewed energy data.

## Start the application

Double-click **START_DASHBOARD.cmd**, then open **http://127.0.0.1:8791**.

For a new Python 3.11+ environment:

```powershell
python -m pip install -e '.[dev]'
python -m billintel.dashboard
```

Install Tesseract with English language data for scans. Ollama and a downloaded local model (`llama3.1:8b` on the development machine) are required for model-based extraction. Installation/downloads require internet once; bill processing uses local services. The launcher attempts to start Ollama if needed.

## Documentation

- [Architecture and file-by-file walkthrough](docs/ARCHITECTURE.md) — start here for code review.
- [Dashboard instructions](docs/DASHBOARD.md) — upload, demo, downloads and troubleshooting.
- [Review speaking notes](docs/REVIEW_GUIDE.md) — explanation and likely TL questions.
- [Local training workflow](docs/TRAINING.md) — draft labels, grouped splits and experimental CPU LoRA training.
- [Validation record](docs/VALIDATION.md) — tested behavior and accuracy limitations.

## Application structure

```text
START_DASHBOARD.cmd          Windows entry point
scripts/start_dashboard.ps1  Start local services and open the browser
billintel/
  dashboard.py              Flask routes and upload validation
  jobs.py                   Background extraction subprocess and job progress
  cli.py                    Command-line interface used by the worker
  extraction.py             Page-by-page processing pipeline
  documents.py              PDF inventory and local Tesseract OCR
  ollama_client.py           Loopback-only Ollama API client
  rules.py                   Recognized-layout extraction rules
  schema.py                  Field types, units and evidence checks
  analytics.py              Reviewed savings/emissions scenarios
  exports.py                Downloadable JSON, CSV and HTML reports
  evaluation.py             Compare output with reviewed labels
  web/                      HTML, CSS and JavaScript frontend
examples/scenario.json      Fictional calculation example
tests/                     Regression and integration tests
```

`EB bills/` and `Procurement Invoices/` contain private source data. `output/` contains private uploads, results and saved reports. These folders are excluded from Git. General procurement-invoice extraction is not implemented.

## Extraction modes

| Mode | Behavior |
|---|---|
| Automatic / `hybrid` | Rules for recognized page layouts; otherwise local Ollama. Unmatched fields on a recognized page remain null. |
| Quick / `rules` | No model needed; unsupported layouts return explicit page errors. |
| Model only / `llm` | Ollama extraction, followed by schema and evidence checks. |

Every result needs review. Missing or rejected values remain unknown, not zero. PDFs can contain multiple invoices, so page amounts are not automatically added together. Solar supply is not assumed to equal delivered self-consumption. The dashboard still uses its original pretrained model. Experimental local fine-tuning is kept separate under `training/`; see the training guide for its data and evaluation limits.

## CLI and tests

```powershell
python -m billintel.cli inventory 'EB bills'
python -m billintel.cli models
python -m billintel.cli extract 'path\to\bill.pdf' --engine hybrid --ocr --max-pages 2
python -m billintel.cli analyze examples/scenario.json
python -m billintel.cli evaluate 'output/result.json' 'output/labels.json'
python -m pytest -q
```

CLI-only vision support is optional (`--vision-model`, `--force-vision`); it requires a compatible downloaded local vision model and has not been validated on this dataset.

The saved static review report under `output/review/` remains an optional offline backup. Its old dataset-specific generator was removed to keep one maintained user workflow: the upload dashboard.
