"""PDF inventory and local Tesseract OCR; no model inference."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import pymupdf


def inventory(folder: Path):
    result = []
    for path in sorted(folder.rglob("*.pdf")):
        row = {"file": str(path)}
        try:
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError("Encrypted PDF requires a password")
                row.update(
                    pages=len(doc),
                    text_pages=sum(len(p.get_text().strip()) >= 80 for p in doc),
                )
        except Exception as exc:
            row["error"] = str(exc)
        result.append(row)
    return result


def ocr_page(page):
    executable = shutil.which("tesseract")
    if not executable:
        candidate = (
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "Tesseract-OCR/tesseract.exe"
        )
        executable = str(candidate) if candidate.is_file() else None
    if not executable:
        raise ValueError(
            "Local Tesseract OCR is not installed; use --vision-model instead"
        )
    with tempfile.TemporaryDirectory(prefix="billintel-") as folder:
        image = Path(folder) / "page.png"
        page.get_pixmap(dpi=220).save(image)
        result = subprocess.run(
            [executable, str(image), "stdout", "-l", "eng", "--psm", "3"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.stdout.strip()
