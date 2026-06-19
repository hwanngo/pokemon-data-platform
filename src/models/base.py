"""SQLAlchemy base model definition."""

import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load the repo-root .env for local (non-Docker) runs. override=False (default)
# means real environment variables — e.g. those injected by docker compose —
# always take precedence, so this is a no-op inside containers.
load_dotenv()

# Get database connection from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pokemon_data"
)

# Create engine
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
