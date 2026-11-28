import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.knowledge import get_knowledge_service
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_knowledge_service, None)


def test_question_and_source_mapping(client):
    def service(question):
        assert question == "How do I bounce?"
        return {
            "status": "completed", "answer": "Bend the knees. [S1]", "model": "test-model",
            "sources": {"S1": {"source_id": "video", "chunk_id": "video:1", "title": "Dance",
                               "source_url": "https://example.test", "time_range_ms": [10, 20],
                               "text": "Internal passage"}},
            "usage": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
            "timings_ms": {"total": 1.0}, "unknown_citations": [],
        }

    app.dependency_overrides[get_knowledge_service] = lambda: service
    response = client.post("/api/v1/knowledge/ask", json={"question": "  How do I bounce?  "})
    assert response.status_code == 200
    data = response.json()
    assert "[S1]" in data["answer"]
    assert data["sources"] == {"S1": {"source_id": "video", "chunk_id": "video:1", "title": "Dance",
                                      "source_url": "https://example.test", "time_range_ms": [10, 20]}}
    assert data["usage"]["total_tokens"] == 25


@pytest.mark.parametrize("body", [{}, {"question": "  "}, {"question": "x" * 2001}, {"question": 123}])
def test_invalid_question_never_calls_service(client, body):
    def unexpected(question):
        pytest.fail("Invalid question reached service")
    app.dependency_overrides[get_knowledge_service] = lambda: unexpected
    assert client.post("/api/v1/knowledge/ask", json=body).status_code == 422


def test_query_token_limit(client):
    def token_limit(question):
        raise HTTPException(422, "Question exceeds the 512-token embedding input limit.")
    app.dependency_overrides[get_knowledge_service] = lambda: token_limit
    response = client.post("/api/v1/knowledge/ask", json={"question": "valid characters"})
    assert response.status_code == 422 and "512-token" in response.json()["detail"]


def test_unconfigured_rag_leaves_health_available(client, monkeypatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert client.post("/api/v1/knowledge/ask", json={"question": "bounce"}).status_code == 503
    assert client.get("/health").status_code == 200
    assert "/api/v1/knowledge/ask" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("result,code,detail", [
    ({"error": {"type": "APITimeoutError", "http_status": None}}, 504, "timed out"),
    ({"error": {"type": "InternalServerError", "http_status": 500}}, 502, "request failed"),
    ({"error": {"type": "AuthenticationError", "http_status": 401}}, 503, "configuration"),
    ({"status": "incomplete", "answer": "partial", "incomplete_reason": "max_output_tokens"}, 502, "token limit"),
    ({"status": "incomplete", "answer": "partial"}, 502, "complete RAG"),
    ({"status": "completed", "answer": " "}, 502, "empty answer"),
    ({"status": "completed", "answer": "Unsupported [S6]", "unknown_citations": ["S6"]}, 502, "unknown source"),
    ({"status": "no_evidence"}, 502, "complete RAG"),
])
def test_failed_answer_is_not_returned_as_success(client, result, code, detail):
    app.dependency_overrides[get_knowledge_service] = lambda: lambda _: result
    response = client.post("/api/v1/knowledge/ask", json={"question": "bounce"})
    assert response.status_code == code
    assert detail in response.json()["detail"]
    assert "answer" not in response.json()
