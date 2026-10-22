"""Dense embeddings with the Mistral API (sync: runs in the Celery worker)."""

from collections.abc import Iterator

from mistralai.client import Mistral

from backend.rag.chunking import estimate_tokens


def embed_texts(
    client: Mistral, model: str, texts: list[str], batch_max_tokens: int
) -> list[list[float]]:
    """Embed texts in as few requests as the per-request token budget allows."""
    vectors: list[list[float]] = []
    for batch in batch_texts(texts, batch_max_tokens):
        response = client.embeddings.create(model=model, inputs=batch)
        embeddings = [item.embedding for item in response.data]
        if len(embeddings) != len(batch) or any(e is None for e in embeddings):
            raise RuntimeError(
                f"Mistral returned {len(embeddings)} embeddings for {len(batch)} texts."
            )
        vectors.extend(embeddings)
    return vectors


def batch_texts(texts: list[str], max_tokens: int) -> Iterator[list[str]]:
    """Consecutive batches of at most max_tokens estimated tokens (at least one text)."""
    batch: list[str] = []
    size = 0
    for text in texts:
        tokens = estimate_tokens(text)
        if batch and size + tokens > max_tokens:
            yield batch
            batch, size = [], 0
        batch.append(text)
        size += tokens
    if batch:
        yield batch
