#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen

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
    for service in REQUIRED_LIVE_SERVICES:
        results.append(_check_service_live_mode(service, required=True))
    for service in OPTIONAL_LIVE_SERVICES:
        results.append(_check_service_live_mode(service, required=False))
    for service, expected_env in MODEL_ENV_TARGETS.items():
        results.append(_check_model_service_env(service, expected_env))
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


def _compose_exec_env(service: str) -> dict[str, str]:
    # Fixed docker compose argv; service names are internal constants.
    completed = subprocess.run(  # nosec B603
        ["docker", "compose", "exec", "-T", service, "env"],
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
                with urlopen(f"{url}{suffix}", timeout=5) as response:  # nosec B310
                    if 200 <= response.status < 300:
                        return CheckResult(service, True, f"{suffix} responded")
            except URLError as exc:
                last_error = str(exc)
            except TimeoutError as exc:
                last_error = str(exc)
        time.sleep(poll_seconds)
    return CheckResult(service, False, f"health endpoint did not respond: {last_error}")


if __name__ == "__main__":
    sys.exit(main())
