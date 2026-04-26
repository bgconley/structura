from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from lib.automation.rule_engine import (
    DocumentRuleContext,
    FilingRuleDefinition,
    evaluate_rule,
)
from lib.automation.rule_policy import RuleValidationError, validate_rule_definition
from lib.automation.watched_folder_policy import (
    WatchedFolderPolicyError,
    file_is_stable,
    validate_watch_path,
)


def test_phase6_rule_engine_explains_matches_and_blocks_unwritable_actions() -> None:
    folder_id = uuid4()
    rule = FilingRuleDefinition(
        name="Aetna EOBs",
        conditions=[
            {"field": "document_family", "op": "eq", "value": "medical_eob"},
            {"field": "contacts", "op": "contains", "value": "Aetna"},
            {"field": "canonical.eob.patient_responsibility", "op": "gte", "value": 50},
            {"field": "search_text", "op": "regex", "value": "claim\\s+ABC123"},
        ],
        actions=[
            {"type": "add_folder", "folder_id": str(folder_id)},
            {"type": "add_tag", "tag": "insurance"},
        ],
        review_required=True,
    )
    context = DocumentRuleContext(
        document_id=uuid4(),
        document_family="medical_eob",
        document_subtype=None,
        counterparty="Aetna",
        tags=["medical"],
        folder_ids=[],
        folder_paths=[],
        contacts=["Aetna Health"],
        canonical_facts={"eob.patient_responsibility": 62.00},
        review_status="user_confirmed",
        sensitivity="medical",
        search_text="Claim ABC123 patient responsibility 62.00",
    )

    result = evaluate_rule(rule, context, writable_folder_ids=set())

    assert result.matched is True
    assert result.review_required is True
    assert [condition.matched for condition in result.conditions] == [True, True, True, True]
    assert result.proposed_actions == [{"type": "add_tag", "tag": "insurance"}]
    assert result.blocked_actions == [
        {
            "type": "add_folder",
            "folder_id": str(folder_id),
            "reason": "Folder is not writable for this actor.",
        }
    ]
    assert "medical" in result.safety_reasons


def test_phase6_rule_validation_rejects_unknown_fields_actions_and_unsafe_regex() -> None:
    with pytest.raises(RuleValidationError, match="Unsupported condition field"):
        validate_rule_definition(
            {
                "name": "bad condition",
                "conditions": [{"field": "raw_document_text", "op": "contains", "value": "x"}],
                "actions": [{"type": "add_tag", "tag": "ok"}],
            }
        )

    with pytest.raises(RuleValidationError, match="Unsupported action type"):
        validate_rule_definition(
            {
                "name": "bad action",
                "conditions": [{"field": "document_family", "op": "eq", "value": "invoice"}],
                "actions": [{"type": "delete_document"}],
            }
        )

    with pytest.raises(RuleValidationError, match="regex"):
        validate_rule_definition(
            {
                "name": "bad regex",
                "conditions": [{"field": "search_text", "op": "regex", "value": "(a+)+"}],
                "actions": [{"type": "add_tag", "tag": "ok"}],
            }
        )


def test_phase6_watched_folder_policy_blocks_managed_paths_and_symlink_escape(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    incoming_root = tmp_path / "incoming"
    watched = incoming_root / "household"
    watched.mkdir(parents=True)
    (runtime_root / "objects" / "canonical").mkdir(parents=True)

    assert (
        validate_watch_path(
            watched,
            runtime_root=runtime_root,
            allowed_roots=[incoming_root],
        )
        == watched.resolve()
    )

    with pytest.raises(WatchedFolderPolicyError, match="managed Structura runtime"):
        validate_watch_path(
            runtime_root / "objects" / "canonical",
            runtime_root=runtime_root,
            allowed_roots=[tmp_path],
        )

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = incoming_root / "escape"
    symlink.symlink_to(outside, target_is_directory=True)
    with pytest.raises(WatchedFolderPolicyError, match="allowed intake roots"):
        validate_watch_path(
            symlink,
            runtime_root=runtime_root,
            allowed_roots=[incoming_root],
        )


def test_phase6_watched_folder_stability_requires_pdf_and_stable_mtime(tmp_path: Path) -> None:
    pdf = tmp_path / "document.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    old_timestamp = time.time() - 120
    os.utime(pdf, (old_timestamp, old_timestamp))

    assert file_is_stable(pdf, min_age_seconds=30) is True

    recent = tmp_path / "recent.pdf"
    recent.write_bytes(b"%PDF-1.7\n%%EOF\n")
    assert file_is_stable(recent, min_age_seconds=30) is False

    text = tmp_path / "not-a-pdf.txt"
    text.write_text("not a pdf", encoding="utf-8")
    old_timestamp = time.time() - 120
    os.utime(text, (old_timestamp, old_timestamp))
    assert file_is_stable(text, min_age_seconds=30) is False
