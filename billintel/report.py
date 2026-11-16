"""Build a private, self-contained HTML report from saved extraction JSON."""
import base64
import html
import json
from pathlib import Path
import pymupdf

CSS = '''body{margin:0;background:#f1f5f3;color:#192d27;font:16px/1.55 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:44px 28px}h1{font-size:42px;line-height:1.12;margin:10px 0}h2{font-size:24px}small,.muted{color:#546c62}header{background:#153d32;color:white;padding:34px;border-radius:18px}header p{color:#d4e9df}.tag{font-size:12px;text-transform:uppercase;letter-spacing:2px}.cards{display:flex;gap:18px;flex-wrap:wrap;margin:24px 0}.card{background:white;padding:22px;border-radius:12px;flex:1;min-width:180px}.big{font-size:32px;font-weight:700}.notice{background:#fff4d9;padding:16px;border-left:4px solid #a77915}.document{background:white;border-radius:14px;padding:24px;margin:25px 0;break-before:page}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.page{width:100%;border:1px solid #ccd7d0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px 8px;border-bottom:1px solid #dbe4df;text-align:left;vertical-align:top}td:first-child{width:43%}code{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}summary{cursor:pointer;font-weight:600}li{margin-bottom:8px}.pill{display:inline-block;padding:3px 9px;background:#e2eee7;border-radius:20px;font-size:12px}@media(max-width:850px){.columns{grid-template-columns:1fr}}@media print{body{background:white}main{padding:0}.document{border:1px solid #ddd}details{display:block}header{color:black;background:#eee}}'''

def build_report(folder: Path, target: Path, summary: dict):
    esc=lambda value:html.escape(str(value))
    evaluation=summary.get('development_evaluation')
    benchmark=(f"Current rules match {evaluation['correct_fields']} of {evaluation['evaluated_fields']} labeled fields on the original development example. The historical model-only baseline was 4/8." if evaluation else 'No local labels were available for this run. See the review guide for historical development results.')
    parts=[f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Greenworks | Review demo</title><style>{CSS}</style><main>',
      '<header><div class="tag">Greenworks / internship review / 17 November 2026</div><h1>From electricity bills<br>to reviewable energy data.</h1><p>Offline extraction • traceable evidence • transparent calculations</p></header>',
      '<div class="cards">'+''.join(f'<div class="card"><div class="big">{esc(v)}</div>{esc(k)}</div>' for k,v in [('PDFs inventoried',summary['pdfs']),('Pages inventoried',summary['pages']),('Text-readable pages',summary['text_pages'])])+'</div>',
      '<p class="notice"><b>Demonstration, not production certification.</b> These selected pages use layout rules and local OCR. Ollama is the fallback for unfamiliar layouts. All results require review. Do not sum different sites, periods or repeated invoices.</p>',
      f'<h2>What improved</h2><p>{esc(benchmark)} These are development examples, not a held-out accuracy score.</p>',
      '<h2>How it works</h2><p>PDF → embedded text or local OCR → known-layout rules / Ollama fallback → typed fields and evidence → human review → reconciled scenario → savings and emissions estimates.</p>']
    for path in sorted(folder.glob('*.json')):
        doc=json.loads(path.read_text(encoding='utf-8'))
        with pymupdf.open(doc['source']) as pdf:
            for row in doc['pages']:
                data=row.get('data',{})
                pix=pdf[row['page']-1].get_pixmap(dpi=105)
                img=base64.b64encode(pix.tobytes('png')).decode()
                parts.append(f'<section class="document"><small>{esc(Path(doc["source"]).name)} · page {row["page"]} of {doc["page_count"]}</small><h2>{esc(data.get("billing_period") or "Unidentified period")} <span class="pill">{esc(row.get("engine", "unknown"))} / {esc(row["method"])}</span></h2><div class="columns"><div><img class="page" alt="Original bill page" src="data:image/png;base64,{img}"></div><div><table><tr><th>Field</th><th>Extracted value</th></tr>')
                for key,value in data.items():
                    if value is None or key=='notes':continue
                    display=f'{value["value"]:,.3f} {value["unit"]}' if isinstance(value,dict) else str(value)
                    parts.append(f'<tr><td>{esc(key.replace("_"," "))}</td><td>{esc(display)}</td></tr>')
                parts.append('</table>')
                for key,value in row.get('derived',{}).items():
                    parts.append(f'<h3>Calculated: {esc(key.replace("_"," "))}</h3><p><b>{value["value"]:,.0f} {esc(value["unit"])}</b><br>{esc(value["formula"])}</p><p>{esc(value["warning"])}</p>')
                parts.append('<h3>Review notes</h3><ul>'+''.join(f'<li>{esc(v)}</li>' for v in row.get('issues',[])+data.get('notes',[]))+'</ul>')
                parts.append('<details><summary>Evidence and calculation details</summary><pre><code>'+esc(json.dumps(row,indent=2))+'</code></pre></details></div></div></section>')
    parts.append('''<section class="document"><h2>Synthetic scenario: explain the formulas</h2><p>This example is fictional. It is not the savings achieved by any dataset company.</p><table><tr><th>Input</th><th>Value</th></tr><tr><td>Grid / solar / wind used</td><td>60,000 / 30,000 / 10,000 kWh</td></tr><tr><td>Avoided grid rate / renewable cost</td><td>INR 8 per kWh / INR 240,000</td></tr><tr><td>Grid / renewable emission factor</td><td>0.70 / 0.05 kg CO2e per kWh (illustrative)</td></tr></table><div class="cards"><div class="card"><div class="big">40%</div>Renewable share</div><div class="card"><div class="big">INR 80,000</div>Estimated net savings</div><div class="card"><div class="big">26 tonnes</div>Estimated avoided CO2e</div></div><p>40,000 × 8 − 240,000 = INR 80,000. Emissions: 40,000 × (0.70 − 0.05) = 26,000 kg CO2e.</p><p>Actual estimates require delivered energy, marginal tariffs, all incremental renewable costs and approved emission factors. An invoice by itself does not establish realized savings or certified carbon reductions.</p><h2>Next milestone</h2><p>Label representative invoices, evaluate unseen documents, reconcile monthly accounts and renewable adjustments, then expand the review interface and trend analysis.</p></section></main></html>''')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n'.join(parts),encoding='utf-8')
    return target
