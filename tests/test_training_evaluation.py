from training.evaluate_adapter import score


def test_invalid_json_does_not_get_credit_for_expected_nulls():
    expected = {"total_payable": None, "notes": []}
    assert score(expected, None)["correct"] == 0
    assert score(expected, {"total_payable": None})["correct"] == 1


def test_numeric_accuracy_requires_matching_unit_and_value():
    expected = {"total_consumption": {"value": 123, "unit": "kWh", "quote": "source"}}
    wrong = {"total_consumption": {"value": 123, "unit": "kVAh"}}
    assert score(expected, wrong)["numeric_correct"] == 0
    correct = {"total_consumption": {"value": 123, "unit": "kWh", "quote": "different"}}
    assert score(expected, correct)["numeric_correct"] == 1
