import hmac
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ask import admin_rate_limit, get_db
from app.config import settings
from app.models import Question

router = APIRouter(prefix="/admin", dependencies=[Depends(admin_rate_limit)])


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not settings.admin_key:
        raise HTTPException(status_code=503, detail="Admin is niet geconfigureerd.")
    if x_admin_key is None or not hmac.compare_digest(
        x_admin_key.encode("utf-8"), settings.admin_key.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Ongeldige admin-sleutel.")


class QuestionOut(BaseModel):
    id: int
    question: str
    answered: bool
    confidence: float
    backend: str
    created_at: datetime


class StatsOut(BaseModel):
    total: int
    answered: int
    unanswered: int
    low_confidence: int


def _filter(kind: str):
    if kind == "unanswered":
        return Question.answered.is_(False)
    if kind == "low_confidence":
        return (Question.answered.is_(True)) & (Question.confidence < settings.low_confidence_below)
    return None


@router.get("/questions", response_model=list[QuestionOut], dependencies=[Depends(require_admin)])
async def list_questions(
    filter: Literal["all", "unanswered", "low_confidence"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[Question]:
    query = select(Question).order_by(Question.id.desc()).limit(limit).offset(offset)
    condition = _filter(filter)
    if condition is not None:
        query = query.where(condition)
    return list((await db.scalars(query)).all())


@router.get("/stats", response_model=StatsOut, dependencies=[Depends(require_admin)])
async def stats(db: AsyncSession = Depends(get_db)) -> StatsOut:
    total = await db.scalar(select(func.count(Question.id))) or 0
    answered = (
        await db.scalar(select(func.count(Question.id)).where(Question.answered.is_(True))) or 0
    )
    low = await db.scalar(select(func.count(Question.id)).where(_filter("low_confidence"))) or 0
    return StatsOut(total=total, answered=answered, unanswered=total - answered, low_confidence=low)
