#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESIDENT_RUNNER = ROOT / "scripts" / "gpu" / "run_phase8_5_resident_corpus.py"
REPORT_ACCEPTANCE = ROOT / "scripts" / "gpu" / "phase8_5_report_acceptance.py"


def main() -> int:
    args = _parse_args()
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    pass_reports: list[Path] = []
    for pass_number in (1, 2):
        run_id = f"{args.run_id_prefix}-pass-{pass_number}"
        report = report_dir / f"{run_id}-report.json"
        pass_reports.append(report)
        result = _run_resident_pass(args, run_id=run_id, report=report)
        if result.returncode != 0:
            return result.returncode

    acceptance = _run_acceptance(pass_reports, require_gold=args.require_gold)
    return acceptance.returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Phase 8.5 resident corpus twice and compare repeatability gates.",
    )
    parser.add_argument("--pdf", action="append", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("/srv/structura/objects/exports/phase85-runs"),
    )
    parser.add_argument(
        "--run-id-prefix",
        default=datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-resident"),
    )
    parser.add_argument("--title-prefix")
    parser.add_argument("--requested-by", default="phase8_5_resident_acceptance")
    parser.add_argument("--timeout-seconds", type=int, default=14_400)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--progress-seconds", type=float, default=20.0)
    parser.add_argument("--allow-active-jobs", action="store_true")
    parser.add_argument("--include-text-embeddings", action="store_true")
    parser.add_argument("--allow-target-dead-letter", action="store_true")
    parser.add_argument("--require-gold", action="store_true")
    args = parser.parse_args()
    if not args.pdf and not args.manifest:
        parser.error("at least one --pdf or --manifest document path is required")
    return args


def _run_resident_pass(
    args: argparse.Namespace,
    *,
    run_id: str,
    report: Path,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(RESIDENT_RUNNER),
        "--run-id",
        run_id,
        "--report",
        str(report),
        "--requested-by",
        args.requested_by,
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
        command.extend(["--title-prefix", f"{args.title_prefix} {run_id}"])
    if args.allow_active_jobs:
        command.append("--allow-active-jobs")
    if args.include_text_embeddings:
        command.append("--include-text-embeddings")
    if args.allow_target_dead_letter:
        command.append("--allow-target-dead-letter")
    # Fixed Python script path and argv-only forwarding; no shell.
    return subprocess.run(command, cwd=ROOT, check=False, text=True)  # nosec B603


def _run_acceptance(
    reports: list[Path],
    *,
    require_gold: bool,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(REPORT_ACCEPTANCE), *(str(report) for report in reports)]
    if require_gold:
        command.append("--require-gold")
    # Fixed Python script path and report argv; no shell.
    return subprocess.run(command, cwd=ROOT, check=False, text=True)  # nosec B603


if __name__ == "__main__":
    raise SystemExit(main())
