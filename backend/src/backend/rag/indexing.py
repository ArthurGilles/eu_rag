"""Writes chunks to Qdrant and removes other versions (sync: runs in the worker)."""

import uuid

from qdrant_client import QdrantClient, models

from backend.core.qdrant import BM25_MODEL, BM25_VECTOR, DENSE_VECTOR
from backend.rag.chunking import Chunk

UPSERT_BATCH_SIZE = 64


def point_id(doc_key: str, version: int, chunk_index: int) -> str:
    """Deterministic id: a retried task overwrites its points instead of duplicating."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"ai-act/{doc_key}/{version}/{chunk_index}")
    )


def upsert_chunks(
    client: QdrantClient,
    collection: str,
    *,
    doc_key: str,
    doc_kind: str,
    version: int,
    chunks: list[Chunk],
    vectors: list[list[float]],
    bm25_avg_len: float,
) -> None:
    points = [
        models.PointStruct(
            id=point_id(doc_key, version, index),
            vector={
                DENSE_VECTOR: vector,
                # Qdrant computes the BM25 term weights; IDF is applied at query time.
                BM25_VECTOR: models.Document(
                    text=chunk.embedding_text,
                    model=BM25_MODEL,
                    options=models.Bm25Config(avg_len=bm25_avg_len),
                ),
            },
            payload={
                "doc_key": doc_key,
                "doc_kind": doc_kind,
                "version": version,
                "provision_key": chunk.provision_key,
                "ref": chunk.ref,
                "header": chunk.header,
                "text": chunk.text,
                "chunk_index": index,
            },
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    # wait=True: once the call returns, the points are written and searchable.
    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        client.upsert(
            collection, points=points[start : start + UPSERT_BATCH_SIZE], wait=True
        )


def delete_version(
    client: QdrantClient, collection: str, doc_key: str, version: int
) -> None:
    _delete(
        client,
        collection,
        doc_key,
        models.FieldCondition(key="version", match=models.MatchValue(value=version)),
    )


def delete_older_versions(
    client: QdrantClient, collection: str, doc_key: str, version: int
) -> None:
    # Strictly older: a newer version may already be published.
    _delete(
        client,
        collection,
        doc_key,
        models.FieldCondition(key="version", range=models.Range(lt=version)),
    )


def _delete(
    client: QdrantClient,
    collection: str,
    doc_key: str,
    condition: models.FieldCondition,
) -> None:
    client.delete(
        collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_key", match=models.MatchValue(value=doc_key)
                    ),
                    condition,
                ]
            )
        ),
        wait=True,
    )
