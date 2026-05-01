"""LocalDiskStore unit tests. Pure storage layer; no HTTP, no DB."""
import io
from pathlib import Path

import pytest

from app.files.store import LocalDiskStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalDiskStore:
    return LocalDiskStore(root=str(tmp_path))


def test_put_writes_sharded_path(tmp_store: LocalDiskStore, tmp_path: Path):
    sha = "abc123def456"
    key = tmp_store.put("hartwood", sha, io.BytesIO(b"hello bytes"))
    expected_path = tmp_path / "hartwood" / "ab" / sha
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"hello bytes"
    assert key == f"hartwood/ab/{sha}"


def test_put_then_get_roundtrips_bytes(tmp_store: LocalDiskStore):
    sha = "ff00aabbcc"
    payload = b"the quick brown fox jumps over the lazy dog" * 100
    key = tmp_store.put("hartwood", sha, io.BytesIO(payload))
    with tmp_store.get(key) as f:
        assert f.read() == payload


def test_exists_true_after_put(tmp_store: LocalDiskStore):
    key = tmp_store.put("hartwood", "deadbeef", io.BytesIO(b"x"))
    assert tmp_store.exists(key) is True


def test_exists_false_for_missing(tmp_store: LocalDiskStore):
    assert tmp_store.exists("hartwood/zz/nope") is False


def test_delete_removes_file(tmp_store: LocalDiskStore):
    key = tmp_store.put("hartwood", "12345678", io.BytesIO(b"y"))
    assert tmp_store.exists(key)
    tmp_store.delete(key)
    assert not tmp_store.exists(key)


def test_put_creates_parent_dirs(tmp_store: LocalDiskStore, tmp_path: Path):
    sha = "9988aa"
    tmp_store.put("brand-new-ws", sha, io.BytesIO(b"."))
    assert (tmp_path / "brand-new-ws" / "99").is_dir()


def test_put_streams_large_payload(tmp_store: LocalDiskStore):
    sha = "bigfile1"
    payload = b"a" * (5 * 1024 * 1024)  # 5 MB
    tmp_store.put("hartwood", sha, io.BytesIO(payload))
    with tmp_store.get(f"hartwood/bi/{sha}") as f:
        assert len(f.read()) == 5 * 1024 * 1024


def test_get_rejects_path_traversal(tmp_store: LocalDiskStore):
    """A storage_key with .. segments must not escape the store root."""
    with pytest.raises(ValueError, match="escapes store root"):
        tmp_store.get("../../../etc/passwd")


def test_delete_rejects_path_traversal(tmp_store: LocalDiskStore):
    with pytest.raises(ValueError, match="escapes store root"):
        tmp_store.delete("../../foo")


def test_exists_returns_false_for_traversal(tmp_store: LocalDiskStore):
    """exists() returns False for invalid keys instead of raising."""
    assert tmp_store.exists("../../../etc/passwd") is False


def test_delete_noop_on_missing(tmp_store: LocalDiskStore):
    """Deleting a missing key is a no-op (orphan GC deferred per spec)."""
    tmp_store.delete("hartwood/ab/nonexistent")  # should not raise
