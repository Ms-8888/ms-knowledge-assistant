from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import ask as ask_module
from app.config import settings
from app.database import SessionLocal, engine
from app.ingest import ingest_folder
from app.main import app
from app.models import Base, Question

SEED = Path(__file__).resolve().parents[2] / "seed"
KEY = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture(autouse=True)
async def prepared(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "test-admin-key")
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.drop_all)
    await ingest_folder(SEED)
    async with SessionLocal() as db:
        db.add_all(
            [
                Question(question="Goed beantwoord", answered=True, confidence=0.8, backend="x"),
                Question(question="Twijfelgeval", answered=True, confidence=0.3, backend="x"),
                Question(question="Onbeantwoord", answered=False, confidence=0.2, backend="x"),
            ]
        )
        await db.commit()
    ask_module._hits.clear()


async def get(path: str, headers: dict | None = None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


async def test_admin_requires_the_key():
    assert (await get("/admin/questions")).status_code == 401
    assert (await get("/admin/questions", {"X-Admin-Key": "fout"})).status_code == 401
    assert (await get("/admin/stats")).status_code == 401


async def test_admin_is_disabled_without_a_configured_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", None)
    assert (await get("/admin/questions", KEY)).status_code == 503


async def test_lists_newest_first_and_filters():
    everything = (await get("/admin/questions", KEY)).json()
    names = [q["question"] for q in everything]
    assert names == ["Onbeantwoord", "Twijfelgeval", "Goed beantwoord"]

    unanswered = (await get("/admin/questions?filter=unanswered", KEY)).json()
    assert [q["question"] for q in unanswered] == ["Onbeantwoord"]

    low = (await get("/admin/questions?filter=low_confidence", KEY)).json()
    assert [q["question"] for q in low] == ["Twijfelgeval"]


async def test_stats_and_pagination_bounds():
    assert (await get("/admin/stats", KEY)).json() == {
        "total": 3,
        "answered": 2,
        "unanswered": 1,
        "low_confidence": 1,
    }
    assert (await get("/admin/questions?limit=1", KEY)).json()[0]["question"] == "Onbeantwoord"
    assert (await get("/admin/questions?limit=500", KEY)).status_code == 422
    assert (await get("/admin/questions?filter=onzin", KEY)).status_code == 422


async def test_admin_is_rate_limited(monkeypatch):
    monkeypatch.setattr(settings, "ask_rate_limit_per_minute", 2)
    codes = [(await get("/admin/stats", KEY)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
