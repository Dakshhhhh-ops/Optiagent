"""Database-backed store for saved projects (a solved problem with its description and report)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from optiagent_api.db import ProjectRow, session_factory, utcnow
from optiagent_core.pipeline import SolveReport
from optiagent_core.schema import AssignmentProblem, TransportationProblem

Problem = TransportationProblem | AssignmentProblem


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


def _summary(row: ProjectRow) -> ProjectSummary:
    return ProjectSummary.model_validate(row, from_attributes=True)


def _project(row: ProjectRow) -> Project:
    data = {c: getattr(row, c) for c in ProjectSummary.model_fields}
    return Project.model_validate(
        {
            **data,
            "description": row.description,
            "dataset_id": row.dataset_id,
            "problem": row.problem,
            "report": row.report,
        }
    )


class ProjectStore:
    def __init__(self, engine: Engine) -> None:
        self.sessions = session_factory(engine)

    def create(
        self,
        *,
        name: str,
        source: Literal["ai", "manual"],
        problem: Problem,
        report: SolveReport,
        description: str | None,
        dataset_id: str | None,
        owner_id: str | None = None,
    ) -> Project:
        now = utcnow()
        row = ProjectRow(
            id=uuid.uuid4().hex,
            owner_id=owner_id,
            name=name,
            kind=problem.kind,
            source=source,
            description=description,
            dataset_id=dataset_id,
            problem=problem.model_dump(mode="json"),
            report=report.model_dump(mode="json"),
            objective=report.result.objective,
            status=report.result.status,
            verified=report.verified,
            created_at=now,
            updated_at=now,
        )
        with self.sessions.begin() as session:
            session.add(row)
        return _project(row)

    def list(self, owner_id: str | None = None) -> list[ProjectSummary]:
        with self.sessions() as session:
            rows = session.scalars(
                select(ProjectRow)
                .where(
                    ProjectRow.owner_id.is_(None)
                    if owner_id is None
                    else ProjectRow.owner_id == owner_id
                )
                .order_by(ProjectRow.updated_at.desc())
            ).all()
            return [_summary(r) for r in rows]

    @staticmethod
    def _owned(session: Session, project_id: str, owner_id: str | None) -> ProjectRow | None:
        row = session.get(ProjectRow, project_id)
        return row if row is not None and row.owner_id == owner_id else None

    def get(self, project_id: str, owner_id: str | None = None) -> Project | None:
        with self.sessions() as session:
            row = self._owned(session, project_id, owner_id)
            return _project(row) if row else None

    def rename(self, project_id: str, name: str, owner_id: str | None = None) -> Project | None:
        with self.sessions.begin() as session:
            row = self._owned(session, project_id, owner_id)
            if row is None:
                return None
            row.name = name
            row.updated_at = utcnow()
            return _project(row)

    def delete(self, project_id: str, owner_id: str | None = None) -> bool:
        with self.sessions.begin() as session:
            row = self._owned(session, project_id, owner_id)
            if row is None:
                return False
            session.delete(row)
            return True
