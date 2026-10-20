from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import AsyncQdrantClient
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.core.config import Settings, get_settings


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(
        request.app.state.engine, expire_on_commit=False
    ) as session:
        yield session


def get_qdrant(request: Request) -> AsyncQdrantClient:
    return request.app.state.qdrant


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant)]
