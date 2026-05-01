"""File storage abstraction.

LocalDiskStore is the only impl in #5a. Future S3-compatible store satisfies
the same Protocol; routes never change.

Storage layout (LocalDiskStore):
    <root>/<workspace_slug>/<sha256[0:2]>/<sha256>
"""
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol


class FileStore(Protocol):
    def put(self, workspace_slug: str, sha256: str, byte_stream: BinaryIO) -> str: ...
    def get(self, storage_key: str) -> BinaryIO: ...
    def delete(self, storage_key: str) -> None: ...
    def exists(self, storage_key: str) -> bool: ...


class LocalDiskStore:
    def __init__(self, root: str):
        self.root = Path(root)

    def _shard_path(self, workspace_slug: str, sha256: str) -> Path:
        return self.root / workspace_slug / sha256[:2] / sha256

    def _key_for(self, workspace_slug: str, sha256: str) -> str:
        return f"{workspace_slug}/{sha256[:2]}/{sha256}"

    def put(self, workspace_slug: str, sha256: str, byte_stream: BinaryIO) -> str:
        target = self._shard_path(workspace_slug, sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            shutil.copyfileobj(byte_stream, out, length=64 * 1024)
        return self._key_for(workspace_slug, sha256)

    def get(self, storage_key: str) -> BinaryIO:
        return (self.root / storage_key).open("rb")

    def delete(self, storage_key: str) -> None:
        path = self.root / storage_key
        if path.exists():
            path.unlink()

    def exists(self, storage_key: str) -> bool:
        return (self.root / storage_key).is_file()


def get_default_store() -> LocalDiskStore:
    """Factory used by FastAPI dependency wiring."""
    root = os.environ.get("FILE_STORE_ROOT", "/uploads")
    return LocalDiskStore(root=root)
