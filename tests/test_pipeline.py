import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from billintel.analytics import Scenario, analyze
from billintel.schema import PageExtraction, review_issues
from billintel.extraction import extract
import pymupdf

@pytest.fixture
def scenario():
    return json.loads(Path('examples/scenario.json').read_text())

def test_known_savings_and_emissions(scenario):
    result = analyze(Scenario(**scenario))
    assert result['estimated_net_savings_inr'] == 80000
    assert result['estimated_avoided_emissions_kg_co2e'] == 26000
    assert result['renewable_share_percent'] == 40

def test_zero_consumption(scenario):
    scenario.update(grid_import_kwh=0, solar_used_kwh=0, wind_used_kwh=0)
    assert analyze(Scenario(**scenario))['renewable_share_percent'] is None

@pytest.mark.parametrize('updates', [{'reviewed':False}, {'solar_used_kwh':-1}, {'grid_import_kwh':float('nan')}, {'power_factor':1.1}])
def test_invalid_scenarios(scenario, updates):
    scenario.update(updates)
    with pytest.raises(ValidationError):
        Scenario(**scenario)

def test_negative_savings_are_preserved(scenario):
    scenario['renewable_cost_inr'] = 500000
    assert analyze(Scenario(**scenario))['estimated_net_savings_inr'] == -180000

def test_kvah_and_missing_evidence_are_flagged():
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='grid', notes=[], total_consumption={'value':200, 'unit':'kVAh','quote':'missing'})
    issues = review_issues(PageExtraction(**data), 'Actual page text')
    assert any('kVAh' in issue for issue in issues)
    assert any('quote not found' in issue for issue in issues)
    assert any('number is absent' in issue for issue in issues)

def test_scan_without_vision_is_explicit_error(tmp_path, monkeypatch):
    monkeypatch.setattr('billintel.extraction.check_model', lambda *a, **k: None)
    path = tmp_path / 'scan.pdf'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    target, result = extract(path, tmp_path / 'results', 'test')
    assert target.exists()
    assert result['complete'] is False
    assert result['pages'][0]['status'] == 'error'
    assert 'vision-model' in result['pages'][0]['error']

def test_currency_cannot_be_consumption():
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='grid', notes=[], total_consumption={'value':100, 'unit':'INR','quote':'100'})
    with pytest.raises(ValidationError):
        PageExtraction(**data)

def test_extraction_provenance_and_partial_run(tmp_path, monkeypatch):
    monkeypatch.setattr('billintel.extraction.check_model', lambda *a, **k: None)
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='grid', notes=[], total_consumption={'value':125,'unit':'kWh','quote':'Consumption 125 kWh'})
    captured = []
    def fake_api(endpoint, payload):
        captured.append(payload)
        return {'message': {'content':json.dumps(data)}}
    monkeypatch.setattr('billintel.extraction.api', fake_api)
    path = tmp_path/'bill.pdf'
    with pymupdf.open() as doc:
        for _ in range(2):
            page = doc.new_page()
            page.insert_text((40,40), 'Consumption 125 kWh. ' + 'Printed electricity bill information. '*4)
        doc.save(path)
    _, result = extract(path, tmp_path/'out', 'test', max_pages=1)
    assert result['processed_pages'] == 1
    assert result['page_count'] == 2
    assert result['complete'] is False
    assert result['pages'][0]['page'] == 1
    assert result['pages'][0]['data']['total_consumption']['value'] == 125
    assert len(result['sha256']) == 64
    assert captured[0]['stream'] is False
    assert captured[0]['options']['temperature'] == 0

def test_evaluation_counts_missing_pages_as_failures():
    from billintel.evaluation import evaluate
    report = evaluate({'sha256':'abc','pages':[]}, {'sha256':'abc','pages':[{'page':1,'fields':{'solar_energy':None}}]})
    assert report['field_accuracy'] == 0
    with pytest.raises(ValueError):
        evaluate({'sha256':'abc'}, {'sha256':'different'})

def test_evaluation_requires_units():
    from billintel.evaluation import evaluate
    extraction = {'sha256':'abc','pages':[{'page':1,'status':'needs_review','data':{'total_consumption':{'value':100,'unit':'kVAh'}}}]}
    labels = {'sha256':'abc','pages':[{'page':1,'fields':{'total_consumption':{'value':100,'unit':'kWh'}}}]}
    assert evaluate(extraction, labels)['correct_fields'] == 0

def test_local_ocr_route(tmp_path, monkeypatch):
    monkeypatch.setattr('billintel.extraction.check_model', lambda *a, **k: None)
    monkeypatch.setattr('billintel.extraction.ocr_page', lambda page:'Solar energy 150 kWh supplied during April 2026. Invoice total INR 900.')
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='solar',notes=[],solar_energy={'value':150,'unit':'kWh','quote':'Solar energy 150 kWh'})
    monkeypatch.setattr('billintel.extraction.api', lambda *a, **k:{'message':{'content':json.dumps(data)}})
    path = tmp_path/'scan.pdf'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(path)
    _, result = extract(path,tmp_path/'out','test',ocr=True)
    assert result['complete'] is True
    assert result['pages'][0]['method'] == 'ocr'
    assert result['pages'][0]['data']['solar_energy']['value'] == 150
    assert any('OCR text' in issue for issue in result['pages'][0]['issues'])

def test_llm_unsupported_number_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr('billintel.extraction.check_model', lambda *a, **k:None)
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='grid',notes=[],total_payable={'value':999,'unit':'INR','quote':'Invoice payable INR 100'})
    monkeypatch.setattr('billintel.extraction.api', lambda *a, **k:{'message':{'content':json.dumps(data)}})
    path=tmp_path/'bill.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((40,40),'Invoice payable INR 100. '+ 'Synthetic invoice reference information. '*3)
        doc.save(path)
    _, result=extract(path,tmp_path/'out','test',engine='llm')
    row=result['pages'][0]
    assert row['data']['total_payable'] is None
    assert row['rejected_candidates']['total_payable']['candidate']['value']==999


def test_rules_need_no_model_server(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Rules engine must not call Ollama')
    monkeypatch.setattr('billintel.extraction.api', forbidden)
    path=tmp_path/'bill.pdf'
    with pymupdf.open() as doc:
        page=doc.new_page()
        page.insert_text((40,40),'High Tension Bill for the Month of April 2025\nNet Amount Payable 900.00\nSynthetic invoice information for local test.')
        doc.save(path)
    _, result=extract(path,tmp_path/'out','test',engine='rules')
    assert result['pages'][0]['data']['total_payable']['value']==900
    assert result['pages'][0]['model'] is None

def test_total_consumption_does_not_prove_grid_import():
    data = {name:None for name in PageExtraction.model_fields}
    data.update(document_type='grid',notes=[],grid_import={'value':125,'unit':'kWh','quote':'Total consumption: 125 kWh'})
    assert any('source label is absent' in s for s in review_issues(PageExtraction(**data),'Total consumption: 125 kWh'))
