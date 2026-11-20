import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import sessionmaker

from app import db
from app.main import app
from app.models import TrainingPlan, TrainingSession, User


def pytest_configure(config):
    config.addinivalue_line("markers", "mysql: uses the dedicated MySQL integration test database")


def pytest_collection_modifyitems(items):
    if os.getenv("RUN_MYSQL_TESTS") == "1":
        return
    skip_mysql = pytest.mark.skip(
        reason="Set RUN_MYSQL_TESTS=1 to run against a dedicated MySQL database."
    )
    for item in items:
        if item.get_closest_marker("mysql"):
            item.add_marker(skip_mysql)


def verify_database(connection, expected_database):
    if connection.scalar(text("SELECT DATABASE()")) != expected_database:
        pytest.fail("Connected MySQL database does not match the configured test database.")


@pytest.fixture(scope="session")
def mysql_engine():
    if os.getenv("RUN_MYSQL_TESTS") != "1":
        pytest.skip("Set RUN_MYSQL_TESTS=1 to run against a dedicated MySQL database.")

    database = os.getenv("MYSQL_DATABASE", "")
    if len(database) > 64 or not re.fullmatch(r"danceflow_[a-z0-9_]+_test", database):
        pytest.fail("Set MYSQL_DATABASE to a dedicated database named danceflow_<name>_test.")
    if not all(os.getenv(key) for key in ("MYSQL_HOST_PORT", "MYSQL_USER", "MYSQL_PASSWORD")):
        pytest.fail("Export MYSQL_HOST_PORT, MYSQL_USER and MYSQL_PASSWORD for the test database.")

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    expected_heads = ScriptDirectory.from_config(config).get_heads()
    engine = db.create_db_engine()
    try:
        with engine.connect() as connection:
            verify_database(connection, database)
            assert connection.scalar(text("SELECT @@session.time_zone")) == "+00:00"
            current_heads = MigrationContext.configure(connection).get_current_heads()
            assert set(current_heads) == set(expected_heads), (
                "Run alembic upgrade head against the test database before running MySQL tests."
            )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def mysql_api(mysql_engine, monkeypatch):
    factory = sessionmaker(bind=mysql_engine)

    def get_test_session():
        with factory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, db.get_db_session, get_test_session)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mysql_user_email(mysql_engine):
    emails = []

    def reserve_email(prefix=""):
        email = f"{prefix}{uuid4().hex}@example.com"
        emails.append(email)
        return email

    yield reserve_email

    # API requests commit their own sessions. Clean up committed rows by ownership.
    if emails:
        with mysql_engine.begin() as connection:
            verify_database(connection, mysql_engine.url.database)
            user_ids = select(User.id).where(User.email.in_(emails))
            plan_ids = select(TrainingPlan.id).where(TrainingPlan.user_id.in_(user_ids))
            connection.execute(delete(TrainingSession).where(TrainingSession.plan_id.in_(plan_ids)))
            connection.execute(delete(TrainingPlan).where(TrainingPlan.user_id.in_(user_ids)))
            connection.execute(delete(User).where(User.email.in_(emails)))
