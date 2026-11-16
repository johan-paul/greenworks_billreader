"""Local upload dashboard. Run with python -m billintel.dashboard."""
from __future__ import annotations
import csv
import html
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from urllib.parse import urlparse
import pymupdf
from flask import Flask, jsonify, request, send_file, abort, Response
from .analytics import Scenario, analyze
from .extraction import api

ROOT = Path(__file__).resolve().parents[1]
PDF_LOCK = threading.Lock()
WORKER_LOCK = threading.Lock()

def create_app(storage=None):
    app=Flask(__name__,static_folder='web',static_url_path='/assets')
    app.config['MAX_CONTENT_LENGTH']=30*1024*1024
    app.config['STORAGE']=Path(storage or ROOT/'output/dashboard')
    app.config['STORAGE'].mkdir(parents=True,exist_ok=True)
    jobs={}
    app.extensions['jobs']=jobs

    @app.before_request
    def local_only():
        if request.host.split(':')[0] not in {'127.0.0.1','localhost'}:
            abort(403)
        if request.method=='POST' and request.headers.get('Origin'):
            if urlparse(request.headers['Origin']).netloc != request.host: abort(403)

    @app.errorhandler(413)
    def too_large(error): return jsonify(error='PDF exceeds the 30 MB upload limit.'),413

    @app.get('/')
    def home(): return app.send_static_file('index.html')

    @app.get('/api/health')
    def health():
        try:
            models=[m['name'] for m in api('/api/tags',timeout=2)['models'] if 'cloud' not in m['name'].lower()]
            return jsonify(app="greenworks",ollama=True,models=models)
        except Exception:
            return jsonify(app="greenworks",ollama=False,models=[])

    def get_job(job_id):
        if job_id not in jobs: abort(404)
        return jobs[job_id]

    def result_for(job):
        matches=list(job['folder'].glob('result/*.json'))
        if not matches:return None
        return json.loads(matches[0].read_text(encoding='utf-8'))

    def worker(job):
        try:
            with WORKER_LOCK:
                job['status']='running'
                command=[sys.executable,'-m','billintel.cli','extract',str(job['folder']/'upload.pdf'),
                    '--output',str(job['folder']/'result'),'--engine',job['engine'],'--model',job['model'],
                    '--ocr','--max-pages',str(job['limit'])]
                with (job['folder']/'processing.log').open('w',encoding='utf-8') as log:
                    process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=log,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=max(900,job['limit']*650))
                result=result_for(job)
                job['status']='done' if process.returncode==0 else 'partial' if result else 'error'
                if not result: job['error']='Processing failed. Check that Ollama is running and the model is installed.'
        except Exception as exc:
            job.update(status='error',error=str(exc))

    @app.post('/api/upload')
    def upload():
        file=request.files.get('file')
        if not file or not file.filename.lower().endswith('.pdf'):return jsonify(error='Choose a PDF bill.'),400
        engine=request.form.get('engine','hybrid')
        if engine not in {'hybrid','rules','llm'}:return jsonify(error='Invalid extraction mode.'),400
        try:limit=int(request.form.get('limit','0'))
        except ValueError:return jsonify(error='Page limit must be a whole number.'),400
        if limit<0:return jsonify(error='Page limit cannot be negative.'),400
        if sum(j['status'] in {'queued','running'} for j in jobs.values())>=3:
            return jsonify(error='Three jobs are already queued. Wait for one to finish.'),429
        content=file.read()
        try:
            with PDF_LOCK, pymupdf.open(stream=content,filetype='pdf') as doc:
                if doc.needs_pass:return jsonify(error='Password-protected PDFs are not supported. Upload an unlocked copy.'),400
                count=len(doc)
                if not 1<=count<=100:return jsonify(error='Upload between 1 and 100 pages per PDF.'),400
        except Exception:return jsonify(error='This file could not be read as a PDF.'),400
        job_id=uuid.uuid4().hex
        folder=app.config['STORAGE']/job_id
        folder.mkdir()
        (folder/'upload.pdf').write_bytes(content)
        job={'id':job_id,'name':Path(file.filename.replace('\\','/')).name,'folder':folder,'pages':count,
             'limit':min(limit or count,count),'engine':engine,'model':request.form.get('model') or 'llama3.1:8b','status':'queued'}
        jobs[job_id]=job
        threading.Thread(target=worker,args=(job,),daemon=True).start()
        return jsonify(id=job_id),202

    @app.get('/api/jobs/<job_id>')
    def status(job_id):
        job=get_job(job_id)
        result=result_for(job)
        if result:result['source']=job['name']
        return jsonify(**{k:v for k,v in job.items() if k!='folder'},result=result)

    @app.get('/api/jobs/<job_id>/pages/<int:page>')
    def preview(job_id,page):
        job=get_job(job_id)
        if not 1<=page<=job['pages']:abort(404)
        with PDF_LOCK, pymupdf.open(job['folder']/'upload.pdf') as doc:
            image=doc[page-1].get_pixmap(dpi=105).tobytes('png')
        return Response(image,mimetype='image/png')

    @app.get('/api/jobs/<job_id>/download/<kind>')
    def download(job_id,kind):
        job=get_job(job_id);result=result_for(job)
        if not result:return jsonify(error='No processed pages yet.'),409
        result['source']=job['name']
        if kind=='json':
            body=json.dumps(result,indent=2);mime='application/json';extension='json'
        elif kind=='csv':
            output=io.StringIO();writer=csv.writer(output)
            writer.writerow(['page','status','field','value','unit','evidence'])
            def safe(value):
                value=str(value)
                return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
            for page in result['pages']:
                if page['status']=='error':writer.writerow([page['page'],'error','error',safe(page['error']),'',''])
                for field,value in page.get('data',{}).items():
                    if value is None or field=='notes':continue
                    cells=[value.get('value'),value.get('unit'),value.get('quote')] if isinstance(value,dict) else [value,'','']
                    writer.writerow([page['page'],page['status'],field,*map(safe,cells)])
                for field,value in page.get('derived',{}).items():
                    writer.writerow([page['page'],'derived',field,value['value'],value['unit'],safe(value['formula'])])
            body=output.getvalue();mime='text/csv';extension='csv'
        elif kind=='html':
            esc=lambda v:html.escape(str(v))
            body=f'<!doctype html><meta charset="utf-8"><title>Greenworks bill report</title><style>body{{font:16px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#173e35}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #ddd}}code{{white-space:pre-wrap}}section{{break-inside:avoid;margin-bottom:40px}}</style><h1>Greenworks · Bill report</h1><p>{esc(job["name"])}</p><p>Processed {result["processed_pages"]} of {result["page_count"]} pages. Review required; no cross-page totals are assumed.</p>'
            for page in result['pages']:
                body+=f'<section><h2>Page {page["page"]} · {esc(page["status"])}</h2>'
                if page['status']=='error':body+=f'<p>{esc(page["error"])}</p>'
                body+='<table><tr><th>Field</th><th>Value</th><th>Evidence</th></tr>'
                for field,value in page.get('data',{}).items():
                    if value is None or field=='notes':continue
                    display=f'{value["value"]:,.3f} {value["unit"]}' if isinstance(value,dict) else value
                    quote=value.get('quote','') if isinstance(value,dict) else ''
                    body+=f'<tr><td>{esc(field)}</td><td>{esc(display)}</td><td>{esc(quote)}</td></tr>'
                body+='</table>'
                for field,value in page.get('derived',{}).items():body+=f'<p><b>{esc(field)}: {value["value"]:,.3f} {esc(value["unit"])}</b> — {esc(value["formula"])}. {esc(value["warning"])}</p>'
                body+='<ul>'+''.join(f'<li>{esc(issue)}</li>' for issue in page.get('issues',[])+page.get('data',{}).get('notes',[]))+'</ul></section>'
            body+='<p>Savings and emissions cannot be established from an unreconciled bill alone. Use reviewed delivered energy, costs, tariffs and sourced emission factors.</p>'
            mime='text/html';extension='html'
        else:abort(404)
        return Response(body,mimetype=mime,headers={'Content-Disposition':f'attachment; filename="greenworks-report.{extension}"'})

    @app.post('/api/scenario')
    def scenario():
        try:return jsonify(analyze(Scenario.model_validate(request.get_json())))
        except Exception as exc:return jsonify(error=str(exc)),400

    return app

if __name__=='__main__':
    create_app().run(host='127.0.0.1',port=8791,debug=False)
