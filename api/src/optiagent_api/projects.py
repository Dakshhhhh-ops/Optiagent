"""SQLite-backed store for saved projects (a solved problem with its description and report).

SQLite keeps the app usable without Docker; the schema is small enough to move to Postgres later.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from optiagent_core.pipeline import SolveReport
from optiagent_core.schema import AssignmentProblem, TransportationProblem

Problem = TransportationProblem | AssignmentProblem

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    source      TEXT NOT NULL,
    description TEXT,
    dataset_id  TEXT,
    problem     TEXT NOT NULL,
    report      TEXT NOT NULL,
    objective   REAL,
    status      TEXT NOT NULL,
    verified    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
)
"""


class ProjectSummary(BaseModel):
    id: str
    name: str
    kind: str
    source: Literal["ai", "manual"]
    objective: float | None
    status: str
    verified: bool
    created_at: datetime
    updated_at: datetime


class Project(ProjectSummary):
    description: str | None
    dataset_id: str | None
    problem: TransportationProblem | AssignmentProblem
    report: SolveReport


class ProjectStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            db.execute(_SCHEMA)
            db.commit()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def create(
        self,
        *,
        name: str,
        source: Literal["ai", "manual"],
        problem: Problem,
        report: SolveReport,
        description: str | None,
        dataset_id: str | None,
    ) -> Project:
        now = datetime.now(UTC).isoformat()
        project_id = uuid.uuid4().hex
        with closing(self._connect()) as db:
            db.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    name,
                    problem.kind,
                    source,
                    description,
                    dataset_id,
                    problem.model_dump_json(),
                    report.model_dump_json(),
                    report.result.objective,
                    report.result.status,
                    int(report.verified),
                    now,
                    now,
                ),
            )
            db.commit()
        project = self.get(project_id)
        assert project is not None
        return project

    def list(self) -> list[ProjectSummary]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id, name, kind, source, objective, status, verified, created_at, "
                "updated_at "
                "FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [
            ProjectSummary.model_validate({**dict(r), "verified": bool(r["verified"])})
            for r in rows
        ]

    def get(self, project_id: str) -> Project | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        return Project.model_validate(
            {
                **data,
                "verified": bool(data["verified"]),
                "problem": json.loads(data["problem"]),
                "report": json.loads(data["report"]),
            }
        )

    def rename(self, project_id: str, name: str) -> Project | None:
        with closing(self._connect()) as db:
            cursor = db.execute(
                "UPDATE projects SET name = ?, updated_at = ? WHERE id = ?",
                (name, datetime.now(UTC).isoformat(), project_id),
            )
            db.commit()
        return self.get(project_id) if cursor.rowcount else None

    def delete(self, project_id: str) -> bool:
        with closing(self._connect()) as db:
            cursor = db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            db.commit()
        return cursor.rowcount > 0
