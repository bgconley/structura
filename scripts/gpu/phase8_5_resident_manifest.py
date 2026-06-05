from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID


class ResidentCorpusEntry:
    def __init__(
        self,
        *,
        path: Path,
        gold_metrics: dict[str, Any] | None = None,
        gold_thresholds: dict[str, Any] | None = None,
    ) -> None:
        self.path = path
        self.gold_metrics = gold_metrics
        self.gold_thresholds = gold_thresholds


def resolve_corpus_entries(args: argparse.Namespace) -> list[ResidentCorpusEntry]:
    entries = [ResidentCorpusEntry(path=pdf) for pdf in list(args.pdf or [])]
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        documents = manifest.get("documents") if isinstance(manifest, dict) else None
        if not isinstance(documents, list):
            raise SystemExit("Manifest must contain a documents array.")
        corpus_gold_metrics = _optional_manifest_mapping(
            manifest,
            "goldMetrics",
            location="Manifest",
        )
        corpus_gold_thresholds = _optional_manifest_mapping(
            manifest,
            "goldThresholds",
            location="Manifest",
        )
        if (corpus_gold_metrics is None) != (corpus_gold_thresholds is None):
            raise SystemExit(
                "Manifest must include both goldMetrics and goldThresholds when either is provided."
            )
        for index, item in enumerate(documents, start=1):
            if not isinstance(item, dict) or not item.get("path"):
                raise SystemExit(f"Manifest document {index} is missing a path.")
            entries.append(
                _entry_from_manifest_item(
                    item,
                    index=index,
                    corpus_gold_metrics=corpus_gold_metrics,
                    corpus_gold_thresholds=corpus_gold_thresholds,
                )
            )
    if not entries:
        raise SystemExit("At least one --pdf or --manifest document is required.")
    for entry in entries:
        if not entry.path.exists():
            raise SystemExit(f"PDF does not exist: {entry.path}")
    return entries


def gold_metadata_by_document_id(
    documents: list[dict[str, Any]],
) -> dict[UUID, dict[str, Any]]:
    metadata: dict[UUID, dict[str, Any]] = {}
    for document in documents:
        gold_metrics = document.get("goldMetrics")
        gold_thresholds = document.get("goldThresholds")
        if gold_metrics is None and gold_thresholds is None:
            continue
        if not isinstance(gold_metrics, dict) or not isinstance(gold_thresholds, dict):
            continue
        metadata[UUID(str(document["document_id"]))] = {
            "goldMetrics": dict(gold_metrics),
            "goldThresholds": dict(gold_thresholds),
        }
    return metadata


def _entry_from_manifest_item(
    item: dict[str, Any],
    *,
    index: int,
    corpus_gold_metrics: dict[str, Any] | None,
    corpus_gold_thresholds: dict[str, Any] | None,
) -> ResidentCorpusEntry:
    document_gold_metrics = _optional_manifest_mapping(
        item,
        "goldMetrics",
        location=f"Manifest document {index}",
    )
    document_gold_thresholds = _optional_manifest_mapping(
        item,
        "goldThresholds",
        location=f"Manifest document {index}",
    )
    if (document_gold_metrics is None) != (document_gold_thresholds is None):
        raise SystemExit(
            f"Manifest document {index} must include both goldMetrics "
            "and goldThresholds when either is provided."
        )
    gold_metrics = (
        document_gold_metrics if document_gold_metrics is not None else corpus_gold_metrics
    )
    gold_thresholds = (
        document_gold_thresholds if document_gold_thresholds is not None else corpus_gold_thresholds
    )
    return ResidentCorpusEntry(
        path=Path(str(item["path"])),
        gold_metrics=gold_metrics,
        gold_thresholds=gold_thresholds,
    )


def _optional_manifest_mapping(
    item: dict[str, Any],
    key: str,
    *,
    location: str,
) -> dict[str, Any] | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SystemExit(f"{location} {key} must be an object.")
    return dict(value)
