from datetime import UTC, datetime

import pytest


pytestmark = pytest.mark.mysql


def test_create_read_and_reject_duplicate_user(mysql_api, mysql_user_email):
    email = mysql_user_email("Dancer-")
    before = datetime.now(UTC).replace(microsecond=0)
    created = mysql_api.post("/api/v1/users", json={"email": email})
    assert created.status_code == 201
    user = created.json()
    assert user["email"] == email
    assert user["created_at"].endswith("Z")
    assert before <= datetime.fromisoformat(user["created_at"]) <= datetime.now(UTC)

    for duplicate in (email, email.lower()):
        response = mysql_api.post("/api/v1/users", json={"email": duplicate})
        assert response.status_code == 409

    looked_up = mysql_api.get(f"/api/v1/users/{user['id']}")
    assert looked_up.status_code == 200
    assert looked_up.json() == user
    assert mysql_api.get("/api/v1/users/2147483647").status_code == 404
