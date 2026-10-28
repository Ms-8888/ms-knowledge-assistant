from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.ingest import ingest_folder
from app.models import Base, Chunk

SEED = Path(__file__).resolve().parents[2] / "seed"


@pytest.fixture(autouse=True)
async def clean_schema():
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.drop_all)
    yield


async def test_ingest_is_repeatable():
    first = await ingest_folder(SEED)
    second = await ingest_folder(SEED)

    assert first["added"] == 5 and first["updated"] == 0
    assert first["chunks"] > 0
    assert second["added"] == 0 and second["unchanged"] == 5
    assert second["chunks"] == first["chunks"]


async def test_stored_embeddings_have_expected_dimension():
    await ingest_folder(SEED)
    async with SessionLocal() as db:
        chunk = await db.scalar(select(Chunk).limit(1))
        count = await db.scalar(select(func.count(Chunk.id)))
    assert len(chunk.embedding) == 384
    assert count > 0
