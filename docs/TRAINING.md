# Local model training

The training tools are separate from the dashboard. They do not replace its installed Ollama model automatically.

## What we are doing

Adapt a small pretrained causal language model using LoRA. LoRA learns a small set of adapter weights while the base model remains frozen. The first laptop experiment uses `Qwen/Qwen2.5-0.5B-Instruct` and CPU PyTorch in `.venv-training`.

This is not training a large language model from scratch. A tiny bootstrap run verifies that the pipeline works; it is not a production-quality bill model or an accuracy claim.

## Files

| File | Purpose |
|---|---|
| `training/prepare_data.py` | Build draft annotations, validate reviewed labels, group related records and produce supervised train/validation/test JSONL. |
| `training/train_lora.py` | CPU LoRA training, assistant-response loss masking, validation loss, adapter checkpoint and run report. |
| `training/requirements.txt` | Pinned training-only libraries; kept out of the dashboard runtime requirements. |
| `tests/test_training.py` | Guard against unreviewed examples, leakage, unsupported evidence, overwrites and target truncation. |
| `output/training/` | Private source text, annotations, dataset splits, model cache and checkpoints. Ignored by Git. |

## Data workflow

```powershell
python -m training.prepare_data draft 'EB bills' output/training/drafts-v2.jsonl
# Add --ocr to read scanned pages as well. This is slower.
```

Each page contains `text`, source PDF hash, page number, extraction method and optional rule-generated `candidate`. Every draft starts with `reviewed=false` and `target=null`. Candidate values are suggestions, not ground truth.

To review a record:

1. Open its source PDF at the specified page. Check the actual digits, units, billing period and labels.
2. Copy the candidate into `target` if useful, then correct it. Populate the complete `PageExtraction` schema; use null for genuinely absent or ambiguous fields, not for fields you have not checked.
3. Include exact supporting text for every numeric value. Do not invent readable numbers when OCR has lost them; flag the record for OCR repair or keep the relevant target unknown.
4. Record `reviewer` and `review_notes`, then set `reviewed=true`. Be explicit whether the reviewer is a person or an AI assistant.
5. Set `group_id` consistently for related or duplicate invoices that must stay together. Document hashes and identical page text are also linked automatically; known invoice identifiers provide another check. These checks cannot discover every business-level duplicate.
6. Save reviewed annotations as a new JSONL version. Never overwrite the original drafts or a previous dataset version.

```powershell
python -m training.prepare_data build output/training/reviewed-v2.jsonl output/training/dataset-v2 --seed 42
```

The builder requires at least three independent groups to create nonempty training, validation and test splits. Approximately 80/10/10 is used for larger datasets, with at least one group reserved for validation and test. Three groups are only a software minimum, not enough evidence for meaningful generalization.

## First bootstrap dataset

Four pages from three PDFs were prepared from previously inspected development examples. Two pages belong to training, one to validation and one to test. Labels are explicitly marked `assistant_visual_bootstrap`, not independently human-verified. The same dataset family has already been used in development, so this must not be presented as an independent benchmark.

The original draft queue had 595 records, with 116 pages needing OCR/blank-page review. The subsequent `drafts-with-ocr-v1.jsonl` contains all 595 pages (479 text, 116 OCR), 222 rule-generated candidates and no processing errors. Successful OCR is not proof that the digits are correct.

## Review batch v2 (18 November 2026)

`output/training/reviewed-v2.jsonl` retains all 595 source records. It contains 45 assistant-reviewed examples and 550 pending pages. No labels are independently human-verified. The batch checks 42 MSEDCL consumption annexures against their account/month, column order, printed kWh total, maximum kVA demand and billed power factor. All distinct normalized template lines were inspected and three representative PDF pages were visually checked. Review notes distinguish this template-based review from individual visual verification.

Maximum demand labels were added where draft rules omitted them. Billed demand, historical charts, and time-of-day surcharge rates are not substituted for maximum demand, current consumption, or a single energy rate. Solar adjustments are not labeled as total solar generation.

`output/training/dataset-v2/manifest.json` records 28 related-document groups: 39 training pages, 3 validation pages and 3 test pages. Grid annexures for the same account and period stay together, including copies in quarterly compilations. The dataset remains heavily biased toward one grid template; solar/wind coverage and independent evaluation are unfinished. `output/training/review-audit-v2.json` records the coverage and limitations. The local review script and private labels remain outside Git.

## Isolated laptop environment

The existing Anaconda PyTorch installation encountered duplicate OpenMP runtime initialization. A clean environment avoids changing the working dashboard environment; the unsafe duplicate-runtime bypass is not used.

```powershell
python -m venv .venv-training
.\.venv-training\Scripts\python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
.\.venv-training\Scripts\python -m pip install -r training/requirements.txt -e .
```

These installations and the first model download require internet. The private bill text and labels stay local. The script does not upload checkpoints or enable experiment tracking. Later training can use cached weights without `--allow-download`.

## Run a bounded experiment

```powershell
.\.venv-training\Scripts\python -m training.train_lora `
  --data output/training/dataset-v1 `
  --output output/training/runs/bootstrap-v1 `
  --steps 4 --threads 6
```

Use a new output directory for each run. The script refuses to overwrite existing run directories. It trains `q_proj` and `v_proj` LoRA adapters with rank 8, alpha 16 and dropout 0.05. It uses a fixed random seed, FP32 CPU execution, gradient checkpointing and batch size one. Training loss applies to the assistant JSON response, not the input bill or instruction tokens. Oversized examples fail rather than silently truncating the expected answer.

The base weights are already cached on this laptop, so this command works offline. Add `--allow-download` only when deliberately setting up an uncached model. The four-step bootstrap command above uses the original four-page dataset, not all 595 pages. To exercise every training example in the expanded reviewed batch once, use `--data output/training/dataset-v2 --output output/training/runs/reviewed-v2 --steps 39 --threads 6`. That is a separate, longer experiment, not a claim of completed training or sufficient convergence.

The training prompt uses the same text and schema instructions as the application's model extraction route. Before training, reviewed labels are validated again and split overlap is checked. The test split is not used for parameter updates or validation-loss selection.

Run files:

- `progress.json`: per-step training loss and elapsed time.
- `adapter/`: LoRA adapter weights/configuration and tokenizer files.
- `training-report.json`: exact base model revision, settings, data counts, validation loss before/after and limitations.

## What to measure next

### Automated local workflow

`training/auto_label.py` uses the installed local Ollama model to propose labels. It preserves existing reviewed targets and stores machine output in `pseudo_target`, never changing `reviewed=false` to true. It checks numeric evidence, source identities, rule disagreements and missing numeric coverage. A passing status means only that these checks passed, not that the label is correct or complete. Private outputs remain under `output/training/`.

```powershell
python -m training.auto_label output/training/reviewed-v2.jsonl output/training/auto-label-v1
```

The command resumes completed pages. It refuses to resume if the source file, model digest, prompt or generation settings changed. Each page is saved atomically under `pages/`; `progress.json` records counts. `annotations.jsonl` is reconstructed at the end of a run. Do not run two workers against the same output directory. Windows file replacement retries brief sharing conflicts. Failed and flagged pages need review; machine output is not automatically promoted into training or evaluation labels.

`training/evaluate_adapter.py` generates answers from the exact base model and trained adapter on the held-out test split, verifies the dataset hashes, and reports schema validity, numeric/unit correctness, null correctness and evidence failures. The initial experimental import gate requires valid schema and supported evidence on every test page, at least 90% numeric accuracy, and no regression against the small base model. This small assistant-reviewed test is insufficient for production approval; it does not compare against the dashboard's larger 8B model.

`training/export_model.py` merges adapters into the exact cached base revision and imports a separate `greenworks-billreader-experimental:v2` model into local Ollama only if that gate passes. No model is uploaded. The dashboard lists installed models but preserves its existing selection/default. Failed evaluation keeps the adapter local for investigation.

`scripts/finish_training.ps1 -TrainingProcessId <PID>` waits for an already-running training process, evaluates its saved adapter, attempts gated export, then resumes the full labeling queue. It runs the expensive stages sequentially. Follow-up errors are written to its log; labeling can still proceed. Keep the laptop awake and powered while these jobs run. The default paths target the v2 dataset/run and v1 automatic-label queue. Rerunning a finished evaluation does not repeat the held-out test.

The active v2 training experiment uses 39 reviewed training examples for 39 optimizer steps; the three validation and three test pages are held out. The other source pages are queued for pseudo-labeling, not secretly treated as verified training data. Completion is recorded by `training-report.json`, `generation-evaluation.json`, and, only after successful import, `import-report.json`. A started process is not evidence that these stages completed.

### Completed laptop check (18 November 2026)

`output/training/runs/bootstrap-v1/` contains a saved LoRA adapter and `training-report.json`. The offline CPU run completed four optimizer steps in 201.8 seconds using the original two training examples, one validation example and one untouched test example. It updated 540,672 adapter parameters. Validation response loss changed from 0.80722 to 0.78811; this single-example result is not extraction accuracy or evidence of generalization. The 45-page v2 dataset was prepared separately and has not yet been trained. All 33 software tests passed, and a separate numerical check confirmed that response-only loss matches standard masked causal loss with finite gradients. No adapter has been deployed to Ollama.

A decrease in training or validation loss is not proof of better extraction. Generate outputs from both the base and fine-tuned models on separately reviewed, unseen invoices. Measure valid-JSON rate, numeric-and-unit accuracy, missing-value accuracy, coverage, error/abstention rate and latency. Compare against the current dashboard's model/rules baseline as well.

Expand verified examples across utilities, bill months, solar/wind suppliers, table layouts and scan quality before a serious training run. Keep commercial duplicates in the same split. Do not tune repeatedly on the final test split.

## Ollama deployment

A LoRA checkpoint is not automatically a working Ollama model. After quality evaluation, merge/export it using the exact recorded base revision and use an Ollama-supported weight format (Safetensors or compatible GGUF), checking compatibility with the installed version. Benchmark the imported model again before selecting it in the dashboard. The first experiment deliberately does not merge, publish, import or replace a model.

## Primary references

- [Hugging Face PEFT](https://huggingface.co/docs/peft/quicktour) — parameter-efficient adaptation.
- [Qwen base-model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) — base model and license.
- [Ollama import documentation](https://docs.ollama.com/import) — supported import workflow.
