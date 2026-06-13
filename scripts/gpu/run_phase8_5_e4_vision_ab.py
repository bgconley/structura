#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE_BRINGUP = ROOT / "scripts" / "gpu" / "phase8_5_live_bringup.sh"
RESIDENT_ACCEPTANCE = ROOT / "scripts" / "gpu" / "run_phase8_5_resident_acceptance.py"

QWEN_VISION_PROFILE = "qwen3-vl-8b-fp8-semantic:v1"


def main() -> int:
    args = _parse_args()
    for mode in ("granite", "qwen"):
        bringup = _run_live_bringup(args, mode=mode)
        if bringup.returncode != 0:
            return bringup.returncode
        acceptance = _run_resident_acceptance(args, mode=mode)
        if acceptance.returncode != 0:
            return acceptance.returncode
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Phase 8.5 E4 vision-lane A/B gate: Granite fallback baseline, "
            "then Qwen vision fallback, with app/extraction containers recreated "
            "for each mode."
        )
    )
    parser.add_argument("--pdf", action="append", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("/srv/structura/objects/exports/phase85-runs/e4-vision-ab"),
    )
    parser.add_argument(
        "--run-id-prefix",
        default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-e4-vision-ab"),
    )
    parser.add_argument("--title-prefix")
    parser.add_argument("--requested-by", default="phase8_5_e4_vision_ab")
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--progress-seconds", type=float, default=20.0)
    parser.add_argument("--allow-active-jobs", action="store_true")
    parser.add_argument("--include-text-embeddings", action="store_true")
    parser.add_argument("--allow-target-dead-letter", action="store_true")
    parser.add_argument("--require-gold", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--qwen-vision-profile", default=QWEN_VISION_PROFILE)
    args = parser.parse_args()
    if not args.pdf and not args.manifest:
        parser.error("at least one --pdf or --manifest document path is required")
    return args


def _run_live_bringup(
    args: argparse.Namespace,
    *,
    mode: str,
) -> subprocess.CompletedProcess[str]:
    command = ["bash", str(LIVE_BRINGUP)]
    if args.build:
        command.append("--build")
    if args.skip_preflight:
        command.append("--skip-preflight")
    env = _mode_env(mode=mode, qwen_vision_profile=args.qwen_vision_profile)
    # Fixed script path and argv-only forwarding; no shell.
    return subprocess.run(command, cwd=ROOT, check=False, text=True, env=env)  # nosec B603


def _run_resident_acceptance(
    args: argparse.Namespace,
    *,
    mode: str,
) -> subprocess.CompletedProcess[str]:
    mode_report_dir = args.report_dir / mode
    command = [
        sys.executable,
        str(RESIDENT_ACCEPTANCE),
        "--report-dir",
        str(mode_report_dir),
        "--run-id-prefix",
        f"{args.run_id_prefix}-{mode}",
        "--requested-by",
        f"{args.requested_by}_{mode}",
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--poll-seconds",
        str(args.poll_seconds),
        "--progress-seconds",
        str(args.progress_seconds),
    ]
    for pdf in args.pdf or []:
        command.extend(["--pdf", str(pdf)])
    if args.manifest:
        command.extend(["--manifest", str(args.manifest)])
    if args.title_prefix:
        command.extend(["--title-prefix", f"{args.title_prefix} {mode}"])
    if args.allow_active_jobs:
        command.append("--allow-active-jobs")
    if args.include_text_embeddings:
        command.append("--include-text-embeddings")
    if args.allow_target_dead_letter:
        command.append("--allow-target-dead-letter")
    if args.require_gold:
        command.append("--require-gold")
    # Fixed Python script path and argv-only forwarding; no shell.
    return subprocess.run(command, cwd=ROOT, check=False, text=True)  # nosec B603


def _mode_env(
    *,
    mode: str,
    qwen_vision_profile: str,
) -> dict[str, str]:
    env = dict(os.environ)
    env["STRUCTURA_MODEL_MODE"] = "live"
    env["STRUCTURA_EMBEDDING_VISUAL_ENABLED"] = "true"
    env["STRUCTURA_QWEN_VISION_PROFILE"] = qwen_vision_profile
    env["STRUCTURA_QWEN_VISION_FALLBACK"] = "true" if mode == "qwen" else "false"
    return env


if __name__ == "__main__":
    raise SystemExit(main())
