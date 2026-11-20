import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import db
from app.main import app
from app.models import TrainingSession


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DF004_MYSQL_TESTS") != "1",
    reason="Run explicitly against the dedicated DF-004 MySQL test database.",
)


@pytest.fixture
def mysql_api():
    if (
        os.getenv("MYSQL_DATABASE") != "danceflow_df004_test"
        or os.getenv("MYSQL_HOST_PORT") != "13308"
        or not os.getenv("MYSQL_USER")
        or not os.getenv("MYSQL_PASSWORD")
    ):
        pytest.fail("Export the dedicated DF-004 database, port, user and password.")

    engine = db.create_db_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT DATABASE()")) == "danceflow_df004_test"
            assert connection.scalar(text("SELECT @@session.time_zone")) == "+00:00"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "10f04d5c9b21"

        factory = sessionmaker(bind=engine)

        def get_test_session():
            with factory() as session:
                yield session

        app.dependency_overrides[db.get_db_session] = get_test_session
        try:
            with TestClient(app) as client:
                yield client, engine
        finally:
            app.dependency_overrides.pop(db.get_db_session)
    finally:
        engine.dispose()


def create_user(client):
    response = client.post("/api/v1/users", json={"email": f"{uuid4().hex}@example.com"})
    assert response.status_code == 201
    return response.json()["id"]


def plan_request(user_id):
    return {
        "user_id": user_id,
        "title": f"Practice {uuid4().hex}",
        "dance_style": "Popping",
        "level": "beginner",
        "goals": ["穩定踩拍", "練習 Hit"],
        "sessions": [
            {"day_of_week": day, "duration_minutes": 20, "focus": focus, "instructions": "Repeat"}
            for day, focus in [(5, "Hit"), (1, "Groove"), (5, "Isolation")]
        ],
    }


def save_plan(client, payload):
    response = client.post("/api/v1/training-plans", json=payload)
    assert response.status_code == 201
    return response.json()


def test_save_read_order_and_paginate(mysql_api):
    client, _ = mysql_api
    user_id = create_user(client)
    other_id = create_user(client)
    path = f"/api/v1/users/{user_id}/training-plans"
    assert client.get(path).json() == {"items": [], "limit": 10, "offset": 0}

    payload = plan_request(user_id)
    first = save_plan(client, payload)
    other = save_plan(client, plan_request(other_id))
    latest = save_plan(client, plan_request(user_id))
    assert first["id"] < other["id"] < latest["id"]
    assert first["created_at"].endswith("Z")
    assert first["goals"] == payload["goals"]
    assert first["user_id"] == user_id
    assert [
        {key: value for key, value in session.items() if key != "id"}
        for session in first["sessions"]
    ] == payload["sessions"]
    assert len({item["id"] for item in first["sessions"]}) == 3

    read = client.get(f"/api/v1/training-plans/{first['id']}")
    assert read.status_code == 200
    assert read.json() == first
    assert client.get(f"{path}?limit=1").json() == {"items": [latest], "limit": 1, "offset": 0}
    assert client.get(f"{path}?limit=1&offset=1").json() == {
        "items": [first], "limit": 1, "offset": 1,
    }
    assert client.get(f"{path}?limit=1&offset=2").json() == {"items": [], "limit": 1, "offset": 2}
    assert client.get(f"/api/v1/users/{other_id}/training-plans").json()["items"] == [other]


@pytest.mark.parametrize(("table", "sql", "constraint"), [
    (
        "users", """
        INSERT INTO training_plans (user_id, title, dance_style, level, goals)
        VALUES (:missing_id, 'FK test', 'Popping', 'beginner', JSON_ARRAY('goal'))
        """, "fk_training_plans_user",
    ),
    (
        "training_plans", """
        INSERT INTO training_sessions
        (plan_id, position, day_of_week, duration_minutes, focus, instructions)
        VALUES (:missing_id, 0, 1, 20, 'Hit', 'Repeat')
        """, "fk_training_sessions_plan",
    ),
])
def test_foreign_keys(mysql_api, table, sql, constraint):
    _, engine = mysql_api
    with engine.connect() as connection:
        missing_id = connection.scalar(text(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table}"))
        with pytest.raises(IntegrityError) as failure:
            connection.execute(text(sql), {"missing_id": missing_id})
        assert failure.value.orig.args[0] == 1452
        assert constraint in failure.value.orig.args[1]
        connection.rollback()


def test_child_insert_failure_rolls_back_plan(mysql_api):
    client, engine = mysql_api
    user_id = create_user(client)
    payload = plan_request(user_id)
    inserted_plan_ids = []

    def invalidate_second_session(mapper, connection, item):
        if item.position == 1:
            inserted_plan_ids.append(connection.scalar(
                text("SELECT id FROM training_plans WHERE id = :id AND title = :title"),
                {"id": item.plan_id, "title": payload["title"]},
            ))
            item.day_of_week = 8

    event.listen(TrainingSession, "before_insert", invalidate_second_session)
    try:
        response = client.post("/api/v1/training-plans", json=payload)
    finally:
        event.remove(TrainingSession, "before_insert", invalidate_second_session)

    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed."}
    assert len(inserted_plan_ids) == 1
    plan_id = inserted_plan_ids[0]
    assert plan_id is not None
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT COUNT(*) FROM training_plans WHERE id = :id"), {"id": plan_id}
        ) == 0
        assert connection.scalar(
            text("SELECT COUNT(*) FROM training_sessions WHERE plan_id = :id"), {"id": plan_id}
        ) == 0

    assert save_plan(client, payload)["user_id"] == user_id
