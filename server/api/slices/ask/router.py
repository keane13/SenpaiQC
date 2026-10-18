from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from container import get_container
from guards import ai_quota

from . import service

router = APIRouter(prefix="/ask", tags=["ask"])


class Turn(BaseModel):
    role: str
    text: str = Field(max_length=4000)


class Question(BaseModel):
    question: str = Field(max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=20)


@router.post("")
def ask(body: Question, user: str = Depends(ai_quota)):
    try:
        return service.ask(get_container(), body.question, [t.model_dump() for t in body.history])
    except ValueError as exc:
        raise HTTPException(422, str(exc))
