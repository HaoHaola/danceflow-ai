import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import db
from app.main import app


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_TESTS") != "1",
    reason="Run explicitly against the dedicated MySQL test database.",
)


@pytest.fixture
def mysql_client(monkeypatch):
    if (
        os.getenv("MYSQL_DATABASE") != "danceflow_df003_test"
        or os.getenv("MYSQL_HOST_PORT") != "13307"
        or not os.getenv("MYSQL_USER")
        or not os.getenv("MYSQL_PASSWORD")
    ):
        pytest.fail("Export the dedicated test database, port, user and password.")

    engine = db.create_db_engine()
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT DATABASE()")) == "danceflow_df003_test"
            assert connection.scalar(text("SELECT @@session.time_zone")) == "+00:00"
        monkeypatch.setattr(db, "_session_factory", sessionmaker(bind=engine))
        with TestClient(app) as client:
            yield client
    finally:
        engine.dispose()


def test_create_read_and_reject_duplicate_user(mysql_client):
    email = f"Dancer-{uuid4().hex}@example.com"
    before = datetime.now(UTC).replace(microsecond=0)
    created = mysql_client.post("/api/v1/users", json={"email": email})
    assert created.status_code == 201
    user = created.json()
    assert user["email"] == email
    assert user["created_at"].endswith("Z")
    assert before <= datetime.fromisoformat(user["created_at"]) <= datetime.now(UTC)

    for duplicate in (email, email.lower()):
        response = mysql_client.post("/api/v1/users", json={"email": duplicate})
        assert response.status_code == 409

    looked_up = mysql_client.get(f"/api/v1/users/{user['id']}")
    assert looked_up.status_code == 200
    assert looked_up.json() == user
    assert mysql_client.get("/api/v1/users/2147483647").status_code == 404
