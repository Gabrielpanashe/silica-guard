import os
import sys
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

# backend/ isn't on sys.path by default when alembic runs from this
# directory the same way it isn't for scripts/ (see seed_demo_data.py) —
# needed to import db_models below.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()  # backend/.env — same file database.py reads DATABASE_URL from

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL from the environment (backend/.env locally, a real env var
# in production) — same variable database.py itself reads, so `alembic
# upgrade head` always targets the same database the app would connect to.
# Falls back to alembic.ini's sqlalchemy.url (plain local SQLite) if unset.
#
# Deliberately NOT routed through config.set_main_option()/engine_from_config
# — configparser's default interpolation treats a bare "%" as the start of
# an interpolation placeholder, and a percent-encoded special character in
# a URL-escaped password (e.g. "%3F" for "?") trips it with a ValueError.
# Building the engine directly with create_engine() sidesteps configparser
# for the URL entirely.
_database_url = os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

from db_models import Base  # noqa: E402

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = create_engine(_database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
