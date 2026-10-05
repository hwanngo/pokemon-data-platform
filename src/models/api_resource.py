"""Generic JSONB store for the PokéAPI mirror's long-tail resources."""

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from src.models.base import Base

# JSONB on Postgres, plain JSON elsewhere (e.g. SQLite in tests).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class ApiResource(Base):
    """Raw mirror of any PokéAPI resource not promoted to a relational table.

    The (resource_type, id) pair is the natural key — e.g. ("berry-flavor", 1).
    """

    __tablename__ = "api_resource"
    __table_args__ = (
        Index("idx_api_resource_name", "resource_type", "name"),
        Index("idx_api_resource_data", "data", postgresql_using="gin"),
    )

    resource_type = Column(String(64), primary_key=True)
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    data = Column(JsonType, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    source_fetched_at = Column(DateTime(timezone=True))
    loaded_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_present = Column(Boolean, nullable=False, server_default="true")

    def __repr__(self):
        return f"<ApiResource(resource_type={self.resource_type}, id={self.id}, name={self.name})>"
