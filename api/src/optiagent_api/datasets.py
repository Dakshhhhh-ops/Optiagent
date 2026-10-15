"""Database-backed store for uploaded datasets.

Original file names are kept only as metadata (stripped of any path), and file contents live in
the database, so nothing a user uploads ever touches the server's file system.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import PurePath

from pydantic import BaseModel
from sqlalchemy import Engine

from optiagent_api.db import DatasetFileRow, DatasetRow, session_factory, utcnow
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


def _meta(row: DatasetRow) -> DatasetMeta:
    return DatasetMeta(
        id=row.id,
        created_at=row.created_at,
        source=row.source,
        files=[
            StoredFile(
                original=f.original,
                stored=f"{f.position}{PurePath(f.original).suffix}",
                size=f.size,
            )
            for f in row.files
        ],
    )


class DatasetStore:
    def __init__(self, engine: Engine, max_file_bytes: int, max_files: int) -> None:
        self.sessions = session_factory(engine)
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files

    def create(
        self, files: list[tuple[str, bytes]], source: str = "upload", owner_id: str | None = None
    ) -> DatasetMeta:
        if not files:
            raise DatasetError("upload at least one file")
        if len(files) > self.max_files:
            raise DatasetError(f"at most {self.max_files} files per dataset")

        rows: list[DatasetFileRow] = []
        for i, (name, data) in enumerate(files):
            original = PurePath(name.replace("\\", "/")).name or f"file_{i + 1}"
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
            rows.append(
                DatasetFileRow(position=i, original=original[:255], size=len(data), content=data)
            )

        dataset = DatasetRow(
            id=uuid.uuid4().hex, owner_id=owner_id, source=source, created_at=utcnow(), files=rows
        )
        with self.sessions.begin() as session:
            session.add(dataset)
        return _meta(dataset)

    def _row(self, dataset_id: str, owner_id: str | None) -> DatasetRow:
        if not _ID.match(dataset_id):
            raise KeyError(dataset_id)
        with self.sessions() as session:
            row = session.get(DatasetRow, dataset_id)
            if row is None or row.owner_id != owner_id:
                raise KeyError(dataset_id)
            _ = row.files  # load while the session is open
            return row

    def meta(self, dataset_id: str, owner_id: str | None = None) -> DatasetMeta:
        return _meta(self._row(dataset_id, owner_id))

    def tables(self, dataset_id: str, owner_id: str | None = None) -> list[Table]:
        row = self._row(dataset_id, owner_id)
        tables: list[Table] = []
        for f in row.files:
            tables.extend(read_file(f.original, f.content))
        return tables
