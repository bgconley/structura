"""Render only the preauthored source recipe; never accept model output or metrics."""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from lib.evaluation.annotations import DocumentAnnotation


def author_fixture(directory: Path) -> None:
    recipe = json.loads((directory / "source-recipe.json").read_text())
    images, annotations, expected = [], [], []
    for number, page in enumerate(recipe["pages"], 1):
        image, annotation, truth = _page(recipe, page, number)
        image.save(directory / f"page-{number}.png")
        annotation["image_sha256"] = _sha((directory / f"page-{number}.png").read_bytes())
        images.append(image)
        annotations.append(annotation)
        expected.append(truth)
    try:
        original = original_bytes(images)
    finally:
        for image in images:
            image.close()
    digest = _sha(original)
    annotation = DocumentAnnotation.model_validate(
        {
            "item_id": "combined-three-family-source-v1",
            "original_sha256": digest,
            "family_labels": [p["family"] for p in recipe["pages"]],
            "modality": "image",
            "origin_group": "authored-three-family-probe-v1",
            "template_group": "simple-visible-ledger-v1",
            "provenance": {
                "origin": "synthetic_author",
                "annotation_revision": "source-recipe-v1",
                "author_reference": recipe["source_author"],
                "adjudicator_reference": None,
                "created_at": recipe["created_at"],
                "source_only": True,
            },
            "pages": annotations,
        }
    )
    _write(directory / "annotation.json", annotation.model_dump(mode="json"))
    _write(
        directory / "expectations.json",
        {
            "schema_version": "structura.synthetic_understanding_expectations.v1",
            "original_sha256": digest,
            "original_byte_size": len(original),
            "source_recipe_sha256": _sha((directory / "source-recipe.json").read_bytes()),
            "scope": "selected_visible_fields_and_all_printed_line_rows",
            "split": "synthetic_regression",
            "threshold_policy": "not_ratified",
            "pages": expected,
        },
    )


def original_bytes(images: list[Image.Image]) -> bytes:
    """Versioned raw grayscale TIFF recipe; caller verifies frozen expected hash/size."""
    gray = [image.convert("L") for image in images]
    try:
        buffer = io.BytesIO()
        gray[0].save(buffer, format="TIFF", save_all=True, append_images=gray[1:])
        return buffer.getvalue()
    finally:
        for image in gray:
            image.close()


def _page(recipe: dict[str, Any], spec: dict[str, Any], number: int):
    image = Image.new("RGB", (recipe["width"], recipe["height"]), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=30)
    table_font = ImageFont.load_default(size=25)
    regions: list[dict[str, Any]] = []
    claims = []
    y = 50

    def text(value, kind="paragraph"):
        nonlocal y
        box = draw.textbbox((60, y), value, font=font)
        if box[2] > recipe["width"] - 40:
            raise ValueError("Authored source line exceeds its visible page.")
        draw.text((60, y), value, font=font, fill="black")
        regions.append(
            {
                "id": f"p{number}-r{len(regions)}",
                "kind": kind,
                "readability": "readable",
                "text": value,
                "bbox": dict(zip(("left", "top", "right", "bottom"), box, strict=True)),
            }
        )
        y += 52

    text(spec["title"], "heading")
    for field in spec["headers"]:
        text(f"{field['label']}: {field['value']}")
        claims.append(_claim(field))
    y += 30
    start_y, height, x = y, 80, 60
    width = sum(c["width"] for c in spec["columns"])
    rows = [[c["label"] for c in spec["columns"]], *spec["rows"]]
    cells, expected_rows = [], []
    for row_index, values in enumerate(rows):
        x = 60
        row_claims = []
        for column, (definition, value) in enumerate(zip(spec["columns"], values, strict=True)):
            right = x + definition["width"]
            draw.rectangle((x, y, right, y + height), outline="black", width=2)
            box = draw.textbbox((x + 12, y + 22), value, font=table_font)
            if box[2] > right - 5:
                raise ValueError("Authored table cell exceeds its visible column.")
            draw.text((x + 12, y + 22), value, font=table_font, fill="black")
            cells.append(
                {
                    "row": row_index,
                    "column": column,
                    "row_span": 1,
                    "column_span": 1,
                    "text": value,
                    "readability": "readable",
                }
            )
            if row_index:
                row_claims.append(_claim({**definition, "value": value}))
            x = right
        if row_index:
            expected_rows.append({"source_row": row_index, "claims": row_claims})
        y += height
    region_id = f"p{number}-table"
    regions.append(
        {
            "id": region_id,
            "kind": "table",
            "readability": "readable",
            "text": "",
            "bbox": {"left": 60, "top": start_y, "right": 60 + width, "bottom": y},
        }
    )
    y += 30
    for field in spec["totals"]:
        text(f"{field['label']}: {field['value']}")
        claims.append(_claim(field))
    text("TEST DATA - fictional people and organizations. All monetary values are USD.", "footer")
    if y > recipe["height"] - 30 or width > recipe["width"] - 120:
        raise ValueError("Authored source content exceeds its page.")
    labels = [*spec["headers"], *spec["totals"]]
    labels.extend(
        {**column, "value": value}
        for values in spec["rows"]
        for column, value in zip(spec["columns"], values, strict=True)
    )
    selected = {
        field["value"]: {"identifier": "identifier", "money": "amount", "date": "date"}[
            field["value_type"]
        ]
        for field in labels
        if field["value_type"] in {"identifier", "money", "date"}
    }
    sensitive = Counter(field["value"] for field in labels if field["value"] in selected)
    annotation = {
        "page_number": number,
        "image_sha256": "0" * 64,
        "pixel_width": recipe["width"],
        "pixel_height": recipe["height"],
        "regions": regions,
        "tables": [
            {
                "region_id": region_id,
                "row_count": len(rows),
                "column_count": len(spec["columns"]),
                "cells": cells,
                "continuation_group": None,
            }
        ],
        "reading_order_pairs": [
            [a["id"], b["id"]] for a, b in zip(regions, regions[1:], strict=False)
        ],
        "sensitive_text": [
            {"text": v, "kind": selected[v], "occurrences": n} for v, n in sensitive.items()
        ],
    }
    return (
        image,
        annotation,
        {"page_number": number, "family": spec["family"], "fields": claims, "rows": expected_rows},
    )


def _claim(field):
    value = field["value"]
    if field["value_type"] == "money":
        value = {"amount": value, "currency": "USD"}
    elif field["value_type"] == "identifiers":
        value = value.split()
    return {"canonical_key": field["key"], "value_type": field["value_type"], "typed_value": value}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
