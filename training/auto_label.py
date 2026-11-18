"""Resumable, local-only pseudo-labeling; never promotes drafts to reviewed data."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from billintel.ollama_client import api, check_model
from billintel.schema import PageExtraction, review_issues
from training.prepare_data import prompt_for, read_jsonl


def check_candidate(target, text, rules=None):
    issues = [x for x in review_issues(target, text) if ":" in x]
    normalized = " ".join(text.lower().split())
    for field in ["supplier", "consumer", "account_number", "invoice_number"]:
        value = getattr(target, field)
        if value and " ".join(value.lower().split()) not in normalized:
            issues.append(f"{field}: text is absent from source")
    for field, expected in (rules or {}).items():
        if field == "notes" or expected is None:
            continue
        actual = getattr(target, field)
        if isinstance(expected, dict):
            if actual is None or (actual.value, actual.unit) != (
                expected["value"],
                expected["unit"],
            ):
                issues.append(f"{field}: disagrees with rule candidate")
        elif actual != expected:
            issues.append(f"{field}: disagrees with rule candidate")
    if not any(isinstance(v, dict) for v in target.model_dump().values()):
        issues.append("coverage: no numeric fields extracted; review page relevance")
    return issues


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    replace_with_retry(temporary, path)


def replace_with_retry(temporary, path):
    # Windows readers/antivirus can briefly hold a destination open.
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.1 * (attempt + 1))


def run(source, output, model, limit=None):
    rows = read_jsonl(source)
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate source IDs")
    check_model(model)
    models = api("/api/tags")["models"]
    digest = next(m["digest"] for m in models if m["name"] == model)
    identity = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "model": model,
        "model_digest": digest,
        "prompt_sha256": hashlib.sha256(prompt_for("").encode()).hexdigest(),
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 16384,
            "num_predict": 2400,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text(encoding="utf-8")) != identity:
            raise ValueError(
                "Resume input/model/prompt differs; use a new output directory"
            )
    else:
        save(manifest, identity)
    # One atomic file per page means interrupted writes do not corrupt the queue.
    pages = output / "pages"
    pages.mkdir(exist_ok=True)
    counts = Counter()
    processed = 0
    for row in rows:
        path = pages / (hashlib.sha256(row["id"].encode()).hexdigest() + ".json")
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
        elif limit is not None and processed >= limit:
            continue
        else:
            started = time.monotonic()
            result = {
                **row,
                "pseudo_target": None,
                "pseudo_issues": [],
                "pseudo_model": model,
                "pseudo_model_digest": digest,
            }
            if row.get("reviewed") is True:
                result["pseudo_status"] = "preserved_reviewed"
            else:
                # Keep target/review provenance untouched. Even passing machine
                # checks cannot establish semantic accuracy or completeness.
                try:
                    if len(row.get("text", "").strip()) < 40:
                        raise ValueError("Insufficient text; needs source/OCR review")
                    if len(row["text"]) > 22000:
                        raise ValueError(
                            "Page exceeds input limit; no silent truncation"
                        )
                    response = api(
                        "/api/chat",
                        {
                            "model": model,
                            "stream": False,
                            "messages": [
                                {"role": "user", "content": prompt_for(row["text"])}
                            ],
                            "format": PageExtraction.model_json_schema(),
                            "options": identity["options"],
                        },
                    )
                    if response.get("done_reason") == "length":
                        raise ValueError(
                            "Generation limit reached; incomplete candidate"
                        )
                    target = PageExtraction.model_validate_json(
                        response["message"]["content"]
                    )
                    issues = check_candidate(target, row["text"], row.get("candidate"))
                    result.update(
                        pseudo_target=target.model_dump(),
                        pseudo_issues=issues,
                        pseudo_status=(
                            "flagged" if issues else "checks_passed_unverified"
                        ),
                    )
                except Exception as exc:
                    result.update(pseudo_status="error", pseudo_issues=[str(exc)])
            result["label_seconds"] = round(time.monotonic() - started, 2)
            save(path, result)
            processed += 1
            print(
                json.dumps(
                    {
                        "page_id": row["id"],
                        "status": result["pseudo_status"],
                        "seconds": result["label_seconds"],
                    }
                ),
                flush=True,
            )
        counts[result["pseudo_status"]] += 1
        save(
            output / "progress.json",
            {
                "total": len(rows),
                "completed": sum(counts.values()),
                "counts": dict(counts),
            },
        )
    # Reconstruct in source order. Existing files remain the resumable source of truth.
    with (output / "annotations.jsonl.tmp").open("w", encoding="utf-8") as handle:
        for row in rows:
            path = pages / (hashlib.sha256(row["id"].encode()).hexdigest() + ".json")
            if path.exists():
                handle.write(
                    json.dumps(
                        json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False
                    )
                    + "\n"
                )
    replace_with_retry(output / "annotations.jsonl.tmp", output / "annotations.jsonl")
    return dict(counts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("limit must be positive")
    print(json.dumps(run(args.source, args.output, args.model, args.limit), indent=2))


if __name__ == "__main__":
    main()
