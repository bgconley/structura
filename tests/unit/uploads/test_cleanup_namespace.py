"""Maintenance never repairs an absent namespace into apparently missing bytes."""

from pathlib import Path
from uuid import uuid4

import pytest

from lib.storage import StorageError
from lib.uploads.staging import UploadStaging
from tests.unit.uploads.test_storage import storage_at
from workers.upload_cleanup.storage_namespace import CleanupStaging


@pytest.mark.parametrize("missing", ["canonical", "staging"])
def test_existing_namespace_constructor_never_creates_missing_directories(tmp_path, missing):
    root = tmp_path / "canonical"
    if missing == "staging":
        root.mkdir()
    with pytest.raises(FileNotFoundError):
        CleanupStaging(storage_at(root))
    assert root.exists() == (missing == "staging")
    assert not (root / ".upload-attempts").exists()


def test_open_and_root_lookup_do_not_create_or_chmod_existing_namespace(tmp_path, monkeypatch):
    storage = storage_at(tmp_path)
    UploadStaging(storage)
    monkeypatch.setattr(Path, "mkdir", lambda *_a, **_kw: pytest.fail("mkdir in cleanup"))
    monkeypatch.setattr("os.chmod", lambda *_a, **_kw: pytest.fail("chmod in cleanup"))
    staging = CleanupStaging(storage)
    assert staging.storage.root_for("canonical") == tmp_path
    with pytest.raises(StorageError):
        staging.open_new(uuid4())


@pytest.mark.parametrize("replaced", ["canonical", "staging"])
def test_running_namespace_rejects_directory_replacement_and_preserves_old_bytes(
    tmp_path, replaced
):
    root = tmp_path / "canonical"
    api_staging = UploadStaging(storage_at(root))
    identity = uuid4()
    api_staging.path(identity).write_bytes(b"reserved source")
    staging = CleanupStaging(api_staging.storage)
    target = root if replaced == "canonical" else staging.root
    retained = tmp_path / "retained"
    target.rename(retained)
    UploadStaging(storage_at(root))  # A plausible but different empty namespace.
    with pytest.raises(StorageError), staging.lock(identity):
        pytest.fail("Replacement namespace acquired for cleanup")
    with pytest.raises(StorageError):
        staging.remove_data(identity)
    source = retained / ".upload-attempts" if replaced == "canonical" else retained
    assert (source / f"{identity}.data").read_bytes() == b"reserved source"
    assert not (staging.root / f"{identity}.lock").exists()


def test_namespace_identity_is_rechecked_after_actual_lock_acquisition(tmp_path, monkeypatch):
    api_staging = UploadStaging(storage_at(tmp_path))
    staging = CleanupStaging(api_staging.storage)
    identity = uuid4()
    staging.path(identity).write_bytes(b"reserved source")
    retained = tmp_path / "retained"

    def replace_during_acquisition(_path):
        staging.root.rename(retained)
        staging.root.mkdir(mode=0o700)

    monkeypatch.setattr("lib.uploads.staging.sync_directory", replace_during_acquisition)
    with pytest.raises(StorageError), staging.lock(identity):
        pytest.fail("Lock on old inode authorized the new namespace")
    assert (retained / f"{identity}.data").read_bytes() == b"reserved source"


def test_symlink_or_shared_permission_namespace_is_rejected_without_repair(tmp_path):
    storage = storage_at(tmp_path)
    api_staging = UploadStaging(storage)
    api_staging.root.chmod(0o750)
    with pytest.raises(StorageError):
        CleanupStaging(storage)
    assert api_staging.root.stat().st_mode & 0o777 == 0o750
    api_staging.root.rename(tmp_path / "other")
    api_staging.root.symlink_to(tmp_path / "other", target_is_directory=True)
    with pytest.raises(StorageError):
        CleanupStaging(storage)
