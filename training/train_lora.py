"""Bounded, response-only LoRA training on reviewed electricity-bill examples."""

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import random
import time

# Disable external experiment tracking and Hub telemetry; no private data is uploaded.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("WANDB_DISABLED", "true")

from training.prepare_data import (
    read_jsonl,
    validated_records,
    assert_no_leakage,
    prompt_for,
)


def encode_example(tokenizer, messages, max_length):
    prompt = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, add_generation_prompt=True
    )
    complete = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=False
    )
    if complete[: len(prompt)] != prompt:
        raise ValueError(
            "Chat template prefix mismatch; response masking would be wrong"
        )
    if len(complete) > max_length:
        raise ValueError(
            f"Example is {len(complete)} tokens, exceeds {max_length}; shorten/review input, never silently truncate targets"
        )
    if len(complete) <= len(prompt):
        raise ValueError("Empty assistant target")
    return {
        "input_ids": complete,
        "labels": [-100] * len(prompt) + complete[len(prompt) :],
    }


def response_loss(model, example):
    import torch

    # Only project the final prompt position + answer positions into the large
    # vocabulary. The model still attends to the complete bill context.
    answers = [value for value in example["labels"] if value != -100]
    inputs = torch.tensor([example["input_ids"]], dtype=torch.long)
    outputs = model(input_ids=inputs, logits_to_keep=len(answers) + 1)
    # Position before each answer token predicts that token (causal shift).
    logits = outputs.logits[:, :-1, :].contiguous()
    targets = torch.tensor(answers, dtype=torch.long)
    return torch.nn.functional.cross_entropy(logits.view(-1, logits.size(-1)), targets)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()
    if args.steps < 1 or args.threads < 1 or args.max_length < 32:
        raise ValueError("Invalid training limits")
    if args.output.exists():
        raise ValueError(
            "Use a new run directory; existing checkpoints are never overwritten"
        )
    rows = {
        name: read_jsonl(args.data / f"{name}.jsonl")
        for name in ["train", "validation", "test"]
    }
    if any(not value for value in rows.values()):
        raise ValueError("Train, validation and test must all be nonempty")
    for subset in rows.values():
        if len(validated_records(subset)) != len(subset):
            raise ValueError("Unreviewed training records")
    assert_no_leakage(rows)
    # Import heavy libraries only after data checks pass.
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model

    random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(args.threads)
    cache = Path("output/training/model-cache").resolve()
    load_options = {
        "revision": args.revision,
        "local_files_only": not args.allow_download,
        "cache_dir": str(cache),
        "trust_remote_code": False,
    }
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, **load_options)
    encoded = {
        name: [
            encode_example(
                tokenizer,
                [
                    {"role": "user", "content": prompt_for(r["text"])},
                    {
                        "role": "assistant",
                        "content": json.dumps(r["target"], ensure_ascii=False),
                    },
                ],
                args.max_length,
            )
            for r in subset
        ]
        for name, subset in rows.items()
        if name != "test"
    }
    print(
        "Token lengths:",
        {k: [len(x["input_ids"]) for x in v] for k, v in encoded.items()},
        flush=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch.float32,
        attn_implementation="sdpa",
        **load_options,
    )
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
            bias="none",
        ),
    )
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print("CPU training; trainable adapter parameters:", trainable, flush=True)

    def validation_loss():
        model.eval()
        loss_sum = 0
        tokens = 0
        with torch.no_grad():
            for example in encoded["validation"]:
                count = sum(v != -100 for v in example["labels"][1:])
                loss = response_loss(model, example).item()
                loss_sum += loss * count
                tokens += count
        return loss_sum / tokens

    args.output.mkdir(parents=True)
    started = time.monotonic()
    baseline = validation_loss()
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=args.learning_rate
    )
    steps = []
    for index in range(args.steps):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        example = encoded["train"][index % len(encoded["train"])]
        loss = response_loss(model, example)
        if not torch.isfinite(loss):
            raise ValueError("Nonfinite training loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        entry = {
            "step": index + 1,
            "loss": float(loss.detach()),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
        steps.append(entry)
        print(json.dumps(entry), flush=True)
        (args.output / "progress.json").write_text(
            json.dumps(steps, indent=2), encoding="utf-8"
        )
    final = validation_loss()
    model.save_pretrained(args.output / "adapter", safe_serialization=True)
    tokenizer.save_pretrained(args.output / "adapter")
    report = {
        "base_model": args.base_model,
        "resolved_revision": getattr(model.config, "_commit_hash", None),
        "device": "cpu",
        "library_versions": {
            name: version(name)
            for name in ["torch", "transformers", "peft", "accelerate", "pydantic"]
        },
        "dataset_sha256": {
            name: hashlib.sha256((args.data / f"{name}.jsonl").read_bytes()).hexdigest()
            for name in rows
        },
        "seed": 42,
        "steps": args.steps,
        "trainable_parameters": trainable,
        "example_counts": {k: len(v) for k, v in rows.items()},
        "base_validation_loss": baseline,
        "adapter_validation_loss": final,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "status": "experimental adapter saved; not deployed",
        "limitations": [
            "Tiny bootstrap data; assistant-reviewed, not independently labeled.",
            "Validation loss is not field extraction accuracy. Test split was not used for optimization.",
            "No claim of improvement over the dashboard model; evaluate held-out generation before deployment.",
        ],
        "settings": {
            "rank": 8,
            "alpha": 16,
            "dropout": 0.05,
            "learning_rate": args.learning_rate,
            "max_length": args.max_length,
        },
        "history": steps,
    }
    (args.output / "training-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
