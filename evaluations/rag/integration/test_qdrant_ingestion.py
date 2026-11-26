from uuid import uuid4

import pytest
from qdrant_client import QdrantClient, models

from evaluations.rag import ingest_qdrant as importer


@pytest.fixture
def target():
    client = QdrantClient(url=importer.URL, timeout=15)
    name = f"week2_3_{uuid4().hex}_test"
    assert client.info().version == importer.SERVER_VERSION
    assert not client.collection_exists(name)
    try:
        yield client, name
    finally:
        try:
            if client.collection_exists(name):
                client.delete_collection(name)
        finally:
            client.close()


@pytest.fixture
def batch():
    documents = {"fixture": {"metadata": {"source_version": "synthetic-v1"}}}
    chunks = [
        {"chunk_id": "fixture:article", "source_id": "fixture", "text": "Step left.",
         "heading_path": ["Practice"], "sources": [{"raw_lines": [2, 2]}]},
        {"chunk_id": "fixture:video", "source_id": "fixture", "text": "Stop.",
         "time_range_ms": [100, 200], "sources": [{"cues": [{"cue_id": "cue-1"}]}]},
    ]
    vectors = [[1.0, 0.0] + [0.0] * 1022, [0.0, 1.0] + [0.0] * 1022]
    metadata = {"revision": "synthetic-model-v1", "release_version": "synthetic-data-v1"}
    return metadata, importer.build_points(documents, chunks, vectors)


def test_import_twice_and_verify_payload(target, batch):
    client, name = target
    metadata, points = batch
    importer.ingest(client, name, metadata, points)
    importer.ingest(client, name, metadata, points)
    importer.verify_collection(client, name, metadata, points)
    rows = {row.payload["chunk_id"]: row for row in importer.read_points(
        client, name, with_vectors=False
    )}
    assert rows["fixture:article"].payload["sources"] == [{"raw_lines": [2, 2]}]
    assert rows["fixture:video"].payload["time_range_ms"] == [100, 200]
    assert rows["fixture:article"].id == importer.point_id("fixture:article")
    assert "source_type" not in rows["fixture:video"].payload


@pytest.mark.parametrize(("size", "metric", "change", "error"), [
    (64, models.Distance.COSINE, {}, "1024-dimensional"),
    (1024, models.Distance.DOT, {}, "cosine"),
    (1024, models.Distance.COSINE, {"revision": "wrong"}, "metadata"),
    (1024, models.Distance.COSINE, {"release_version": "wrong"}, "metadata"),
    (1024, models.Distance.COSINE, None, "metadata"),
])
def test_incompatible_collection_rejected_before_upsert(target, batch, size, metric, change, error):
    client, name = target
    metadata, points = batch
    existing_metadata = None if change is None else {**metadata, **change}
    client.create_collection(
        name, vectors_config=models.VectorParams(size=size, distance=metric),
        metadata=existing_metadata,
    )
    with pytest.raises(ValueError, match=error):
        importer.ingest(client, name, metadata, points)
    assert client.count(name, exact=True).count == 0


def test_exact_query_points_ranks_fixed_vectors(target, batch):
    from evaluations.rag.evaluate_dense import exact_search, reference_check

    client, name = target
    metadata, points = batch
    importer.ingest(client, name, metadata, points)
    hits = exact_search(client, name, points[1].vector, limit=2)
    assert [hit.id for hit in hits] == [points[1].id, points[0].id]
    assert [hit.payload for hit in hits] == [points[1].payload, points[0].payload]
    reference_check(
        [{"chunk_id": hit.payload["chunk_id"], "score": hit.score} for hit in hits],
        {"fixture:video": 1.0, "fixture:article": 0.0}, k=2,
    )
