"""Immutable render-set admission, page checkpoints and seal-once persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from psycopg.types.json import Jsonb

from lib.document_processing.models import ProcessingBinding, content_digest
from lib.evidence.authority_repository import fence_set, lock_set, lock_source, require_producer
from lib.evidence.errors import EvidenceConflict
from lib.evidence.manifest import completion_manifest, expected_render_set, validate_asset
from lib.evidence.models import (
    ExpectedRenderSet,
    RenderSetBinding,
    RetainedPageAsset,
    render_set_id,
)
from lib.jobs.ownership import current_job_attempt


def create_set(cur: Any, processing: ProcessingBinding) -> RenderSetBinding:
    binding = RenderSetBinding(processing, render_set_id(processing.parse_generation_id))
    cur.execute("SELECT id FROM document_parse_render_sets WHERE id=%s", (binding.render_set_id,))
    if cur.fetchone() is not None:
        lock_set(cur, binding)
        fence_set(cur, binding)
        return binding
    run = lock_source(cur, processing, include_artifacts=True)
    cur.execute(
        "SELECT * FROM document_parse_page_checkpoints WHERE parse_generation_id=%s "
        "ORDER BY page_number",
        (processing.parse_generation_id,),
    )
    expected = expected_render_set(run, cur.fetchall())
    attempt = current_job_attempt()
    if attempt is None:
        raise EvidenceConflict("Retained source admission requires a claimed producer.")
    # The producer/source FK identities are already locked before the job fence.
    cur.execute(
        "SELECT * FROM document_parse_render_sets WHERE id=%s FOR UPDATE", (binding.render_set_id,)
    )
    row = cur.fetchone()
    if row is not None:
        require_producer(row)
        if (
            row["expected_json"] != expected.model_dump(mode="json")
            or row["expected_sha256"] != expected.fingerprint
        ):
            raise EvidenceConflict("Retained source set was assigned different content.")
    else:
        cur.execute(
            """INSERT INTO document_parse_render_sets
            (id,document_id,household_id,processing_run_id,parse_generation_id,producer_job_id,
             original_asset_id,original_sha256,expected_json,expected_sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                binding.render_set_id,
                processing.document_id,
                run["household_id"],
                processing.processing_run_id,
                processing.parse_generation_id,
                attempt.job_id,
                run["original_asset_id"],
                run["original_sha256"],
                Jsonb(expected.model_dump(mode="json")),
                expected.fingerprint,
            ),
        )
    fence_set(cur, binding)
    return binding


def load_assets(
    cur: Any, binding: RenderSetBinding, expected: ExpectedRenderSet
) -> tuple[RetainedPageAsset, ...]:
    cur.execute(
        "SELECT * FROM document_parse_page_render_assets "
        "WHERE render_set_id=%s ORDER BY page_number",
        (binding.render_set_id,),
    )
    assets = []
    for row in cur.fetchall():
        asset = RetainedPageAsset.model_validate(row["asset_json"])
        validate_asset(asset, expected)
        if (
            (asset.id, asset.page_number, asset.page_id)
            != (row["id"], row["page_number"], row["page_id"])
            or row["document_id"] != expected.document_id
            or row["parse_generation_id"] != expected.parse_generation_id
            or row["content_sha256"] != asset.fingerprint
        ):
            raise EvidenceConflict("Retained source row identity is inconsistent.")
        assets.append(asset)
    return tuple(assets)


def register_asset(
    cur: Any,
    binding: RenderSetBinding,
    asset: RetainedPageAsset,
    *,
    commit_source: Callable[[], None],
) -> str:
    header, expected = lock_set(
        cur,
        binding,
        content_hashes=(asset.render.image_sha256,),
        checkpoint_page_number=asset.page_number,
    )
    validate_asset(asset, expected)
    cur.execute("SELECT * FROM document_parse_page_render_assets WHERE id=%s", (asset.id,))
    row = cur.fetchone()
    if row is not None:
        if (
            row["asset_json"] != asset.model_dump(mode="json")
            or row["content_sha256"] != asset.fingerprint
            or row["render_set_id"] != binding.render_set_id
            or row["document_id"] != binding.processing.document_id
            or row["parse_generation_id"] != binding.processing.parse_generation_id
            or (row["page_id"], row["page_number"]) != (asset.page_id, asset.page_number)
        ):
            raise EvidenceConflict("Retained page identity already contains different bytes.")
    elif header["state"] != "building":
        raise EvidenceConflict("Sealed retained evidence cannot acquire another page.")
    # The hash lock is held through commit. The verified staged object must exist
    # before INSERT so cleanup cannot create a permanently missing pointer.
    commit_source()
    if row is None:
        cur.execute(
            """INSERT INTO document_parse_page_render_assets
            (id,render_set_id,document_id,parse_generation_id,page_number,page_id,asset_json,content_sha256)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                asset.id,
                binding.render_set_id,
                binding.processing.document_id,
                binding.processing.parse_generation_id,
                asset.page_number,
                asset.page_id,
                Jsonb(asset.model_dump(mode="json")),
                asset.fingerprint,
            ),
        )
    fence_set(cur, binding)
    return asset.fingerprint


def seal_set(cur: Any, binding: RenderSetBinding) -> dict[str, Any]:
    header, expected = lock_set(cur, binding)
    completion = completion_manifest(expected, load_assets(cur, binding, expected))
    digest = content_digest(completion)
    if header["state"] == "sealed":
        if header["completion_json"] != completion or header["completion_sha256"] != digest:
            raise EvidenceConflict("Retained source seal is inconsistent.")
    else:
        cur.execute(
            "UPDATE document_parse_render_sets SET state='sealed',completion_json=%s,"
            "completion_sha256=%s,sealed_at=clock_timestamp() WHERE id=%s AND state='building'",
            (Jsonb(completion), digest, binding.render_set_id),
        )
    fence_set(cur, binding)
    return completion


def execution_source(cur: Any, binding: RenderSetBinding) -> dict[str, Any]:
    lock_set(cur, binding)
    cur.execute(
        "SELECT r.config_json,g.structure_json,a.uri,a.mime_type,a.byte_size,a.sha256 "
        "FROM document_processing_runs r JOIN document_parse_generations g "
        "ON g.id=r.parse_generation_id AND g.creator_run_id=r.id "
        "JOIN document_assets a ON a.id=r.original_asset_id "
        "AND a.document_id=r.document_id AND a.asset_role='original' "
        "WHERE r.id=%s AND r.document_id=%s AND g.id=%s",
        (
            binding.processing.processing_run_id,
            binding.processing.document_id,
            binding.processing.parse_generation_id,
        ),
    )
    row = cur.fetchone()
    if row is None:
        raise EvidenceConflict("Retained original source is unavailable.")
    fence_set(cur, binding)
    return dict(row)
