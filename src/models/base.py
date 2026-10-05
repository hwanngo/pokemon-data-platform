"""SQLAlchemy base model definition."""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

# Load the repo-root .env for local (non-Docker) runs. override=False (default)
# means real environment variables — e.g. those injected by docker compose —
# always take precedence, so this is a no-op inside containers.
load_dotenv()


def database_url() -> URL | None:
    """Resolve an explicit URL or complete local PostgreSQL settings."""
    value = os.getenv("DATABASE_URL")
    if value:
        return make_url(value)

    keys = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    supplied = [key for key in keys if os.getenv(key)]
    if supplied and len(supplied) != len(keys):
        raise ValueError("Set all of POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB")
    if supplied:
        return URL.create(
            "postgresql+psycopg2",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DB"],
        )
    return None


_url = database_url()
engine = (
    create_engine(
        _url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=30000"}
        if _url.get_backend_name() == "postgresql"
        else {},
    )
    if _url is not None
    else None
)
_session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def SessionLocal():
    """Create a session only when a database was explicitly configured."""
    if engine is None:
        raise RuntimeError("Set DATABASE_URL or POSTGRES_USER/PASSWORD/DB before database access")
    return _session_factory()


# Create declarative base
Base = declarative_base()


# Function to get database session (FastAPI dependency)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Yield a session that is always closed — use for CLI/dashboard/loaders.

    Prefer this over `next(get_db())`: discarding that generator leaves the
    session (and its pooled connection) dangling until GC.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
