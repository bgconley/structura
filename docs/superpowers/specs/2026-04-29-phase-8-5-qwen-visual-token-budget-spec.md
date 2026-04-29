# Phase 8.5 Qwen Visual Token Budget Spec

## Goal

Make Qwen3-VL-4B Smart Parse use bounded planner-resolution visual inputs while
preserving full-resolution Docling and Granite extraction inputs.

## Runtime Position

Qwen3-VL-4B remains the default Smart Parse semantic planner on
`model-qwen-semantic:8104`. The service keeps four-page semantic image fan-in as
the normal first attempt, matching the historical Qwen3-VL-2B document shape for
short PDFs. Exact Docling page coverage remains mandatory; page-window fallback
is still allowed when a multi-image request violates the Docling coverage
contract.

This change does not make Qwen3-VL 8B active. High Quality and rescue remain
disabled/deferred unless the user explicitly enables them under the existing
Phase 8.5 intent policy.

## Visual Token Budget

Qwen's 32x visual-token guidance is the contract:

```text
visual_tokens ~= rendered_pixels / (32 * 32)
```

The Smart Parse planner budget is:

```text
min_visual_tokens_per_image = 256
max_visual_tokens_per_image = 2560
spatial_compression = 32
min_pixels = 256 * 32 * 32 = 262144
max_pixels = 2560 * 32 * 32 = 2621440
```

The Qwen vLLM service must receive:

```json
{"size":{"shortest_edge":262144,"longest_edge":2621440}}
```

This is a planner-only budget. Do not downscale Docling originals globally. Do
not weaken Granite inputs. Granite keeps page/crop images and Docling
table/layout context for extraction.

Qwen semantic prompts must also avoid token-heavy physical-layout details that
are not needed for semantic routing. Send Docling page, element, and table IDs
with bounded text/table snippets, but omit element bbox arrays and page image
hashes from the Qwen prompt. Docling persistence and Granite extraction inputs
remain unchanged.

## Output Budget

Smart Parse keeps `max_output_tokens = 6144` for now. With planner-resolution
image tokens and TurboQuant available for evaluation, reducing output tokens is
not part of this change. Any future reduction must be based on canary evidence.

## Timeout Policy

The Qwen semantic timeout is configurable and defaults to 300 seconds. The
previous 60-second generic model timeout is too short for live Qwen3-VL-4B
semantic canaries after context capacity is solved.

## Canary Report

Before live corpus validation, `scripts/gpu/run_phase8_5_semantic_canary.py`
must emit a token-budget section that records:

- rendered page image dimensions,
- Qwen planner image grid and visual-token estimate,
- Docling context token estimate,
- prompt token estimate,
- schema token estimate,
- requested output tokens,
- conservative total request-size estimate,
- selected fan-in sequence.
- whether legacy page aliases, page image hashes, or element bboxes were present
  in the model-facing prompt context.

The estimates are diagnostic. They do not replace vLLM metrics, but they should
make visual-token blowups visible before full-pipeline corpus runs.

## Validation Order

1. Run focused unit tests for the model profile, Compose service contract,
   timeout config, vLLM start script, and semantic canary token budget.
2. Rebuild/restart only the Qwen semantic service as needed.
3. Run BH Photo, BMW, and EOB semantic/full-pipeline canaries first.
4. Run the nine-document private canary after the first three documents are
   stable.
5. Decide whether TurboQuant becomes the standard Smart Parse backend only after
   observing context capacity, latency, and output quality.
