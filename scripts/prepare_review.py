"""Reproducible review demo. Private outputs stay under output/ and out of Git."""
from pathlib import Path
import json
from collections import Counter
from billintel.extraction import extract, inventory
from billintel.rules import parse_rules
from billintel.report import build_report
from billintel.analytics import Scenario, analyze
from billintel.evaluation import evaluate
import pymupdf

root=Path(__file__).resolve().parents[1]
folder=root/'EB bills'
out=root/'output/review'
out.mkdir(parents=True,exist_ok=True)
rows=inventory(folder)
summary={'pdfs':len(rows),'pages':sum(r.get('pages',0) for r in rows),'text_pages':sum(r.get('text_pages',0) for r in rows)}
coverage=Counter()
for item in rows:
    if 'error' in item: continue
    with pymupdf.open(item['file']) as pdf:
        for page in pdf:
            text=page.get_text(sort=True)
            if len(text.strip())<80:coverage['needs_ocr_or_blank_review']+=1;continue
            parsed=parse_rules(text)
            coverage[parsed[1]['template'] if parsed else 'unsupported_text_layout']+=1
summary['text_only_rule_coverage']=dict(coverage)
(out/'inventory-summary.json').write_text(json.dumps(summary,indent=2))
for name,limit in [('1001_Electricity Bill_Q1 (4).pdf',2),('Apple India Solar bills.pdf',1),('1.Apr-25.pdf',1),('Bill for8-2024.pdf',1)]:
    matches=list(folder.rglob(name))
    if not matches:raise FileNotFoundError(f'Demo source missing: {name}')
    extract(matches[0],out/'extractions','llama3.1:8b',max_pages=limit,ocr=True,engine='rules')
scenario=Scenario.model_validate_json((root/'examples/scenario.json').read_text())
(out/'synthetic-analysis.json').write_text(json.dumps(analyze(scenario),indent=2))
labels_path=root/'output/reviewed-labels.json'
if labels_path.exists():
    labels=json.loads(labels_path.read_text())
    for candidate in (out/'extractions').glob('*.json'):
        result=json.loads(candidate.read_text())
        if result['sha256']==labels['sha256']:
            evaluation=evaluate(result,labels)
            (out/'evaluation.json').write_text(json.dumps(evaluation,indent=2))
            summary['development_evaluation']={k:evaluation[k] for k in ['correct_fields','evaluated_fields']}
(out/'inventory-summary.json').write_text(json.dumps(summary,indent=2))
report=build_report(out/'extractions',out/'review-demo.html',summary)
print(json.dumps(summary,indent=2))
print('Open:',report)
