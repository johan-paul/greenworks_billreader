import json

import pytest

from billintel.schema import PageExtraction
from training import auto_label
from training.prepare_data import write_jsonl


def target():
    result = {key: None for key in PageExtraction.model_fields}
    result.update(document_type="grid", notes=[])
    result["total_payable"] = {
        "value": 123,
        "unit": "INR",
        "quote": "Total payable INR 123",
    }
    return result


def test_wrong_evidence_and_rule_disagreement_are_flagged():
    value = PageExtraction.model_validate(target())
    issues = auto_label.check_candidate(value, "Total payable INR 321", target())
    assert any("quote not found" in s for s in issues)
    rule = target()
    rule["total_payable"]["value"] = 999
    assert any(
        "disagrees" in s
        for s in auto_label.check_candidate(value, "Total payable INR 123", rule)
    )


def test_resume_preserves_reviewed_labels_and_never_approves_pseudo_labels(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(auto_label, "check_model", lambda model: None)
    calls = []

    def api(path, payload=None):
        if path == "/api/tags":
            return {"models": [{"name": "local", "digest": "abc"}]}
        calls.append(payload)
        return {"message": {"content": json.dumps(target())}, "done_reason": "stop"}

    monkeypatch.setattr(auto_label, "api", api)
    source = tmp_path / "source.jsonl"
    rows = [
        {
            "id": "a",
            "text": "Electricity bill for account 1. Total payable INR 123",
            "reviewed": False,
            "target": None,
        },
        {
            "id": "b",
            "text": "Reviewed source",
            "reviewed": True,
            "target": target(),
            "reviewer": "person",
        },
    ]
    write_jsonl(source, rows)
    output = tmp_path / "labels"
    auto_label.run(source, output, "local")
    auto_label.run(source, output, "local")
    assert len(calls) == 1
    results = auto_label.read_jsonl(output / "annotations.jsonl")
    assert results[0]["pseudo_status"] == "checks_passed_unverified"
    assert results[0]["reviewed"] is False and results[0]["target"] is None
    assert results[1]["target"] == rows[1]["target"]
    assert results[1]["reviewer"] == "person"
    rows[0]["text"] += "changed"
    write_jsonl(source, rows)
    with pytest.raises(ValueError, match="differs"):
        auto_label.run(source, output, "local")
