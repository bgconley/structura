#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.model_runtime.profiles import (  # noqa: E402
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    VISUAL_EMBED_PROFILE,
    get_model_profile,
    required_live_profile_names,
)

REQUIRED_LIVE_SERVICES = (
    "api",
    "worker-extraction",
    "worker-semantic-annotations",
)
OPTIONAL_LIVE_SERVICES = ("worker-visual-embeddings",)
MODEL_HEALTH_TARGETS = {
    "model-qwen-semantic": "http://127.0.0.1:8104",
    "model-granite": "http://127.0.0.1:8101",
    "model-vl-embed": "http://127.0.0.1:8103",
}
MODEL_ENV_TARGETS = {
    "model-qwen-semantic": {
        "STRUCTURA_VLLM_MODEL_ID": "Qwen/Qwen3-VL-8B-Instruct-FP8",
        "STRUCTURA_VLLM_SERVED_MODEL_NAME": "Qwen/Qwen3-VL-8B-Instruct-FP8",
        "STRUCTURA_MODEL_PROFILE": "qwen3-vl-8b-fp8-semantic:v1",
    },
    "model-granite": {
        "STRUCTURA_GRANITE_MODEL_ID": "ibm-granite/granite-4.0-3b-vision",
        "STRUCTURA_MODEL_PROFILE": "granite-4.0-3b-vision-bf16:v1",
    },
}
# Profile registry is the single source of truth for server token/image
# limits; the running container env must agree with it.
MODEL_LIMIT_TARGETS = {
    "model-qwen-semantic": {
        "profile_name": QWEN_SEMANTIC_PROFILE,
        "max_model_len_env": "STRUCTURA_VLLM_MAX_MODEL_LEN",
        "limit_mm_env": "STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT",
        "required": True,
    },
    "model-granite": {
        "profile_name": GRANITE_VISION_PROFILE,
        "max_model_len_env": "STRUCTURA_GRANITE_MAX_MODEL_LEN",
        "limit_mm_env": "STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT",
        "required": True,
    },
    "model-vl-embed": {
        "profile_name": VISUAL_EMBED_PROFILE,
        "max_model_len_env": None,
        "limit_mm_env": "STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT",
        "required": False,
    },
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preflight Phase 8.5 resident live-model runtime containers."
    )
    parser.add_argument("--skip-model-health", action="store_true")
    parser.add_argument("--health-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--health-poll-seconds", type=float, default=5.0)
    args = parser.parse_args()

    results: list[CheckResult] = []
    results.append(_check_required_live_profiles_registered())
    for service in REQUIRED_LIVE_SERVICES:
        results.append(_check_service_live_mode(service, required=True))
    for service in OPTIONAL_LIVE_SERVICES:
        results.append(_check_service_live_mode(service, required=False))
    for service, expected_env in MODEL_ENV_TARGETS.items():
        results.append(_check_model_service_env(service, expected_env))
    for service, limit_target in MODEL_LIMIT_TARGETS.items():
        results.append(_check_model_service_limits(service, limit_target))
    if not args.skip_model_health:
        for service, url in MODEL_HEALTH_TARGETS.items():
            results.append(
                _check_model_health(
                    service,
                    url,
                    timeout_seconds=args.health_timeout_seconds,
                    poll_seconds=args.health_poll_seconds,
                )
            )

    for result in results:
        status = "ok" if result.ok else "failed"
        print(f"{result.name}: {status}: {result.message}")
    failed = [result for result in results if not result.ok]
    return 1 if failed else 0


def _check_service_live_mode(service: str, *, required: bool) -> CheckResult:
    try:
        env = _compose_exec_env(service)
    except subprocess.CalledProcessError as exc:
        if not required:
            return CheckResult(service, True, "service not running; optional check skipped")
        return CheckResult(service, False, f"unable to inspect container env: {exc}")
    model_mode = env.get("STRUCTURA_MODEL_MODE")
    if model_mode != "live":
        return CheckResult(
            service,
            False,
            f"STRUCTURA_MODEL_MODE must be live, got {model_mode!r}",
        )
    if service in {"api", "worker-extraction", "worker-semantic-annotations"}:
        qwen_url = env.get("STRUCTURA_MODEL_QWEN_SEMANTIC_URL")
        if qwen_url != "http://model-qwen-semantic:8104":
            return CheckResult(
                service,
                False,
                f"STRUCTURA_MODEL_QWEN_SEMANTIC_URL is unexpected: {qwen_url!r}",
            )
    if service in {"api", "worker-extraction"}:
        granite_url = env.get("STRUCTURA_MODEL_GRANITE_URL")
        if granite_url != "http://model-granite:8101":
            return CheckResult(
                service,
                False,
                f"STRUCTURA_MODEL_GRANITE_URL is unexpected: {granite_url!r}",
            )
    return CheckResult(service, True, "live model env verified")


def _check_model_service_env(service: str, expected: dict[str, str]) -> CheckResult:
    try:
        env = _compose_exec_env(service)
    except subprocess.CalledProcessError as exc:
        return CheckResult(service, False, f"unable to inspect model container env: {exc}")
    mismatches = [
        f"{key}={env.get(key)!r} expected {value!r}"
        for key, value in expected.items()
        if env.get(key) != value
    ]
    if mismatches:
        return CheckResult(service, False, "; ".join(mismatches))
    return CheckResult(service, True, "model identity env verified")


def _check_required_live_profiles_registered() -> CheckResult:
    missing: list[str] = []
    for profile_name in required_live_profile_names():
        try:
            get_model_profile(profile_name)
        except KeyError:
            missing.append(profile_name)
    if missing:
        return CheckResult(
            "required-live-profiles",
            False,
            f"unregistered live profiles: {', '.join(missing)}",
        )
    return CheckResult(
        "required-live-profiles",
        True,
        f"{len(required_live_profile_names())} required live profiles registered",
    )


def _check_model_service_limits(service: str, target: dict[str, object]) -> CheckResult:
    name = f"{service}-limits"
    required = bool(target.get("required", True))
    try:
        env = _compose_exec_env(service)
    except subprocess.CalledProcessError as exc:
        if not required:
            return CheckResult(name, True, "service not running; optional limit check skipped")
        return CheckResult(name, False, f"unable to inspect model container env: {exc}")
    profile = get_model_profile(str(target["profile_name"]))
    mismatches: list[str] = []
    max_model_len_env = target.get("max_model_len_env")
    if max_model_len_env and profile.max_model_len is not None:
        actual = env.get(str(max_model_len_env))
        if actual != str(profile.max_model_len):
            mismatches.append(
                f"{max_model_len_env}={actual!r} expected {profile.max_model_len} "
                f"from profile {profile.name}"
            )
    limit_mm_env = target.get("limit_mm_env")
    if limit_mm_env and profile.max_images_per_request is not None:
        actual_images = _limit_mm_image_count(env.get(str(limit_mm_env)))
        if actual_images != profile.max_images_per_request:
            mismatches.append(
                f"{limit_mm_env} image limit {actual_images!r} expected "
                f"{profile.max_images_per_request} from profile {profile.name}"
            )
    if mismatches:
        return CheckResult(name, False, "; ".join(mismatches))
    return CheckResult(name, True, "server limits match profile registry")


def _limit_mm_image_count(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    image_limit = parsed.get("image")
    return int(image_limit) if isinstance(image_limit, int | float) else None


def _compose_exec_env(service: str) -> dict[str, str]:
    # Fixed docker compose argv; service names are internal constants.
    completed = subprocess.run(  # nosec B603
        _docker_compose_command("exec", "-T", service, "env"),
        check=True,
        text=True,
        capture_output=True,
    )
    env: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def _docker_compose_command(*args: str) -> list[str]:
    docker = shutil.which("docker") or "docker"
    return [docker, "compose", *args]


def _check_model_health(
    service: str,
    url: str,
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> CheckResult:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not checked"
    while time.monotonic() < deadline:
        for suffix in ("/healthz", "/health"):
            try:
                status = _http_health_status(url, suffix)
                if 200 <= status < 300:
                    return CheckResult(service, True, f"{suffix} responded")
            except (HTTPException, OSError, TimeoutError, ValueError) as exc:
                last_error = str(exc)
        time.sleep(poll_seconds)
    return CheckResult(service, False, f"health endpoint did not respond: {last_error}")


def _http_health_status(url: str, suffix: str) -> int:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("model health target must be an http:// URL")
    if parsed.query or parsed.fragment:
        raise ValueError("model health target must not include query or fragment")
    path = f"{parsed.path.rstrip('/')}{suffix}"
    connection = HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return int(response.status)
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
