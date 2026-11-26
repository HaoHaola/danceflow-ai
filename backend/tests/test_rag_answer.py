from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
import json

import pytest


@pytest.fixture
def rag(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import answer

    return answer


def test_context_uses_rerank_order_and_actual_metadata(rag):
    chunks = {
        "article": {"chunk_id": "article", "source_id": "a", "title": "Article",
                    "source_url": "https://example.test/a", "text": "Full\narticle.",
                    "heading_path": ["Groove", "Bounce"], "section_index": 2},
        "video": {"chunk_id": "video", "source_id": "b", "title": "Video",
                  "source_url": "https://example.test/b", "text": "Full video.",
                  "time_range_ms": [1200, 3600]},
        "minimal": {"chunk_id": "minimal", "source_id": "c", "text": "No metadata."},
    }
    ranked = [{"chunk_id": cid} for cid in ("video", "article", "minimal")]
    original = json.dumps(chunks)

    context, sources = rag.build_context(ranked, chunks)

    assert list(sources) == ["S1", "S2", "S3"]
    assert sources == {"S1": chunks["video"], "S2": chunks["article"], "S3": chunks["minimal"]}
    assert "title" not in sources["S3"]
    for block, (label, source) in zip(context.split("\n\n"), sources.items(), strict=True):
        header, encoded = block.split("\n", 1)
        assert header == f"[{label}]"
        assert json.loads(encoded) == source
    assert json.dumps(chunks) == original


def test_empty_context_and_unknown_reference_ids(rag):
    assert rag.build_context([], {}) == ("", {})
    assert rag.unknown_citations("Unsupported claim [S1].", {"S1": {}}) == []
    assert rag.unknown_citations("[S1][S6] [S99] [S6]", {"S1": {}}) == ["S6", "S99"]
    assert rag.unknown_citations("[S1]", {}) == ["S1"]


@pytest.mark.parametrize("status,reason", [("completed", None), ("incomplete", "max_output_tokens")])
def test_generation_request_and_response_mapping(rag, status, reason):
    client = Mock()
    usage = {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17}
    client.responses.create.return_value = SimpleNamespace(
        output_text="彎曲膝蓋 [S1]。", model="actual-model", status=status,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        usage=Mock(model_dump=Mock(return_value=usage)),
    )

    result = rag.generate(client, "configured-model", "怎麼練？", "[S1]\n參考資料")

    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["model"] == "configured-model"
    assert kwargs["instructions"] == rag.INSTRUCTIONS
    assert json.loads(kwargs["input"]) == {
        "question": "怎麼練？", "retrieved_passages": "[S1]\n參考資料",
    }
    assert kwargs["reasoning"] == {"effort": "none"}
    assert kwargs["max_output_tokens"] == 1500
    assert result == {"answer": "彎曲膝蓋 [S1]。", "model": "actual-model", "status": status,
                      "incomplete_reason": reason, "usage": usage}


def test_generation_uses_shared_settings_and_client_options(rag, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("OPENAI_MODEL", "configured-model")
    load_env = Mock()
    client_factory = Mock(return_value=MagicMock())
    generate = Mock(return_value={})
    monkeypatch.setattr(rag, "load_local_env", load_env)
    monkeypatch.setattr(rag, "OpenAI", client_factory)
    monkeypatch.setattr(rag, "generate", generate)

    rag.generate_from_settings("question", "context")

    load_env.assert_called_once_with()
    client_factory.assert_called_once_with(api_key="synthetic-key", timeout=60.0, max_retries=0)
    generate.assert_called_once_with(
        client_factory.return_value.__enter__.return_value, "configured-model", "question", "context",
    )
    monkeypatch.delenv("OPENAI_API_KEY")
    client_factory.reset_mock()
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        rag.generate_from_settings("question", "context")
    client_factory.assert_not_called()


@pytest.fixture
def candidates():
    chunks = {str(i): {"chunk_id": str(i), "text": f"Body {i}",
                       "embedding_text": f"Heading\nBody {i}"} for i in range(1, 11)}
    hits = [{"chunk_id": cid, "rank": i, "score": 1 / i,
             "payload": {"chunk_id": cid, "text": chunk["text"]}}
            for i, (cid, chunk) in enumerate(chunks.items(), 1)]
    return chunks, hits


@pytest.mark.parametrize("status,reason,output,unknown,message", [
    ("completed", None, "Reply [S1].", [], False),
    ("completed", None, "Reply [S6].", ["S6"], True),
    ("incomplete", "max_output_tokens", "Partial [S1]", [], True),
    ("completed", None, "", [], True),
])
def test_pipeline_only_sends_top_five_and_reports_answer_status(
    rag, candidates, status, reason, output, unknown, message,
):
    chunks, hits = candidates
    retrieve = Mock(return_value=(hits, {"query_embedding": 2.0, "qdrant_round_trip": 1.0}))
    score = Mock(return_value=(list(range(10)), [40] * 10))
    generator = Mock(return_value={"answer": output, "status": status, "incomplete_reason": reason})

    result = rag.run_pipeline("question", retrieve, score, chunks, generator)

    retrieve.assert_called_once_with("question")
    score.assert_called_once_with([("question", c["embedding_text"]) for c in chunks.values()])
    assert [s["chunk_id"] for s in result["sources"].values()] == ["10", "9", "8", "7", "6"]
    sent_question, sent_context = generator.call_args.args
    assert sent_question == "question"
    assert "Body 5" not in sent_context and '"text": "Body 10"' in sent_context
    assert result["unknown_citations"] == unknown
    assert ("message" in result) is message
    if reason:
        assert "上限" in result["message"]
    assert result["timings_ms"]["query_embedding"] == 2.0


def test_pipeline_dry_run_and_empty_retrieval(rag, candidates):
    chunks, hits = candidates
    dry_run = rag.run_pipeline("question", lambda _: (hits, {}), lambda _: ([0] * 10, [40] * 10), chunks)
    assert dry_run["status"] == "dry_run"
    assert dry_run["sources"]["S1"]["chunk_id"] == "1"
    assert "[S5]" in dry_run["context"]
    score, generator = Mock(), Mock()
    empty = rag.run_pipeline("question", lambda _: ([], {}), score, chunks, generator)
    assert empty["status"] == "no_evidence"
    assert empty["sources"] == {}
    score.assert_not_called()
    generator.assert_not_called()


def test_llm_only_request_has_no_context_or_tools(rag):
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text="Answer", model="actual-model", status="completed",
        incomplete_details=None, usage=None,
    )
    rag.generate(client, "configured-model", "Original question?", None)
    assert client.responses.create.call_args.kwargs == {
        "model": "configured-model", "instructions": rag.LLM_ONLY_INSTRUCTIONS,
        "input": "Original question?", "reasoning": {"effort": "none"}, "max_output_tokens": 1500,
    }


def test_llm_only_cli_does_not_import_retrieval_dependencies(rag, monkeypatch, capsys):
    import builtins
    original = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name.split(".")[0] not in {"torch", "qdrant_client", "sentence_transformers"}
        return original(name, *args, **kwargs)

    generator = Mock(return_value={
        "answer": "Answer", "status": "completed", "model": "actual-model",
        "incomplete_reason": None, "usage": None,
    })
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(rag, "generate_from_settings", generator)
    assert rag.main(["--mode", "llm-only", "--question", "Original question?"]) == 0
    generator.assert_called_once_with("Original question?", None)
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "llm-only" and output["sources"] == {}
    assert "retrieval" not in output["settings"]


def test_api_error_is_saved_without_raw_message(rag, monkeypatch):
    import httpx
    from openai import APIConnectionError

    client_factory = Mock(return_value=MagicMock())
    monkeypatch.setattr(rag, "load_local_env", Mock())
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(rag, "OpenAI", client_factory)
    monkeypatch.setattr(rag, "generate", Mock(side_effect=APIConnectionError(
        message="sensitive detail", request=httpx.Request("POST", "https://example.test"),
    )))
    result = rag.run_llm_only("question")
    assert result["status"] == "api_error"
    assert result["error"] == {"http_status": None, "type": "APIConnectionError"}
    assert "sensitive detail" not in json.dumps(result)
