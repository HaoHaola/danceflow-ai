from pathlib import Path

import pytest


@pytest.fixture
def evaluation(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import evaluate_dense

    return evaluate_dense


@pytest.mark.parametrize(("hits", "member", "complete", "outcome"), [
    (["a", "a2"], True, False, "missing_required_chunks"),
    (["a2", "b"], True, True, "complete"),
    (["c"], True, True, "complete"),
    (["partial"], False, False, "partial_only"),
    (["extra"], False, False, "supplemental_only"),
    (["unrelated"], False, False, "no_annotated_hit"),
])
def test_or_of_and_plans(evaluation, hits, member, complete, outcome):
    question = {
        "minimum_sufficient": {"evaluation_chunk_sets": [["a", "b"], ["a2", "b"], ["c"]]},
        "supplemental_group_ids": ["extra"],
        "evidence_groups": [
            {"group_id": "extra", "chunk_support": {"partial": "partial", "extra": "sufficient"}},
        ],
    }
    result = evaluation.score_question(question, hits)
    assert (result["member_hit"], result["complete_plan"], result["outcome"]) == (
        member, complete, outcome,
    )


def test_near_ties_at_rank_and_cutoff(evaluation):
    reference = {"a": 0.9, "b": 0.9 - 1e-7, "c": 0.9 - 2e-7}
    hits = [{"chunk_id": cid, "score": reference[cid]} for cid in ("c", "a")]
    result = evaluation.reference_check(hits, reference, k=2)
    assert not result["same_order"]
    assert result["cutoff_tie"]


@pytest.mark.parametrize(("rows", "error"), [
    ([("b", .7), ("a", .9)], "inverts"),
    ([("a", .9), ("c", .5)], "omitted"),
    ([("a", .8), ("b", .7)], "scores differ"),
])
def test_distinct_scores_and_ranks_checked(evaluation, rows, error):
    hits = [{"chunk_id": cid, "score": score} for cid, score in rows]
    with pytest.raises(ValueError, match=error):
        evaluation.reference_check(hits, {"a": .9, "b": .7, "c": .5}, k=2)


def test_query_preflight_counts_full_prompt_without_truncation(evaluation):
    def tokenizer(text, *, add_special_tokens, truncation):
        assert text == evaluation.QUERY_PROMPT + "query"
        assert add_special_tokens and not truncation
        return {"input_ids": [0] * 513}

    with pytest.raises(ValueError, match="exceed the 512-token limit"):
        evaluation.check_query_tokens(tokenizer, [("fixture", "query")])


def test_k_prefixes_preserve_order_and_count_candidate_tokens(evaluation):
    ids = ["a", "a2", "partial", "other", "b", "x", "y", "z", "u", "v"]
    question = {
        "minimum_sufficient": {"evaluation_chunk_sets": [["a", "b"], ["a2", "b"]]},
        "supplemental_group_ids": ["extra"],
        "evidence_groups": [
            {"group_id": "extra", "chunk_support": {"partial": "partial"}},
        ],
    }
    hits = [{"chunk_id": cid, "rank": i} for i, cid in enumerate(ids, 1)]
    results = evaluation.score_prefixes(question, hits, dict(zip(ids, range(1, 11))))
    assert [results[k]["complete_plan"] for k in ("3", "5", "10")] == [False, True, True]
    assert all(result["member_hit"] for result in results.values())
    assert [results[k]["candidate_tokens"] for k in ("3", "5", "10")] == [6, 15, 55]
    assert results["3"]["missing_by_plan"] == [["b"], ["b"]]


def test_completion_rank_uses_first_complete_alternative(evaluation):
    question = {"minimum_sufficient": {"evaluation_chunk_sets": [["a", "b"], ["c", "d"]]}}
    hits = [
        {"chunk_id": cid, "rank": rank, "score": 1 / rank}
        for cid, rank in [("a", 1), ("b", 11), ("c", 4), ("d", 7)]
    ]
    result = evaluation.completion_ranks(question, hits)
    assert result["minimum_completion_k"] == 7
    first, second = result["plans"]
    assert first["completion_rank"] == 11
    assert second["completion_rank"] == 7
    assert second["missing_by_k"] == {"3": ["c", "d"], "5": ["d"], "10": []}
    assert second["required"] == hits[2:]
