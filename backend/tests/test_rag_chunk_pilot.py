import json
import re
from pathlib import Path

import pytest


@pytest.fixture
def pilot(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    from evaluations.rag import chunk_pilot

    return chunk_pilot


class OfflineTokenizer:
    def __call__(
        self, text, *, add_special_tokens, truncation, return_offsets_mapping=False
    ):
        assert truncation is False
        offsets = [match.span() for match in re.finditer(r"\S+", text)]
        result = {"input_ids": [0] * (len(offsets) + int(add_special_tokens))}
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result


def document(records, transcript=None):
    if transcript is None and all(row["kind"] != "heading" for row in records):
        structured = [heading("title", ["Practice"])]
        previous = None
        for row in records:
            if row["heading_path"] != previous:
                structured.append(heading(f"section-{len(structured)}", row["heading_path"]))
                previous = row["heading_path"]
            structured.append(row)
        records = structured
    result = {
        "metadata": {
            "doc_id": "synthetic-dance", "title": "Practice",
            "source_url": "https://example.com/synthetic", "raw_sha256": "synthetic",
        },
        "cleaning_version": "fixture",
        "records": records,
    }
    if transcript is not None:
        result["transcript"] = transcript
    return json.dumps(result).encode()


def block(index, subsection, text):
    return {
        "block_id": f"block-{index}", "heading_path": ["Practice", subsection],
        "raw_lines": [index, index], "kind": "paragraph", "text": text,
    }


def heading(key, path):
    return {
        "block_id": f"heading-{key}", "heading_path": path,
        "raw_lines": [1, 1], "kind": "heading",
        "text": f"{'#' * len(path)} {path[-1]}",
    }


def test_headings_attach_to_body_without_merging_siblings(pilot):
    from evaluations.rag import chunk_batch

    records = [
        heading("title", ["Practice"]),
        heading("week", ["Practice", "Week 1"]),
        heading("empty", ["Practice", "Week 1", "Hitting"]),
        heading("bounce", ["Practice", "Week 1", "Bounce"]),
        {**block(1, "Bounce", "Bend."), "heading_path": ["Practice", "Week 1", "Bounce"]},
        heading("tail", ["Practice", "Week 1", "Next topic"]),
    ]
    payload = document(records)
    data = json.loads(payload)
    tokenizer = OfflineTokenizer()
    chunks = pilot.build_chunks(payload, tokenizer)
    chunk_batch.verify_chunks(data, chunks, tokenizer)
    assert len(chunks) == 1
    chunk, = chunks
    assert chunk["text"] == "Bend."
    assert chunk["embedding_text"] == "Practice\nWeek 1 > Bounce\n\nBend."
    assert chunk["token_count"] == 7
    assert chunk["heading_block_ids"] == ["heading-title", "heading-week", "heading-bounce"]

    outline = {node["block_id"]: node for node in pilot.article_structure(data)["headings"]}
    assert outline["heading-empty"]["body_block_ids"] == outline["heading-tail"]["body_block_ids"] == []
    assert outline["heading-bounce"]["body_block_ids"] == ["block-1"]
    assert outline["heading-bounce"]["parent_block_id"] == "heading-week"
    assert outline["heading-empty"]["raw_lines"] == [1, 1]
    assert pilot.build_chunks(document(records[:4]), tokenizer) == []


def test_article_coverage_and_repeatable_sentence_overlap(pilot):
    records = [
        block(1, "Groove", "Move on beat."),
        block(2, "Groove", "Repeat slowly."),
        block(3, "Groove", "Switch side."),
        block(4, "Balance", "Pause in place."),
    ]
    tokenizer = OfflineTokenizer()
    settings = {**pilot.SETTINGS, "max_tokens": 8, "max_overlap_tokens": 2}
    payload = document(records)
    chunks = pilot.build_chunks(payload, tokenizer, settings)

    assert chunks == pilot.build_chunks(payload, tokenizer, settings)
    assert len({chunk["chunk_id"] for chunk in chunks}) == 3
    assert [chunk["section_index"] for chunk in chunks] == [1, 1, 2]
    assert [chunk["overlap_tokens"] for chunk in chunks] == [0, 2, 0]
    assert chunks[1]["text"] == "Repeat slowly.\n\nSwitch side."
    assert chunks[1]["embedding_text"].startswith("Practice\nGroove\n\n")
    assert all(chunk["token_count"] <= 8 for chunk in chunks)


def test_overlong_article_uses_sentence_then_token_boundaries(pilot):
    paragraph = "One two. Three four five six seven eight. Nine ten."
    tokenizer = OfflineTokenizer()
    settings = {**pilot.SETTINGS, "max_tokens": 7, "max_overlap_tokens": 2}
    chunks = pilot.build_chunks(document([block(1, "Groove", paragraph)]), tokenizer, settings)
    assert len(chunks) >= 3
    assert chunks[0]["text"].strip() == "One two."
    assert "".join(chunk["text"][chunk["overlap_chars"]:] for chunk in chunks) == paragraph
    for chunk in chunks:
        for source in chunk["sources"]:
            start, end = source["block_range"]
            left, right = source["body_range"]
            assert chunk["text"][left:right] == paragraph[start:end]
        assert chunk["token_count"] <= 7


def subtitles(lines):
    cues, spans, retained, excluded = [], [], [], []
    original_offset = offset = 0
    for index, text in enumerate(lines, 1):
        cue_id = f"cue-{index}"
        cue = {"cue_id": cue_id, "plain_text": text, "raw_lines": [index, index]}
        cues.append(cue)
        span = {
            "text": text, "char_range": [original_offset, original_offset + len(text)],
            "sources": [{
                "cue_id": cue_id, "plain_range": [0, len(text)],
                "start_ms": index * 1000, "end_ms": index * 1000 + 800,
            }],
        }
        spans.append(span)
        original_offset += len(text) + 1
        if text == "[Music]":
            excluded.append(span)
        else:
            retained.append({**span, "char_range": [offset, offset + len(text)]})
            offset += len(text) + 1
    return cues, {
        "version": "3", "spans": spans,
        "chunking_input": {
            "text": " ".join(span["text"] for span in retained),
            "spans": retained, "excluded_markers": excluded,
        },
    }


def test_subtitle_overlap_and_split_cue_are_traceable(pilot):
    cues, transcript = subtitles(
        ["Step left", "[Music]", "Step right now", "Hold", "one two three four five six seven"]
    )
    settings = {**pilot.SETTINGS, "max_tokens": 7, "max_overlap_tokens": 3}
    chunks = pilot.build_chunks(document(cues, transcript), OfflineTokenizer(), settings)
    assert chunks[1]["text"] == "Step right now Hold "
    assert chunks[1]["overlap_tokens"] == 3
    assert chunks[1]["time_range_ms"] == [3000, 4800]
    assert "".join(
        chunk["text"][chunk["overlap_chars"]:] for chunk in chunks
    ) == transcript["chunking_input"]["text"]
    assert len(chunks) == 4
    for chunk in chunks:
        assert chunk["token_count"] <= 7
        assert chunk["new_body_range"][0] < chunk["new_body_range"][1]
        for source in chunk["sources"]:
            left, right = source["body_range"]
            for cue in source["cues"]:
                original = next(item for item in cues if item["cue_id"] == cue["cue_id"])
                start, end = cue["plain_range"]
                assert original["plain_text"][start:end] == chunk["text"][left:right]
                assert cue["raw_lines"] == original["raw_lines"]


def test_subtitles_reject_changed_v3_text(pilot):
    cues, transcript = subtitles(["Step left", "[Music]", "Step right"])
    transcript["chunking_input"]["text"] = "Step left Step wrong"
    with pytest.raises(ValueError, match="projection range"):
        pilot.build_chunks(document(cues, transcript), OfflineTokenizer())


def test_batch_loads_only_selected_verified_baseline(pilot, monkeypatch, tmp_path):
    import hashlib

    from evaluations.rag import chunk_batch

    source_id = "steezy-fixture"
    monkeypatch.setattr(chunk_batch, "SOURCE_IDS", (source_id,))
    baseline = tmp_path / "clean-v3-baseline"
    baseline.mkdir()
    data = json.loads(document([block(1, "Groove", "Hold the beat.")]))
    data["metadata"].update(doc_id=source_id, source_type="article")
    payload = json.dumps(data).encode()
    (tmp_path / "manifest.json").write_text(json.dumps([data["metadata"]]))
    (tmp_path / "validation-summary-v3-baseline.json").write_text(json.dumps([{
        "doc_id": source_id, "file": f"{source_id}.json", "validation_status": "passed",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }]))
    path = baseline / f"{source_id}.json"
    path.write_bytes(payload)
    (baseline / "temporary.json").write_text("not selected")

    assert list(chunk_batch.load_baseline(tmp_path)) == [(source_id, payload)]
    path.write_bytes(payload + b" ")
    with pytest.raises(ValueError, match="digest mismatch"):
        list(chunk_batch.load_baseline(tmp_path))


def test_batch_checks_coverage_and_source_pointers(pilot):
    from evaluations.rag import chunk_batch

    payload = document([block(1, "Groove", "Hold the beat.")])
    tokenizer = OfflineTokenizer()
    chunks = pilot.build_chunks(payload, tokenizer)
    chunk_batch.verify_chunks(json.loads(payload), chunks, tokenizer)
    assert chunk_batch.summarize(chunks)["overlap_tokens"] == [0]

    chunks[0]["sources"] = []
    with pytest.raises(ValueError, match="Missing source pointer"):
        chunk_batch.verify_chunks(json.loads(payload), chunks, tokenizer)
