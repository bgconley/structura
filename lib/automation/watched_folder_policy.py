from __future__ import annotations

import time
from pathlib import Path
from typing import Any

MANAGED_RUNTIME_DIRS = {
    "postgres",
    "redis",
    "objects",
    "staging",
    "cache",
    "config",
    "logs",
    "backups",
    "observability",
    "tmp",
    "models",
}
DEFAULT_WATCH_POLICY: dict[str, Any] = {
    "allowedExtensions": [".pdf"],
    "stabilityDelaySeconds": 30,
    "processedFilePolicy": "leave",
    "recursive": False,
    "targetFolderIds": [],
    "tags": [],
}


class WatchedFolderPolicyError(ValueError):
    pass


def validate_watch_path(
    path: str | Path,
    *,
    runtime_root: Path,
    allowed_roots: list[Path] | None = None,
) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise WatchedFolderPolicyError("Watched-folder paths must be absolute.")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise WatchedFolderPolicyError("Watched-folder path must exist.") from exc
    if not resolved.is_dir():
        raise WatchedFolderPolicyError("Watched-folder path must be a directory.")

    runtime = runtime_root.resolve()
    if resolved == runtime:
        raise WatchedFolderPolicyError("Cannot watch the managed Structura runtime root.")
    if resolved.is_relative_to(runtime):
        relative_parts = resolved.relative_to(runtime).parts
        if relative_parts and relative_parts[0] in MANAGED_RUNTIME_DIRS:
            raise WatchedFolderPolicyError("Cannot watch managed Structura runtime directories.")

    if allowed_roots is not None:
        allowed = [root.resolve(strict=True) for root in allowed_roots]
        if not any(resolved == root or resolved.is_relative_to(root) for root in allowed):
            raise WatchedFolderPolicyError(
                "Watched-folder path must stay within allowed intake roots."
            )
    return resolved


def normalize_watch_policy(value: dict[str, Any] | None) -> dict[str, Any]:
    policy = {**DEFAULT_WATCH_POLICY, **(value or {})}
    extensions = policy.get("allowedExtensions")
    if not isinstance(extensions, list) or not extensions:
        raise WatchedFolderPolicyError("allowedExtensions must be a non-empty array.")
    normalized_extensions = []
    for extension in extensions:
        if not isinstance(extension, str):
            raise WatchedFolderPolicyError("allowedExtensions entries must be strings.")
        normalized = extension.lower().strip()
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        if normalized != ".pdf":
            raise WatchedFolderPolicyError("Phase 6 watched folders accept PDF files only.")
        normalized_extensions.append(normalized)
    policy["allowedExtensions"] = sorted(set(normalized_extensions))
    policy["stabilityDelaySeconds"] = max(1, int(policy.get("stabilityDelaySeconds", 30)))
    if policy.get("processedFilePolicy") not in {"leave", "move_processed", "move_failed"}:
        raise WatchedFolderPolicyError(
            "processedFilePolicy must be leave, move_processed, or move_failed."
        )
    policy["recursive"] = bool(policy.get("recursive", False))
    if not isinstance(policy.get("targetFolderIds"), list):
        raise WatchedFolderPolicyError("targetFolderIds must be an array.")
    if not isinstance(policy.get("tags"), list):
        raise WatchedFolderPolicyError("tags must be an array.")
    return policy


def iter_candidate_files(path: Path, *, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(candidate for candidate in path.glob(pattern) if candidate.is_file())


def is_safe_candidate_file(candidate: Path, *, watch_root: Path) -> bool:
    if candidate.is_symlink():
        return False
    try:
        resolved_candidate = candidate.resolve(strict=True)
        resolved_root = watch_root.resolve(strict=True)
    except OSError:
        return False
    return resolved_candidate == resolved_root or resolved_candidate.is_relative_to(resolved_root)


def file_is_stable(path: Path, *, min_age_seconds: int) -> bool:
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size <= 0:
        return False
    if time.time() - stat.st_mtime < min_age_seconds:
        return False
    with path.open("rb") as source:
        return source.read(5) == b"%PDF-"
