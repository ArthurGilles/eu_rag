from qdrant_client import AsyncQdrantClient, QdrantClient, models

from backend.core.config import get_settings

DENSE_VECTOR = "dense"
BM25_VECTOR = "bm25"
# BM25 vectors are computed by the Qdrant server itself (since Qdrant 1.15.2).
BM25_MODEL = "qdrant/bm25"


def create_async_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    # cloud_inference=True sends `models.Document` objects to the server, which runs
    # the BM25 model, instead of embedding them locally with fastembed.
    return AsyncQdrantClient(
        host=settings.qdrant_host, port=settings.qdrant_port, cloud_inference=True
    )


def create_sync_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(
        host=settings.qdrant_host, port=settings.qdrant_port, cloud_inference=True
    )


async def ensure_collection(client: AsyncQdrantClient) -> None:
    """Create the chunk collection, or check that the existing one is compatible."""
    settings = get_settings()
    name = settings.qdrant_collection
    if not await client.collection_exists(name):
        await client.create_collection(
            name,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(
                    size=settings.embedding_dim, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={
                BM25_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        return
    params = (await client.get_collection(name)).config.params
    dense = (
        params.vectors.get(DENSE_VECTOR) if isinstance(params.vectors, dict) else None
    )
    bm25 = (params.sparse_vectors or {}).get(BM25_VECTOR)
    if (
        dense is None
        or dense.size != settings.embedding_dim
        or dense.distance != models.Distance.COSINE
        or bm25 is None
        or bm25.modifier != models.Modifier.IDF
    ):
        raise RuntimeError(
            f"Qdrant collection '{name}' does not have the expected vectors "
            f"('{DENSE_VECTOR}': {settings.embedding_dim} dimensions, cosine; "
            f"'{BM25_VECTOR}': sparse with IDF). Delete it and re-upload the documents."
        )
