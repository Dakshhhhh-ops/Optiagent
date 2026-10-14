"""File-backed store for uploaded datasets.

Files are saved under server-generated names; the original names live only in meta.json,
so a crafted filename can never escape the dataset folder.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePath

from pydantic import BaseModel

from optiagent_core.ingest import SUPPORTED_EXTENSIONS, Table, read_file

_ID = re.compile(r"^[0-9a-f]{32}$")


class StoredFile(BaseModel):
    original: str
    stored: str
    size: int


class DatasetMeta(BaseModel):
    id: str
    created_at: datetime
    files: list[StoredFile]
    source: str = "upload"


class DatasetError(ValueError):
    pass


class DatasetStore:
    def __init__(self, root: Path, max_file_bytes: int, max_files: int) -> None:
        self.root = root
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def _dir(self, dataset_id: str) -> Path:
        if not _ID.match(dataset_id):
            raise KeyError(dataset_id)
        return self.root / dataset_id

    def create(self, files: list[tuple[str, bytes]], source: str = "upload") -> DatasetMeta:
        if not files:
            raise DatasetError("upload at least one file")
        if len(files) > self.max_files:
            raise DatasetError(f"at most {self.max_files} files per dataset")

        stored: list[tuple[StoredFile, bytes]] = []
        for i, (name, data) in enumerate(files):
            original = PurePath(name).name or f"file_{i + 1}"
            suffix = PurePath(original).suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                raise DatasetError(
                    f"{original}: unsupported file type; use {', '.join(SUPPORTED_EXTENSIONS)}"
                )
            if len(data) > self.max_file_bytes:
                raise DatasetError(
                    f"{original}: larger than {self.max_file_bytes / 1_000_000:g} MB"
                )
            try:
                read_file(original, data)
            except Exception as exc:
                raise DatasetError(f"{original}: could not be read ({exc})") from exc
            stored.append(
                (StoredFile(original=original, stored=f"{i}{suffix}", size=len(data)), data)
            )

        meta = DatasetMeta(
            id=uuid.uuid4().hex,
            created_at=datetime.now(UTC),
            files=[f for f, _ in stored],
            source=source,
        )
        folder = self._dir(meta.id)
        folder.mkdir(parents=True)
        for f, data in stored:
            (folder / f.stored).write_bytes(data)
        (folder / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        return meta

    def meta(self, dataset_id: str) -> DatasetMeta:
        path = self._dir(dataset_id) / "meta.json"
        if not path.exists():
            raise KeyError(dataset_id)
        return DatasetMeta.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def tables(self, dataset_id: str) -> list[Table]:
        meta = self.meta(dataset_id)
        folder = self._dir(dataset_id)
        tables: list[Table] = []
        for f in meta.files:
            tables.extend(read_file(f.original, (folder / f.stored).read_bytes()))
        return tables
