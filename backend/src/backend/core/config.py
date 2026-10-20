from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    qdrant_host: str
    qdrant_port: int = 6333
    mistral_api_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
