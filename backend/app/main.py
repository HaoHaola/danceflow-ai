import re
from datetime import UTC
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, status
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_db_session
from .models import User
from .schemas import (
    HealthResponse,
    TrainingPlanDraftRequest,
    TrainingPlanDraftResponse,
    UserCreate,
    UserResponse,
)


app = FastAPI(title="DanceFlow AI")
DbSession = Annotated[Session, Depends(get_db_session)]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/v1/training-plans/draft", response_model=TrainingPlanDraftResponse)
def draft_training_plan(request: TrainingPlanDraftRequest) -> TrainingPlanDraftResponse:
    weekly_minutes = request.days_per_week * request.minutes_per_session
    return TrainingPlanDraftResponse(
        status="placeholder",
        message="AI generation has not been implemented yet.",
        weekly_minutes=weekly_minutes,
    )


def is_duplicate_email(error: IntegrityError) -> bool:
    original = error.orig
    return (
        isinstance(original, MySQLIntegrityError)
        and len(original.args) == 2
        and original.args[0] == 1062
        and isinstance(original.args[1], str)
        and re.search(r" for key '(?:users\.)?uq_users_email'\Z", original.args[1]) is not None
    )


def user_response(user: User) -> UserResponse:
    # The users table stores UTC as a timezone-naive MySQL DATETIME.
    return UserResponse(
        id=user.id, email=user.email, created_at=user.created_at.replace(tzinfo=UTC)
    )


@app.post("/api/v1/users", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def create_user(request: UserCreate, session: DbSession) -> UserResponse:
    user = User(email=request.email)
    try:
        session.add(user)
        session.flush()
        session.refresh(user)
        response = user_response(user)
        session.commit()
    except SQLAlchemyError as error:
        session.rollback()
        if isinstance(error, IntegrityError) and is_duplicate_email(error):
            raise HTTPException(status_code=409, detail="Email already exists.") from None
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    return response


@app.get("/api/v1/users/{user_id}", response_model=UserResponse)
def get_user(user_id: Annotated[int, Path(gt=0)], session: DbSession) -> UserResponse:
    try:
        user = session.get(User, user_id)
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user_response(user)
