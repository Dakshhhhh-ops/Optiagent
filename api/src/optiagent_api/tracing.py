"""Requirement traceability computed on the server, from data the server holds."""

from __future__ import annotations

from fastapi import HTTPException

from optiagent_agent.review import Review
from optiagent_agent.traceability import TraceabilityReport, TraceRow, trace
from optiagent_api.datasets import DatasetStore
from optiagent_core.ingest import AssignmentMapping, TransportationMapping, load_problem
from optiagent_core.schema import AssignmentProblem, TransportationProblem


def trace_on_server(
    problem: TransportationProblem | AssignmentProblem,
    description: str | None,
    *,
    dataset_id: str | None,
    mapping: TransportationMapping | AssignmentMapping | None,
    requirements: list[str],
    review: Review | None,
    datasets: DatasetStore,
    user: str | None,
) -> TraceabilityReport:
    """Trace a problem. A client-supplied mapping is trusted only after the stored upload,
    re-read with it, gives exactly this problem."""

    def run(used: TransportationMapping | AssignmentMapping | None) -> TraceabilityReport:
        return trace(problem, description, mapping=used, requirements=requirements, review=review)

    if not (dataset_id and mapping is not None):
        return run(None)
    try:
        tables = datasets.tables(dataset_id, user)
    except KeyError:
        raise HTTPException(404, f"unknown dataset {dataset_id!r}") from None
    if load_problem(tables, mapping).problem == problem:
        return run(mapping)
    report = run(None)
    mismatch = TraceRow(
        requirement="uploaded data",
        interpretation="The problem differs from what the mapping reads from the uploaded files.",
        method="file_data",
        status="unresolved",
        note="Values were changed after loading, or the mapping is not the one used.",
    )
    report.requirements.insert(0, mismatch)
    return report
