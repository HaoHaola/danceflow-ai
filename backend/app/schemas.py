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
