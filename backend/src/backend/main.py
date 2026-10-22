from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routes import documents, health
from backend.core.database import create_db_and_tables, create_db_engine
from backend.core.qdrant import create_async_qdrant_client, ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.engine = create_db_engine()
    app.state.qdrant = create_async_qdrant_client()
    await create_db_and_tables(app.state.engine)
    await ensure_collection(app.state.qdrant)
    yield
    await app.state.qdrant.close()
    await app.state.engine.dispose()


app = FastAPI(title="Mon Projet", lifespan=lifespan)

app.include_router(health.router)
app.include_router(documents.router)
