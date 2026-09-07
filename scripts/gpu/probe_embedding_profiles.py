"""Exercise candidate embedding adapters together; not a corpus/capacity release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.model_runtime.clients.text_embeddings import TextEmbeddingClient  # noqa: E402
from lib.model_runtime.clients.visual_embeddings import (  # noqa: E402
    VisualEmbeddingClient,
    VisualQueryEmbeddingClient,
)
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest  # noqa: E402
from lib.model_runtime.credentials import model_api_key  # noqa: E402
from lib.model_runtime.profiles import (  # noqa: E402
    TEXT_EMBED_BLACKBIRD_PROFILE,
    VISUAL_EMBED_BLACKBIRD_PROFILE,
    get_model_profile,
)
from lib.search.embeddings.validation import validated_response_vectors  # noqa: E402


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True)) / math.sqrt(
        sum(a * a for a in left) * sum(b * b for b in right)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-url", required=True)
    parser.add_argument("--visual-url", required=True)
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--image-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("The output must be a new file.")
    key = model_api_key(None, args.api_key_file)
    text_profile = get_model_profile(TEXT_EMBED_BLACKBIRD_PROFILE)
    visual_profile = get_model_profile(VISUAL_EMBED_BLACKBIRD_PROFILE)
    text_client = TextEmbeddingClient(
        profile=text_profile, http_client_base_url=args.text_url, api_key=key
    )
    image_client = VisualEmbeddingClient(
        profile=visual_profile, http_client_base_url=args.visual_url, api_key=key
    )
    query_client = VisualQueryEmbeddingClient(
        profile=visual_profile, http_client_base_url=args.visual_url, api_key=key
    )
    image = args.image_path.read_bytes()
    image_input = EmbeddingInput(image_bytes=image, mime_type="image/png")
    mixed_input = EmbeddingInput(
        text="Synthetic repair invoice with line items and a total amount",
        image_bytes=image,
        mime_type="image/png",
    )
    document_request = EmbeddingRequest(
        profile_name=text_profile.name,
        inputs=(
            EmbeddingInput(
                text="Repair invoice INV-902: service 42.80, credit -12.35, total 30.45."
            ),
            EmbeddingInput(text="Travel brochure: tropical beach, palm trees and ocean waves."),
        ),
        output_dimensions=1536,
        timeout_seconds=90,
    )
    text_query = EmbeddingRequest(
        profile_name=text_profile.name,
        inputs=(EmbeddingInput(text="What is the total amount on the repair invoice?"),),
        output_dimensions=1536,
        purpose="query",
        timeout_seconds=90,
    )
    image_request = EmbeddingRequest(
        profile_name=visual_profile.name,
        inputs=(image_input, mixed_input),
        output_dimensions=2048,
        timeout_seconds=120,
    )
    visual_query = EmbeddingRequest(
        profile_name=visual_profile.name,
        inputs=(
            EmbeddingInput(text="Invoice for repair service with line items and a total amount"),
            EmbeddingInput(text="Tropical beach vacation with palm trees and ocean waves"),
        ),
        output_dimensions=2048,
        purpose="query",
        timeout_seconds=90,
    )
    cases = {
        "document_ingestion": (text_client, document_request, text_profile),
        "text_query": (text_client, text_query, text_profile),
        "image_and_mixed_ingestion": (image_client, image_request, visual_profile),
        "visual_query": (query_client, visual_query, visual_profile),
    }
    measurements = []
    # Warmup, then overlap all four paths twice. This is a bounded concurrency
    # smoke, not a sustained workload or a percentile performance estimate.
    for round_number in range(3):
        start = time.monotonic()
        with ThreadPoolExecutor(max_workers=4 if round_number else 1) as executor:
            pending = {
                name: executor.submit(client.embed, request)
                for name, (client, request, _profile) in cases.items()
            }
            responses = {name: future.result() for name, future in pending.items()}
        vectors = {
            name: validated_response_vectors(
                response, request=cases[name][1], profile=cases[name][2]
            )
            for name, response in responses.items()
        }
        text_scores = [
            cosine(vectors["text_query"][0], value) for value in vectors["document_ingestion"]
        ]
        image_scores = [
            cosine(vectors["image_and_mixed_ingestion"][0], value)
            for value in vectors["visual_query"]
        ]
        if not text_scores[0] > text_scores[1] or not image_scores[0] > image_scores[1]:
            raise RuntimeError("Synthetic relevant-document ranking did not pass.")
        if len(set(responses["image_and_mixed_ingestion"].input_sha256)) != 2:
            raise RuntimeError("Image-only and mixed input identities collided.")
        measurements.append(
            {
                "round": round_number,
                "concurrent": round_number > 0,
                "elapsed_ms": round((time.monotonic() - start) * 1000),
                "requests": {
                    name: {
                        "profile": response.profile_name,
                        "reported_model": response.model_name,
                        "declared_artifact_revision": response.artifact_revision,
                        "dimensions": response.dimensions,
                        "vectors": len(response.vectors),
                        "latency_ms": response.latency_ms,
                        "input_sha256": response.input_sha256,
                    }
                    for name, response in responses.items()
                },
                "text_similarities": text_scores,
                "image_similarities": image_scores,
            }
        )
    report = {
        "passed": True,
        "fixture_type": "synthetic_model_backed_smoke",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "rounds": measurements,
        "production_activated": False,
        "corpus_quality_gate": "not_evaluated",
        "sustained_capacity_gate": "not_evaluated",
    }
    with args.output.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
