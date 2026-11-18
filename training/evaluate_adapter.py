"""Compare offline base/adapter generations on untouched reviewed test pages."""

import argparse
from contextlib import nullcontext
import json
import math
import os
from pathlib import Path
import time

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("WANDB_DISABLED", "true")

from billintel.schema import PageExtraction, review_issues
from training.prepare_data import (
    read_jsonl,
    validated_records,
    prompt_for,
    assert_no_leakage,
)


def score(expected, actual):
    counts = {
        "fields": 0,
        "correct": 0,
        "numeric_fields": 0,
        "numeric_correct": 0,
        "null_fields": 0,
        "null_correct": 0,
    }
    for field, value in expected.items():
        if field == "notes":
            continue
        got = actual.get(field) if actual is not None else None
        passed = actual is not None and field in actual
        if isinstance(value, dict):
            passed = (
                passed
                and isinstance(got, dict)
                and got.get("unit") == value["unit"]
                and isinstance(got.get("value"), (int, float))
                and math.isclose(got["value"], value["value"], rel_tol=0, abs_tol=0.01)
            )
            counts["numeric_fields"] += 1
            counts["numeric_correct"] += int(bool(passed))
        else:
            passed = passed and got == value
            if value is None:
                counts["null_fields"] += 1
                counts["null_correct"] += int(bool(passed))
        counts["fields"] += 1
        counts["correct"] += int(bool(passed))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    output = args.run / "generation-evaluation.json"
    if output.exists():
        raise ValueError(
            "Evaluation already exists; do not repeatedly tune against test data"
        )
    report = json.loads((args.run / "training-report.json").read_text(encoding="utf-8"))
    import hashlib

    rows = {}
    for name in ["train", "validation", "test"]:
        path = args.data / f"{name}.jsonl"
        if (
            hashlib.sha256(path.read_bytes()).hexdigest()
            != report["dataset_sha256"][name]
        ):
            raise ValueError("Dataset changed since training")
        rows[name] = read_jsonl(path)
        if len(validated_records(rows[name])) != len(rows[name]):
            raise ValueError("Unreviewed evaluation labels")
    assert_no_leakage(rows)
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    torch.set_num_threads(args.threads)
    options = dict(
        local_files_only=True,
        trust_remote_code=False,
        cache_dir=str(Path("output/training/model-cache").resolve()),
        revision=report["resolved_revision"],
    )
    tokenizer = AutoTokenizer.from_pretrained(report["base_model"], **options)
    model = AutoModelForCausalLM.from_pretrained(
        report["base_model"], dtype=torch.float32, attn_implementation="sdpa", **options
    )
    model = PeftModel.from_pretrained(model, args.run / "adapter")
    model.eval()
    model.config.use_cache = True
    results = {"base": [], "adapter": []}
    for label in results:
        with model.disable_adapter() if label == "base" else nullcontext():
            for row in rows["test"]:
                started = time.monotonic()
                inputs = tokenizer.apply_chat_template(
                    [{"role": "user", "content": prompt_for(row["text"])}],
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                )
                with torch.inference_mode():
                    generated = model.generate(
                        inputs,
                        attention_mask=torch.ones_like(inputs),
                        max_new_tokens=1800,
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                raw = tokenizer.decode(
                    generated[0, inputs.shape[1] :], skip_special_tokens=True
                )
                actual, error, issues = None, None, []
                try:
                    parsed = PageExtraction.model_validate_json(raw)
                    actual = parsed.model_dump()
                    issues = [x for x in review_issues(parsed, row["text"]) if ":" in x]
                except ValueError as exc:
                    error = str(exc)
                entry = dict(
                    id=row["id"],
                    raw=raw,
                    schema_valid=actual is not None,
                    evidence_issues=issues,
                    error=error,
                    seconds=round(time.monotonic() - started, 2),
                    **score(row["target"], actual),
                )
                results[label].append(entry)
                print(
                    json.dumps(
                        {
                            "model": label,
                            "id": row["id"],
                            "valid": actual is not None,
                            "seconds": entry["seconds"],
                        }
                    ),
                    flush=True,
                )
                (args.run / "evaluation-progress.json").write_text(
                    json.dumps(results, indent=2), encoding="utf-8"
                )
    totals = {}
    for label, entries in results.items():
        totals[label] = {
            key: sum(e[key] for e in entries)
            for key in [
                "fields",
                "correct",
                "numeric_fields",
                "numeric_correct",
                "null_fields",
                "null_correct",
            ]
        }
        totals[label]["valid_json_pages"] = sum(e["schema_valid"] for e in entries)
        totals[label]["evidence_failure_pages"] = sum(
            bool(e["evidence_issues"]) for e in entries
        )
    eligible = (
        totals["adapter"]["valid_json_pages"] == len(rows["test"])
        and totals["adapter"]["evidence_failure_pages"] == 0
        and totals["adapter"]["numeric_fields"] > 0
        and totals["adapter"]["numeric_correct"] / totals["adapter"]["numeric_fields"]
        >= 0.9
        and totals["adapter"]["numeric_correct"] >= totals["base"]["numeric_correct"]
        and totals["adapter"]["correct"] >= totals["base"]["correct"]
    )
    output.write_text(
        json.dumps(
            {
                "summary": totals,
                "experimental_import_eligible": eligible,
                "scope": "Small assistant-reviewed test set; not an independent benchmark or production approval. No comparison with dashboard 8B model.",
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
