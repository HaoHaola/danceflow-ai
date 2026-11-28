from pathlib import Path

import pytest


@pytest.fixture
def reranker(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import evaluate_reranker

    return evaluate_reranker


def test_pairs_use_locked_text_and_keep_candidate_order(reranker):
    chunks = {
        "a": {"text": "First.", "embedding_text": "First section\n\nFirst."},
        "b": {"text": "Second.", "embedding_text": "Second section\n\nSecond."},
    }
    hits = [
        {"chunk_id": cid, "payload": {"chunk_id": cid, "text": chunks[cid]["text"]}}
        for cid in ("b", "a")
    ]
    assert reranker.model_pairs("query", hits, chunks) == [
        ("query", chunks["b"]["embedding_text"]), ("query", chunks["a"]["embedding_text"]),
    ]
    hits[0]["payload"]["text"] = chunks["a"]["text"]
    with pytest.raises(ValueError, match="does not match locked chunk b"):
        reranker.model_pairs("query", hits, chunks)


def test_rerank_uses_only_score_and_dense_rank_for_ties(reranker):
    hits = [{"chunk_id": str(rank), "rank": rank, "score": 1 / rank}
            for rank in range(1, 7)]
    ranked = reranker.order_candidates(hits, [1, 4, 4, 2, 9, 3], [50] * 6)
    assert [row["chunk_id"] for row in ranked] == ["5", "2", "3", "6", "4", "1"]
    assert [row["rerank_rank"] for row in ranked] == list(range(1, 7))
    assert ranked[0]["dense_score"] == hits[4]["score"]
    with pytest.raises(ValueError, match="non-finite"):
        reranker.order_candidates(hits, [1, 4, float("nan"), 2, 9, 3], [50] * 6)


def test_prefixes_share_one_order_and_require_whole_evidence_plan(reranker):
    ids = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
    hits = [{"chunk_id": cid, "rank": rank, "score": 1 / rank}
            for rank, cid in enumerate(ids, 1)]
    ranked = reranker.order_candidates(hits, [1, 0, 0, 3, 4, 5, 2, 0, 0, 0], [40] * 10)
    question = {
        "question_id": "synthetic-fixture", "language": "en",
        "minimum_sufficient": {"evaluation_chunk_sets": [["d", "g"], ["j"]]},
        "supplemental_group_ids": [], "evidence_groups": [],
    }
    chunks = {cid: {"embedding_text": f"passage {cid}"} for cid in ids}

    def tokenizer(text, *, add_special_tokens, truncation):
        assert not add_special_tokens
        assert not truncation
        return {"input_ids": text.split()}

    row = reranker.evaluate_question(question, hits, ranked, chunks, tokenizer)
    top3, top5 = (row["selected"][name] for name in ("rerank_3", "rerank_5"))
    assert top3["chunk_ids"] == top5["chunk_ids"][:3]
    assert top3["evaluation"]["member_hit"]
    assert not top3["evaluation"]["complete_plan"]
    assert top5["evaluation"]["complete_plan"]
    assert top3["evaluation"]["missing_by_plan"] == [["g"], ["j"]]
    assert top5["tokens"] == 10
    assert row["changes"]["rerank_5_to_rerank_3"]["metrics"]["complete_plan"] == "regressed"


def test_instruction_selection_keeps_original_default(reranker):
    assert reranker.parse_args(["--smoke-only"]).instruction == "default"
    assert reranker.INSTRUCTIONS["default"] == (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    picked = reranker.parse_args(["--smoke-only", "--instruction", "evidence-v1"])
    assert reranker.INSTRUCTIONS[picked.instruction] == (
        "Retrieve passages containing explicit textual evidence useful for answering the dance question, "
        "including definitions, movement sequences, or practice instructions. A passage may support "
        "only part of the question. Mere topic mentions or introductions to unavailable media are insufficient."
    )
    v2 = reranker.parse_args(["--smoke-only", "--instruction", "evidence-v2"])
    assert reranker.INSTRUCTIONS[v2.instruction] == reranker.INSTRUCTIONS["evidence-v1"] + (
        " Treat descriptions of the relevant body parts and how they move together or in sequence "
        "as evidence for the queried movement, even when the movement itself is not named."
    )


def test_bge_tokenizes_pairs_and_rejects_overflow(reranker):
    bge = reranker.BgeReranker.__new__(reranker.BgeReranker)
    bge.max_length = 5

    def tokenizer(query, *, text_pair, add_special_tokens, padding, truncation):
        assert query == ["繁中 query", "English query"]
        assert text_pair == ["first passage", "second passage"]
        assert add_special_tokens and not padding and not truncation
        return {"input_ids": [[0] * 4, [0] * 5]}

    bge.tokenizer = tokenizer
    pairs = [("繁中 query", "first passage"), ("English query", "second passage")]
    assert bge.tokenize_pairs(pairs)[1] == [4, 5]
    bge.max_length = 4
    with pytest.raises(ValueError, match="no truncation performed"):
        bge.tokenize_pairs(pairs)
