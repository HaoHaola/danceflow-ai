from pathlib import Path

import pytest


@pytest.fixture
def staged_batch(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import ingest_qdrant as importer

    chunks = [
        {"chunk_id": f"fixture:{i}", "embedding_text": "Step left.",
         "token_count": 3, "overlap_tokens": 0}
        for i in range(154)
    ]
    inputs = {
        "release": {"release_version": "synthetic"},
        "corpus": {"batch_summary_sha256": "synthetic"},
    }

    def stage(configuration):
        artifact, _, _ = importer.embed_batch.embed_or_reuse(
            tmp_path, configuration, chunks, lambda texts: [[1.0] + [0.0] * 1023] * len(texts)
        )
        return artifact

    return importer, chunks, inputs, stage


def test_artifact_rejects_changed_bytes_and_chunk_order(staged_batch):
    importer, chunks, inputs, stage = staged_batch
    artifact = stage({**importer.EMBEDDING_SPEC, "inputs": inputs})
    vectors, metadata = importer.load_batch(artifact, chunks, inputs)
    assert len(vectors) == 154
    assert metadata["revision"] == importer.embed_batch.REVISION
    with pytest.raises(ValueError, match="fingerprint differs"):
        importer.load_batch(artifact, chunks[::-1], inputs)

    file = artifact / "vectors.json"
    file.write_bytes(file.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        importer.load_batch(artifact, chunks, inputs)


def test_artifact_rejects_wrong_revision(staged_batch):
    importer, chunks, inputs, stage = staged_batch
    artifact = stage({**importer.EMBEDDING_SPEC, "inputs": inputs, "revision": "wrong"})
    with pytest.raises(ValueError, match="incompatible revision"):
        importer.load_batch(artifact, chunks, inputs)


def test_question_amendment_reuses_only_pinned_artifact_for_same_corpus(staged_batch):
    from hashlib import sha256

    importer, chunks, inputs, stage = staged_batch
    artifact = stage({**importer.EMBEDDING_SPEC, "inputs": inputs})
    pin = sha256(importer.embed_batch.json_bytes(inputs["release"])).hexdigest()
    revised = {
        **inputs,
        "release": {**inputs["release"], "dataset_sha256": "new-question-hash",
                    "embedding_release_sha256": pin},
    }
    assert importer.load_batch(artifact, chunks, revised) == importer.load_batch(artifact, chunks, inputs)
    with pytest.raises(ValueError, match="incompatible inputs"):
        importer.load_batch(artifact, chunks, {**revised, "corpus": {"batch_summary_sha256": "changed"}})
    with pytest.raises(ValueError, match="incompatible inputs"):
        importer.load_batch(artifact, chunks, {**revised, "release": {"embedding_release_sha256": "bad"}})
