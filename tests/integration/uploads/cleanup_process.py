"""Real worker processes with test-only crash barriers in an isolated database."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from lib.config import get_settings
from lib.storage import ObjectStorage
from lib.uploads.policy import UploadPolicy
from lib.uploads.staging import UploadStaging
from scripts.gpu.probe_database import verify_isolated_database
from tests.integration.uploads.test_lifecycle import rows


class PipeBarrier:
    """Single-writer test signal without a process-shared Condition lock.

    SIGKILL can strand multiprocessing.Event's synchronization lock. These
    bounded tests send at most a few one-byte signals, safely below pipe capacity.
    """

    def __init__(self, context):
        self.reader, self.writer = context.Pipe(duplex=False)
        self.observed = False

    def set(self):
        self.writer.send_bytes(b"1")

    def wait(self, timeout=None):
        if self.observed:
            return True
        if not self.reader.poll(timeout):
            return False
        self.observed = self.reader.recv_bytes() == b"1"
        return self.observed

    def close(self):
        self.reader.close()
        self.writer.close()


def runtime_environment(upload, tmp_path):
    """Use the real default runtime layout, preserving the fixture's cleanup owner."""
    url = os.environ["STRUCTURA_TEST_DATABASE_URL"]
    expected = verify_isolated_database(url)
    # The real worker is intentionally global. Never point it at test transfers
    # whose storage belongs to another fixture root.
    assert not rows(
        "SELECT t.id FROM upload_transfers t JOIN upload_attempts a ON a.id=t.upload_id "
        "WHERE a.household_id<>%s AND t.cleanup_confirmed_at IS NULL",
        (upload.credential.household_id,),
    ), "Another fixture still owns reserved upload IO."
    root = tmp_path / "runtime"
    storage = ObjectStorage(
        canonical_root=root / "objects" / "canonical",
        derived_root=root / "objects" / "derived",
        export_root=root / "objects" / "exports",
    )
    upload.service.storage = storage
    upload.service.staging = UploadStaging(storage)
    upload.service.policy = UploadPolicy(cleanup_lease_seconds=2)
    return {
        **os.environ,
        "STRUCTURA_DATABASE_URL": url,
        "STRUCTURA_RUNTIME_ROOT": str(root),
        "STRUCTURA_UPLOAD_CLEANUP_EXPECTED_DATABASE": expected,
        "STRUCTURA_UPLOAD_CLEANUP_INTERVAL_SECONDS": "1",
        "STRUCTURA_UPLOAD_CLEANUP_SWEEP_BUDGET_SECONDS": "2",
        "STRUCTURA_UPLOAD_CLEANUP_STALE_SECONDS": "5",
        "STRUCTURA_UPLOAD_CLEANUP_LEASE_SECONDS": "2",
        "STRUCTURA_UPLOAD_CLEANUP_HEALTH_PORT": "0",
    }


def run_once(environment):
    result = subprocess.run(
        [sys.executable, "-m", "workers.upload_cleanup.worker", "--once"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    return result


def transfer_record(identity):
    return rows("SELECT * FROM upload_transfers WHERE id=%s", (identity,))[0]


def wait_for(predicate, *, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError("Expected bounded process progress did not occur.")


def wait_for_claim_expiry(identity):
    wait_for(
        lambda: rows(
            "SELECT cleanup_expires_at<=clock_timestamp() AS expired "
            "FROM upload_transfers WHERE id=%s",
            (identity,),
        )[0]["expired"]
    )


def barrier_worker(environment, stage, identity, ready, release):
    """Execute the actual CLI; fault injection only pauses its persistence seams."""
    import lib.uploads.cleanup as cleanup
    from workers.upload_cleanup.worker import main

    os.environ.update(environment)
    get_settings.cache_clear()
    claim_cleanup = cleanup.claim_cleanup
    finish_cleanup = cleanup.finish_cleanup

    def pause():
        ready.set()
        if not release.wait(30):
            raise AssertionError("Cleanup test barrier was not released.")

    def claim(*args):
        result = claim_cleanup(*args)
        if stage == "after_claim" and result and result.transfer_id == identity:
            pause()
        return result

    def finish(value):
        if stage == "after_unlink" and value.transfer_id == identity:
            pause()
        return finish_cleanup(value)

    cleanup.claim_cleanup = claim
    cleanup.finish_cleanup = finish
    sys.argv = ["upload-cleanup-test", "--once"]
    raise SystemExit(main())


def stalled_writer(root, identity, ready, release):
    """A real open writer can outlive its DB lease and is never stolen by cleanup."""
    storage = ObjectStorage(canonical_root=Path(root))
    staging = UploadStaging(storage)
    with staging.lock(identity), staging.open_new(identity) as stream:
        stream.write(b"first bytes")
        stream.flush()
        ready.set()
        if not release.wait(30):
            raise AssertionError("Writer test barrier was not released.")
        stream.write(b"late bytes")
