"""Supervised upload-retention owner; no queue, model or public API capability."""

from __future__ import annotations

import argparse
import os
import signal
import threading
import time
from collections import Counter
from dataclasses import asdict

import psycopg
from pydantic import ValidationError

from lib.observability import configure_logging, log_event
from lib.storage import ObjectStorage, StorageError
from lib.uploads.cleanup import CleanupSweep, sweep_expired_uploads
from lib.uploads.policy import UploadPolicy
from workers.upload_cleanup.configuration import CleanupRuntimeConfiguration, retry_delay
from workers.upload_cleanup.health import CleanupHealth, start_cleanup_health
from workers.upload_cleanup.runtime_repository import (
    CleanupRuntimeUnavailable,
    record_cleanup_health,
    validate_runtime_database,
)
from workers.upload_cleanup.storage_namespace import CleanupStaging

RUNTIME_CODES = frozenset(
    {
        "cleanup_configuration_unavailable",
        "cleanup_database_mismatch",
        "cleanup_migration_unavailable",
        "cleanup_database_unavailable",
        "cleanup_storage_unavailable",
    }
)


def run_cleanup_worker(
    configuration: CleanupRuntimeConfiguration,
    stop: threading.Event,
    health: CleanupHealth,
    *,
    once: bool = False,
) -> int:
    policy = UploadPolicy()
    staging: CleanupStaging | None = None
    while not stop.is_set():
        started = time.monotonic()
        result = CleanupSweep()
        errors: list[str] = []
        target_verified = False
        try:
            validate_runtime_database(configuration.expected_database)
            target_verified = True
            if staging is None:
                staging = CleanupStaging(ObjectStorage())
            staging.storage.assert_available()
            result = sweep_expired_uploads(
                staging,
                policy,
                limit=configuration.limit,
                budget_seconds=configuration.sweep_budget_seconds,
                should_stop=stop.is_set,
                progress=health.progress,
                before_claim=staging.storage.assert_available,
            )
            errors.extend(result.error_codes)
        except CleanupRuntimeUnavailable as exc:
            code = str(exc)
            errors.append(code if code in RUNTIME_CODES else "cleanup_configuration_unavailable")
        except psycopg.Error:
            errors.append("cleanup_database_unavailable")
        except (OSError, StorageError):
            errors.append("cleanup_storage_unavailable")
        metrics: dict[str, object] = asdict(result)
        metrics.pop("error_codes")
        metrics["elapsed_seconds"] = round(max(0, time.monotonic() - started), 3)
        metrics["error_counts"] = dict(sorted(Counter(errors).items()))
        if target_verified:
            try:
                record_cleanup_health("degraded" if errors else "ok", metrics)
            except psycopg.Error:
                errors.append("cleanup_database_unavailable")
                metrics["error_counts"] = dict(sorted(Counter(errors).items()))
        failures = health.finish(succeeded=not errors)
        log_event("upload_cleanup_sweep", **metrics, consecutive_failures=failures)
        if once:
            return 1 if errors else 0
        delay = retry_delay(configuration.interval_seconds, failures)
        if not errors:
            delay = configuration.interval_seconds
        stop.wait(delay)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervised Structura upload cleanup")
    parser.add_argument("--once", action="store_true", help="Run one bounded operator sweep")
    args = parser.parse_args()
    configure_logging()
    stop = threading.Event()
    server = None
    health = None
    try:
        configuration = CleanupRuntimeConfiguration(
            expected_database=os.environ.get("STRUCTURA_UPLOAD_CLEANUP_EXPECTED_DATABASE", "")
        )
        # Explicit configuration is mandatory; do not clean a default dev database/root.
        if not os.environ.get("STRUCTURA_DATABASE_URL") or not os.environ.get(
            "STRUCTURA_RUNTIME_ROOT"
        ):
            raise CleanupRuntimeUnavailable("cleanup_configuration_unavailable")
        health = CleanupHealth(configuration.stale_seconds)
        server = start_cleanup_health(health, 0 if args.once else configuration.health_port)

        def handle_stop(_signum: int, _frame: object) -> None:
            health.stop()
            stop.set()

        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)
        log_event("upload_cleanup_started")
        return run_cleanup_worker(configuration, stop, health, once=args.once)
    except (ValidationError, CleanupRuntimeUnavailable):
        log_event("upload_cleanup_configuration_failed", code="cleanup_configuration_unavailable")
        return 2
    except Exception:
        # Process boundary: unexpected failures restart under supervision without
        # leaking exception messages, source paths, SQL parameters or tracebacks.
        log_event("upload_cleanup_fatal", code="cleanup_unexpected_failure")
        return 1
    finally:
        if health:
            health.stop()
        if server:
            server.shutdown()
            server.server_close()
        log_event("upload_cleanup_stopped")


if __name__ == "__main__":
    raise SystemExit(main())
