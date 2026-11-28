from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, EmailStr, Field, StringConstraints, field_validator


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


class UserCreate(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def require_address_only(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if "<" in value or ">" in value:
                raise ValueError("Enter a single email address without a display name.")
        return value

    @field_validator("email")
    @classmethod
    def check_email_length(cls, email: str) -> str:
        if len(email) > 254:
            raise ValueError("Email must have at most 254 characters.")
        return email


class UserResponse(BaseModel):
    id: int
    email: str
    created_at: AwareDatetime


class TrainingSessionCreate(BaseModel):
    day_of_week: int = Field(strict=True, ge=1, le=7)
    duration_minutes: int = Field(strict=True, ge=1, le=2147483647)
    focus: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class TrainingPlanCreate(BaseModel):
    user_id: int = Field(strict=True, ge=1, le=2147483647)
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    dance_style: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    level: Literal["beginner", "intermediate", "advanced"]
    goals: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    ] = Field(min_length=1, max_length=10)
    sessions: list[TrainingSessionCreate] = Field(min_length=1, max_length=28)


class TrainingSessionResponse(TrainingSessionCreate):
    id: int


class TrainingPlanResponse(TrainingPlanCreate):
    id: int
    created_at: AwareDatetime
    sessions: list[TrainingSessionResponse] = Field(min_length=1, max_length=28)


class TrainingPlanListResponse(BaseModel):
    items: list[TrainingPlanResponse]
    limit: int
    offset: int


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class KnowledgeSource(BaseModel):
    chunk_id: str
    source_id: str
    title: str
    source_url: str
    section_index: int | None = None
    heading_path: list[str] | None = None
    time_range_ms: tuple[int, int] | None = None


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: dict | None = None
    output_tokens_details: dict | None = None


class AskResponse(BaseModel):
    answer: str
    sources: dict[str, KnowledgeSource]
    model: str
    usage: TokenUsage | None
    timings_ms: dict[str, float | None]
