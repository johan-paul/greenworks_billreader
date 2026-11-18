"""Prepare draft annotations and build leakage-checked supervised examples."""

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
import pymupdf
from billintel.documents import ocr_page
from billintel.extraction import PROMPT
from billintel.rules import parse_rules
from billintel.schema import PageExtraction, review_issues


def read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )


def prompt_for(text):
    return (
        PROMPT
        + json.dumps(PageExtraction.model_json_schema())
        + "\n<bill_page>\n"
        + text
        + "\n</bill_page>"
    )


def prepare(folder, output, use_ocr=False):
    if output.exists():
        raise ValueError(
            "Draft file already exists; choose a new path so annotations are not overwritten"
        )
    records = []
    for source in sorted(folder.rglob("*.pdf")):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        try:
            with pymupdf.open(source) as pdf:
                if pdf.needs_pass:
                    raise ValueError("Encrypted PDF")
                for index, page in enumerate(pdf):
                    text = page.get_text(sort=True).strip()
                    method = "text"
                    if len(text) < 80:
                        method = "ocr" if use_ocr else "needs_ocr"
                        if use_ocr:
                            text = ocr_page(page)
                    parsed = parse_rules(text) if len(text) >= 80 else None
                    records.append(
                        {
                            "id": f"{digest}:{index+1}",
                            "source": str(source.resolve()),
                            "document_sha256": digest,
                            "page": index + 1,
                            "text": text,
                            "method": method,
                            "candidate": parsed[0].model_dump() if parsed else None,
                            "target": None,
                            "reviewed": False,
                            "reviewer": None,
                            "review_notes": "",
                            "group_id": digest,
                        }
                    )
        except Exception as exc:
            records.append(
                {"source": str(source.resolve()), "error": str(exc), "reviewed": False}
            )
    write_jsonl(output, records)
    return {
        "records": len(records),
        "draft_candidates": sum(bool(r.get("candidate")) for r in records),
        "needs_ocr": sum(r.get("method") == "needs_ocr" for r in records),
        "reviewed": 0,
        "errors": sum("error" in r for r in records),
    }


def validated_records(records):
    ready = []
    seen = set()
    for row in records:
        if row.get("reviewed") is not True:
            continue
        if not row.get("reviewer") or not row.get("review_notes"):
            raise ValueError("Reviewed records require a reviewer and review notes")
        if not row.get("group_id") or not row.get("document_sha256"):
            raise ValueError("Document and grouping identities are required")
        if row.get("id") in seen:
            raise ValueError("Duplicate record ID")
        seen.add(row["id"])
        if row.get("method") == "needs_ocr" or len(row.get("text", "").strip()) < 40:
            raise ValueError("Record has no usable text/OCR")
        target = PageExtraction.model_validate(row["target"])
        issues = review_issues(target, row["text"])
        if any(
            "quote not found" in x
            or "number is absent" in x
            or "source label is absent" in x
            for x in issues
        ):
            raise ValueError(f"Unsupported numeric evidence in {row['id']}")
        ready.append({**row, "target": target.model_dump()})
    return ready


def leakage_keys(row):
    keys = ["doc:" + row["document_sha256"], "group:" + row["group_id"]]
    normalized = re.sub(r"\s+", " ", row["text"]).strip().lower()
    keys.append("text:" + hashlib.sha256(normalized.encode()).hexdigest())
    target = row["target"]
    # Consumption annexures can lack invoice IDs and differ slightly between
    # monthly PDFs and quarterly compilations. Keep the same account/month
    # together even when text hashes differ. Conservative over-grouping is OK.
    if (
        target.get("document_type") == "grid"
        and target.get("account_number")
        and target.get("billing_period")
    ):
        period = re.sub(r"[^a-z0-9]", "", target["billing_period"].lower())
        keys.append("grid-period:" + target["account_number"].strip() + ":" + period)
    if target.get("invoice_number") and (
        target.get("account_number") or target.get("consumer")
    ):
        keys.append(
            "invoice:"
            + str(
                (
                    target.get("account_number") or target["consumer"],
                    target.get("supplier"),
                    target["invoice_number"],
                )
            )
        )
    return keys


def assert_no_leakage(splits):
    owners = {}
    for name, rows in splits.items():
        for row in rows:
            for key in leakage_keys(row):
                if key in owners and owners[key] != name:
                    raise ValueError(
                        "Split leakage: same document, group, invoice or text crosses splits"
                    )
                owners[key] = name


def build(records, destination, seed=42):
    if destination.exists():
        raise ValueError("Output directory exists; use a new versioned directory")
    ready = validated_records(records)
    # Union all document, invoice, reviewed group and identical-text relationships.
    parents = list(range(len(ready)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners = {}
    for i, row in enumerate(ready):
        for key in leakage_keys(row):
            if key in owners:
                parents[find(i)] = find(owners[key])
            else:
                owners[key] = i
    groups = {}
    for i, row in enumerate(ready):
        groups.setdefault(find(i), []).append(row)
    grouped = list(groups.values())
    if len(grouped) < 3:
        raise ValueError(
            "Need at least 3 independently grouped, reviewed documents for train/validation/test"
        )
    random.Random(seed).shuffle(grouped)
    n_test = max(1, round(len(grouped) * 0.1))
    n_val = max(1, round(len(grouped) * 0.1))
    splits = {
        "test": [r for g in grouped[:n_test] for r in g],
        "validation": [r for g in grouped[n_test : n_test + n_val] for r in g],
        "train": [r for g in grouped[n_test + n_val :] for r in g],
    }
    assert_no_leakage(splits)
    destination.mkdir(parents=True)
    for name, rows in splits.items():
        write_jsonl(
            destination / f"{name}.jsonl",
            [
                {
                    **r,
                    "messages": [
                        {"role": "user", "content": prompt_for(r["text"])},
                        {
                            "role": "assistant",
                            "content": json.dumps(r["target"], ensure_ascii=False),
                        },
                    ],
                }
                for r in rows
            ],
        )
    manifest = {
        "seed": seed,
        "groups": len(grouped),
        "counts": {k: len(v) for k, v in splits.items()},
        "purpose": "experimental bootstrap; not an independent accuracy benchmark",
        "label_reviewers": sorted({r["reviewer"] for r in ready}),
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("draft")
    p.add_argument("folder", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--ocr", action="store_true")
    p = sub.add_parser("build")
    p.add_argument("annotations", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = (
        prepare(args.folder, args.output, args.ocr)
        if args.command == "draft"
        else build(read_jsonl(args.annotations), args.output, args.seed)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
