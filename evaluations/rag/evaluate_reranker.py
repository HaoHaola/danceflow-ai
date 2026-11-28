"""Run reranker development evaluations on locked dense candidates."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
from importlib.metadata import version
from math import isfinite
from pathlib import Path
import platform
import resource
from statistics import mean, quantiles
import subprocess
from time import perf_counter

if __package__:
    from . import evaluate_dense as dense
else:
    import evaluate_dense as dense

embed = dense.embed_batch
ingest = dense.ingest_qdrant
release = embed.release

MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
BGE_MODEL = "BAAI/bge-reranker-v2-m3"
BGE_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
INSTRUCTIONS = {
    "default": INSTRUCTION,
    "evidence-v1": (
        "Retrieve passages containing explicit textual evidence useful for answering the dance "
        "question, including definitions, movement sequences, or practice instructions. A "
        "passage may support only part of the question. Mere topic mentions or introductions "
        "to unavailable media are insufficient."
    ),
}
MAX_LENGTH = 8192
INSTRUCTIONS["evidence-v2"] = INSTRUCTIONS["evidence-v1"] + (
    " Treat descriptions of the relevant body parts and how they move together or in sequence "
    "as evidence for the queried movement, even when the movement itself is not named."
)
INSTRUCTIONS["evidence-v3"] = INSTRUCTIONS["evidence-v2"] + (
    " For comparison questions, definitions and explanations of either individual concept "
    "are useful evidence, even when the passage does not mention the other concept. "
    "Do not favor a passage solely because it mentions multiple query terms."
)
BATCH_SIZE = 2
ATTENTION = "eager"
CANDIDATES = 10
ROUNDS = 3
OUTPUT = release.LOCAL / "week2.3" / "reranker"
METRICS = ("member_hit", "complete_plan")
VARIANTS = ("dense_3", "dense_5", "dense_10", "rerank_3", "rerank_5")
SMOKE_DOCS = ("Bend and release your knees to practice the hip hop bounce.",
              "Saturn is a gas giant with prominent rings.")
SMOKE_QUERIES = ("How do I practice the hip hop bounce?", "怎麼練習街舞的上下彈動？")


def model_pairs(query, hits, chunks):
    pairs = []
    for hit in hits:
        cid = hit["chunk_id"]
        chunk = chunks[cid]
        if hit["payload"]["chunk_id"] != cid or hit["payload"]["text"] != chunk["text"]:
            raise ValueError(f"Candidate payload does not match locked chunk {cid}")
        pairs.append((query, chunk["embedding_text"]))
    return pairs


def order_candidates(hits, scores, lengths):
    rows = []
    for hit, score, length in zip(hits, scores, lengths, strict=True):
        if not isfinite(score):
            raise ValueError("Reranker returned a non-finite score")
        rows.append({
            "chunk_id": hit["chunk_id"], "dense_rank": hit["rank"], "dense_score": hit["score"],
            "reranker_score": score, "reranker_input_tokens": length,
        })
    rows.sort(key=lambda row: (-row["reranker_score"], row["dense_rank"]))
    return [{**row, "rerank_rank": rank} for rank, row in enumerate(rows, 1)]


def selection(question, ids, chunks, tokenizer):
    text = "\n\n".join(chunks[cid]["embedding_text"] for cid in ids)
    return {
        "chunk_ids": ids,
        "characters": len(text),
        "tokens": dense.token_count(tokenizer, text, special=False),
        "evaluation": dense.score_question(question, ids),
    }


def compare_selection(before, after):
    changes = {}
    for metric in METRICS:
        delta = after["evaluation"][metric] - before["evaluation"][metric]
        changes[metric] = {1: "improved", 0: "unchanged", -1: "regressed"}[delta]
    return {
        "metrics": changes,
        **{key: after[key] - before[key] for key in ("characters", "tokens")},
    }


def verify_hits(actual, saved, points):
    if len(actual) != len(saved):
        raise ValueError("Candidate count differs")
    for rank, (hit, expected) in enumerate(zip(actual, saved, strict=True), 1):
        cid = hit["chunk_id"]
        point = points[cid]
        if (rank != hit["rank"] or rank != expected["rank"]
                or cid != expected["chunk_id"] or hit["point_id"] != point.id
                or hit["payload"] != point.payload
                or not abs(hit["score"] - expected["score"]) <= dense.SCORE_TOLERANCE):
            raise ValueError(f"Candidate mismatch at rank {rank}: {cid}")


def load_candidates(args, questions, dataset_sha, metadata, points):
    saved_runs = [release.read(path) for path in (args.baseline, args.diagnostics)]
    for run, k in zip(saved_runs, (5, 10), strict=True):
        expected = {
            "collection": ingest.COLLECTION, "inputs": metadata, "query_prompt": dense.QUERY_PROMPT,
            "dataset_sha256": dataset_sha, "top_k": k, "exact": True,
        }
        if any(run.get(key) != value for key, value in expected.items()):
            raise ValueError("Saved run does not match locked configuration")
    candidates = {}
    for baseline, diagnostic, question in zip(
        saved_runs[0]["questions"], saved_runs[1]["questions"], questions, strict=True
    ):
        key = question["question_id"]
        if any(row["question_id"] != key or row["question"] != question["question"]
               or row["language"] != question["language"] for row in (baseline, diagnostic)):
            raise ValueError(f"Saved query differs for {key}")
        hits = diagnostic["hits"]
        if len(hits) != CANDIDATES or len({hit["chunk_id"] for hit in hits}) != CANDIDATES:
            raise ValueError(f"Expected 10 distinct candidates for {key}")
        verify_hits(hits, hits, points)
        verify_hits(baseline["hits"], hits[:5], points)
        candidates[key] = hits
    return candidates


class Reranker:
    def __init__(self, device):
        import torch

        self.torch = torch
        self.device = device
        self.dtype = torch.float32
        if device == "mps" and not torch.backends.mps.is_available():
            raise RuntimeError("MPS is unavailable. To try CPU/float32, pass --device cpu.")

    def sync(self):
        if self.device == "mps":
            self.torch.mps.synchronize()

    def memory(self):
        sample = {"process_ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        if self.device == "mps":
            sample.update({
                "mps_current_bytes": self.torch.mps.current_allocated_memory(),
                "mps_driver_bytes": self.torch.mps.driver_allocated_memory(),
            })
        return sample

    def smoke(self):
        results = {}
        for language, query in zip(("en", "zh-Hant"), SMOKE_QUERIES, strict=True):
            scores, lengths = self.score([(query, text) for text in SMOKE_DOCS])
            if not all(map(isfinite, scores)) or not scores[0] > scores[1]:
                raise ValueError(f"{language}: smoke relevance check failed: {scores}")
            results[language] = {"relevant": scores[0], "unrelated": scores[1], "input_tokens": lengths}
        return results


class QwenReranker(Reranker):
    def __init__(self, device, instruction=INSTRUCTION):
        from huggingface_hub import hf_hub_download
        from transformers import AutoModelForCausalLM, AutoTokenizer

        super().__init__(device)
        self.instruction = instruction
        options = {"revision": REVISION, "local_files_only": True}
        template_path = hf_hub_download(MODEL_ID, "chat_template.jinja", **options)
        self.template = Path(template_path).read_text()
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side="left", **options)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, dtype=self.dtype, attn_implementation=ATTENTION, **options,
        ).eval().to(device)
        self.sync()
        self.token_ids = [self.tokenizer.convert_tokens_to_ids(word) for word in ("no", "yes")]

    def score(self, pairs):
        scores, lengths = [], []
        for start in range(0, len(pairs), BATCH_SIZE):
            batch = pairs[start:start + BATCH_SIZE]
            messages = [[{"role": "system", "content": self.instruction},
                         {"role": "query", "content": query},
                         {"role": "document", "content": document}]
                        for query, document in batch]
            ids = self.tokenizer.apply_chat_template(
                messages, chat_template=self.template, tokenize=True, truncation=False,
            )
            for offset, tokens in enumerate(ids):
                if len(tokens) > MAX_LENGTH:
                    raise ValueError(
                        f"Pair {start + offset + 1}: {len(tokens) - MAX_LENGTH} excess tokens "
                        f"({len(tokens)} > {MAX_LENGTH}); no truncation performed"
                    )
            lengths.extend(map(len, ids))
            inputs = self.tokenizer.pad({"input_ids": ids}, padding=True, return_tensors="pt")
            with self.torch.inference_mode():
                logits = self.model(
                    **inputs.to(self.device), logits_to_keep=1, use_cache=False,
                ).logits[:, -1, self.token_ids].float()
                scores.extend((logits[:, 1] - logits[:, 0]).cpu().tolist())
        self.sync()
        return scores, lengths

class BgeReranker(Reranker):
    def __init__(self, device):
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        super().__init__(device)
        options = {"revision": BGE_REVISION, "local_files_only": True}
        self.tokenizer = AutoTokenizer.from_pretrained(BGE_MODEL, **options)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            BGE_MODEL, dtype=self.dtype, attn_implementation=ATTENTION, **options,
        ).eval().to(device)
        config = self.model.config
        if config.model_type != "xlm-roberta" or config.num_labels != 1:
            raise ValueError("Expected the pinned XLM-R single-logit classifier")
        # XLM-R reserves positions through pad_token_id before real tokens.
        self.max_length = min(self.tokenizer.model_max_length,
                              config.max_position_embeddings - config.pad_token_id - 1)
        self.sync()

    def tokenize_pairs(self, pairs):
        query, document = zip(*pairs, strict=True)
        encoded = self.tokenizer(list(query), text_pair=list(document),
                                 add_special_tokens=True, padding=False, truncation=False)
        lengths = [len(ids) for ids in encoded["input_ids"]]
        if max(lengths) > self.max_length:
            raise ValueError(f"BGE pair lengths {lengths} exceed {self.max_length}; no truncation performed")
        return encoded, lengths

    def score(self, pairs):
        scores, lengths = [], []
        for start in range(0, len(pairs), BATCH_SIZE):
            encoded, sizes = self.tokenize_pairs(pairs[start:start + BATCH_SIZE])
            inputs = self.tokenizer.pad(encoded, padding=True, return_tensors="pt").to(self.device)
            with self.torch.inference_mode():
                logits = self.model(**inputs, return_dict=True).logits
                if logits.shape != (len(sizes), 1):
                    raise ValueError(f"Unexpected BGE classifier output shape {logits.shape}")
                scores.extend(logits[:, 0].float().cpu().tolist())
            lengths.extend(sizes)
        self.sync()
        return scores, lengths


def evaluate_question(question, hits, ranked, chunks, tokenizer):
    dense_ids = [hit["chunk_id"] for hit in hits]
    rerank_ids = [hit["chunk_id"] for hit in ranked]
    selected = {
        name: selection(question, ids[:int(name.split("_")[-1])], chunks, tokenizer)
        for name, ids in zip(VARIANTS, [dense_ids] * 3 + [rerank_ids] * 2, strict=True)
    }
    pairs = (
        ("dense_10", "rerank_3"), ("dense_10", "rerank_5"), ("dense_3", "rerank_3"),
        ("dense_5", "rerank_5"), ("rerank_5", "rerank_3"),
    )
    return {
        "question_id": question["question_id"], "language": question["language"],
        "dense": [{"chunk_id": hit["chunk_id"], "rank": hit["rank"], "score": hit["score"]}
                  for hit in hits],
        "reranked": ranked, "selected": selected,
        "changes": {f"{before}_to_{after}": compare_selection(selected[before], selected[after])
                    for before, after in pairs},
    }


def aggregate(results):
    variants = {}
    for name in results[0]["selected"]:
        selections = [row["selected"][name] for row in results]
        variants[name] = {
            "metrics": dense.summarize([
                {"language": row["language"], "evaluation": item["evaluation"]}
                for row, item in zip(results, selections, strict=True)
            ]),
            **{key: {"total": sum(item[key] for item in selections),
                     "mean": mean(item[key] for item in selections)}
               for key in ("characters", "tokens")},
        }
    comparisons = {}
    for name in results[0]["changes"]:
        before, after = name.split("_to_")
        comparisons[name] = {
            "metrics": {
                metric: {
                    status: [row["question_id"] for row in results
                             if row["changes"][name]["metrics"][metric] == status]
                    for status in ("improved", "regressed", "unchanged")
                } for metric in METRICS
            },
            "volume": {
                key: {
                    "difference": variants[after][key]["total"] - variants[before][key]["total"],
                    "percent_change": 100 * (variants[after][key]["total"] /
                                             variants[before][key]["total"] - 1),
                } for key in ("characters", "tokens")
            },
        }
    return variants, comparisons


def rank_question(scorer, question, hits, chunks):
    pairs = model_pairs(question["question"], hits, chunks)
    try:
        scores, lengths = scorer.score(pairs)
    except ValueError as error:
        ids = [hit["chunk_id"] for hit in hits]
        raise ValueError(f"{question['question_id']}, dense candidate order {ids}: {error}") from error
    return order_candidates(hits, scores, lengths)


def benchmark(scorer, query_model, client, questions, candidates, chunks, points, memory):
    measurements, results = [], []
    for repetition in range(ROUNDS):
        for question in questions:
            key, query = question["question_id"], question["question"]
            started = perf_counter()
            _, live_hits, timings = dense.run_query(query_model, client, query, limit=CANDIDATES)
            rerank_start = perf_counter()
            ranked = rank_question(scorer, question, live_hits, chunks)
            finished = perf_counter()
            verify_hits(live_hits, candidates[key], points)
            measurements.append({
                "question_id": key, "round": repetition + 1,
                "query_embedding": timings["query_embedding"],
                "qdrant_round_trip": timings["qdrant_round_trip"],
                "dense_top10": timings["end_to_end"],
                "rerank_top10": 1000 * (finished - rerank_start),
                "full_pipeline": 1000 * (finished - started),
            })
            memory.append(scorer.memory())
            if repetition == 0:
                results.append(evaluate_question(
                    question, candidates[key], ranked, chunks, query_model.tokenizer
                ))
        print(f"Completed timing round {repetition + 1}/{ROUNDS}", flush=True)
    return results, measurements


def git_snapshot():
    root = Path(__file__).resolve().parents[2]

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    return {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
            "status_porcelain": git("status", "--porcelain=v1")}


def run_instruction_comparison(args, scorer, load_seconds, state, smoke, smoke_seconds,
                               questions, chunks, candidates, dataset_sha, metadata):
    from transformers import AutoTokenizer

    saved_hashes = {str(path): release.sha256(path) for path in (args.baseline, args.diagnostics)}
    default_hash = release.sha256(args.default_result)
    original = release.read(args.default_result)
    bge = args.reranker == "bge"
    scoring_settings = {
        "model": MODEL_ID, "revision": REVISION,
        "template": original["template"] if bge else scorer.template,
        "device": "mps", "dtype": "torch.float32", "attention": ATTENTION,
        "max_length": MAX_LENGTH, "batch_size": BATCH_SIZE, "truncation": False,
        "score": "last-position yes logit minus no logit", "padding": "left",
        "use_cache": False, "logits_to_keep": 1, "threads": embed.THREADS,
    }
    token_proxy = {"model": embed.MODEL_ID, "revision": embed.REVISION,
                   "join": "\n\n", "special_tokens": False}
    packages = {name: version(name) for name in original["packages"]}
    expected = {
        **scoring_settings, "instruction": INSTRUCTION, "dataset_sha256": dataset_sha,
        "embedding_artifact": metadata, "collection": ingest.COLLECTION,
        "saved_runs": saved_hashes, "query_prompt": dense.QUERY_PROMPT,
        "query_normalization": True, "exact": True, "retrieval_k": CANDIDATES,
        "packages": packages, "token_proxy": token_proxy,
        "text_input": "locked embedding_text as stored, with no additional metadata",
    }
    mismatches = [key for key, value in expected.items() if original.get(key) != value]
    if mismatches or (not bge and (
        scorer.device != scoring_settings["device"] or str(scorer.dtype) != scoring_settings["dtype"]
    )):
        raise ValueError(f"Default experiment configuration differs: {mismatches}")

    tokenizer = AutoTokenizer.from_pretrained(
        embed.MODEL_ID, revision=embed.REVISION, local_files_only=True,
    )
    defaults = {}
    for question, row in zip(questions, original["questions"], strict=True):
        key = question["question_id"]
        hits = candidates[key]
        by_dense_rank = sorted(row["reranked"], key=lambda hit: hit["dense_rank"])
        if [hit["chunk_id"] for hit in by_dense_rank] != [hit["chunk_id"] for hit in hits]:
            raise ValueError(f"Default candidates differ for {key}")
        ranked = order_candidates(hits, [hit["reranker_score"] for hit in by_dense_rank],
                                  [hit["reranker_input_tokens"] for hit in by_dense_rank])
        if row != evaluate_question(question, hits, ranked, chunks, tokenizer):
            raise ValueError(f"Default rankings or metrics differ for {key}")
        defaults[key] = row

    references = {}
    if bge:
        for name in ("evidence-v1", "evidence-v2"):
            path = getattr(args, name.replace("-", "_") + "_result")
            reference = release.read(path)
            if any(reference.get(key) != value for key, value in expected.items()
                   if key not in ("instruction", "query_normalization", "exact", "retrieval_k", "text_input")):
                raise ValueError(f"{name} reference settings differ")
            if reference["instruction"] != INSTRUCTIONS[name]:
                raise ValueError(f"{name} reference instruction differs")
            label = name.replace("-", "_")
            rows = {}
            for question, row in zip(questions, reference["questions"], strict=True):
                key = question["question_id"]
                if row["question_id"] != key or row["dense"] != defaults[key]["dense"]:
                    raise ValueError(f"{name} candidates differ for {key}")
                ranked_ids = [hit["chunk_id"] for hit in row["reranked"]]
                if sorted(ranked_ids) != sorted(hit["chunk_id"] for hit in candidates[key]):
                    raise ValueError(f"{name} ranking differs in candidate membership for {key}")
                rows[key] = {}
                for k in (3, 5):
                    variant = f"{label}_{k}"
                    saved = row["selected"][variant]
                    if saved != selection(question, ranked_ids[:k], chunks, tokenizer):
                        raise ValueError(f"{name} selected evidence differs for {key}")
                    rows[key][variant] = saved
            references[label] = {"path": str(path), "sha256": release.sha256(path), "rows": rows}
        for question in questions:
            key = question["question_id"]
            try:
                scorer.tokenize_pairs(model_pairs(question["question"], candidates[key], chunks))
            except ValueError as error:
                raise ValueError(f"{key}: {error}") from error

    warmup_start = perf_counter()
    for question in questions[:3]:
        rank_question(scorer, question, candidates[question["question_id"]], chunks)
    warmup_seconds = perf_counter() - warmup_start

    results, samples = [], []
    rounds = 1 if bge or args.instruction in ("evidence-v2", "evidence-v3") else ROUNDS
    variant = "bge" if bge else args.instruction.replace("-", "_")
    for repetition in range(rounds):
        for question in questions:
            key = question["question_id"]
            hits = candidates[key]
            started = perf_counter()
            ranked = rank_question(scorer, question, hits, chunks)
            samples.append({"question_id": key, "round": repetition + 1,
                            "rerank_ms": 1000 * (perf_counter() - started)})
            if repetition != 0:
                continue
            row = evaluate_question(question, hits, ranked, chunks, tokenizer)
            default = defaults[key]
            picked = {name: row["selected"][name] for name in VARIANTS[:3]}
            for k in (3, 5):
                if not bge:
                    picked[f"default_{k}"] = default["selected"][f"rerank_{k}"]
                picked[f"{variant}_{k}"] = row["selected"][f"rerank_{k}"]
            for reference in references.values():
                picked.update(reference["rows"][key])
            pairs = [(f"{prefix}_{k}", f"{variant}_{k}")
                     for prefix in ("dense", *(references or {"default": None})) for k in (3, 5)]
            row["selected"] = picked
            if not bge:
                row["default_ranked"] = default["reranked"]
            row["changes"] = {f"{a}_to_{b}": compare_selection(picked[a], picked[b]) for a, b in pairs}
            results.append(row)
        print(f"Completed {variant} round {repetition + 1}/{rounds}", flush=True)

    variants, comparisons = aggregate(results)
    if any(variants[name] != original["variants"][name] for name in VARIANTS[:3]):
        raise ValueError("Dense metrics or candidate volume differ from the original evaluation")
    p = quantiles([row["rerank_ms"] for row in samples], n=100, method="inclusive")
    lengths = [hit["reranker_input_tokens"] for row in results for hit in row["reranked"]]
    run = {
        "analysis": "post_failure_instruction_development_evaluation", "git": state,
        **scoring_settings, "instruction_name": args.instruction,
        "instruction": None if bge else scorer.instruction,
        "dataset_sha256": dataset_sha, "embedding_artifact": metadata,
        "collection": ingest.COLLECTION, "saved_runs": saved_hashes,
        "default_result": {"path": str(args.default_result), "sha256": default_hash},
        "script_sha256": release.sha256(Path(__file__)), "packages": packages,
        "token_proxy": token_proxy, "query_prompt": dense.QUERY_PROMPT,
        "candidate_source": "saved exact top-10", "live_retrieval_measured": False,
        "model_load_seconds": load_seconds, "smoke": smoke, "smoke_seconds": smoke_seconds,
        "warmup_seconds": warmup_seconds,
        "warmup_queries": [q["question_id"] for q in questions[:3]], "timing_rounds": rounds,
        "reranker_input_tokens": {"pairs": len(lengths), "total": sum(lengths), "max": max(lengths),
                                  "mean_per_query": sum(lengths) / len(questions), "truncated_pairs": 0},
        "rerank_latency_ms": {"n": len(samples), "p50": p[49], "p95": p[94]},
        "percentile_method": "linear interpolation at zero-based (n - 1) * p",
        "timings_ms": samples, "variants": variants, "comparisons": comparisons, "questions": results,
    }
    if bge:
        run.update({
            "analysis": "bge_reranker_development_evaluation",
            "model": BGE_MODEL, "revision": BGE_REVISION, "tokenizer_revision": BGE_REVISION,
            "device": scorer.device, "dtype": str(scorer.dtype),
            "max_length": scorer.max_length, "padding": scorer.tokenizer.padding_side,
            "score": "raw single sequence-classification logit",
            "reference_results": {name: {key: reference[key] for key in ("path", "sha256")}
                                  for name, reference in references.items()},
        })
        for field in ("instruction_name", "template", "use_cache", "logits_to_keep"):
            del run[field]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = OUTPUT / f"{'bge' if bge else args.instruction}-{timestamp}.json"
    with path.open("xb") as stream:
        stream.write(embed.json_bytes(run))
    print(f"Results: {path}")
    print(run["rerank_latency_ms"])


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--device", choices=("mps", "cpu"), default="mps")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--instruction", choices=INSTRUCTIONS, default="default")
    parser.add_argument("--reranker", choices=("qwen", "bge"), default="qwen")
    parser.add_argument("--evidence-v1-result", type=Path)
    parser.add_argument("--evidence-v2-result", type=Path)
    parser.add_argument("--default-result", type=Path, help="Saved default rerank result for instruction comparisons")
    args = parser.parse_args(argv)
    if not args.smoke_only and not all((args.artifact, args.baseline, args.diagnostics)):
        parser.error("--artifact, --baseline and --diagnostics are required for evaluation")
    if args.reranker == "bge" and args.instruction != "default":
        parser.error("BGE scores text pairs directly and does not accept a Qwen instruction")
    if not args.smoke_only and args.reranker == "bge" and not all(
        (args.default_result, args.evidence_v1_result, args.evidence_v2_result)
    ):
        parser.error("BGE comparison requires the saved default, evidence-v1 and evidence-v2 results")
    if not args.smoke_only and args.instruction != "default" and args.default_result is None:
        parser.error("--default-result is required for instruction comparisons")
    return args


def main():
    args = parse_args()

    import torch
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(embed.THREADS)
    state = git_snapshot()
    started = perf_counter()
    scorer = (BgeReranker(args.device) if args.reranker == "bge"
              else QwenReranker(args.device, INSTRUCTIONS[args.instruction]))
    reranker_load = perf_counter() - started
    print(f"Reranker model load: {reranker_load:.3f} s", flush=True)
    memory = [scorer.memory()]
    started = perf_counter()
    smoke = scorer.smoke()
    smoke_seconds = perf_counter() - started
    print(f"Smoke: {smoke}", flush=True)
    if args.smoke_only:
        return

    documents, chunk_rows, locked = embed.load_locked_inputs()
    questions = release.validate_release(
        release.PILOT / "dataset.json", release.PILOT / "review.md", locked["release"], locked["corpus"]
    )
    chunks = {chunk["chunk_id"]: chunk for chunk in chunk_rows}
    vectors, metadata = ingest.load_batch(args.artifact, chunk_rows, locked)
    point_list = ingest.build_points(documents, chunk_rows, vectors)
    points = {point.payload["chunk_id"]: point for point in point_list}
    dataset_sha = locked["release"]["dataset_sha256"]
    candidates = load_candidates(args, questions, dataset_sha, metadata, points)

    if args.reranker == "bge" or args.instruction != "default":
        run_instruction_comparison(args, scorer, reranker_load, state, smoke, smoke_seconds,
                                   questions, chunks, candidates, dataset_sha, metadata)
        return

    started = perf_counter()
    query_model = SentenceTransformer(
        embed.MODEL_ID, revision=embed.REVISION, local_files_only=True,
        device="cpu", model_kwargs={"dtype": torch.float32},
    )
    query_model.max_seq_length = embed.MAX_SEQUENCE_LENGTH
    query_model_load = perf_counter() - started
    dense.check_query_tokens(query_model.tokenizer, [(q["question_id"], q["question"]) for q in questions])

    with closing(QdrantClient(url=ingest.URL, timeout=15)) as client:
        server = client.info().version
        if server != ingest.SERVER_VERSION:
            raise ValueError(f"Unexpected Qdrant version {server}")
        ingest.verify_collection(client, ingest.COLLECTION, metadata, point_list)
        for question in questions[:3]:
            query = question["question"]
            _, hits, _ = dense.run_query(query_model, client, query, limit=CANDIDATES)
            verify_hits(hits, candidates[question["question_id"]], points)
            scores, lengths = scorer.score(model_pairs(query, hits, chunks))
            order_candidates(hits, scores, lengths)
        memory.append(scorer.memory())
        results, measurements = benchmark(
            scorer, query_model, client, questions, candidates, chunks, points, memory
        )

    variants, comparisons = aggregate(results)
    latency = {}
    for key in ("query_embedding", "qdrant_round_trip", "dense_top10", "rerank_top10", "full_pipeline"):
        samples = [row[key] for row in measurements]
        p = quantiles(samples, n=100, method="inclusive")
        latency[key] = {"n": len(samples), "p50": p[49], "p95": p[94]}
    lengths = [hit["reranker_input_tokens"] for row in results for hit in row["reranked"]]
    run = {
        "analysis": "development_evaluation", "git": state, "dataset_sha256": dataset_sha,
        "script_sha256": release.sha256(Path(__file__)),
        "embedding_artifact": metadata, "collection": ingest.COLLECTION, "qdrant_server": server,
        "saved_runs": {str(path): release.sha256(path) for path in (args.baseline, args.diagnostics)},
        "command_arguments": vars(args) | {name: str(getattr(args, name))
                                           for name in ("artifact", "baseline", "diagnostics")},
        "model": MODEL_ID, "revision": REVISION, "instruction": INSTRUCTION, "template": scorer.template,
        "device": args.device, "dtype": str(scorer.dtype), "max_length": MAX_LENGTH, "batch_size": BATCH_SIZE,
        "score": "last-position yes logit minus no logit", "attention": ATTENTION, "padding": "left",
        "truncation": False, "use_cache": False, "logits_to_keep": 1, "threads": embed.THREADS,
        "model_load_seconds": {"reranker": reranker_load, "query_embedding": query_model_load},
        "query_prompt": dense.QUERY_PROMPT, "query_device": "cpu", "query_dtype": "float32",
        "query_normalization": True, "exact": True, "retrieval_k": CANDIDATES,
        "warmup_queries": [q["question_id"] for q in questions[:3]], "timing_rounds": ROUNDS,
        "reranker_input_tokens": {"pairs": len(lengths), "total": sum(lengths), "max": max(lengths),
                                  "mean_per_query": sum(lengths) / len(questions)},
        "text_input": "locked embedding_text as stored, with no additional metadata",
        "token_proxy": {"model": embed.MODEL_ID, "revision": embed.REVISION,
                        "join": "\n\n", "special_tokens": False},
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: version(name) for name in (
            "torch", "transformers", "sentence-transformers", "qdrant-client", "huggingface-hub",
            "tokenizers", "safetensors", "numpy", "jinja2",
        )},
        "smoke": smoke, "timings_ms": measurements, "latency_ms": latency,
        "percentile_method": "linear interpolation at zero-based (n - 1) * p",
        "memory_max_observed": {key: max(sample[key] for sample in memory) for key in memory[0]},
        "memory_scope": "Python process ru_maxrss (macOS bytes) and sampled MPS allocator after calls",
        "variants": variants, "comparisons": comparisons, "questions": results,
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = OUTPUT / f"development-{timestamp}.json"
    with path.open("xb") as stream:
        stream.write(embed.json_bytes(run))
    print(f"Results: {path}")
    print(latency)


if __name__ == "__main__":
    main()
