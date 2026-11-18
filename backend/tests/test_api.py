import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
DRAFT_URL = "/api/v1/training-plans/draft"


@pytest.fixture
def draft_request():
    return {
        "dance_style": "  popping  ",
        "level": "beginner",
        "goals": ["  improve hits  "],
        "days_per_week": 3,
        "minutes_per_session": 30,
    }


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_valid_draft(draft_request):
    response = client.post(DRAFT_URL, json=draft_request)

    assert response.status_code == 200
    assert response.json() == {
        "status": "placeholder",
        "message": "AI generation has not been implemented yet.",
        "weekly_minutes": 90,
    }


@pytest.mark.parametrize(
    ("field", "value", "location"),
    [
        ("days_per_week", 0, ["days_per_week"]),
        ("days_per_week", 8, ["days_per_week"]),
        ("days_per_week", "3", ["days_per_week"]),
        ("minutes_per_session", 0, ["minutes_per_session"]),
        ("minutes_per_session", -1, ["minutes_per_session"]),
        ("minutes_per_session", 30.0, ["minutes_per_session"]),
        ("minutes_per_session", True, ["minutes_per_session"]),
        ("dance_style", "   ", ["dance_style"]),
        ("level", "expert", ["level"]),
        ("goals", [], ["goals"]),
        ("goals", ["improve hits", "   "], ["goals", 1]),
    ],
)
def test_invalid_draft(draft_request, field, value, location):
    draft_request[field] = value

    response = client.post(DRAFT_URL, json=draft_request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", *location]


@pytest.mark.parametrize(
    "field", ["dance_style", "level", "goals", "days_per_week", "minutes_per_session"]
)
def test_missing_required_field(draft_request, field):
    del draft_request[field]

    response = client.post(DRAFT_URL, json=draft_request)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
