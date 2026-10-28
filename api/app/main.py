from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import text

from app.admin import router as admin_router
from app.ask import router as ask_router
from app.config import settings
from app.database import SessionLocal, engine
from app.ingest import ingest_folder
from app.models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    if settings.auto_ingest and Path(settings.seed_dir).is_dir():
        await ingest_folder(Path(settings.seed_dir))
    yield
    await engine.dispose()


app = FastAPI(title="Knowledge Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(ask_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            vector = await db.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
    except Exception:
        return {"status": "degraded", "db": "error", "pgvector": "unknown"}
    return {"status": "ok", "db": "ok", "pgvector": "ok" if vector else "missing"}
