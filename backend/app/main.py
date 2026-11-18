from fastapi import FastAPI

from .schemas import (
    HealthResponse,
    TrainingPlanDraftRequest,
    TrainingPlanDraftResponse,
)


app = FastAPI(title="DanceFlow AI")


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
