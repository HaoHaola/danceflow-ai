from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class TrainingPlanDraftRequest(BaseModel):
    dance_style: NonBlankText
    level: Literal["beginner", "intermediate", "advanced"]
    goals: list[NonBlankText] = Field(min_length=1)
    days_per_week: int = Field(strict=True, ge=1, le=7)
    minutes_per_session: int = Field(strict=True, gt=0)


class TrainingPlanDraftResponse(BaseModel):
    status: Literal["placeholder"]
    message: str
    weekly_minutes: int
