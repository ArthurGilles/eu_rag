from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    qdrant_host: str
    qdrant_port: int = 6333
    mistral_api_key: str

    qdrant_collection: str = "ai_act"
    embedding_model: str = "mistral-embed"
    embedding_dim: int = 1024
    # Estimated tokens per embeddings request, with a margin under the 8192 limit.
    embedding_batch_max_tokens: int = 6000
    chunk_max_tokens: int = 500
    # Average chunk length in BM25 tokens (after stopwords and stemming), measured on
    # the 316 chunks of the whole AI Act; Qdrant's default is 256.
    bm25_avg_len: float = 115.0
    max_upload_bytes: int = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
