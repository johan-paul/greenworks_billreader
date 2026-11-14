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
