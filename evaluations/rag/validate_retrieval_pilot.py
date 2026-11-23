"""Validate the local Week 2.2 retrieval pilot against its frozen inputs."""

import hashlib
import json
from collections import Counter
from datetime import date
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / "local"
LOCK = ROOT / "retrieval-set-v1.lock.json"
CLEAN = LOCAL / "week2.1/clean-v3-baseline"
BATCH = LOCAL / "week2.2/batch-headings-v2"
PILOT = LOCAL / "week2.2/retrieval-pilot-v1"


def read(path):
    return json.loads(path.read_bytes())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_corpus():
    summary = read(BATCH / "summary.json")
    sources = {row["source_id"]: row for row in summary}
    assert len(summary) == len(sources) == 15
    for directory in (CLEAN, BATCH / "chunks"):
        assert {path.stem for path in directory.glob("*.json")} == sources.keys()

    documents, chunks, versions = {}, {}, {}
    for source_id, row in sources.items():
        clean_path = CLEAN / f"{source_id}.json"
        chunk_path = BATCH / "chunks" / clean_path.name
        document = read(clean_path)
        assert document["metadata"]["doc_id"] == source_id
        assert document["metadata"]["synthetic"] is False
        clean_hash = sha256(clean_path)
        assert clean_hash == row["input_sha256"]
        source_chunks = read(chunk_path)
        assert len(source_chunks) == row["chunks"]
        settings = source_chunks[0]["chunking_settings"]
        identity = hashlib.sha256(json.dumps([clean_hash, settings], sort_keys=True).encode())
        for number, chunk in enumerate(source_chunks, 1):
            expected_id = f"{source_id}:{identity.hexdigest()[:16]}:{number:04d}"
            assert chunk["chunk_id"] == expected_id and expected_id not in chunks
            assert chunk["source_id"] == source_id and chunk["input_sha256"] == clean_hash
            assert chunk["source_url"] == document["metadata"]["source_url"]
            assert chunk["raw_sha256"] == document["metadata"]["raw_sha256"]
            assert chunk["chunking_settings"] == settings
            chunks[expected_id] = chunk
        documents[source_id] = document
        versions[source_id] = {
            "clean_sha256": clean_hash,
            "raw_sha256": document["metadata"]["raw_sha256"],
            "chunks_sha256": sha256(chunk_path),
            "cleaning_version": document["cleaning_version"],
            "transcript_version": document.get("transcript", {}).get("version"),
            "chunking_settings": settings,
            "chunk_count": len(source_chunks),
        }
    assert len(chunks) == 154
    return documents, chunks, {
        "corpus": "week2.1/clean-v3-baseline",
        "chunk_batch": "week2.2/batch-headings-v2",
        "batch_summary_sha256": sha256(BATCH / "summary.json"),
        "sources": versions,
    }


def locations(chunk, document, start, end):
    """Map a half-open chunk-body range to exact clean block/cue ranges."""
    body = chunk["text"]
    assert 0 <= start < end <= len(body)
    records = {
        record.get("block_id", record.get("cue_id")): record
        for record in document["records"]
    }
    result = []
    cursor = start
    for origin in chunk["sources"]:
        origin_start, origin_end = origin["body_range"]
        left, right = max(start, origin_start), min(end, origin_end)
        if left >= right:
            continue
        assert not body[cursor:left].strip()
        cursor = right
        local_start, local_end = left - origin_start, right - origin_start
        if "block_id" in origin:
            record = records[origin["block_id"]]
            offset = origin["block_range"][0]
            first, last = offset + local_start, offset + local_end
            assert 0 <= first < last <= len(record["text"])
            assert record["text"][first:last] == body[left:right]
            assert record["raw_lines"] == origin["raw_lines"]
            assert record["heading_path"] == chunk["heading_path"]
            result.append({
                "block_id": record["block_id"], "char_range": [first, last],
                "raw_lines": record["raw_lines"], "heading_path": record["heading_path"],
            })
        else:
            # Use the first retained cue for each span. The chunk preserves
            # additional equivalent rolling-caption copies.
            cue = origin["cues"][0]
            record = records[cue["cue_id"]]
            offset = cue["plain_range"][0]
            first, last = offset + local_start, offset + local_end
            assert 0 <= first < last <= len(record["plain_text"])
            assert record["plain_text"][first:last] == body[left:right]
            for field in ("start_ms", "end_ms", "raw_lines"):
                assert record[field] == cue[field]
            assert 0 <= record["start_ms"] < record["end_ms"]
            result.append({
                "cue_id": record["cue_id"], "char_range": [first, last],
                "raw_lines": record["raw_lines"],
                "start_ms": record["start_ms"], "end_ms": record["end_ms"],
            })
    assert result and not body[cursor:end].strip()
    return result


def matching_chunks(chunk, chunks, start, end):
    """Include any overlapping chunk containing the same entire source range."""
    absolute_start = chunk["source_text_range"][0] + start
    absolute_end = chunk["source_text_range"][0] + end
    return [
        item["chunk_id"]
        for item in chunks.values()
        if item["source_id"] == chunk["source_id"]
        and item["section_index"] == chunk["section_index"]
        and item["source_text_range"][0] <= absolute_start
        and item["source_text_range"][1] >= absolute_end
    ]


def minimal_chunk_sets(evidence):
    """Return OR alternatives, deduplicating IDs within each AND set."""
    candidates = {frozenset(ids) for ids in product(*[
        item["relevant_chunk_ids"] for item in evidence
    ])}
    return sorted(sorted(ids) for ids in candidates
                  if not any(other < ids for other in candidates))


def validate_questions(questions, documents, chunks):
    """Validate mappings and Boolean evidence plans without local dependencies."""
    by_id = {question["question_id"]: question for question in questions}
    assert len(questions) == len(by_id)
    evidence_count = 0
    for question in questions:
        points = {point["point_id"] for point in question["expected_answer_points"]}
        groups = question["evidence_groups"]
        group_ids = {group["group_id"] for group in groups}
        assert len(groups) == len(group_ids)
        minimum = question["minimum_sufficient"]["any_of"]
        supplemental = question["supplemental_group_ids"]
        assert minimum and len(minimum) == len(set(minimum))
        assert len(supplemental) == len(set(supplemental))
        assert not set(minimum) & set(supplemental)
        assert set(minimum) | set(supplemental) == group_ids
        minimum_sets = set()
        assert {point for group in groups for point in group["supports"]} == points
        for group in groups:
            group_chunks = set()
            assert set(group["supports"]) <= points
            assert set(group["supports"]) == {
                point for evidence in group["evidence"] for point in evidence["supports"]
            }
            for evidence in group["evidence"]:
                chunk = chunks[evidence["anchor_chunk_id"]]
                source_id = evidence["source_id"]
                assert chunk["source_id"] == source_id
                assert chunk["source_url"] == evidence["source_url"]
                start, end = evidence["chunk_char_range"]
                assert evidence["excerpt"] == chunk["text"][start:end]
                assert evidence["locations"] == locations(chunk, documents[source_id], start, end)
                assert evidence["relevant_chunk_ids"] == matching_chunks(chunk, chunks, start, end)
                for chunk_id in evidence["relevant_chunk_ids"]:
                    mapped = chunks[chunk_id]
                    offset = chunk["source_text_range"][0] - mapped["source_text_range"][0]
                    assert mapped["text"][start + offset:end + offset] == evidence["excerpt"]
                    assert evidence["locations"] == locations(
                        mapped, documents[source_id], start + offset, end + offset
                    )
                group_chunks.update(evidence["relevant_chunk_ids"])
                evidence_count += 1
            assert set(group["relevant_chunk_ids"]) == group_chunks
            chunk_sets = minimal_chunk_sets(group["evidence"])
            mode = group["mode"]
            assert mode in {"sufficient", "partial", "all_required"}
            assert group["evaluation_chunk_sets"] == ([] if mode == "partial" else chunk_sets)
            complete_chunks = {ids[0] for ids in chunk_sets if len(ids) == 1}
            if mode == "sufficient":
                assert complete_chunks
            if mode == "all_required":
                assert not complete_chunks and all(len(ids) > 1 for ids in chunk_sets)
            if group["group_id"] in minimum:
                assert mode != "partial"
                minimum_sets.update(tuple(ids) for ids in chunk_sets)
            assert set(group["chunk_support"]) == group_chunks
            for chunk_id, support in group["chunk_support"].items():
                expected = "sufficient" if mode == "sufficient" and chunk_id in complete_chunks else "partial"
                assert support == expected
        assert all(not any(set(other) < set(ids) for other in minimum_sets) for ids in minimum_sets)
        assert question["minimum_sufficient"]["evaluation_chunk_sets"] == [
            list(ids) for ids in sorted(minimum_sets)
        ]
    return evidence_count


def validate_release(dataset_file, preview_file, lock, version):
    assert sha256(dataset_file) == lock["dataset_sha256"], "Dataset SHA-256 mismatch"
    assert sha256(preview_file) == lock["preview_sha256"], "Preview SHA-256 mismatch"
    dataset = read(dataset_file)
    assert dataset["version"] == version
    assert version["batch_summary_sha256"] == lock["batch_summary_sha256"]
    assert dataset["schema_version"] == lock["schema_version"] == 2
    assert dataset["release_version"] == lock["release_version"]
    assert dataset["review_status"] == "approved"
    questions = dataset["questions"]
    assert len(questions) == lock["questions"] == lock["approved"] == 30
    assert len({question["question"].strip().casefold() for question in questions}) == 30
    assert Counter(question["language"] for question in questions) == lock["languages"] == {"en": 15, "zh-Hant": 15}
    for question in questions:
        assert question["review_status"] == "approved"
        review = question["review"]
        assert date.fromisoformat(review["date"]).isoformat() == review["date"] == "2026-11-24"
        assert review["reviewer"] == "user" and review["basis"].strip()
    by_id = {question["question_id"]: question for question in questions}
    for qid, group_id in (("pilot-bounce", "downbeat"), ("pilot-arm-wave", "twelve-point")):
        group = next(group for group in by_id[qid]["evidence_groups"] if group["group_id"] == group_id)
        assert group["mode"] == "partial"
        assert group_id in by_id[qid]["supplemental_group_ids"]
    assert any(note["scope"] == "twelve-point" and note["reason"].strip()
               for note in by_id["pilot-arm-wave"]["human_review_notes"])
    return questions


def validate():
    documents, chunks, version = load_corpus()
    lock = read(LOCK)
    questions = validate_release(PILOT / "dataset.json", PILOT / "review.md", lock, version)
    evidence_count = validate_questions(questions, documents, chunks)
    assert evidence_count == lock["evidence_entries"]
    print(f"Verified {lock['release_version']}: {len(questions)} approved questions, "
          f"{evidence_count} evidence entries, {len(documents)} sources and {len(chunks)} chunks")


if __name__ == "__main__":
    validate()
