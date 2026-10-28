from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import ask as ask_module
from app.config import settings
from app.database import SessionLocal, engine
from app.ingest import ingest_folder
from app.llm import NOT_FOUND, Passage
from app.main import app
from app.models import Base, Question

SEED = Path(__file__).resolve().parents[2] / "seed"


class FakeLLM:
    name = "fake"

    def __init__(self, reply: str):
        self.reply = reply
        self.calls: list[list[Passage]] = []

    async def generate(self, question, passages):
        self.calls.append(passages)
        return self.reply


@pytest.fixture(autouse=True)
async def seeded():
    async with engine.begin() as conn:
        await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.run_sync(Base.metadata.drop_all)
    await ingest_folder(SEED)
    ask_module._hits.clear()
    yield
    app.dependency_overrides.clear()


async def post(question: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/ask", json={"question": question})


async def test_in_scope_question_returns_cited_passage_without_a_key():
    response = await post("Hoeveel vakantiedagen heb ik per jaar?")
    body = response.json()
    assert response.status_code == 200
    assert body["answered"] is True
    assert body["backend"] == "extractive"
    assert "25 vakantiedagen" in body["answer"]
    assert body["citations"][0]["source"] == "medewerkershandboek.md"
    assert body["confidence"] >= settings.min_score


async def test_pdf_and_docx_sources_are_cited():
    pdf = (await post("Waar verzamelen we bij brandalarm?")).json()
    docx = (await post("Wat is de proefperiode van een nieuwe medewerker?")).json()
    assert pdf["citations"][0]["source"] == "veiligheid.pdf" and pdf["citations"][0]["page"] == 1
    assert docx["citations"][0]["source"] == "onboarding.docx"


async def test_out_of_scope_question_says_it_does_not_know():
    body = (await post("Wat is de hoofdstad van Frankrijk?")).json()
    assert body["answered"] is False
    assert body["answer"].startswith("Ik weet het niet")
    assert body["citations"] == []
    assert body["confidence"] == 0.0


async def test_llm_answer_is_returned_with_citations_and_receives_passages():
    llm = FakeLLM("Je hebt 25 dagen (medewerkershandboek.md).")
    app.dependency_overrides[ask_module.get_llm] = lambda: llm
    body = (await post("Hoeveel vakantiedagen heb ik per jaar?")).json()
    assert body["answered"] is True
    assert body["answer"] == "Je hebt 25 dagen (medewerkershandboek.md)."
    assert body["backend"] == "fake"
    assert body["citations"]
    assert llm.calls and len(llm.calls[0]) == settings.top_k


async def test_llm_not_found_marker_becomes_a_dont_know():
    app.dependency_overrides[ask_module.get_llm] = lambda: FakeLLM(NOT_FOUND)
    body = (await post("Hoeveel vakantiedagen heb ik per jaar?")).json()
    assert body["answered"] is False
    assert body["answer"].startswith("Ik weet het niet")


async def test_daily_cap_blocks_llm_calls(monkeypatch):
    monkeypatch.setattr(settings, "llm_daily_call_cap", 1)
    app.dependency_overrides[ask_module.get_llm] = lambda: FakeLLM("Antwoord.")
    first = await post("Hoeveel vakantiedagen heb ik per jaar?")
    second = await post("Hoeveel vakantiedagen heb ik per jaar?")
    assert first.status_code == 200
    assert second.status_code == 429


async def test_kill_switch_disables_generation(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    app.dependency_overrides[ask_module.get_llm] = lambda: FakeLLM("Antwoord.")
    assert (await post("Hoeveel vakantiedagen heb ik per jaar?")).status_code == 503


async def test_invalid_questions_are_rejected():
    assert (await post("ab")).status_code == 422
    assert (await post("x" * 501)).status_code == 422


async def test_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "ask_rate_limit_per_minute", 2)
    codes = [(await post("Hoeveel vakantiedagen heb ik per jaar?")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


async def test_questions_are_logged():
    await post("Wat is de hoofdstad van Frankrijk?")
    await post("Hoeveel vakantiedagen heb ik per jaar?")
    async with SessionLocal() as db:
        rows = (await db.scalars(select(Question).order_by(Question.id))).all()
        count = await db.scalar(select(func.count(Question.id)))
    assert count == 2
    assert [r.answered for r in rows] == [False, True]


async def test_ollama_backend_calls_the_local_server():
    import httpx

    from app.llm import OllamaBackend

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"message": {"content": " Antwoord. "}})

    backend = OllamaBackend(transport=httpx.MockTransport(handler))
    passage = Passage("a.md", "Kop", None, "Tekst", 0.9)
    assert await backend.generate("Vraag?", [passage]) == "Antwoord."
    assert seen["url"].endswith("/api/chat")
    assert '"stream":false' in seen["body"].replace(" ", "")
    assert "<passage" in seen["body"]


@pytest.mark.parametrize(
    "reply",
    ["NIET_GEVONDEN", "Niet_gevonden", "NIEGT_GEVONDEN", " niet gevonden. ", "NIET_GEVONDEN."],
)
def test_not_found_marker_tolerates_small_model_slips(reply):
    from app.llm import is_not_found

    assert is_not_found(reply)


def test_real_answers_are_not_mistaken_for_the_marker():
    from app.llm import is_not_found

    real = "Brandstof voor privégebruik wordt niet vergoed (medewerkershandboek.md)."
    contradiction = "Er is niets gevonden dat dit tegenspreekt, dus je hebt recht op 25 dagen."
    assert not is_not_found(real)
    assert not is_not_found(contradiction)
