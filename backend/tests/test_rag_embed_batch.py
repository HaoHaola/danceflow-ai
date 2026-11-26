import json
from pathlib import Path

import pytest


@pytest.fixture
def batch(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import embed_batch

    return embed_batch


def test_preflight_rejects_full_input_over_limit(batch):
    from evaluations.rag.chunk_pilot import build_chunks

    def tokenizer(text, *, add_special_tokens, truncation):
        assert truncation is False
        return {"input_ids": [0] * (len(text.split()) + int(add_special_tokens))}

    document = {
        "metadata": {
            "doc_id": "fixture", "title": "Practice",
            "source_url": "https://example.com/practice", "raw_sha256": "fixture",
        },
        "cleaning_version": "fixture",
        "records": [{
            "kind": "paragraph", "block_id": "b1", "heading_path": [],
            "raw_lines": [1, 1], "text": "Step left.",
        }],
    }
    chunks = build_chunks(json.dumps(document).encode(), tokenizer)
    batch.verify_inputs({"fixture": document}, chunks, tokenizer)

    def overlong_tokenizer(text, *, add_special_tokens, truncation):
        if add_special_tokens:
            assert truncation is False
            return {"input_ids": [0] * 513}
        return tokenizer(text, add_special_tokens=False, truncation=truncation)

    with pytest.raises(ValueError, match="Invalid embedding token count"):
        batch.verify_inputs({"fixture": document}, chunks, overlong_tokenizer)


@pytest.mark.parametrize(("vectors", "error"), [
    ([], "Expected 1 vectors"),
    ([[1.0]], "expected 1024 dimensions"),
    ([[float("nan")] + [0.0] * 1023], "finite numeric"),
    ([[0.0] * 1024], "L2 norm"),
])
def test_invalid_vectors_are_rejected(batch, vectors, error):
    with pytest.raises(ValueError, match=error):
        batch.verify_vectors(vectors, 1)


def test_artifact_mapping_reuse_and_corruption(batch, tmp_path):
    chunks = [
        {"chunk_id": "fixture:2", "embedding_text": "Practice twice.",
         "token_count": 3, "overlap_tokens": 0},
        {"chunk_id": "fixture:1", "embedding_text": "Step left.",
         "token_count": 3, "overlap_tokens": 0},
    ]
    vectors = [[1.0, 0.0] + [0.0] * 1022, [0.0, 1.0] + [0.0] * 1022]
    configuration = {"revision": "fixture"}

    def encode(texts):
        assert texts == ["Practice twice.", "Step left."]
        return vectors

    output, manifest, reused = batch.embed_or_reuse(tmp_path, configuration, chunks, encode)
    assert not reused
    assert manifest["chunk_ids"] == ["fixture:2", "fixture:1"]
    assert batch.release.read(output / "vectors.json") == vectors

    def never_encode(texts):
        pytest.fail("The verified artifact should be reused")

    assert batch.embed_or_reuse(tmp_path, configuration, chunks, never_encode) == (
        output, manifest, True,
    )
    (output / "vectors.json").write_text("[]")
    with pytest.raises(ValueError, match="vector artifact SHA-256 mismatch"):
        batch.embed_or_reuse(tmp_path, configuration, chunks, never_encode)
