"""Chunk and verify the selected Week 2.1 v3 baseline corpus."""

import argparse
import hashlib
import json
from itertools import groupby
from pathlib import Path
from statistics import median

if __package__:
    from .chunk_pilot import (
        MODEL_ID, REVISION, SETTINGS, article_layout, article_structure, build_chunks,
        save_article_structure, token_count,
    )
else:
    from chunk_pilot import (
        MODEL_ID, REVISION, SETTINGS, article_layout, article_structure, build_chunks,
        save_article_structure, token_count,
    )


SOURCE_IDS = (
    "steezy-how-to-be-a-good-dancer",
    "steezy-how-to-execute-movement",
    "steezy-basics-dance-musicality",
    "steezy-how-to-freestyle-dance-2",
    "steezy-how-to-learn-popping",
    "steezy-how-to-take-a-dance-class-2",
    "steezy-how-to-train-your-foundation-fundamentals-2",
    "steezy-how-to-train-your-musicality-as-a-dancer",
    "steezy-what-is-house-dance",
    "steezy-what-is-popping-dance",
    "youtube-hip-hop-bounce",
    "youtube-arm-waves-inside-out",
    "youtube-hip-hop-fundamentals",
    "youtube-locking-the-lock",
    "youtube-locking-running-man-skeeter-rabbit",
)


def load_baseline(root):
    manifest = json.loads((root / "manifest.json").read_bytes())
    summary = json.loads((root / "validation-summary-v3-baseline.json").read_bytes())
    documents = {row["doc_id"]: row for row in manifest}
    entries = {row["doc_id"]: row for row in summary}
    if len(manifest) != len(SOURCE_IDS) or set(documents) != set(SOURCE_IDS):
        raise ValueError("Manifest does not identify the selected 15 sources")
    if len(summary) != len(SOURCE_IDS) or set(entries) != set(SOURCE_IDS):
        raise ValueError("Validation summary does not identify the selected 15 sources")
    baseline = root / "clean-v3-baseline"
    if baseline.is_symlink():
        raise ValueError("The baseline directory must not be a symlink")
    for source_id in SOURCE_IDS:
        filename = f"{source_id}.json"
        path = baseline / filename
        entry = entries[source_id]
        if path.is_symlink() or entry["file"] != filename or entry["validation_status"] != "passed":
            raise ValueError(f"Invalid baseline file entry for {source_id}")
        payload = path.read_bytes()
        document = json.loads(payload)
        metadata = document["metadata"]
        expected_type = "transcript" if source_id.startswith("youtube-") else "article"
        if (
            hashlib.sha256(payload).hexdigest() != entry["sha256"]
            or metadata["doc_id"] != source_id
            or metadata["source_type"] != expected_type
            or metadata["raw_sha256"] != documents[source_id]["raw_sha256"]
            or metadata["source_url"] != documents[source_id]["source_url"]
        ):
            raise ValueError(f"Baseline identity or digest mismatch for {source_id}")
        yield source_id, payload


def check_source_pointers(chunk, records, canonical):
    body = chunk["text"]
    start = chunk["source_text_range"][0]
    if "time_range_ms" in chunk:
        pointers = [cue for source in chunk["sources"] for cue in source["cues"]]
        if chunk["time_range_ms"] != [
            min(cue["start_ms"] for cue in pointers), max(cue["end_ms"] for cue in pointers),
        ]:
            raise ValueError("Chunk time range does not match cue pointers")
    cursor = 0
    for source in chunk["sources"]:
        left, right = source["body_range"]
        lo, hi = source["source_text_range"]
        if (
            not cursor <= left < right <= len(body)
            or body[cursor:left].strip()
            or [start + left, start + right] != [lo, hi]
        ):
            raise ValueError("Invalid chunk source range")
        text = body[left:right]
        if text != canonical[lo:hi]:
            raise ValueError("Source slice does not match")
        if "block_id" in source:
            block = records[source["block_id"]]
            begin, end = source["block_range"]
            if (
                block["kind"] == "heading" or block["kind"] != source["kind"]
                or block["text"][begin:end] != text or block["raw_lines"] != source["raw_lines"]
            ):
                raise ValueError("Article block does not match")
        else:
            for pointer in source["cues"]:
                cue = records[pointer["cue_id"]]
                begin, end = pointer["plain_range"]
                if cue["plain_text"][begin:end] != text or any(
                    cue[key] != pointer[key] for key in ("start_ms", "end_ms", "raw_lines")
                ):
                    raise ValueError("Subtitle cue does not match")
        cursor = right
    if body[cursor:].strip():
        raise ValueError("Missing source pointer")


def verify_chunks(document, chunks, tokenizer):
    if "transcript" in document:
        sections = [([], None, document["transcript"]["chunking_input"]["text"])]
        records = {row["cue_id"]: row for row in document["records"]}
    else:
        _, layout = article_layout(document["records"])
        sections = [
            (list(heading), list(heading_ids), "\n\n".join(row["text"] for row in blocks))
            for heading, heading_ids, blocks in layout
        ]
        records = {row["block_id"]: row for row in document["records"]}
    groups = [(index, list(group)) for index, group in groupby(
        chunks, key=lambda chunk: chunk["section_index"]
    )]
    if [index for index, _ in groups] != list(range(1, len(sections) + 1)):
        raise ValueError("Chunk section order or coverage differs")
    title = document["metadata"]["title"]
    for (_, group), (heading, heading_ids, canonical) in zip(groups, sections):
        subsection = heading[1:] if heading and heading[0] == title else heading
        prefix = "\n".join((title, " > ".join(subsection))) if subsection else title
        cursor = 0
        previous = ""
        for chunk in group:
            text = chunk["text"]
            start, end = chunk["source_text_range"]
            overlap = chunk["overlap_chars"]
            overlap_text = text[:overlap]
            if (
                not 0 <= start <= cursor < end <= len(canonical)
                or start + overlap != cursor or text != canonical[start:end]
                or chunk["new_body_range"] != [overlap, len(text)]
                or not text[overlap:].strip() or not previous.endswith(overlap_text)
            ):
                raise ValueError("Missing, changed, or repeated new text")
            actual_tokens = token_count(tokenizer, chunk["embedding_text"])
            actual_overlap = token_count(tokenizer, overlap_text, special=False)
            if (
                chunk["heading_path"] != heading
                or chunk.get("heading_block_ids") != heading_ids
                or chunk["embedding_text"] != (prefix + "\n\n" + text).strip()
                or actual_tokens != chunk["token_count"] or actual_tokens > SETTINGS["max_tokens"]
            ):
                raise ValueError("Invalid embedding token count")
            if actual_overlap != chunk["overlap_tokens"] or actual_overlap > SETTINGS["max_overlap_tokens"]:
                raise ValueError("Invalid overlap token count")
            check_source_pointers(chunk, records, canonical)
            cursor, previous = end, text
        if cursor != len(canonical):
            raise ValueError("Incomplete section coverage")


def summarize(chunks):
    counts = [chunk["token_count"] for chunk in chunks]
    seen, split = set(), set()
    for chunk in chunks:
        new_units = {
            source["block_id"] if "block_id" in source else source["cues"][0]["cue_id"]
            for source in chunk["sources"]
            if source["body_range"][1] > chunk["overlap_chars"]
        }
        split.update(seen & new_units)
        seen.update(new_units)
    return {
        "source_id": chunks[0]["source_id"],
        "input_sha256": chunks[0]["input_sha256"],
        "chunks": len(chunks),
        "tokens": counts,
        "min_median_max": [min(counts), median(counts), max(counts)],
        "overlap_tokens": [chunk["overlap_tokens"] for chunk in chunks],
        "split_blocks": sorted(unit for unit in split if unit.startswith("block-")),
        "split_cues": sorted(unit for unit in split if unit.startswith("cue-")),
    }


def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    baseline_root = args.baseline_root.resolve()
    if output_dir == baseline_root or baseline_root in output_dir.parents:
        parser.error("--output-dir must be outside --baseline-root")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, local_files_only=True)
    if not tokenizer.is_fast:
        raise ValueError("The batch requires tokenizer character offsets")
    results, structures, summary = {}, {}, []
    for source_id, payload in load_baseline(baseline_root):
        document = json.loads(payload)
        chunks = build_chunks(payload, tokenizer)
        verify_chunks(document, chunks, tokenizer)
        results[source_id] = chunks
        if "transcript" not in document:
            structures[source_id] = article_structure(document)
        summary.append(summarize(chunks))
    chunk_dir = output_dir / "chunks"
    paths = [chunk_dir / f"{source_id}.json" for source_id in results]
    if chunk_dir.is_symlink() or any(path.is_symlink() for path in [*paths, output_dir / "summary.json"]):
        raise ValueError("Refusing to write batch output through a symlink")
    chunk_dir.mkdir(parents=True, exist_ok=True)
    for source_id, chunks in results.items():
        save_json(chunk_dir / f"{source_id}.json", chunks)
    for source_id, structure in structures.items():
        save_article_structure(output_dir, source_id, structure)
    save_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
