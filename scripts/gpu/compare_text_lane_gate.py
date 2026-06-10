"""E1 gate comparison: text-lane corpus run(s) vs the pinned baseline report.

Reads production-corpus reports (same shape as run-9) and prints the E1 gate
criteria from the 2026-06-10 extractive-first plan:

- jobs/dead letters: candidate run has zero target dead letters;
- per-document line-item rows >= baseline for table-bearing documents;
- quality outcomes per document vs baseline;
- expected-field coverage rollup vs baseline;
- repeatability: with two candidate runs, canonical-output fingerprints per
  document filename must match between runs A and B.

Read-only; pass --baseline, --candidate, optional --candidate-b.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-b", type=Path)
    return parser


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _filename(document: dict[str, Any]) -> str:
    info = document.get("document") or {}
    return str(
        info.get("original_filename")
        or info.get("originalFilename")
        or info.get("filename")
        or info.get("title")
        or document.get("filename")
        or "?"
    )


def _doc_stats(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for document in report.get("documents", []):
        jobs = document.get("jobs") or []
        job_counter = Counter(str(job.get("status")) for job in jobs if isinstance(job, dict))
        extractions = document.get("extractions") or []
        lanes = Counter()
        quality = Counter()
        for row in extractions:
            if not isinstance(row, dict):
                continue
            normalization = row.get("normalization_json") or row.get("normalizationJson") or {}
            lane = normalization.get("lane") if isinstance(normalization, dict) else None
            if lane:
                lanes[str(lane)] += 1
            outcome = row.get("quality_outcome") or row.get("qualityOutcome")
            if outcome:
                quality[str(outcome)] += 1
        stats[_filename(document)] = {
            "line_items": len(document.get("lineItems") or []),
            "fields": len(document.get("fields") or []),
            "observations": len(document.get("observations") or []),
            "jobs": dict(job_counter),
            "dead_letters": job_counter.get("dead_letter", 0),
            "lanes": dict(lanes),
            "quality_outcomes": dict(quality),
        }
    return stats


def _fingerprints(report: dict[str, Any]) -> dict[str, str]:
    payload = report.get("repeatabilityFingerprints") or {}
    canonical = payload.get("canonicalOutput") or payload.get("canonical_output") or {}
    if isinstance(canonical, dict):
        return {str(key): str(value) for key, value in canonical.items()}
    return {}


def _coverage_mean(report: dict[str, Any]) -> float | None:
    payload = report.get("expectedFieldCoverage") or {}
    for key in ("meanCoverage", "mean_coverage", "mean"):
        value = payload.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def main() -> int:
    args = build_parser().parse_args()
    baseline = _load(args.baseline)
    candidate = _load(args.candidate)
    base_stats = _doc_stats(baseline)
    cand_stats = _doc_stats(candidate)
    failures: list[str] = []

    print(f"baseline:  {baseline.get('runId')}")
    print(f"candidate: {candidate.get('runId')}")
    print()
    print(
        f"{'document':<42} {'LI b->c':>9} {'fields b->c':>12} {'obs b->c':>10} {'dead':>5}  lanes"
    )
    for name in sorted(set(base_stats) | set(cand_stats)):
        base = base_stats.get(name, {})
        cand = cand_stats.get(name, {})
        line = (
            f"{name[:42]:<42} "
            f"{base.get('line_items', '-'):>4}->{cand.get('line_items', '-'):<4} "
            f"{base.get('fields', '-'):>5}->{cand.get('fields', '-'):<6} "
            f"{base.get('observations', '-'):>4}->{cand.get('observations', '-'):<5} "
            f"{cand.get('dead_letters', 0):>5}  {cand.get('lanes', {})}"
        )
        print(line)
        if cand.get("dead_letters", 0):
            failures.append(f"{name}: {cand['dead_letters']} dead-letter job(s)")
        if (
            isinstance(base.get("line_items"), int)
            and isinstance(cand.get("line_items"), int)
            and base["line_items"] > 0
            and cand["line_items"] < base["line_items"]
        ):
            failures.append(
                f"{name}: line items regressed {base['line_items']} -> {cand['line_items']}"
            )
    print()
    base_cov = _coverage_mean(baseline)
    cand_cov = _coverage_mean(candidate)
    print(f"expected-field coverage mean: {base_cov} -> {cand_cov}")
    base_quality = Counter()
    cand_quality = Counter()
    for stats, counter in ((base_stats, base_quality), (cand_stats, cand_quality)):
        for doc in stats.values():
            counter.update(doc.get("quality_outcomes", {}))
    print(f"quality outcomes: {dict(base_quality)} -> {dict(cand_quality)}")

    if args.candidate_b is not None:
        candidate_b = _load(args.candidate_b)
        prints_a = _fingerprints(candidate)
        prints_b = _fingerprints(candidate_b)
        stats_b = _doc_stats(candidate_b)
        mismatched = []
        # fingerprints key by document id, which differs per run (fresh
        # ingest); compare per filename via per-document canonical counts and
        # the report-level fingerprint multisets.
        if sorted(prints_a.values()) != sorted(prints_b.values()):
            for name in sorted(set(cand_stats) | set(stats_b)):
                a_items = cand_stats.get(name, {}).get("line_items")
                b_items = stats_b.get(name, {}).get("line_items")
                if a_items != b_items:
                    mismatched.append(f"{name}: line items {a_items} vs {b_items}")
            failures.append(
                "repeatability: canonical-output fingerprint multisets differ between "
                f"candidate runs ({len(prints_a)} vs {len(prints_b)} documents)"
                + (f"; per-doc diffs: {mismatched}" if mismatched else "")
            )
        else:
            print("repeatability: canonical-output fingerprints identical across runs A/B")

    print()
    if failures:
        print("GATE FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("GATE CHECKS PASSED (line items, dead letters, repeatability where applicable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
