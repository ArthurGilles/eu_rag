import asyncio
from collections.abc import Sequence

from kombu.exceptions import OperationalError
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import defer
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.models.document import Document, DocumentKind, DocumentStatus
from backend.tasks.ingestion import ingest_document


async def save_upload(
    session: AsyncSession,
    kind: DocumentKind,
    number: int,
    filename: str,
    content: str,
) -> Document:
    """Insert the document, or replace the existing one's content under a new version.

    A single statement, so two concurrent uploads always get different versions.
    """
    statement = insert(Document).values(
        kind=kind,
        number=number,
        filename=filename,
        content=content,
        version=1,
        status=DocumentStatus.pending,
    )
    statement = (
        statement.on_conflict_do_update(
            index_elements=["kind", "number"],
            set_={
                "filename": statement.excluded.filename,
                "content": statement.excluded.content,
                "version": Document.version + 1,
                "status": DocumentStatus.pending,
                "error": None,
                "updated_at": func.now(),
            },
        )
        .returning(Document)
        .execution_options(populate_existing=True)
    )
    document = (await session.exec(statement)).scalar_one()
    await session.commit()
    return document


async def enqueue_ingestion(session: AsyncSession, document: Document) -> None:
    """Queue the ingestion of the document's current version (after its commit)."""
    try:
        # .delay() blocks on Redis, with retries: keep it off the event loop.
        await asyncio.to_thread(ingest_document.delay, document.id, document.version)
    except OperationalError:
        await session.exec(
            update(Document)
            .where(Document.id == document.id, Document.version == document.version)
            .values(
                status=DocumentStatus.failed,
                error="The ingestion queue is unavailable.",
            )
        )
        await session.commit()
        raise


async def list_documents(session: AsyncSession) -> Sequence[Document]:
    statement = (
        select(Document)
        .options(defer(Document.content))
        .order_by(Document.kind, Document.number)
    )
    return (await session.exec(statement)).all()


async def get_document(session: AsyncSession, document_id: int) -> Document | None:
    return await session.get(Document, document_id)
