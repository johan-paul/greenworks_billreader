import io
import json
import time
import pymupdf
import pytest
from billintel.dashboard import create_app

@pytest.fixture
def client(tmp_path):
    app=create_app(tmp_path)
    app.config.update(TESTING=True)
    return app.test_client()

def pdf_bytes(text='High Tension Bill for the Month of April 2025\nNet Amount Payable 900.00\nSynthetic invoice information for local dashboard testing.'):
    with pymupdf.open() as doc:
        p=doc.new_page();p.insert_text((40,40),text)
        return doc.tobytes()

def test_upload_validation(client):
    assert client.post('/api/upload').status_code==400
    assert client.post('/api/upload',data={'file':(io.BytesIO(b'bad'),'bill.pdf')}).status_code==400
    assert client.post('/api/upload',data={'file':(io.BytesIO(pdf_bytes()),'bill.pdf'),'limit':'-1'}).status_code==400
    assert client.post('/api/upload',data={'file':(io.BytesIO(pdf_bytes()),'bill.pdf'),'engine':'remote'}).status_code==400

def test_local_origin_and_unknown_job(client):
    assert client.get('/api/health',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/api/scenario',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/jobs/missing').status_code==404

def test_upload_to_exports_end_to_end(client):
    response=client.post('/api/upload',data={'file':(io.BytesIO(pdf_bytes()),'../../bill.pdf'),'engine':'rules'})
    assert response.status_code==202
    job_id=response.json['id']
    for _ in range(100):
        state=client.get('/api/jobs/'+job_id).json
        if state['status'] not in {'queued','running'}:break
        time.sleep(.1)
    assert state['status']=='done'
    assert state['name']=='bill.pdf'
    assert state['result']['pages'][0]['data']['total_payable']['value']==900
    assert state['result']['source']=='bill.pdf'
    assert client.get(f'/api/jobs/{job_id}/pages/1').mimetype=='image/png'
    assert client.get(f'/api/jobs/{job_id}/pages/2').status_code==404
    for kind in ['json','csv','html']:
        result=client.get(f'/api/jobs/{job_id}/download/{kind}')
        assert result.status_code==200
        assert 'attachment' in result.headers['Content-Disposition']
        assert b'900' in result.data

def test_scenario_endpoint_requires_review(client):
    from pathlib import Path
    payload=json.loads(Path('examples/scenario.json').read_text())
    result=client.post('/api/scenario',json=payload)
    assert result.json['estimated_net_savings_inr']==80000
    payload['reviewed']=False
    assert client.post('/api/scenario',json=payload).status_code==400
