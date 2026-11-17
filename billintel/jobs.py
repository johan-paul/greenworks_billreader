"""Background job execution. One extraction subprocess runs at a time."""

import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
WORKER_LOCK = threading.Lock()


def result_for(job):
    matches = list(job["folder"].glob("result/*.json"))
    if not matches:
        return None
    return json.loads(matches[0].read_text(encoding="utf-8"))


def run_job(job):
    try:
        with WORKER_LOCK:
            job["status"] = "running"
            command = [
                sys.executable,
                "-m",
                "billintel.cli",
                "extract",
                str(job["folder"] / "upload.pdf"),
                "--output",
                str(job["folder"] / "result"),
                "--engine",
                job["engine"],
                "--model",
                job["model"],
                "--ocr",
                "--max-pages",
                str(job["limit"]),
            ]
            with (job["folder"] / "processing.log").open("w", encoding="utf-8") as log:
                process = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    timeout=max(900, job["limit"] * 650),
                )
            result = result_for(job)
            job["status"] = (
                "done" if process.returncode == 0 else "partial" if result else "error"
            )
            if not result:
                job["error"] = (
                    "Processing failed. Check that Ollama is running and the model is installed."
                )
    except Exception as exc:
        job.update(status="error", error=str(exc))
