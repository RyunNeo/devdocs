from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base

target_metadata = Base.metadata
database_url = Settings().database_url


def run_migrations_offline():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    options = {} if database_url.startswith("sqlite") else {"connect_timeout": 5}
    engine = create_engine(database_url, connect_args=options)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
