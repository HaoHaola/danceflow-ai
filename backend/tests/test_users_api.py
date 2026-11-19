from contextlib import closing
from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient
from pymysql.err import IntegrityError as MySQLIntegrityError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.main import app
from app.models import User


@pytest.fixture
def api():
    session = Mock(spec=Session)
    app.dependency_overrides[db.get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            yield client, session
    finally:
        app.dependency_overrides.pop(db.get_db_session)


def test_session_factory_is_lazy_and_reused(monkeypatch):
    engine_factory = Mock()
    factory = Mock()
    sessionmaker = Mock(return_value=factory)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "create_db_engine", engine_factory)
    monkeypatch.setattr(db, "sessionmaker", sessionmaker)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    engine_factory.assert_not_called()

    first, second = MagicMock(), MagicMock()
    factory.side_effect = [first, second]
    with closing(db.get_db_session()) as request:
        assert next(request) is first.__enter__.return_value
    with closing(db.get_db_session()) as request:
        assert next(request) is second.__enter__.return_value
    engine_factory.assert_called_once()
    sessionmaker.assert_called_once()
    first.__exit__.assert_called_once()
    second.__exit__.assert_called_once()


def test_create_user(api):
    client, session = api

    def populate(user):
        user.id = 7
        user.created_at = datetime(2026, 11, 19, 12)

    session.refresh.side_effect = populate
    response = client.post("/api/v1/users", json={"email": " Dancer@EXAMPLE.COM "})
    assert response.status_code == 201
    assert response.json() == {
        "id": 7, "email": "Dancer@example.com", "created_at": "2026-11-19T12:00:00Z",
    }
    assert [call[0] for call in session.method_calls] == ["add", "flush", "refresh", "commit"]


@pytest.mark.parametrize("payload", [
    {},
    {"email": "invalid"},
    {"email": "Name <dancer@example.com>"},
    {"email": "a" * 64 + "@" + ".".join(["b" * 63] * 3) + ".com"},
])
def test_invalid_email(api, payload):
    client, session = api
    assert client.post("/api/v1/users", json=payload).status_code == 422
    assert not session.method_calls


@pytest.mark.parametrize(("code", "key", "expected_status"), [
    (1062, "users.uq_users_email", 409),
    (1062, "uq_users_email", 409),
    (1062, "PRIMARY", 500),
    (1048, "uq_users_email", 500),
])
def test_insert_failure(api, code, key, expected_status):
    client, session = api
    session.flush.side_effect = IntegrityError(
        None, None, MySQLIntegrityError(code, f"Duplicate entry 'test' for key '{key}'")
    )
    response = client.post("/api/v1/users", json={"email": "dancer@example.com"})
    assert response.status_code == expected_status
    assert key not in response.text
    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_commit_failure(api):
    client, session = api

    def populate(user):
        user.id = 7
        user.created_at = datetime(2026, 11, 19, 12)

    session.refresh.side_effect = populate
    session.commit.side_effect = SQLAlchemyError("internal details")
    response = client.post("/api/v1/users", json={"email": "dancer@example.com"})
    assert response.status_code == 500
    assert "internal details" not in response.text
    session.rollback.assert_called_once()


def test_get_user(api):
    client, session = api
    session.get.return_value = User(
        id=7, email="dancer@example.com", created_at=datetime(2026, 11, 19, 12)
    )
    response = client.get("/api/v1/users/7")
    assert response.status_code == 200
    assert response.json() == {
        "id": 7, "email": "dancer@example.com", "created_at": "2026-11-19T12:00:00Z",
    }
    session.get.assert_called_once_with(User, 7)
    session.commit.assert_not_called()


def test_get_missing_user(api):
    client, session = api
    session.get.return_value = None
    assert client.get("/api/v1/users/7").status_code == 404


@pytest.mark.parametrize("user_id", ["0", "invalid"])
def test_invalid_user_id(api, user_id):
    client, session = api
    assert client.get(f"/api/v1/users/{user_id}").status_code == 422
    session.get.assert_not_called()
