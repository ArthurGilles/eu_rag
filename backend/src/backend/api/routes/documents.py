from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, UploadFile, status
from kombu.exceptions import OperationalError

from backend.api.deps import SessionDep, SettingsDep
from backend.models.document import Document
from backend.rag.parsing import read_header
from backend.schemas.document import DocumentRead
from backend.services.documents import (
    enqueue_ingestion,
    get_document,
    list_documents,
    save_upload,
)

router = APIRouter(prefix="/api")


@router.post(
    "/documents", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentRead
)
async def upload_document(
    file: UploadFile, session: SessionDep, settings: SettingsDep
) -> Document:
    """Store a chapter or annex and queue its ingestion.

    Only quick checks happen here: the document is parsed once, by the worker.
    """
    raw = await file.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file exceeds {settings.max_upload_bytes} bytes.",
        )
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is not valid UTF-8."
        ) from None
    header = read_header(content)
    if header is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The file must start with 'CHAPTER <roman numeral>' or "
            "'ANNEX <roman numeral>'.",
        )
    kind, number = header
    document = await save_upload(session, kind, number, file.filename or "", content)
    try:
        await enqueue_ingestion(session, document)
    except OperationalError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The ingestion queue is unavailable, try again later.",
        ) from None
    return document


@router.get("/documents", response_model=list[DocumentRead])
async def read_documents(session: SessionDep) -> Sequence[Document]:
    return await list_documents(session)


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def read_document(document_id: int, session: SessionDep) -> Document:
    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return document
