from uuid import uuid4

import pytest
from ax_persistence import ArtifactStoreError, LocalBulkArtifactStore


def test_artifacts_are_private_atomic_and_job_scoped(tmp_path) -> None:
    store = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    job_id = uuid4()
    artifact = store.write_text(job_id, "reports/1.md", "private")
    path = store.local_path(artifact.uri)

    assert path.read_text() == "private"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700

    with pytest.raises(ArtifactStoreError, match="outside"):
        store.read_text((tmp_path.parent / "other.txt").as_uri())

    store.remove_job(job_id)
    assert not path.exists()


def test_verified_json_rejects_corruption(tmp_path) -> None:
    store = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    artifact = store.write_json(uuid4(), "input.json", {"safe": True})

    with pytest.raises(ArtifactStoreError, match="checksum"):
        store.read_verified_json(artifact.uri, "0" * 64)


def test_remove_file_is_scoped_and_retries_missing_files(tmp_path) -> None:
    store = LocalBulkArtifactStore(tmp_path.resolve(), minimum_free_bytes=0)
    job_id = uuid4()
    store.write_text(job_id, "weekly-reports.zip", "zip")
    with pytest.raises(ArtifactStoreError):
        store.remove_file(job_id, "../outside.zip")
    assert store.remove_file(job_id, "weekly-reports.zip")
    assert not store.remove_file(job_id, "weekly-reports.zip")
