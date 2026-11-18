"""Merge an evaluated local adapter and import an explicitly experimental Ollama model."""

import argparse
import json
import os
from pathlib import Path
import subprocess

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--name", default="greenworks-billreader-experimental:v2")
    args = parser.parse_args()
    report = json.loads((args.run / "training-report.json").read_text(encoding="utf-8"))
    evaluation = json.loads(
        (args.run / "generation-evaluation.json").read_text(encoding="utf-8")
    )
    if evaluation.get("experimental_import_eligible") is not True:
        print(
            "Import skipped: generation checks did not pass. Existing dashboard model retained."
        )
        return
    from billintel.ollama_client import local_models

    if args.name in local_models():
        raise ValueError("Ollama model name already exists; refusing overwrite")
    destination = args.run / "merged"
    if destination.exists():
        raise ValueError("Merged weights already exist; refusing overwrite")
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    torch.set_num_threads(4)
    options = dict(
        local_files_only=True,
        trust_remote_code=False,
        cache_dir=str(Path("output/training/model-cache").resolve()),
        revision=report["resolved_revision"],
    )
    model = AutoModelForCausalLM.from_pretrained(
        report["base_model"], dtype=torch.float32, **options
    )
    model = PeftModel.from_pretrained(model, args.run / "adapter")
    merged = model.merge_and_unload(safe_merge=True).to(torch.float16)
    merged.save_pretrained(destination, safe_serialization=True)
    tokenizer = AutoTokenizer.from_pretrained(report["base_model"], **options)
    tokenizer.save_pretrained(destination)
    modelfile = destination / "Modelfile"
    modelfile.write_text(
        'FROM .\nTEMPLATE """{{ range .Messages }}<|im_start|>{{ .Role }}\n{{ .Content }}<|im_end|>\n{{ end }}<|im_start|>assistant\n"""\nPARAMETER stop "<|im_end|>"\nPARAMETER stop "<|im_start|>"\nPARAMETER temperature 0\nPARAMETER num_ctx 8192\n',
        encoding="utf-8",
    )
    executable = Path(os.environ["LOCALAPPDATA"]) / "Programs/Ollama/ollama.exe"
    subprocess.run(
        [str(executable), "create", args.name, "-f", str(modelfile.resolve())],
        cwd=destination,
        check=True,
    )
    (args.run / "import-report.json").write_text(
        json.dumps(
            {
                "name": args.name,
                "status": "Imported locally; experimental, not selected as dashboard default",
                "evaluation": str((args.run / "generation-evaluation.json").resolve()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
