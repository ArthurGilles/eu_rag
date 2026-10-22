from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class DocumentKind(StrEnum):
    chapter = "chapter"
    annex = "annex"


class DocumentStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    indexed = "indexed"
    failed = "failed"


class Document(SQLModel, table=True):
    """An uploaded chapter or annex: one row per (kind, number), updated on re-upload.

    `version` is incremented by every upload, `indexed_version` is the version whose
    provisions and Qdrant points are currently published. `status` and `error`
    describe the latest uploaded version.
    """

    __table_args__ = (UniqueConstraint("kind", "number"),)

    id: int | None = Field(default=None, primary_key=True)
    kind: DocumentKind
    number: int
    title: str | None = None
    filename: str
    content: str
    version: int = 1
    indexed_version: int | None = None
    status: DocumentStatus = DocumentStatus.pending
    error: str | None = None
    chunk_count: int | None = None
    created_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )


class Provision(SQLModel, table=True):
    """A citable unit of a document (article, annex or annex section), in full."""

    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", ondelete="CASCADE", index=True)
    key: str = Field(unique=True)
    label: str
    title: str
    header: str
    position: int
    text: str
    token_count: int
