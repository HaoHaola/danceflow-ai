"""Import or verify the locked Week 2.3 document vectors in local Qdrant."""

import argparse
import hashlib
import math
from pathlib import Path
from uuid import UUID, uuid5

if __package__:
    from . import embed_batch
else:
    import embed_batch

URL = "http://127.0.0.1:6333"
SERVER_VERSION = "1.16.3"
COLLECTION = "danceflow_week2_3_dense_v1"
POINT_NAMESPACE = UUID("f3cc5068-6e49-4f00-9f24-a68483517ce5")
PAYLOAD_FIELDS = (
    "chunk_id", "source_id", "source_url", "title", "text", "input_sha256",
    "raw_sha256", "cleaning_version", "transcript_version", "chunking_settings",
    "section_index", "heading_path", "heading_block_ids", "source_text_range",
    "sources", "time_range_ms",
)
EMBEDDING_SPEC = {
    "schema_version": 1,
    "model": embed_batch.MODEL_ID,
    "revision": embed_batch.REVISION,
    "input_field": "embedding_text",
    "document_prompt": embed_batch.DOCUMENT_PROMPT,
    "max_sequence_length": embed_batch.MAX_SEQUENCE_LENGTH,
    "max_overlap_tokens": embed_batch.SETTINGS["max_overlap_tokens"],
    "special_tokens": True,
    "truncation_allowed": False,
    "device": "cpu",
    "dtype": "float32",
    "dimensions": embed_batch.DIMENSIONS,
    "normalize_embeddings": True,
    "norm_tolerance": embed_batch.NORM_TOLERANCE,
}


def load_batch(artifact, chunks, inputs):
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if len(chunk_ids) != 154 or len(set(chunk_ids)) != 154:
        raise ValueError("Expected 154 unique locked chunk IDs")
    manifest = embed_batch.release.read(artifact / "manifest.json")
    configuration = manifest["configuration"]
    for key, expected in {**EMBEDDING_SPEC, "inputs": inputs}.items():
        if key not in configuration or configuration[key] != expected:
            raise ValueError(f"Embedding manifest has incompatible {key}")
    fingerprint = hashlib.sha256(embed_batch.json_bytes([configuration, chunk_ids])).hexdigest()
    if artifact.name != fingerprint:
        raise ValueError("Embedding artifact directory fingerprint differs")
    manifest, vectors = embed_batch.load_artifact(artifact, configuration, chunk_ids)
    return vectors, {
        "payload_schema_version": 1,
        "model": configuration["model"],
        "revision": configuration["revision"],
        "release_version": inputs["release"]["release_version"],
        "batch_summary_sha256": inputs["corpus"]["batch_summary_sha256"],
        "embedding_fingerprint": fingerprint,
        "vectors_sha256": manifest["vectors_sha256"],
    }


def point_id(chunk_id):
    return str(uuid5(POINT_NAMESPACE, chunk_id))


def build_points(documents, chunks, vectors):
    from qdrant_client import models

    points = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        payload = {key: chunk[key] for key in PAYLOAD_FIELDS if key in chunk}
        metadata = documents[chunk["source_id"]]["metadata"]
        for key in ("source_type", "source_version"):
            if key in metadata:
                payload[key] = metadata[key]
        points.append(models.PointStruct(id=point_id(chunk["chunk_id"]), vector=vector, payload=payload))
    return points


def check_collection(client, name, metadata):
    from qdrant_client import models

    config = client.get_collection(name).config
    vectors = config.params.vectors
    if not isinstance(vectors, models.VectorParams) or vectors.size != embed_batch.DIMENSIONS:
        raise ValueError(f"{name}: expected a single {embed_batch.DIMENSIONS}-dimensional vector")
    if vectors.distance != models.Distance.COSINE:
        raise ValueError(f"{name}: expected cosine distance")
    if vectors.datatype not in (None, models.Datatype.FLOAT32) or config.quantization_config:
        raise ValueError(f"{name}: expected float32 vectors without quantization")
    if config.metadata != metadata:
        raise ValueError(f"{name}: collection metadata is missing or incompatible")


def read_points(client, name, *, with_vectors):
    offset = None
    while True:
        rows, offset = client.scroll(
            name, offset=offset, limit=128, with_payload=True, with_vectors=with_vectors,
        )
        yield from rows
        if offset is None:
            break


def verify_collection(client, name, metadata, points):
    check_collection(client, name, metadata)
    count = client.count(name, exact=True).count
    if count != len(points):
        raise ValueError(f"{name}: expected {len(points)} points, got {count}")
    expected = {point.id: point for point in points}
    for row in read_points(client, name, with_vectors=True):
        point = expected.pop(row.id, None)
        if point is None or row.payload != point.payload:
            raise ValueError(f"{name}: unexpected point ID or payload for {row.id}")
        if len(row.vector) != len(point.vector) or not all(
            math.isclose(actual, wanted, rel_tol=0, abs_tol=1e-6)
            for actual, wanted in zip(row.vector, point.vector, strict=True)
        ):
            raise ValueError(f"{name}: stored vector differs for {row.id}")
    if expected:
        raise ValueError(f"{name}: {len(expected)} expected points missing")


def ingest(client, name, metadata, points):
    from qdrant_client import models

    expected_ids = {point.id for point in points}
    if not points or len(expected_ids) != len(points):
        raise ValueError("Expected a nonempty batch with unique point IDs")
    if not client.collection_exists(name):
        client.create_collection(
            name, vectors_config=models.VectorParams(
                size=embed_batch.DIMENSIONS, distance=models.Distance.COSINE,
            ),
            metadata=metadata,
        )
    check_collection(client, name, metadata)
    if any(row.id not in expected_ids for row in read_points(client, name, with_vectors=False)):
        raise ValueError(f"{name}: collection contains unexpected point IDs")
    result = client.upsert(name, points=points, wait=True)
    if result.status != models.UpdateStatus.COMPLETED:
        raise RuntimeError(f"{name}: upsert did not complete")
    verify_collection(client, name, metadata, points)


def main():
    from qdrant_client import QdrantClient

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    documents, chunks, inputs = embed_batch.load_locked_inputs()
    vectors, metadata = load_batch(args.artifact, chunks, inputs)
    points = build_points(documents, chunks, vectors)
    client = QdrantClient(url=URL, timeout=15)
    try:
        server = client.info().version
        if server != SERVER_VERSION:
            raise ValueError(f"Expected Qdrant {SERVER_VERSION}, got {server}")
        if args.verify_only:
            verify_collection(client, COLLECTION, metadata, points)
        else:
            ingest(client, COLLECTION, metadata, points)
    finally:
        client.close()
    print(f"Verified {len(points)} points, vectors and payloads in {COLLECTION} on Qdrant {server}")


if __name__ == "__main__":
    main()
