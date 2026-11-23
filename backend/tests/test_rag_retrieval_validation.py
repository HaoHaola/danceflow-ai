from pathlib import Path

import pytest


@pytest.fixture
def validator(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import validate_retrieval_pilot

    return validate_retrieval_pilot


def test_minimal_plans_deduplicate_and_keep_alternatives(validator):
    evidence = [
        {"relevant_chunk_ids": ["shared", "first"]},
        {"relevant_chunk_ids": ["shared", "second"]},
    ]
    assert validator.minimal_chunk_sets(evidence) == [["first", "second"], ["shared"]]


def test_question_validation_checks_source_mapping_and_partial_support(validator):
    document = {"records": [
        {"block_id": "b1", "text": "Step left.", "raw_lines": [3, 3], "heading_path": ["Practice"]},
        {"block_id": "b2", "text": "Then stop.", "raw_lines": [5, 5], "heading_path": ["Practice"]},
    ]}
    chunks = {}
    for index, record in enumerate(document["records"], 1):
        length = len(record["text"])
        chunk_id = f"fixture:{index}"
        chunks[chunk_id] = {
            "chunk_id": chunk_id, "source_id": "fixture", "source_url": "https://example.com/practice",
            "section_index": index, "heading_path": ["Practice"], "text": record["text"],
            "source_text_range": [0, length],
            "sources": [{"body_range": [0, length], "block_id": record["block_id"],
                         "block_range": [0, length], "raw_lines": record["raw_lines"]}],
        }
    evidence = [
        {"source_id": "fixture", "source_url": chunk["source_url"], "anchor_chunk_id": cid,
         "chunk_char_range": [0, 4], "excerpt": chunk["text"][:4],
         "locations": [{
             "block_id": record["block_id"], "char_range": [0, 4],
             "raw_lines": record["raw_lines"], "heading_path": ["Practice"],
         }], "supports": [record["block_id"]], "relevant_chunk_ids": [cid]}
        for (cid, chunk), record in zip(chunks.items(), document["records"])
    ]
    ids = list(chunks)
    group = {
        "group_id": "sequence", "mode": "all_required", "supports": ["b1", "b2"],
        "evidence": evidence, "relevant_chunk_ids": ids, "evaluation_chunk_sets": [ids],
        "chunk_support": dict.fromkeys(ids, "partial"),
    }
    question = {
        "question_id": "fixture-question", "expected_answer_points": [{"point_id": key} for key in ("b1", "b2")],
        "evidence_groups": [group], "supplemental_group_ids": [],
        "minimum_sufficient": {"any_of": ["sequence"], "evaluation_chunk_sets": [ids]},
    }
    assert validator.validate_questions([question], {"fixture": document}, chunks) == 2
    group["chunk_support"][ids[0]] = "sufficient"
    with pytest.raises(AssertionError):
        validator.validate_questions([question], {"fixture": document}, chunks)
    group["chunk_support"][ids[0]] = "partial"
    evidence[0]["locations"][0]["char_range"] = [1, 5]
    with pytest.raises(AssertionError):
        validator.validate_questions([question], {"fixture": document}, chunks)


def test_release_rejects_byte_changes_before_parsing(validator, tmp_path):
    dataset = tmp_path / "dataset.json"
    preview = tmp_path / "review.md"
    dataset.write_text("{}\n")
    preview.write_text("Fixture preview\n")
    lock = {"dataset_sha256": validator.sha256(dataset), "preview_sha256": validator.sha256(preview)}
    preview.write_text("Changed preview\n")
    with pytest.raises(AssertionError, match="Preview SHA-256 mismatch"):
        validator.validate_release(dataset, preview, lock, {})
    dataset.write_text("{ }\n")
    with pytest.raises(AssertionError, match="Dataset SHA-256 mismatch"):
        validator.validate_release(dataset, preview, lock, {})
