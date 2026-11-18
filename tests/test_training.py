import json
import pytest
from billintel.schema import PageExtraction
from training.prepare_data import (
    build,
    read_jsonl,
    validated_records,
    assert_no_leakage,
    prompt_for,
)
from training.train_lora import encode_example


def record(identity, page=1):
    target = {key: None for key in PageExtraction.model_fields}
    target.update(document_type="unknown", notes=[])
    return {
        "id": f"{identity}:{page}",
        "document_sha256": identity,
        "group_id": identity,
        "page": page,
        "text": f"Document {identity} page {page}: synthetic source text for testing only. No energy amounts printed.",
        "method": "text",
        "target": target,
        "reviewed": True,
        "reviewer": "test",
        "review_notes": "Synthetic fixture.",
    }


def test_drafts_are_not_training_labels():
    row = record("a")
    row["reviewed"] = False
    assert validated_records([row]) == []


def test_build_keeps_whole_documents_together(tmp_path):
    rows = [record("a", 1), record("a", 2), record("b"), record("c"), record("d")]
    manifest = build(rows, tmp_path / "v1")
    split = {
        name: read_jsonl(tmp_path / "v1" / f"{name}.jsonl")
        for name in ["train", "validation", "test"]
    }
    assert_no_leakage(split)
    assert sum(manifest["counts"].values()) == 5
    assert (
        sum(
            any(r["document_sha256"] == "a" for r in records)
            for records in split.values()
        )
        == 1
    )
    for subset in split.values():
        for row in subset:
            assert row["messages"][0]["content"] == prompt_for(row["text"])
            assert json.loads(row["messages"][1]["content"]) == row["target"]
    with pytest.raises(ValueError, match="exists"):
        build(rows, tmp_path / "v1")


def test_cross_split_duplicate_text_is_rejected():
    a = record("a")
    b = record("b")
    b["text"] = a["text"]
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage({"train": [a], "test": [b]})


def test_numeric_evidence_required():
    row = record("a")
    row["target"]["total_payable"] = {
        "value": 100,
        "unit": "INR",
        "quote": "not found 100",
    }
    with pytest.raises(ValueError, match="evidence"):
        validated_records([row])


def test_duplicate_documents_cannot_supply_three_splits(tmp_path):
    a = record("a")
    b = record("b")
    c = record("c")
    b["text"] = a["text"]
    c["text"] = a["text"]
    with pytest.raises(ValueError, match="at least 3"):
        build([a, b, c], tmp_path / "v1")


def test_response_only_mask_and_no_silent_truncation():
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return [1, 2, 3] if kwargs["add_generation_prompt"] else [1, 2, 3, 4, 5]

    messages = [
        {"role": "user", "content": "bill"},
        {"role": "assistant", "content": "answer"},
    ]
    assert encode_example(Tokenizer(), messages, 10)["labels"] == [
        -100,
        -100,
        -100,
        4,
        5,
    ]
    with pytest.raises(ValueError, match="never silently truncate"):
        encode_example(Tokenizer(), messages, 4)


def test_grid_annexures_for_same_account_month_cannot_cross_splits():
    a, b = record("monthly"), record("quarterly")
    for row in [a, b]:
        row["target"].update(
            document_type="grid", account_number="123", billing_period="MAY-2026"
        )
    b["target"]["billing_period"] = "May 2026"
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage({"train": [a], "test": [b]})
