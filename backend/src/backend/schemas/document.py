from datetime import datetime

from sqlmodel import SQLModel

from backend.models.document import DocumentKind, DocumentStatus


class DocumentRead(SQLModel):
    id: int
    kind: DocumentKind
    number: int
    title: str | None
    filename: str
    version: int
    indexed_version: int | None
    status: DocumentStatus
    error: str | None
    chunk_count: int | None
    created_at: datetime
    updated_at: datetime
