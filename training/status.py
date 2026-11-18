"""Read local training/labeling progress without starting or modifying jobs."""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import time


def read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def display(root):
    run = root / "runs/reviewed-v2"
    labels = root / "auto-label-v1"
    history = read(run / "progress.json", [])
    report = read(run / "training-report.json", None)
    evaluation = read(run / "generation-evaluation.json", None)
    imported = read(run / "import-report.json", None)
    print("\nUpdated:", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"))
    print(
        "Training:",
        "COMPLETE" if report else "not yet complete",
        f"({history[-1]['step'] if history else 0}/39 steps)",
    )
    if history and not report:
        latest = history[-1]
        age = max(0, time.time() - (run / "progress.json").stat().st_mtime)
        print(f"Last recorded update: {age / 60:.1f} minutes ago")
        if len(history) >= 2:
            seconds = (latest["elapsed_seconds"] - history[0]["elapsed_seconds"]) / (
                len(history) - 1
            )
            print(
                f"Approx. optimizer time remaining: {max(0, 39-latest['step']) * seconds / 60:.0f} minutes; validation/evaluation extra"
            )
        if age > 600:
            print(
                "WARNING: progress is stale; check the process and logs. Completion is not confirmed."
            )
    print("Generation evaluation:", "COMPLETE" if evaluation else "pending or running")
    if evaluation:
        print(
            "Experimental import gate:",
            "passed" if evaluation.get("experimental_import_eligible") else "failed",
        )
    print("Ollama import:", imported["name"] if imported else "not completed")
    counts = Counter()
    durations = []
    for path in (labels / "pages").glob("*.json"):
        row = read(path, {})
        if row.get("pseudo_status"):
            counts[row["pseudo_status"]] += 1
            if row["pseudo_status"] not in {"preserved_reviewed", "error"}:
                durations.append(row["label_seconds"])
    print(
        f"Label queue: {sum(counts.values())}/595 pages processed (includes preserved reviewed pages)"
    )
    print("Statuses:", dict(counts))
    generated = counts["flagged"] + counts["checks_passed_unverified"]
    remaining = max(0, 550 - generated - counts["error"])
    print(
        f"Automatic labeling: {generated}/550 pending-review pages have draft labels; {remaining} attempts remaining"
    )
    if durations:
        print(
            f"Rough labeling compute time remaining: {remaining * sum(durations) / len(durations) / 3600:.1f} hours"
        )
        print(
            "Estimate excludes training/evaluation wait and manual review; page times vary."
        )
    print(
        "Labeling is scheduled AFTER training/evaluation. Saved progress does not prove a worker is currently active."
    )
    print("Follow-up log:", (run / "followup.log").resolve())
    print("Error log:", (run / "followup-error.log").resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("output/training"))
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    try:
        while True:
            display(args.root)
            if not args.watch:
                break
            time.sleep(30)
    except KeyboardInterrupt:
        print("Stopped watching. Training/labeling jobs are unaffected.")


if __name__ == "__main__":
    main()
