import os
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from optiagent_api.db import Base, get_engine, migrate


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """A fresh, migrated database for one test.

    SQLite by default. Set OPTIAGENT_TEST_DATABASE_URL to run the same tests on Postgres
    (CI does); the schema is dropped and rebuilt for every test.
    """
    url = os.environ.get("OPTIAGENT_TEST_DATABASE_URL")
    if not url:
        engine = get_engine(f"sqlite:///{tmp_path.as_posix()}/test.db")
    else:
        engine = get_engine(url)
        with engine.begin() as connection:
            Base.metadata.drop_all(connection)
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    migrate(engine)
    return engine


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> None:
    """Rate limits are process-wide; start every test with a clean slate."""
    from optiagent_api.security import limiter

    limiter.reset()
