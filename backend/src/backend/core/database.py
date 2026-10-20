from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel

import backend.models  # noqa: F401  (registers the tables on SQLModel.metadata)
from backend.core.config import get_settings


def create_db_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


async def create_db_and_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
