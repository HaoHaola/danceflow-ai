import re
from datetime import UTC
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Query, status
from pydantic import ValidationError
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from .db import get_db_session
from .models import TrainingPlan, TrainingSession, User
from .schemas import (
    HealthResponse,
    TrainingPlanDraftRequest,
    TrainingPlanDraftResponse,
    TrainingPlanCreate,
    TrainingPlanListResponse,
    TrainingPlanResponse,
    TrainingSessionResponse,
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


def training_plan_response(plan: TrainingPlan) -> TrainingPlanResponse:
    return TrainingPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        title=plan.title,
        dance_style=plan.dance_style,
        level=plan.level,
        goals=plan.goals,
        created_at=plan.created_at.replace(tzinfo=UTC),
        sessions=[
            TrainingSessionResponse.model_validate(item, from_attributes=True)
            for item in plan.sessions
        ],
    )


@app.post(
    "/api/v1/training-plans",
    status_code=status.HTTP_201_CREATED,
    response_model=TrainingPlanResponse,
)
def create_training_plan(request: TrainingPlanCreate, session: DbSession) -> TrainingPlanResponse:
    plan = TrainingPlan(
        **request.model_dump(exclude={"sessions"}),
        sessions=[
            TrainingSession(position=position, **item.model_dump())
            for position, item in enumerate(request.sessions)
        ],
    )
    try:
        if session.get(User, request.user_id) is None:
            raise HTTPException(status_code=404, detail="User not found.")
        session.add(plan)
        session.flush()
        session.refresh(plan, attribute_names=["created_at"])
        response = training_plan_response(plan)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        original = error.orig
        if (
            isinstance(original, MySQLIntegrityError)
            and len(original.args) == 2
            and original.args[0] == 1452
            and isinstance(original.args[1], str)
            and "CONSTRAINT `fk_training_plans_user` FOREIGN KEY" in original.args[1]
        ):
            raise HTTPException(status_code=404, detail="User not found.") from None
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    except ValidationError:
        session.rollback()
        raise HTTPException(status_code=500, detail="Invalid training plan response.") from None
    return response


@app.get("/api/v1/training-plans/{plan_id}", response_model=TrainingPlanResponse)
def get_training_plan(
    plan_id: Annotated[int, Path(ge=1, le=2147483647)], session: DbSession
) -> TrainingPlanResponse:
    try:
        plan = session.get(TrainingPlan, plan_id, options=[selectinload(TrainingPlan.sessions)])
        if plan is None:
            raise HTTPException(status_code=404, detail="Training plan not found.")
        return training_plan_response(plan)
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    except ValidationError:
        raise HTTPException(status_code=500, detail="Invalid training plan response.") from None


@app.get("/api/v1/users/{user_id}/training-plans", response_model=TrainingPlanListResponse)
def list_training_plans(
    user_id: Annotated[int, Path(ge=1, le=2147483647)],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> TrainingPlanListResponse:
    try:
        if session.get(User, user_id) is None:
            raise HTTPException(status_code=404, detail="User not found.")
        query = (
            select(TrainingPlan)
            .where(TrainingPlan.user_id == user_id)
            .order_by(TrainingPlan.id.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(TrainingPlan.sessions))
        )
        return TrainingPlanListResponse(
            items=[training_plan_response(plan) for plan in session.scalars(query)],
            limit=limit,
            offset=offset,
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database operation failed.") from None
    except ValidationError:
        raise HTTPException(status_code=500, detail="Invalid training plan response.") from None
