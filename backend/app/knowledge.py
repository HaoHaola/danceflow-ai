import os
from pathlib import Path
from threading import Lock
from typing import Annotated, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from .config import load_local_env
from .schemas import AskRequest, AskResponse


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
_service = None
_service_lock = Lock()


def ask_runtime(question: str) -> dict:
    global _service

    try:
        with _service_lock:
            load_local_env()
            artifact = os.getenv("RAG_ARTIFACT", "").strip()
            device = os.getenv("RAG_RERANKER_DEVICE", "mps")
            if not artifact or not os.getenv("OPENAI_API_KEY", "").strip() or device not in {"mps", "cpu"}:
                raise HTTPException(503, "RAG runtime or configuration is unavailable.")
            from evaluations.rag.answer import QueryTokenLimitError, RagService
            from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

            if _service is None:
                _service = RagService(Path(artifact), device)
            service = _service
    except (ImportError, OSError):
        raise HTTPException(503, "RAG runtime or configuration is unavailable.") from None

    try:
        return service.ask(question)
    except QueryTokenLimitError:
        raise HTTPException(422, "Question exceeds the 512-token embedding input limit.") from None
    except ResponseHandlingException as error:
        if isinstance(error.source, (httpx.TimeoutException, TimeoutError)):
            raise HTTPException(504, "Qdrant timed out.") from None
        if isinstance(error.source, httpx.ConnectError):
            raise HTTPException(503, "Qdrant is unavailable.") from None
        raise HTTPException(502, "Qdrant request failed.") from None
    except UnexpectedResponse as error:
        if error.status_code == 404:
            raise HTTPException(503, "RAG collection is unavailable.") from None
        if error.status_code in {408, 504}:
            raise HTTPException(504, "Qdrant timed out.") from None
        raise HTTPException(502, "Qdrant request failed.") from None
    except (ImportError, OSError, ValueError, RuntimeError, KeyError, AssertionError):
        raise HTTPException(503, "RAG runtime or configuration is unavailable.") from None
    except Exception:
        raise HTTPException(502, "RAG processing failed.") from None


def get_knowledge_service() -> Callable[[str], dict]:
    return ask_runtime


@router.post("/ask", response_model=AskResponse, response_model_exclude_unset=True,
             responses={502: {"description": "Upstream or invalid answer"},
                        503: {"description": "RAG runtime unavailable"},
                        504: {"description": "Upstream timeout"}})
def ask(request: AskRequest, service: Annotated[Callable[[str], dict], Depends(get_knowledge_service)]) -> AskResponse:
    result = service(request.question)
    api_error = result.get("error")
    if api_error:
        if api_error["type"] == "APITimeoutError" or api_error["http_status"] in {408, 504}:
            raise HTTPException(504, "OpenAI request timed out.")
        if api_error["http_status"] in {401, 403}:
            raise HTTPException(503, "OpenAI configuration is unavailable.")
        raise HTTPException(502, "OpenAI request failed.")
    if result["status"] != "completed":
        if result.get("incomplete_reason") == "max_output_tokens":
            raise HTTPException(502, "Answer exceeded the output token limit.")
        raise HTTPException(502, "No complete RAG answer was available.")
    if not result["answer"].strip():
        raise HTTPException(502, "OpenAI returned an empty answer.")
    if result.get("unknown_citations"):
        raise HTTPException(502, "Answer contains an unknown source reference.")
    try:
        return AskResponse.model_validate(result)
    except ValidationError:
        raise HTTPException(502, "RAG returned an invalid response.") from None
