from sqlalchemy import Engine, inspect

from optiagent_api.datasets import DatasetStore
from optiagent_api.db import migrate, normalize_url
from optiagent_api.projects import ProjectStore
from optiagent_core.examples import list_examples
from optiagent_core.pipeline import solve_problem


def test_migrations_create_the_schema_and_can_run_twice(engine: Engine) -> None:
    migrate(engine)  # already migrated by the fixture; must be a no-op
    tables = set(inspect(engine).get_table_names())
    assert {"projects", "datasets", "dataset_files", "alembic_version"} <= tables


def test_postgres_urls_use_psycopg() -> None:
    assert normalize_url("postgres://u:p@h/db").startswith("postgresql+psycopg://")
    assert normalize_url("postgresql://u:p@h/db?sslmode=require") == (
        "postgresql+psycopg://u:p@h/db?sslmode=require"
    )
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_projects_are_isolated_by_owner(engine: Engine) -> None:
    store = ProjectStore(engine)
    problem = next(e.problem for e in list_examples() if e.id == "t1_two_by_two")
    report = solve_problem(problem)
    mine = store.create(
        name="mine", source="manual", problem=problem, report=report,
        description=None, dataset_id=None, owner_id="alice",
    )  # fmt: skip

    assert [p.id for p in store.list("alice")] == [mine.id]
    assert store.list("bob") == []
    assert store.list(None) == []
    assert store.get(mine.id, "bob") is None
    assert store.rename(mine.id, "hacked", "bob") is None
    assert store.delete(mine.id, "bob") is False
    assert store.get(mine.id, "alice") is not None
    assert store.get(mine.id, "alice").report.result.objective == 80  # type: ignore[union-attr]


def test_datasets_are_isolated_by_owner(engine: Engine) -> None:
    store = DatasetStore(engine, max_file_bytes=10_000, max_files=3)
    meta = store.create([("a.csv", b"x,y\n1,2")], owner_id="alice")
    assert store.tables(meta.id, "alice")[0].rows == [["1", "2"]]
    for other in ("bob", None):
        try:
            store.tables(meta.id, other)
        except KeyError:
            pass
        else:
            raise AssertionError(f"{other} could read alice's dataset")
