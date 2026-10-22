"""Celery task ingesting an uploaded chapter or annex into Qdrant and Postgres."""

from typing import Any

import httpx
from mistralai.client import Mistral
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from sqlmodel import Session, delete, select

from backend.core.celery_app import celery_app
from backend.core.config import get_settings
from backend.core.database_sync import DatabaseTask
from backend.core.mistral import create_mistral_client
from backend.core.qdrant import create_sync_qdrant_client
from backend.models.document import Document, DocumentStatus, Provision
from backend.rag.chunking import chunk_document, estimate_tokens
from backend.rag.embedding import embed_texts
from backend.rag.indexing import delete_older_versions, delete_version, upsert_chunks
from backend.rag.parsing import parse_document


class IngestionTask(DatabaseTask):
    """Base task adding Qdrant and Mistral clients, created lazily per worker process."""

    _qdrant: QdrantClient | None = None
    _mistral: Mistral | None = None

    @property
    def qdrant(self) -> QdrantClient:
        if self._qdrant is None:
            self._qdrant = create_sync_qdrant_client()
        return self._qdrant

    @property
    def mistral(self) -> Mistral:
        if self._mistral is None:
            self._mistral = create_mistral_client()
        return self._mistral

    def on_failure(
        self, exc: Exception, task_id: str, args: Any, kwargs: Any, einfo: Any
    ) -> None:
        """Record the error on the document, unless a newer upload replaced it."""
        document_id, version = args
        with self.session() as session:
            document = session.get(Document, document_id)
            if document is not None and document.version == version:
                document.status = DocumentStatus.failed
                document.error = f"{type(exc).__name__}: {exc}"
                session.add(document)
                session.commit()


@celery_app.task(
    base=IngestionTask,
    bind=True,
    # The message is acknowledged once the task ends: redelivered if the worker dies.
    acks_late=True,
    reject_on_worker_lost=True,
    # The outcome is stored on the document row.
    ignore_result=True,
    # Network errors (after the Mistral client's own retries): retry the whole task.
    autoretry_for=(httpx.TransportError, ResponseHandlingException),
    retry_backoff=True,
    max_retries=5,
)
def ingest_document(self: IngestionTask, document_id: int, version: int) -> None:
    """Parse, chunk, embed and index one version of a document, then publish it.

    Every step can be replayed: points have deterministic ids, and the publication
    is a single transaction checking that no newer version has been uploaded.
    """
    settings = get_settings()

    with self.session() as session:
        document = _lock(session, document_id)
        if document is None or document.version != version:
            return  # superseded by a newer upload
        document.status = DocumentStatus.processing
        content = document.content
        session.add(document)
        session.commit()

    parsed = parse_document(content)
    chunks = chunk_document(parsed, settings.chunk_max_tokens)
    vectors = embed_texts(
        self.mistral,
        settings.embedding_model,
        [chunk.embedding_text for chunk in chunks],
        settings.embedding_batch_max_tokens,
    )
    # The new version is written next to the published one, which is still served.
    upsert_chunks(
        self.qdrant,
        settings.qdrant_collection,
        doc_key=parsed.doc_key,
        doc_kind=parsed.kind,
        version=version,
        chunks=chunks,
        vectors=vectors,
        bm25_avg_len=settings.bm25_avg_len,
    )

    with self.session() as session:
        document = _lock(session, document_id)
        if document is None or document.version != version:
            # Superseded while running: publish nothing and drop the points just
            # written, unless they are the ones currently published.
            if document is None or document.indexed_version != version:
                delete_version(
                    self.qdrant, settings.qdrant_collection, parsed.doc_key, version
                )
            return
        session.exec(delete(Provision).where(Provision.document_id == document_id))
        session.add_all(
            Provision(
                document_id=document_id,
                key=provision.key,
                label=provision.label,
                title=provision.title,
                header=provision.header,
                position=position,
                text=provision.text,
                token_count=estimate_tokens(provision.text),
            )
            for position, provision in enumerate(parsed.provisions)
        )
        document.title = parsed.title
        document.indexed_version = version
        document.status = DocumentStatus.indexed
        document.error = None
        document.chunk_count = len(chunks)
        session.add(document)
        session.commit()

    delete_older_versions(
        self.qdrant, settings.qdrant_collection, parsed.doc_key, version
    )


def _lock(session: Session, document_id: int) -> Document | None:
    """Load the document and lock its row until the end of the transaction."""
    statement = select(Document).where(Document.id == document_id).with_for_update()
    return session.exec(statement).one_or_none()
