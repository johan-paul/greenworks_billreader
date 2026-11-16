# Upload dashboard - quick start

1. Double-click `START_DASHBOARD.cmd` in the project folder.
2. Open http://127.0.0.1:8791 if the browser does not open automatically.
3. Choose or drag in an electricity bill PDF.
4. Keep **Automatic - rules + Ollama** for general uploads. Use **Quick - recognized layouts only** for a fast demonstration of the supported examples.
5. Choose all pages, or a first-page/first-two-page preview. Click **Analyze bill**.
6. Select a processed page to see its values, original image, evidence and review notes.
7. Download the **HTML report**, **CSV**, or **JSON**. The HTML report can be opened offline and printed to PDF through the browser.

## Recommended review walkthrough

- Upload the MSEDCL example `1001_Electricity Bill_Q1 (4).pdf` from the local dataset. Select Quick mode and First 2 pages. Show the payable amount on page 1 and consumption on page 2.
- Upload `Apple India Solar bills.pdf`. Select Quick mode and First page. Show the scanned original, line-item-derived solar supply and payable amount.
- Open **Savings & impact**, click **Load fictional example**, review the assumptions, check the confirmation box and calculate. Explain that the example is fictional. For real estimates, replace every input with reviewed values.

## What the dashboard supports

- One PDF per upload; maximum 30 MB and 100 pages.
- Embedded text and scanned pages through local OCR.
- Automatic rules/Ollama routing, rules-only mode, or model-only mode.
- Background processing, per-page progress and explicit errors.
- Selected-page metrics, evidence and rejected model candidates.
- HTML, CSV and JSON extraction reports.
- A separate scenario calculator with input validation, recommendations, energy mix and downloadable scenario JSON.

An arbitrary PDF can be uploaded within these limits, but accurate extraction is not guaranteed for every layout. Unknown formats use Ollama in Automatic mode; inference may take minutes per page. Quick mode reports unsupported layouts explicitly. Password-protected or malformed PDFs are rejected. Partial previews and failed pages are labeled; no automatic cross-page totals are calculated.

The report extracts what is supported by the bill. Real savings require delivered energy, costs and tariffs that may come from other records. The scenario form therefore requires explicit reviewed inputs instead of silently assuming them from invoice amounts or solar supply.

## Offline operation and storage

The app serves only on loopback at `127.0.0.1:8791`. OCR and model inference are local. Initial dependency/model installation requires internet; normal processing does not. The launcher starts the dashboard and attempts to start Ollama if necessary. Quick mode does not need Ollama. The server runs in the background so closing the browser does not stop it.

Uploaded bills and results are stored in `output/dashboard/`, which is ignored by Git. Session history is held in memory and is not restored after a browser refresh/server restart; downloaded reports and saved extraction files remain on disk. Keep a downloaded report as a review backup. No cloud hosting is used.

## Troubleshooting

- If startup fails, inspect `output/dashboard/server-errors.log`.
- If dependencies are missing, run `python -m pip install -e .` once.
- If Ollama is unavailable, start Ollama or use Quick mode for supported layouts.
- If a page fails, use the page selector to inspect its error. Other processed pages remain available for download.
- If a bill takes too long, use a small page preview for the review. Avoid queuing the entire dataset.
- To run with visible logs: `python -m billintel.dashboard` (when the dashboard is not already running).

## Verification

Automated tests cover invalid uploads, local-origin checks, a real upload-to-extraction subprocess, page previews, all three extraction exports, and scenario validation. Browser checks exercised the real grid and scanned-solar upload flows, the scenario calculator, loaded source images and mobile layout without JavaScript errors. These functional checks do not establish general extraction accuracy.
