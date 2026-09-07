from __future__ import annotations

import pytest

import lib.storage.reference_cleanup as reference_cleanup
from lib.storage.verified_publication import prepare_original
from lib.uploads.cleanup import clean_transfer
from tests.integration.uploads.test_cleanup import expire, staged
from tests.integration.uploads.test_lifecycle import rows


def test_failed_canonical_unlink_sync_retains_reservation_until_durable_missing_retry(
    upload, monkeypatch
):
    lease, content = staged(upload)
    prepared = prepare_original(
        upload.service.storage,
        upload.service.staging.path(lease.transfer_id),
        upload.service.staging.publication_path(lease.transfer_id),
        content,
    )
    stored = prepared.commit()
    expire(lease.transfer_id)
    real_sync = reference_cleanup.sync_directory

    def fail_leaf(parent):
        if parent == stored.path.parent:
            raise OSError("Synthetic canonical directory sync failure")
        real_sync(parent)

    monkeypatch.setattr(reference_cleanup, "sync_directory", fail_leaf)
    with pytest.raises(OSError, match="Synthetic canonical directory sync failure"):
        clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    assert not stored.path.exists()
    assert upload.service.staging.path(lease.transfer_id).exists()
    assert upload.service.staging.publication_path(lease.transfer_id).exists()
    reservation = rows("SELECT * FROM upload_transfers WHERE id=%s", (lease.transfer_id,))[0]
    assert reservation["cleanup_confirmed_at"] is None and reservation["io_stopped_at"] is None
    observed = []

    def observe(parent):
        real_sync(parent)
        observed.append(parent)

    monkeypatch.setattr(reference_cleanup, "sync_directory", observe)
    rows(
        "UPDATE upload_transfers SET cleanup_expires_at=clock_timestamp()-interval '1 second' "
        "WHERE id=%s RETURNING id",
        (lease.transfer_id,),
    )
    assert clean_transfer(upload.service.staging, lease.transfer_id, upload.service.policy)
    assert observed == list(stored.path.parents)
    assert not upload.service.staging.path(lease.transfer_id).exists()
    assert not upload.service.staging.publication_path(lease.transfer_id).exists()
    assert rows("SELECT * FROM upload_transfers WHERE id=%s", (lease.transfer_id,))[0][
        "cleanup_confirmed_at"
    ]
