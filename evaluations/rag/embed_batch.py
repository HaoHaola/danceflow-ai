"""Embed the locked Week 2.2 document batch using the local Qwen cache."""

import hashlib
import json
import math
import os
import platform
from importlib.metadata import version
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

if __package__:
    from . import validate_retrieval_pilot as release
    from .chunk_batch import verify_chunks
    from .chunk_pilot import SETTINGS
    from .prepare_corpus import TRANSCRIPT_VERSION, read_snapshot
    from .smoke_embedding import MAX_SEQUENCE_LENGTH, MODEL_ID, REVISION
else:
    import validate_retrieval_pilot as release
    from chunk_batch import verify_chunks
    from chunk_pilot import SETTINGS
    from prepare_corpus import TRANSCRIPT_VERSION, read_snapshot
    from smoke_embedding import MAX_SEQUENCE_LENGTH, MODEL_ID, REVISION


OUTPUT = release.LOCAL / "week2.3" / "embeddings"
DIMENSIONS = 1024
DOCUMENT_PROMPT = ""
BATCH_SIZE = 8
THREADS = 4
NORM_TOLERANCE = 1e-6


def load_locked_inputs():
    if not __debug__:
        raise RuntimeError("Run without -O because the release validator uses assertions")

    documents, chunks, corpus_version = release.load_corpus()
    lock = release.read(release.LOCK)
    questions = release.validate_release(
        release.PILOT / "dataset.json", release.PILOT / "review.md", lock, corpus_version
    )
    if release.validate_questions(questions, documents, chunks) != lock["evidence_entries"]:
        raise ValueError("Evidence count differs from the release lock")

    source_root = release.CLEAN.parent
    for source_id, document in documents.items():
        metadata = document["metadata"]
        for label in ("raw", "original"):
            if f"{label}_path" in metadata:
                read_snapshot(
                    source_root, metadata[f"{label}_path"], metadata[f"{label}_sha256"],
                    source_id, label,
                )
        transcript = document.get("transcript")
        if transcript is not None and transcript["version"] != TRANSCRIPT_VERSION:
            raise ValueError(f"{source_id}: expected transcript v3")
    return documents, list(chunks.values()), {"release": lock, "corpus": corpus_version}


def verify_inputs(documents, chunks, tokenizer):
    for source_id, group in groupby(chunks, key=lambda chunk: chunk["source_id"]):
        source_chunks = list(group)
        for chunk in source_chunks:
            settings = chunk["chunking_settings"]
            if any(settings.get(key) != SETTINGS[key] for key in (
                "tokenizer", "revision", "max_tokens", "max_overlap_tokens",
            )):
                raise ValueError(f"{chunk['chunk_id']}: incompatible token settings")
        try:
            verify_chunks(documents[source_id], source_chunks, tokenizer)
        except ValueError as error:
            raise ValueError(f"{source_id}: {error}") from error


def verify_vectors(vectors, row_count):
    if len(vectors) != row_count:
        raise ValueError(f"Expected {row_count} vectors, got {len(vectors)}")
    for index, vector in enumerate(vectors):
        if len(vector) != DIMENSIONS:
            raise ValueError(f"Row {index}: expected {DIMENSIONS} dimensions")
        if not all(type(value) in (int, float) and math.isfinite(value) for value in vector):
            raise ValueError(f"Row {index}: expected finite numeric components")
        norm = math.hypot(*vector)
        if abs(norm - 1.0) > NORM_TOLERANCE:
            raise ValueError(f"Row {index}: L2 norm {norm} differs from 1")


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()


def load_artifact(directory, configuration, chunk_ids):
    manifest = release.read(directory / "manifest.json")
    if manifest["configuration"] != configuration or manifest["chunk_ids"] != chunk_ids:
        raise ValueError(f"{directory}: cached configuration or chunk mapping differs")
    if manifest["shape"] != [len(chunk_ids), DIMENSIONS]:
        raise ValueError(f"{directory}: cached shape differs")
    data = (directory / "vectors.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest["vectors_sha256"]:
        raise ValueError(f"{directory}: vector artifact SHA-256 mismatch")
    vectors = json.loads(data)
    verify_vectors(vectors, len(chunk_ids))
    return manifest, vectors


def read_artifact(directory, configuration, chunk_ids):
    return load_artifact(directory, configuration, chunk_ids)[0]


def embed_or_reuse(output, configuration, chunks, encode):
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    if not chunk_ids or len(set(chunk_ids)) != len(chunk_ids):
        raise ValueError("Expected a nonempty batch with unique chunk IDs")
    fingerprint = hashlib.sha256(json_bytes([configuration, chunk_ids])).hexdigest()
    directory = output / fingerprint
    if directory.exists():
        return directory, read_artifact(directory, configuration, chunk_ids), True

    started = perf_counter()
    vectors = encode([chunk["embedding_text"] for chunk in chunks])
    encode_seconds = perf_counter() - started
    verify_vectors(vectors, len(chunk_ids))
    data = json_bytes(vectors)
    manifest = {
        "configuration": configuration,
        "chunk_ids": chunk_ids,
        "shape": [len(chunk_ids), DIMENSIONS],
        "max_token_count": max(chunk["token_count"] for chunk in chunks),
        "max_overlap_tokens_observed": max(chunk["overlap_tokens"] for chunk in chunks),
        "vectors_sha256": hashlib.sha256(data).hexdigest(),
        "model_load_and_encode_seconds": encode_seconds,
    }
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as temp:
        staged = Path(temp) / "artifact"
        staged.mkdir()
        (staged / "vectors.json").write_bytes(data)
        (staged / "manifest.json").write_bytes(json_bytes(manifest))
        try:
            staged.rename(directory)
        except OSError:
            if not directory.is_dir():
                raise
            return directory, read_artifact(directory, configuration, chunk_ids), True
    return directory, manifest, False


def encode_documents(texts):
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(THREADS)
    model = SentenceTransformer(
        MODEL_ID, revision=REVISION, local_files_only=True, device="cpu",
        model_kwargs={"dtype": torch.float32},
    )
    model.max_seq_length = MAX_SEQUENCE_LENGTH
    vectors = model.encode(
        texts, prompt=DOCUMENT_PROMPT, batch_size=BATCH_SIZE, normalize_embeddings=True,
        show_progress_bar=False,
    )
    if str(vectors.dtype) != "float32":
        raise ValueError(f"Expected float32 embeddings, got {vectors.dtype}")
    return vectors.tolist()


def main():
    from transformers import AutoTokenizer

    documents, chunks, inputs = load_locked_inputs()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, local_files_only=True)
    verify_inputs(documents, chunks, tokenizer)
    configuration = {
        "schema_version": 1,
        "inputs": inputs,
        "model": MODEL_ID,
        "revision": REVISION,
        "input_field": "embedding_text",
        "document_prompt": DOCUMENT_PROMPT,
        "max_sequence_length": MAX_SEQUENCE_LENGTH,
        "max_overlap_tokens": SETTINGS["max_overlap_tokens"],
        "special_tokens": True,
        "truncation_allowed": False,
        "device": "cpu",
        "dtype": "float32",
        "dimensions": DIMENSIONS,
        "normalize_embeddings": True,
        "norm_tolerance": NORM_TOLERANCE,
        "batch_size": BATCH_SIZE,
        "torch_threads": THREADS,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_cores": os.cpu_count(),
        "packages": {package: version(package) for package in (
            "torch", "transformers", "sentence-transformers", "huggingface-hub", "tokenizers",
            "safetensors", "numpy",
        )},
    }
    directory, manifest, reused = embed_or_reuse(OUTPUT, configuration, chunks, encode_documents)
    action = "Reused" if reused else "Encoded"
    print(f"{action} {manifest['shape']} float32 embeddings at {directory}")
    print(f"Max input tokens: {manifest['max_token_count']}; "
          f"max overlap tokens: {manifest['max_overlap_tokens_observed']}")
    print(f"Vector SHA-256: {manifest['vectors_sha256']}")
    if not reused:
        print(f"Model load and encoding: {manifest['model_load_and_encode_seconds']:.3f} s")


if __name__ == "__main__":
    main()
