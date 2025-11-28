"""
SQLAlchemy database models.

Hybrid approach: Store metadata in DB, keep markdown files for content.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Project(Base):
    """Project metadata."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    client: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(50), default="Paraguay")
    language: Mapped[str] = mapped_column(String(10), default="es")
    status: Mapped[str] = mapped_column(String(50), default="created")
    campaign_type: Mapped[str] = mapped_column(String(50), default="integrated")

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        onupdate=datetime.utcnow,
        nullable=True
    )

    # Brief metadata (content still in files)
    brief_parsed: Mapped[bool] = mapped_column(default=False)
    brief_file_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    # Relationships
    ideas: Mapped[list["Idea"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )
    research_items: Mapped[list["ResearchItem"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Project(id={self.id}, name={self.name})>"


class Idea(Base):
    """Idea metadata and scores."""

    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))

    # Content stored in file
    file_path: Mapped[str] = mapped_column(String(500))

    # Scores
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="ideas")

    def __repr__(self):
        return f"<Idea(id={self.id}, title={self.title}, score={self.overall_score})>"


class ResearchItem(Base):
    """Research item metadata."""

    __tablename__ = "research_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("projects.id", ondelete="CASCADE")
    )

    category: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="web")

    # Content stored in file
    file_path: Mapped[str] = mapped_column(String(500))

    # Metadata
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="research_items")

    def __repr__(self):
        return f"<ResearchItem(id={self.id}, title={self.title})>"
