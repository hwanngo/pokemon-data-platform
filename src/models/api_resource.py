"""Generic JSONB store for the PokéAPI mirror's long-tail resources."""

from sqlalchemy import JSON, Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base

# JSONB on Postgres, plain JSON elsewhere (e.g. SQLite in tests).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class ApiResource(Base):
    """Raw mirror of any PokéAPI resource not promoted to a relational table.

    The (resource_type, id) pair is the natural key — e.g. ("berry-flavor", 1).
    """

    __tablename__ = "api_resource"

    resource_type = Column(String(64), primary_key=True)
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    data = Column(JsonType, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<ApiResource(resource_type={self.resource_type}, id={self.id}, name={self.name})>"
