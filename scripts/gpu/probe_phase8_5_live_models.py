#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class ProbeTarget:
    name: str
    base_url: str
    model: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Structura Phase 8.5 live models.")
    parser.add_argument("--qwen-url", default="http://127.0.0.1:8100")
    parser.add_argument("--qwen-model", default="Qwen/Qwen3-VL-8B-Instruct")
    parser.add_argument("--qwen-semantic-url", default="http://127.0.0.1:8104")
    parser.add_argument("--qwen-semantic-model", default="Qwen/Qwen3-VL-2B-Instruct")
    parser.add_argument("--granite-url", default="http://127.0.0.1:8101")
    parser.add_argument("--granite-model", default="ibm-granite/granite-4.0-3b-vision")
    parser.add_argument("--text-embed-url", default="http://127.0.0.1:8102")
    parser.add_argument("--text-embed-model", default="Qwen/Qwen3-Embedding-4B")
    parser.add_argument("--visual-embed-url", default="http://127.0.0.1:8103")
    parser.add_argument("--visual-embed-model", default="Qwen/Qwen3-VL-Embedding-2B")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    probe_vision_generate(
        ProbeTarget("model-qwen", args.qwen_url, args.qwen_model),
        timeout=args.timeout,
    )
    probe_vision_generate(
        ProbeTarget(
            "model-qwen-semantic",
            args.qwen_semantic_url,
            args.qwen_semantic_model,
        ),
        timeout=args.timeout,
    )
    probe_vision_generate(
        ProbeTarget("model-granite", args.granite_url, args.granite_model),
        timeout=args.timeout,
    )
    probe_embedding(
        ProbeTarget("model-embed", args.text_embed_url, args.text_embed_model),
        dimensions=1536,
        visual=False,
        timeout=args.timeout,
    )
    probe_embedding(
        ProbeTarget("model-vl-embed", args.visual_embed_url, args.visual_embed_model),
        dimensions=1024,
        visual=True,
        timeout=args.timeout,
    )
    print("Phase 8.5 live inference probes completed")
    return 0


def probe_vision_generate(target: ProbeTarget, *, timeout: float) -> None:
    image_url = f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode('ascii')}"
    payload = {
        "model": target.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Return only JSON with normalized.ok=true and "
                            "confidence.ok=1 for this health probe."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ],
        "max_tokens": 64,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    response = post_json(target.base_url, "/v1/chat/completions", payload, timeout=timeout)
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SystemExit(f"{target.name}: chat completion response is missing choices")
    print(f"{target.name}: chat completion ok")


def probe_embedding(
    target: ProbeTarget,
    *,
    dimensions: int,
    visual: bool,
    timeout: float,
) -> None:
    if visual:
        payload = _visual_embedding_payload(target.model, dimensions)
    else:
        payload = {
            "model": target.model,
            "input": ["invoice total balance due"],
            "dimensions": dimensions,
        }
    response = post_json(target.base_url, "/v1/embeddings", payload, timeout=timeout)
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise SystemExit(f"{target.name}: embedding response is missing data")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list) or len(embedding) != dimensions:
        actual = len(embedding) if isinstance(embedding, list) else "none"
        raise SystemExit(
            f"{target.name}: embedding dimension mismatch (expected {dimensions}, got {actual})"
        )
    print(f"{target.name}: embedding ok")


def _visual_embedding_payload(model: str, dimensions: int) -> dict[str, Any]:
    image_url = f"data:image/png;base64,{base64.b64encode(PNG_1X1).decode('ascii')}"
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": [{"type": "text", "text": "Represent the user's input."}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "blank scanned document page"},
                ],
            },
        ],
        "dimensions": dimensions,
    }


def post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{url}: HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"{url}: request failed: {exc}") from exc
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise SystemExit(f"{url}: response is not a JSON object")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
