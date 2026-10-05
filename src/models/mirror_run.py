"""Per-resource ingestion outcomes used for freshness and retry visibility."""

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, func

from src.models.base import Base


class MirrorResourceRun(Base):
    __tablename__ = "mirror_resource_runs"
    __table_args__ = (Index("idx_mirror_run_resource_completed", "resource_type", "completed_at"),)

    run_id = Column(String(36), primary_key=True)
    resource_type = Column(String(64), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(16), nullable=False)
    attempted = Column(Integer, nullable=False)
    succeeded = Column(Integer, nullable=False)
    failed = Column(Integer, nullable=False)
    failed_ids = Column(JSON, nullable=False)
