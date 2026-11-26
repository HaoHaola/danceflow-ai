"""Evaluate the locked 30-query dense retrieval baseline against local Qdrant."""

import argparse
import math
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from itertools import combinations
from pathlib import Path
from statistics import mean, quantiles
from time import perf_counter

if __package__:
    from . import embed_batch, ingest_qdrant
    from .chunk_pilot import token_count
    from .smoke_embedding import QUERY_PROMPT
else:
    import embed_batch
    import ingest_qdrant
    from chunk_pilot import token_count
    from smoke_embedding import QUERY_PROMPT


TOP_K = 5
DIAGNOSTIC_K = (3, 5, 10)
DIAGNOSTIC_QUESTION = "pilot-arm-wave"
SCORE_TOLERANCE = 1e-6
WARMUPS = (
    "How do I practice a groove?",
    "跳舞時如何跟上節拍？",
    "What should I focus on during a dance drill?",
)
OUTPUT = embed_batch.release.LOCAL / "week2.3" / "dense"


def score_question(question, retrieved_ids):
    retrieved = set(retrieved_ids)
    plans = [set(ids) for ids in question["minimum_sufficient"]["evaluation_chunk_sets"]]
    member = any(plan & retrieved for plan in plans)
    complete = any(plan <= retrieved for plan in plans) # if plan is incluede in retrieved
    supplemental_groups = set(question["supplemental_group_ids"])
    supplemental_hits = [
        {"group_id": group["group_id"], "chunk_id": chunk_id, "support": support}
        for group in question["evidence_groups"] if group["group_id"] in supplemental_groups
        for chunk_id, support in group["chunk_support"].items() if chunk_id in retrieved
    ]
    if complete:
        outcome = "complete"
    elif member:
        outcome = "missing_required_chunks"
    elif supplemental_hits:
        outcome = ("partial_only" if all(hit["support"] == "partial" for hit in supplemental_hits)
                   else "supplemental_only")
    else:
        outcome = "no_annotated_hit"
    return {
        "member_hit": member,
        "complete_plan": complete,
        "outcome": outcome,
        "missing_by_plan": [
            sorted(plan - retrieved) for plan in plans
        ],
        "supplemental_hits": supplemental_hits,
    }


def reference_check(hits, reference, k=TOP_K):
    ids = [hit["chunk_id"] for hit in hits]
    if len(ids) != k or len(set(ids)) != k or any(cid not in reference for cid in ids):
        raise ValueError("Unexpected IDs or count in Qdrant results")
    errors = [abs(hit["score"] - reference[cid]) for hit, cid in zip(hits, ids, strict=True)]
    if not all(math.isfinite(error) and error <= SCORE_TOLERANCE for error in errors):
        raise ValueError("Qdrant scores differ from local dot products")
    ordered_scores = [reference[cid] for cid in ids]
    if any(later - earlier > SCORE_TOLERANCE for earlier, later in combinations(ordered_scores, 2)):
        raise ValueError("Qdrant ranking inverts distinct local scores")
    ranked = sorted(reference, key=lambda cid: (-reference[cid], cid))
    if any(reference[cid] - min(ordered_scores) > SCORE_TOLERANCE for cid in ranked if cid not in ids):
        raise ValueError("Qdrant omitted a higher-scoring local result")
    return {
        "max_score_error": max(errors),
        "local_top_ids": ranked[:k],
        "same_order": ranked[:k] == ids,
        "cutoff_tie": len(ranked) > k and (
            reference[ranked[k - 1]] - reference[ranked[k]] <= SCORE_TOLERANCE
        ),
    }


def check_query_tokens(tokenizer, inputs):
    counts = []
    for label, query in inputs:
        count = token_count(tokenizer, QUERY_PROMPT + query)
        if count > embed_batch.MAX_SEQUENCE_LENGTH:
            raise ValueError(f"{label}: {count} query input tokens exceed the 512-token limit")
        counts.append(count)
    return counts


def exact_search(client, name, vector, *, limit=TOP_K):
    from qdrant_client import models

    return client.query_points(
        name, query=vector, limit=limit, search_params=models.SearchParams(exact=True),
        with_payload=True, with_vectors=False,
    ).points


def ranked_hits(points):
    return [
        {"rank": rank, "chunk_id": point.payload["chunk_id"], "point_id": point.id,
         "score": point.score, "payload": point.payload}
        for rank, point in enumerate(points, 1)
    ]


def run_query(model, client, query, *, limit=TOP_K):
    started = perf_counter()
    vector = model.encode(query, prompt=QUERY_PROMPT, normalize_embeddings=True,
                          show_progress_bar=False).tolist()
    encoded = perf_counter()
    points = exact_search(client, ingest_qdrant.COLLECTION, vector, limit=limit)
    searched = perf_counter()
    hits = ranked_hits(points)
    finished = perf_counter()
    return vector, hits, {
        "query_embedding": 1000 * (encoded - started),
        "qdrant_round_trip": 1000 * (searched - encoded),
        "end_to_end": 1000 * (finished - started),
    }


def summarize(results):
    summary = {}
    for language in ("overall", "zh-Hant", "en"):
        rows = [row for row in results if language == "overall" or row["language"] == language]
        summary[language] = {
            metric: {"numerator": hits, "denominator": len(rows), "rate": hits / len(rows)}
            for metric in ("member_hit", "complete_plan")
            for hits in [sum(row["evaluation"][metric] for row in rows)]
        }
    return summary


def score_prefixes(question, hits, token_counts):
    ids = [hit["chunk_id"] for hit in hits]
    return {
        str(k): {
            **score_question(question, ids[:k]),
            "candidate_tokens": sum(token_counts[cid] for cid in ids[:k]),
        }
        for k in DIAGNOSTIC_K
    }


def completion_ranks(question, full_ranking):
    by_id = {hit["chunk_id"]: hit for hit in full_ranking}
    plans = []
    for ids in question["minimum_sufficient"]["evaluation_chunk_sets"]:
        required = [by_id[cid] for cid in dict.fromkeys(ids)]
        plans.append({
            "required": required,
            "completion_rank": max(hit["rank"] for hit in required),
            "missing_by_k": {
                str(k): [hit["chunk_id"] for hit in required if hit["rank"] > k]
                for k in DIAGNOSTIC_K
            },
        })
    return {
        "plans": plans,
        "minimum_completion_k": min(plan["completion_rank"] for plan in plans),
    }


def summarize_prefixes(results):
    summary = {}
    for k in map(str, DIAGNOSTIC_K):
        rows = [{**row, "evaluation": row["by_k"][k]} for row in results]
        counts = [row["evaluation"]["candidate_tokens"] for row in rows]
        summary[k] = {
            "metrics": summarize(rows),
            "incomplete_question_ids": [
                row["question_id"] for row in rows if not row["evaluation"]["complete_plan"]
            ],
            "candidate_tokens": {"mean": mean(counts), "total": sum(counts),
                                 "min": min(counts), "max": max(counts)},
        }
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--diagnose", action="store_true", help="Run post-baseline rank and k analysis")
    args = parser.parse_args()

    import torch
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer

    started = perf_counter()
    documents, chunks, inputs = embed_batch.load_locked_inputs()
    release = embed_batch.release
    questions = release.validate_release(
        release.PILOT / "dataset.json", release.PILOT / "review.md", inputs["release"], inputs["corpus"]
    )
    vectors, metadata = ingest_qdrant.load_batch(args.artifact, chunks, inputs)
    points = ingest_qdrant.build_points(documents, chunks, vectors)
    expected_points = {point.id: point.payload for point in points}
    results = []
    validation_seconds = 0
    rank_diagnosis = None
    limit = DIAGNOSTIC_K[-1] if args.diagnose else TOP_K
    with_client = QdrantClient(url=ingest_qdrant.URL, timeout=15)
    try:
        server = with_client.info().version
        if server != ingest_qdrant.SERVER_VERSION:
            raise ValueError(f"Expected Qdrant {ingest_qdrant.SERVER_VERSION}, got {server}")
        ingest_qdrant.verify_collection(with_client, ingest_qdrant.COLLECTION, metadata, points)
        data_validation_seconds = perf_counter() - started

        torch.set_num_threads(embed_batch.THREADS)
        started = perf_counter()
        model = SentenceTransformer(
            embed_batch.MODEL_ID, revision=embed_batch.REVISION, local_files_only=True,
            device="cpu", model_kwargs={"dtype": torch.float32},
        )
        model.max_seq_length = embed_batch.MAX_SEQUENCE_LENGTH
        if next(model.parameters()).dtype != torch.float32:
            raise ValueError("Expected float32 query encoder")
        model_load_seconds = perf_counter() - started
        started = perf_counter()
        query_inputs = [(question["question_id"], question["question"]) for question in questions]
        token_counts = check_query_tokens(model.tokenizer, query_inputs)
        warmup_token_counts = []
        if not args.diagnose:
            warmup_inputs = [(f"warmup-{i}", query) for i, query in enumerate(WARMUPS, 1)]
            warmup_token_counts = check_query_tokens(model.tokenizer, warmup_inputs)
        token_validation_seconds = perf_counter() - started
        if args.diagnose:
            candidate_tokens = {
                chunk["chunk_id"]: token_count(model.tokenizer, chunk["embedding_text"], special=False)
                for chunk in chunks
            }
        else:
            for query in WARMUPS:
                run_query(model, with_client, query)
        for question, count in zip(questions, token_counts, strict=True):
            vector, hits, latency = run_query(model, with_client, question["question"], limit=limit)
            started = perf_counter()
            embed_batch.verify_vectors([vector], 1)
            if any(hit["payload"] != expected_points.get(hit["point_id"]) for hit in hits):
                raise ValueError(f"{question['question_id']}: unexpected point payload")
            reference = {
                point.payload["chunk_id"]: math.fsum(a * b for a, b in zip(vector, doc_vector, strict=True))
                for point, doc_vector in zip(points, vectors, strict=True)
            }
            try:
                comparison = reference_check(hits, reference, k=limit)
            except ValueError as error:
                raise ValueError(f"{question['question_id']}: {error}") from error
            row = {
                "question_id": question["question_id"], "language": question["language"],
                "question": question["question"], "token_count": count,
                "hits": hits, "exact_reference": comparison,
            }
            if args.diagnose:
                row["by_k"] = score_prefixes(question, hits, candidate_tokens)
                if question["question_id"] == DIAGNOSTIC_QUESTION:
                    full_ranking = ranked_hits(exact_search(
                        with_client, ingest_qdrant.COLLECTION, vector, limit=len(points)
                    ))
                    if any(hit["payload"] != expected_points.get(hit["point_id"]) for hit in full_ranking):
                        raise ValueError("Unexpected point payload in complete ranking")
                    full_check = reference_check(full_ranking, reference, k=len(points))
                    rank_diagnosis = {
                        "question_id": DIAGNOSTIC_QUESTION,
                        "ranking": full_ranking,
                        "exact_reference": full_check,
                        **completion_ranks(question, full_ranking),
                    }
            else:
                row["evaluation"] = score_question(question, [hit["chunk_id"] for hit in hits])
                row["latency_ms"] = latency
            results.append(row)
            validation_seconds += perf_counter() - started
    finally:
        with_client.close()

    run = {
        "collection": ingest_qdrant.COLLECTION,
        "inputs": metadata,
        "dataset_sha256": inputs["release"]["dataset_sha256"],
        "qdrant_server": server, "qdrant_client": version("qdrant-client"),
        "torch": version("torch"), "transformers": version("transformers"),
        "sentence_transformers": version("sentence-transformers"),
        "python": platform.python_version(), "platform": platform.platform(),
        "query_prompt": QUERY_PROMPT, "device": "cpu", "dtype": "float32",
        "normalize_embeddings": True, "threads": embed_batch.THREADS,
        "max_sequence_length": model.max_seq_length, "exact": True, "top_k": limit,
        "score_tolerance": SCORE_TOLERANCE,
        "model_load_seconds": model_load_seconds,
        "data_validation_seconds": data_validation_seconds,
        "token_validation_seconds": token_validation_seconds,
        "questions": results,
    }
    if args.diagnose:
        if rank_diagnosis is None:
            raise ValueError(f"Missing locked question {DIAGNOSTIC_QUESTION}")
        run.update({
            "analysis": "exploratory_post_baseline",
            "candidate_tokens_include_special_tokens": False,
            "by_k": summarize_prefixes(results),
            "rank_diagnosis": rank_diagnosis,
        })
    else:
        latency_summary = {}
        for stage in results[0]["latency_ms"]:
            values = [row["latency_ms"][stage] for row in results]
            percentiles = quantiles(values, n=100, method="inclusive")
            latency_summary[stage] = {"n": len(values), "p50": percentiles[49], "p95": percentiles[94]}
        run.update({
            "metrics": summarize(results),
            "latency_ms": latency_summary,
            "warmups": [{"query": query, "token_count": count}
                        for query, count in zip(WARMUPS, warmup_token_counts, strict=True)],
            "result_validation_and_scoring_seconds": validation_seconds,
            "percentile_method": "linear interpolation at (n - 1) * p on zero-based sorted samples",
        })
    OUTPUT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    prefix = "diagnostics" if args.diagnose else "baseline"
    path = OUTPUT / f"{prefix}-{timestamp}.json"
    with path.open("xb") as stream:
        stream.write(embed_batch.json_bytes(run))
    print(f"Verified exact search for {len(results)} questions. Results: {path}")
    print(run["by_k"] if args.diagnose else run["metrics"])
    if not args.diagnose:
        print(latency_summary)


if __name__ == "__main__":
    main()
