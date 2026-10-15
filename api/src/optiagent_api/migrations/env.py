"""Alembic environment. Migrations run programmatically from optiagent_api.db.migrate()."""

from alembic import context

from optiagent_api.db import Base

connection = context.config.attributes["connection"]
context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=connection.dialect.name == "sqlite",
)
with context.begin_transaction():
    context.run_migrations()
