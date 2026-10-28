import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.embeddings import embed
from app.llm import LLMBackend, Passage, get_backend, is_not_found
from app.models import Chunk, Document, Question

router = APIRouter()
logger = logging.getLogger(__name__)

NO_ANSWER = "Ik weet het niet: dit staat niet in de beschikbare documenten."

_hits: dict[str, deque[float]] = defaultdict(deque)


async def get_db():
    async with SessionLocal() as session:
        yield session


def make_rate_limit(scope: str) -> Callable[[Request], None]:
    """Per-client sliding window; `ask` and `admin` get separate buckets."""

    def limit(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if len(_hits) > 500:  # drop clients that have been quiet for a minute
            for key in [k for k, w in _hits.items() if not w or now - w[-1] > 60]:
                del _hits[key]
        window = _hits[f"{scope}:{client}"]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= settings.ask_rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="Te veel vragen, probeer het zo opnieuw.")
        window.append(now)

    return limit


rate_limit = make_rate_limit("ask")
admin_rate_limit = make_rate_limit("admin")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Citation(BaseModel):
    source: str
    heading: str | None
    page: int | None
    score: float
    text: str


class AskResponse(BaseModel):
    answered: bool
    answer: str
    confidence: float
    backend: str
    citations: list[Citation]


async def retrieve(db: AsyncSession, question: str) -> list[Passage]:
    vector = (await asyncio.to_thread(embed, [question]))[0]
    distance = Chunk.embedding.cosine_distance(vector)
    rows = await db.execute(
        select(Chunk, Document.source, (1 - distance).label("score"))
        .join(Document, Document.id == Chunk.document_id)
        .order_by(distance)
        .limit(settings.top_k)
    )
    return [
        Passage(source=source, heading=c.heading, page=c.page, text=c.text, score=float(score))
        for c, source, score in rows.all()
    ]


async def calls_today(db: AsyncSession, backend: str) -> int:
    return (
        await db.scalar(
            select(func.count(Question.id)).where(
                Question.backend == backend,
                Question.created_at >= func.date_trunc("day", func.now()),
            )
        )
        or 0
    )


def get_llm() -> LLMBackend:
    return get_backend()


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(rate_limit)])
async def ask(
    body: AskRequest, db: AsyncSession = Depends(get_db), llm: LLMBackend = Depends(get_llm)
) -> AskResponse:
    passages = await retrieve(db, body.question)
    top = passages[0].score if passages else 0.0
    answered = bool(passages) and top >= settings.min_score
    answer = NO_ANSWER
    backend_used = llm.name
    llm_called = False

    if answered:
        if llm.name != "extractive":
            if not settings.llm_enabled:
                raise HTTPException(status_code=503, detail="Antwoorden genereren staat uit.")
            if await calls_today(db, llm.name) >= settings.llm_daily_call_cap:
                raise HTTPException(status_code=429, detail="Dagelijkse limiet bereikt.")
        llm_called = llm.name != "extractive"
        try:
            generated = await llm.generate(body.question, passages)
        except Exception:  # a model outage must not turn into a 500 for the visitor
            logger.exception("Answer generation failed; falling back to the best passage")
            generated, backend_used = None, "extractive"
        if generated is None:
            answer = passages[0].text
        elif is_not_found(generated):
            answered = False
        else:
            answer = generated

    if not answered:
        answer = NO_ANSWER

    db.add(
        Question(
            question=body.question,
            answered=answered,
            confidence=round(top, 3),
            backend=llm.name if llm_called else "none",
        )
    )
    await db.commit()

    return AskResponse(
        answered=answered,
        answer=answer,
        confidence=round(top, 3) if answered else 0.0,
        backend=backend_used,
        citations=[
            Citation(
                source=p.source,
                heading=p.heading,
                page=p.page,
                score=round(p.score, 3),
                text=p.text,
            )
            for p in passages
        ]
        if answered
        else [],
    )
