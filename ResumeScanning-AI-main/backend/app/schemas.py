from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScreeningSummary(BaseModel):
    id: int
    title: str
    candidate_count: int
    top_score: float
    created_at: datetime


class ScreeningResponse(BaseModel):
    id: int
    title: str
    job_description: str
    requirements: dict[str, Any]
    candidates: list[dict[str, Any]]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    app: str
    database: str
