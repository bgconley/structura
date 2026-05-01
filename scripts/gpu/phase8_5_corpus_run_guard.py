from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import os
import signal
import socket

# GPU validation invokes fixed docker commands.
import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Self

DEFAULT_CORPUS_LOCK_PATH = Path("/tmp/structura_phase8_5_private_corpus.lock")
CORPUS_CONTAINER_LABEL = "structura.phase8_5_private_corpus"
CORPUS_CONTAINER_RUN_LABEL = f"{CORPUS_CONTAINER_LABEL}.run_id"


class CorpusRunGuard:
    """Owns singleton locking and one-off Compose container cleanup for corpus runs."""

    def __init__(
        self,
        *,
        root: Path,
        lock_path: Path,
        title_prefix: str,
        argv: list[str] | None = None,
    ) -> None:
        self.root = root
        self.lock_path = lock_path
        self.title_prefix = title_prefix
        self.argv = list(argv or sys.argv)
        self.run_id: str | None = None
        self._lock_file: Any = None
        self._container_counter = 0

    def __enter__(self) -> Self:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock_file.seek(0)
            existing = self._lock_file.read().strip()
            print(
                json.dumps(
                    {
                        "stage": "corpus_lock_refused",
                        "message": "Another Phase 8.5 private corpus run is already active.",
                        "lock_path": str(self.lock_path),
                        "active_run": existing or None,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            raise SystemExit(9) from exc

        started_at = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = f"{started_at}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._write_lock_metadata()
        self._install_signal_cleanup_handlers()
        self._cleanup_labeled_corpus_containers(exclude_run_id=self.run_id)
        print(
            json.dumps(
                {
                    "stage": "corpus_lock_acquired",
                    "lock_path": str(self.lock_path),
                    "run_id": self.run_id,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc_type, exc_value, traceback
        if self.run_id:
            self.cleanup_current_run_containers()
        if self._lock_file is not None:
            with contextlib.suppress(OSError):
                self._lock_file.seek(0)
                self._lock_file.truncate()
            with contextlib.suppress(OSError):
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None
        with contextlib.suppress(OSError):
            self.lock_path.unlink()
        return False

    def compose_run_options(self, service: str) -> list[str]:
        if not self.run_id:
            return []
        self._container_counter += 1
        safe_service = service.replace("_", "-")
        short_run_id = self.run_id[-18:].lower()
        name = f"structura-phase85-{short_run_id}-{self._container_counter:03d}-{safe_service}"
        return [
            "--name",
            name,
            "--label",
            f"{CORPUS_CONTAINER_LABEL}=true",
            "--label",
            f"{CORPUS_CONTAINER_RUN_LABEL}={self.run_id}",
        ]

    def cleanup_current_run_containers(self) -> None:
        if not self.run_id:
            return
        ids = self._docker_container_ids_for_label(f"{CORPUS_CONTAINER_RUN_LABEL}={self.run_id}")
        self._stop_and_remove_containers(ids)

    def _write_lock_metadata(self) -> None:
        if self._lock_file is None or not self.run_id:
            return
        self._lock_file.seek(0)
        self._lock_file.truncate()
        self._lock_file.write(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "pid": os.getpid(),
                    "host": socket.gethostname(),
                    "cwd": str(self.root),
                    "title_prefix": self.title_prefix,
                    "started_at": dt.datetime.now(dt.UTC).isoformat(),
                    "argv": self.argv,
                },
                sort_keys=True,
            )
        )
        self._lock_file.write("\n")
        self._lock_file.flush()
        os.fsync(self._lock_file.fileno())

    def _install_signal_cleanup_handlers(self) -> None:
        def _handler(signum: int, _frame: Any) -> None:
            self.cleanup_current_run_containers()
            raise SystemExit(128 + signum)

        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            with contextlib.suppress(Exception):
                signal.signal(sig, _handler)

    def _cleanup_labeled_corpus_containers(self, *, exclude_run_id: str | None = None) -> None:
        ids = self._docker_container_ids_for_label(f"{CORPUS_CONTAINER_LABEL}=true")
        if not ids:
            return
        if exclude_run_id:
            current_ids = set(
                self._docker_container_ids_for_label(
                    f"{CORPUS_CONTAINER_RUN_LABEL}={exclude_run_id}"
                )
            )
            ids = [container_id for container_id in ids if container_id not in current_ids]
        self._stop_and_remove_containers(ids)

    def _docker_container_ids_for_label(self, label_filter: str) -> list[str]:
        result = subprocess.run(  # nosec B603
            ["docker", "ps", "-aq", "--filter", f"label={label_filter}"],
            cwd=self.root,
            check=False,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _stop_and_remove_containers(self, container_ids: list[str]) -> None:
        if not container_ids:
            return
        subprocess.run(  # nosec B603
            ["docker", "stop", *container_ids],
            cwd=self.root,
            check=False,
            text=True,
            capture_output=True,
        )
        subprocess.run(  # nosec B603
            ["docker", "rm", "-f", *container_ids],
            cwd=self.root,
            check=False,
            text=True,
            capture_output=True,
        )
