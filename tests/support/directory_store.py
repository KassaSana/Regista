"""An ObjectStore over a local directory, standing in for R2 in tests (no network)."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

from regista.pipeline.remote import RemoteObject


class DirectoryStore:
    """Objects are files under ``root``; checksum metadata is kept beside them in memory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.metadata: dict[str, str] = {}
        self.requests: list[tuple[str, str]] = []

    def _path(self, key: str) -> Path:
        return self.root / key

    def stat(self, key: str) -> RemoteObject | None:
        self.requests.append(("stat", key))
        path = self._path(key)
        if not path.exists():
            return None
        return RemoteObject(key, path.stat().st_size, self.metadata.get(key))

    def upload(self, path: Path, key: str, sha256: str) -> None:
        self.requests.append(("upload", key))
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        self.metadata[key] = sha256

    def download(self, key: str, path: Path) -> None:
        self.requests.append(("download", key))
        shutil.copyfile(self._path(key), path)

    def put_bytes(self, key: str, contents: bytes, sha256: str) -> None:
        self.requests.append(("put", key))
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        self.metadata[key] = sha256

    def get_bytes(self, key: str) -> bytes:
        self.requests.append(("get", key))
        return self._path(key).read_bytes()

    def keys(self, prefix: str) -> Iterator[str]:
        self.requests.append(("list", prefix))
        if not self.root.exists():
            return
        for path in sorted(self.root.rglob("*")):
            key = path.relative_to(self.root).as_posix()
            if path.is_file() and key.startswith(prefix):
                yield key

    def transfers(self) -> int:
        """Uploads, puts, gets, and downloads (not metadata checks)."""
        return sum(kind in ("upload", "put", "get", "download") for kind, _ in self.requests)
