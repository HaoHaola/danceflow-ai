from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db_session
from app.main import app


@pytest.fixture
def payload():
    return {
        "user_id": 7,
        "title": " Popping ",
        "dance_style": " Popping ",
        "level": "beginner",
        "goals": [" Hit on beat "],
        "sessions": [
            {"day_of_week": 5, "duration_minutes": 20, "focus": " Hit ", "instructions": " Repeat "},
            {"day_of_week": 1, "duration_minutes": 15, "focus": " Groove ", "instructions": " Count "},
        ],
    }


@pytest.fixture
def api():
    session = Mock(spec=Session)

    def flush():
        plan = session.add.call_args.args[0]
        plan.id = 42
        plan.created_at = datetime(2026, 11, 20, 3, 15)
        for item in plan.sessions:
            item.id = 91 + item.position

    session.flush.side_effect = flush
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.pop(get_db_session)


def test_create_and_read(api, payload):
    client, session = api
    created = client.post("/api/v1/training-plans", json=payload)
    assert created.status_code == 201
    data = created.json()
    assert data == {
        **payload,
        "id": 42,
        "title": "Popping",
        "dance_style": "Popping",
        "goals": ["Hit on beat"],
        "created_at": "2026-11-20T03:15:00Z",
        "sessions": [
            {**item, "id": 91 + index, "focus": item["focus"].strip(),
             "instructions": item["instructions"].strip()}
            for index, item in enumerate(payload["sessions"])
        ],
    }
    assert [call[0] for call in session.method_calls] == ["get", "add", "flush", "refresh", "commit"]
    plan = session.add.call_args.args[0]
    session.get.return_value = plan
    session.scalars.return_value = [plan]
    assert client.get("/api/v1/training-plans/42").json() == data
    assert client.get("/api/v1/users/7/training-plans?limit=2&offset=1").json() == {
        "items": [data], "limit": 2, "offset": 1,
    }


@pytest.mark.parametrize(("key", "value"), [
    ("user_id", "7"), ("user_id", 7.0), ("user_id", True), ("user_id", 2147483648),
    ("title", " "), ("title", "a" * 121), ("dance_style", "a" * 65),
    ("level", "expert"), ("goals", []), ("goals", [" "]), ("goals", ["a" * 201]),
    ("goals", ["a"] * 11), ("sessions", []),
])
def test_invalid_plan(api, payload, key, value):
    client, session = api
    payload[key] = value
    assert client.post("/api/v1/training-plans", json=payload).status_code == 422
    session.add.assert_not_called()


@pytest.mark.parametrize(("key", "value"), [
    ("day_of_week", 0), ("day_of_week", 8), ("day_of_week", "1"), ("day_of_week", 1.0),
    ("duration_minutes", True), ("duration_minutes", 0), ("duration_minutes", 2147483648),
    ("focus", " "), ("focus", "a" * 121), ("instructions", "a" * 1001),
])
def test_invalid_session(api, payload, key, value):
    client, session = api
    payload["sessions"][0][key] = value
    assert client.post("/api/v1/training-plans", json=payload).status_code == 422
    session.add.assert_not_called()


def test_list_bounds_and_empty(api, payload):
    client, session = api
    payload["sessions"] *= 15
    assert client.post("/api/v1/training-plans", json=payload).status_code == 422
    session.scalars.return_value = []
    path = "/api/v1/users/7/training-plans"
    assert client.get(path).json() == {"items": [], "limit": 10, "offset": 0}
    assert client.get(path + "?limit=20&offset=10000").status_code == 200
    for query in ("limit=0", "limit=21", "offset=-1", "offset=10001"):
        assert client.get(f"{path}?{query}").status_code == 422


def test_missing_records(api, payload):
    client, session = api
    session.get.return_value = None
    assert client.post("/api/v1/training-plans", json=payload).status_code == 404
    assert client.get("/api/v1/training-plans/42").status_code == 404
    assert client.get("/api/v1/users/7/training-plans").status_code == 404
    session.commit.assert_not_called()


@pytest.mark.parametrize(("constraint", "status"), [
    ("fk_training_plans_user", 404), ("fk_training_sessions_plan", 500),
])
def test_integrity_error(api, payload, constraint, status):
    client, session = api
    session.flush.side_effect = IntegrityError(
        None, None, MySQLIntegrityError(1452, f"CONSTRAINT `{constraint}` FOREIGN KEY")
    )
    response = client.post("/api/v1/training-plans", json=payload)
    assert response.status_code == status
    assert constraint not in response.text
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_commit_failure(api, payload):
    client, session = api
    session.commit.side_effect = SQLAlchemyError("private database error")
    response = client.post("/api/v1/training-plans", json=payload)
    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    session.rollback.assert_called_once()


def test_response_validation_failure(api, payload):
    client, session = api
    session.refresh.side_effect = lambda plan, **kwargs: setattr(plan, "id", None)
    response = client.post("/api/v1/training-plans", json=payload)
    assert response.status_code == 500
    assert response.json() == {"detail": "Invalid training plan response."}
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_draft_still_works_without_database(api):
    client, session = api
    result = client.post("/api/v1/training-plans/draft", json={
        "dance_style": "Popping", "level": "beginner", "goals": ["Hit"],
        "days_per_week": 3, "minutes_per_session": 20,
    })
    assert result.status_code == 200
    assert result.json() == {
        "status": "placeholder", "message": "AI generation has not been implemented yet.",
        "weekly_minutes": 60,
    }
    assert not session.method_calls
