from __future__ import annotations

import json

import pytest

from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.layout_scoring import continuation_scores
from lib.evaluation.text_scoring import sequence_counts
from tests.unit.evaluation.conftest import evaluate, replace_output


def test_reference_fixture_measures_content_without_claiming_release_or_live_proof(inputs):
    report = evaluate(inputs)
    doc = report["documents"][0]
    assert report["status"] == "computed"
    assert report["threshold_policy"] == "not_ratified"
    assert set(report["unevaluated_stages"].values()) == {"not_evaluated"}
    assert doc["coverage"]["source_pages"] == 2
    assert doc["parse_tokens"]["expected"] == 12
    assert doc["parse_tokens"]["matched"] == 12
    assert doc["searchable_tokens"]["matched"] == 12
    assert doc["pages"][0]["layout"]["geometry"]["mean_iou_with_missing_zero"] == pytest.approx(1)
    assert doc["pages"][0]["layout"]["tables"]["cell_text_exact"] == 4


@pytest.mark.parametrize("change,omitted,inserted", [("remove", 1, 0), ("duplicate", 0, 1)])
def test_repeated_text_occurrences_cannot_collapse_into_a_set(inputs, change, omitted, inserted):
    output = json.loads(inputs[2].raw_pages[0].raw_output)
    if change == "remove":
        output["elements"].pop(1)
    else:
        output["elements"].insert(2, dict(output["elements"][1]))
    report = evaluate(inputs, capture=replace_output(inputs[2], output))
    metric = report["documents"][0]["parse_tokens"]
    assert metric["omitted"] == omitted
    assert metric["inserted"] == inserted


def test_deferred_page_remains_in_coverage_and_readable_recall_denominators(inputs):
    data = inputs[2].model_dump(mode="json")
    page = data["structure"]["pages"][1]
    page.update(
        source=None, state="deferred", diagnostics=["resource_limit"], elements=[], tables=[]
    )
    data["structure"]["invocations"].pop()
    data["raw_pages"].pop()
    data["structure"]["chunks"] = [c for c in data["structure"]["chunks"] if c["page_number"] == 1]
    doc = evaluate(inputs, capture=DocumentCapture.model_validate(data))["documents"][0]
    assert doc["coverage"]["reported_processed_fraction"] == 0.5
    assert doc["coverage"]["state_counts"] == {"deferred": 1, "processed": 1}
    assert doc["parse_tokens"]["expected"] == 12
    assert doc["parse_tokens"]["omitted"] == 4
    assert doc["parse_tokens"]["recall"] == 8 / 12


def test_one_cent_transcription_error_does_not_borrow_arithmetic_tolerance(inputs):
    output = json.loads(inputs[2].raw_pages[0].raw_output)
    output["elements"][3]["table"]["cells"][3]["text"] = "12.51"
    page = evaluate(inputs, capture=replace_output(inputs[2], output))["documents"][0]["pages"][0]
    assert page["text"]["exact_sensitive_text"]["amount"]["matched"] == 0
    assert page["text"]["parse_tokens"]["omitted"] == 1
    assert page["text"]["parse_tokens"]["inserted"] == 1
    assert page["layout"]["tables"]["cell_text_exact"] == 3


def test_wrong_geometry_and_reading_order_do_not_hide_behind_correct_text(inputs):
    output = json.loads(inputs[2].raw_pages[0].raw_output)
    output["elements"][0]["bbox"] = dict(left=500, top=800, right=700, bottom=900)
    output["elements"][0], output["elements"][1] = output["elements"][1], output["elements"][0]
    page = evaluate(inputs, capture=replace_output(inputs[2], output))["documents"][0]["pages"][0]
    assert page["layout"]["reading_order"]["reversed_pairs"] == 1
    assert page["layout"]["geometry"]["mean_iou_with_missing_zero"] < 0.9
    assert page["layout"]["geometry"]["source_pixel_support"] == "not_evaluated"


def test_missing_cell_and_changed_grid_are_measured(inputs):
    output = json.loads(inputs[2].raw_pages[0].raw_output)
    table = output["elements"][3]["table"]
    table["row_count"] = 3
    table["cells"].pop(0)
    table["cells"][-1]["row_span"] = 2
    page = evaluate(inputs, capture=replace_output(inputs[2], output))["documents"][0]["pages"][0]
    scores = page["layout"]["tables"]
    assert scores["grid_exact"] == 0 and scores["grid_expected"] == 1
    assert scores["cells"]["omitted"] == 1
    assert scores["span_exact"] == 2 and scores["span_expected"] == 4


def test_searchable_omission_is_distinct_from_good_parse(inputs):
    data = inputs[2].model_dump(mode="json")
    data["structure"]["chunks"] = data["structure"]["chunks"][:-1]
    doc = evaluate(inputs, capture=DocumentCapture.model_validate(data))["documents"][0]
    assert doc["parse_tokens"]["omitted"] == 0
    assert doc["searchable_tokens"]["omitted"] == 3


def test_uncertain_reference_is_explicitly_unscored_not_perfect_or_wrong(inputs):
    data = inputs[1].model_dump(mode="json")
    data["pages"][1]["regions"][1].update(readability="ambiguous", text="")
    data["pages"][1]["sensitive_text"] = []
    doc = evaluate(inputs, annotation=DocumentAnnotation.model_validate(data))["documents"][0]
    assert doc["coverage"]["source_pages"] == 2
    assert doc["coverage"]["text_not_evaluated_pages"] == 1
    assert doc["pages"][1]["text"]["status"] == "not_evaluated"
    assert doc["parse_tokens"]["expected"] == 8


def test_continuation_groups_use_relations_not_provider_labels_and_count_false_joins():
    result = continuation_scores(
        [
            dict(gold_group="gold-A", actual_group="prediction-X", matched=True),
            dict(gold_group="gold-A", actual_group="prediction-X", matched=True),
            dict(gold_group="gold-B", actual_group="prediction-X", matched=True),
        ]
    )
    assert result == dict(
        expected_links=1, correct_links=1, omitted_links=0, false_joins=2, unrelated_pairs=2
    )


def test_invented_table_cannot_hide_a_false_continuation_link(inputs):
    output = json.loads(inputs[2].raw_pages[0].raw_output)
    output["elements"][3]["table"]["continuation_key"] = "invented-link"
    output["elements"].append(json.loads(json.dumps(output["elements"][3])))
    doc = evaluate(inputs, capture=replace_output(inputs[2], output))["documents"][0]
    assert doc["pages"][0]["layout"]["tables"]["tables"]["inserted"] == 1
    assert doc["continuation"]["false_joins"] == 1


def test_empty_denominators_and_long_page_budget_are_explicit():
    assert sequence_counts("", "")["precision"] is None
    assert sequence_counts("", "")["recall"] is None
    assert sequence_counts("present", "")["recall"] == 0
    with pytest.raises(ValueError, match="budget"):
        sequence_counts("word " * 5001, "word")
