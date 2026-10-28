"""Cases found by an independent code and security review of the first release."""

import shutil
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import ask as ask_module
from app.chunking import MAX_CHARS, chunk, parse_markdown
from app.config import settings
from app.database import SessionLocal, engine
from app.ingest import ingest_folder
from app.llm import is_not_found
from app.main import app
from app.models import Base, Chunk, Document

SEED = Path(__file__).resolve().parents[2] / "seed"


class FakeLLM:
    name = "fake"

    def __init__(self, reply="Antwoord.", error=None):
        self.reply, self.error, self.calls = reply, error, 0

    async def generate(self, question, passages):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture(autouse=True)
async def fresh():
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    ask_module._hits.clear()
    yield
    app.dependency_overrides.clear()


async def post(question, headers=None):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/ask", json={"question": question}, headers=headers or {})


async def test_a_file_removed_from_the_folder_is_removed_from_the_knowledge_base(tmp_path):
    for name in ("medewerkershandboek.md", "it-beveiliging.md"):
        shutil.copy(SEED / name, tmp_path / name)
    await ingest_folder(tmp_path)
    (tmp_path / "it-beveiliging.md").unlink()
    stats = await ingest_folder(tmp_path)
    async with SessionLocal() as db:
        sources = (await db.scalars(select(Document.source))).all()
        chunks = await db.scalar(select(func.count(Chunk.id)))
    assert sources == ["medewerkershandboek.md"]
    assert stats["removed"] == 1
    assert chunks == stats["chunks"]


async def test_one_unreadable_file_does_not_stop_the_rest(tmp_path):
    shutil.copy(SEED / "medewerkershandboek.md", tmp_path / "goed.md")
    (tmp_path / "kapot.pdf").write_bytes(b"this is not a pdf")
    stats = await ingest_folder(tmp_path)
    assert stats["failed"] == 1
    assert stats["added"] == 1


def test_a_long_line_without_punctuation_is_still_split():
    chunks = chunk(parse_markdown("## Kop\n\n" + "a" * 3000))
    assert len(chunks) > 1
    assert all(len(c.text) <= MAX_CHARS for c in chunks)


def test_an_answer_that_merely_contains_the_word_gevonden_is_not_a_refusal():
    assert not is_not_found("Het document is gevonden op SharePoint.")
    assert is_not_found("NIET_GEVONDEN")
    assert is_not_found("Niet_gevonden")
    assert is_not_found("NIEGT_GEVONDEN")


async def test_questions_that_never_reach_the_model_do_not_use_the_daily_cap(monkeypatch):
    await ingest_folder(SEED)
    monkeypatch.setattr(settings, "llm_daily_call_cap", 1)
    llm = FakeLLM()
    app.dependency_overrides[ask_module.get_llm] = lambda: llm
    for _ in range(3):
        await post("Wat is de hoofdstad van Frankrijk?")
    assert llm.calls == 0
    assert (await post("Hoeveel vakantiedagen heb ik per jaar?")).status_code == 200


async def test_a_failing_model_falls_back_to_the_passage_instead_of_a_500():
    await ingest_folder(SEED)
    app.dependency_overrides[ask_module.get_llm] = lambda: FakeLLM(error=TimeoutError("slow"))
    response = await post("Hoeveel vakantiedagen heb ik per jaar?")
    body = response.json()
    assert response.status_code == 200
    assert body["answered"] is True
    assert body["backend"] == "extractive"
    assert "25 vakantiedagen" in body["answer"]


async def test_a_non_ascii_admin_key_is_a_401_not_a_crash(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "geheim")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/stats", headers=[(b"x-admin-key", "é".encode("utf-8"))])
    assert response.status_code == 401


async def test_admin_and_ask_have_separate_rate_limits(monkeypatch):
    await ingest_folder(SEED)
    monkeypatch.setattr(settings, "ask_rate_limit_per_minute", 2)
    monkeypatch.setattr(settings, "admin_key", "geheim")
    for _ in range(2):
        await post("Hoeveel vakantiedagen heb ik per jaar?")
    assert (await post("Hoeveel vakantiedagen heb ik per jaar?")).status_code == 429
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/stats", headers={"X-Admin-Key": "geheim"})
    assert response.status_code == 200


def test_old_rate_limit_entries_are_evicted():
    ask_module._hits.clear()
    for number in range(2000):
        ask_module._hits[f"ask:10.0.{number // 250}.{number % 250}"].append(0.0)

    class Client:
        host = "9.9.9.9"

    class Request:
        client = Client()

    ask_module.rate_limit(Request())
    assert len(ask_module._hits) < 50
