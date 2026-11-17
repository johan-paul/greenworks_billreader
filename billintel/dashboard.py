"""Local upload dashboard. Run with python -m billintel.dashboard."""

from __future__ import annotations
from pathlib import Path
import threading
import uuid
from urllib.parse import urlparse
import pymupdf
from flask import Flask, jsonify, request, abort, Response
from .analytics import Scenario, analyze
from .ollama_client import api
from .jobs import result_for, run_job
from .exports import render_export

ROOT = Path(__file__).resolve().parents[1]
PDF_LOCK = threading.Lock()


def create_app(storage=None):
    app = Flask(__name__, static_folder="web", static_url_path="/assets")
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    app.config["STORAGE"] = Path(storage or ROOT / "output/dashboard")
    app.config["STORAGE"].mkdir(parents=True, exist_ok=True)
    jobs = {}
    app.extensions["jobs"] = jobs

    @app.before_request
    def local_only():
        if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            abort(403)
        if request.method == "POST" and request.headers.get("Origin"):
            if urlparse(request.headers["Origin"]).netloc != request.host:
                abort(403)

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="PDF exceeds the 30 MB upload limit."), 413

    @app.get("/")
    def home():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        try:
            models = [
                m["name"]
                for m in api("/api/tags", timeout=2)["models"]
                if "cloud" not in m["name"].lower()
            ]
            return jsonify(app="greenworks", ollama=True, models=models)
        except Exception:
            return jsonify(app="greenworks", ollama=False, models=[])

    def get_job(job_id):
        if job_id not in jobs:
            abort(404)
        return jobs[job_id]

    @app.post("/api/upload")
    def upload():
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".pdf"):
            return jsonify(error="Choose a PDF bill."), 400
        engine = request.form.get("engine", "hybrid")
        if engine not in {"hybrid", "rules", "llm"}:
            return jsonify(error="Invalid extraction mode."), 400
        try:
            limit = int(request.form.get("limit", "0"))
        except ValueError:
            return jsonify(error="Page limit must be a whole number."), 400
        if limit < 0:
            return jsonify(error="Page limit cannot be negative."), 400
        if sum(j["status"] in {"queued", "running"} for j in jobs.values()) >= 3:
            return (
                jsonify(error="Three jobs are already queued. Wait for one to finish."),
                429,
            )
        content = file.read()
        try:
            with PDF_LOCK, pymupdf.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass:
                    return (
                        jsonify(
                            error="Password-protected PDFs are not supported. Upload an unlocked copy."
                        ),
                        400,
                    )
                count = len(doc)
                if not 1 <= count <= 100:
                    return jsonify(error="Upload between 1 and 100 pages per PDF."), 400
        except Exception:
            return jsonify(error="This file could not be read as a PDF."), 400
        job_id = uuid.uuid4().hex
        folder = app.config["STORAGE"] / job_id
        folder.mkdir()
        (folder / "upload.pdf").write_bytes(content)
        job = {
            "id": job_id,
            "name": Path(file.filename.replace("\\", "/")).name,
            "folder": folder,
            "pages": count,
            "limit": min(limit or count, count),
            "engine": engine,
            "model": request.form.get("model") or "llama3.1:8b",
            "status": "queued",
        }
        jobs[job_id] = job
        threading.Thread(target=run_job, args=(job,), daemon=True).start()
        return jsonify(id=job_id), 202

    @app.get("/api/jobs/<job_id>")
    def status(job_id):
        job = get_job(job_id)
        result = result_for(job)
        if result:
            result["source"] = job["name"]
        return jsonify(**{k: v for k, v in job.items() if k != "folder"}, result=result)

    @app.get("/api/jobs/<job_id>/pages/<int:page>")
    def preview(job_id, page):
        job = get_job(job_id)
        if not 1 <= page <= job["pages"]:
            abort(404)
        with PDF_LOCK, pymupdf.open(job["folder"] / "upload.pdf") as doc:
            image = doc[page - 1].get_pixmap(dpi=105).tobytes("png")
        return Response(image, mimetype="image/png")

    @app.get("/api/jobs/<job_id>/download/<kind>")
    def download(job_id, kind):
        job = get_job(job_id)
        result = result_for(job)
        if not result:
            return jsonify(error="No processed pages yet."), 409
        result["source"] = job["name"]
        if kind not in {"json", "csv", "html"}:
            abort(404)
        body, mime, extension = render_export(result, job["name"], kind)
        return Response(
            body,
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="greenworks-report.{extension}"'
            },
        )

    @app.post("/api/scenario")
    def scenario():
        try:
            return jsonify(analyze(Scenario.model_validate(request.get_json())))
        except Exception as exc:
            return jsonify(error=str(exc)), 400

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8791, debug=False)
