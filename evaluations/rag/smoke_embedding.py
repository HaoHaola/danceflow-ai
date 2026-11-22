"""Run an opt-in Qwen embedding smoke test against a cached model snapshot."""

import json
from importlib.metadata import version
from time import perf_counter

MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QUERY_PROMPT = (
    "Instruct: Given a street dance question, retrieve relevant English passages "
    "from dance articles and instructional video transcripts that answer it.\nQuery: "
)
MAX_SEQUENCE_LENGTH = 512
QUERIES = ["初學者怎麼練習手臂波浪？", "How can a beginner practice an arm wave?"]
DOCUMENTS = {
    "arm_wave": "Practice an arm wave slowly, passing the motion from fingers to wrist, elbow, and shoulder.",
    "unrelated": "Water tomato plants at the base and check the soil moisture before watering again.",
}


def main():
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(4)
    started = perf_counter()
    model = SentenceTransformer(
        MODEL_ID,
        revision=REVISION,
        local_files_only=True,
        device="cpu",
        model_kwargs={"dtype": torch.float32},
    )
    load_seconds = perf_counter() - started
    model.max_seq_length = MAX_SEQUENCE_LENGTH
    texts = [QUERY_PROMPT + query for query in QUERIES] + list(DOCUMENTS.values())
    token_counts = [len(ids) for ids in model.tokenizer(texts)["input_ids"]]
    assert max(token_counts) <= model.max_seq_length, token_counts

    started = perf_counter()
    query_vectors = model.encode(QUERIES, prompt=QUERY_PROMPT, normalize_embeddings=True)
    query_seconds = perf_counter() - started
    started = perf_counter()
    document_vectors = model.encode(
        list(DOCUMENTS.values()), prompt="", normalize_embeddings=True
    )
    document_seconds = perf_counter() - started

    assert query_vectors.shape == (len(QUERIES), 1024), query_vectors.shape
    assert document_vectors.shape == (len(DOCUMENTS), 1024), document_vectors.shape
    vectors = np.vstack((query_vectors, document_vectors))
    assert np.isfinite(vectors).all()
    norms = np.linalg.norm(vectors, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-6, rtol=0)
    similarities = query_vectors @ document_vectors.T

    result = {
        "model": MODEL_ID,
        "revision": REVISION,
        "versions": {
            package: version(package)
            for package in (
                "torch", "transformers", "sentence-transformers", "huggingface-hub",
                "tokenizers", "safetensors", "numpy",
            )
        },
        "device": str(model.device),
        "model_dtype": str(next(model.parameters()).dtype),
        "embedding_dtype": str(vectors.dtype),
        "query_prompt": QUERY_PROMPT,
        "max_seq_length": model.max_seq_length,
        "token_counts": token_counts,
        "shape": list(vectors.shape),
        "all_finite": True,
        "l2_norms": norms.tolist(),
        "document_order": list(DOCUMENTS),
        "query_order": QUERIES,
        "cosine_similarities": similarities.tolist(),
        "load_seconds": load_seconds,
        "query_encode_seconds": query_seconds,
        "document_encode_seconds": document_seconds,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
