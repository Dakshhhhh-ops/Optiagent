"""Turn uploaded CSV / Excel files into typed problems, deterministically."""

from optiagent_core.ingest.mapping import (
    AssignmentMapping,
    DataIssue,
    KeyValue,
    LoadResult,
    LongLayout,
    Mapping,
    MatrixLayout,
    TransportationMapping,
    load_problem,
)
from optiagent_core.ingest.suggest import Suggestion, suggest_mapping
from optiagent_core.ingest.tables import (
    SUPPORTED_EXTENSIONS,
    Table,
    TableProfile,
    profile_table,
    read_file,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "AssignmentMapping",
    "DataIssue",
    "KeyValue",
    "LoadResult",
    "LongLayout",
    "Mapping",
    "MatrixLayout",
    "Suggestion",
    "Table",
    "TableProfile",
    "TransportationMapping",
    "load_problem",
    "profile_table",
    "read_file",
    "suggest_mapping",
]
