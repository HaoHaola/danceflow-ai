"""Prepare DanceFlow AI corpus documents from local snapshots."""

import argparse
import hashlib
import json
import re
import sys
from html import unescape
from html.entities import html5
from pathlib import Path


CLEANING_VERSION = "1"
TRANSCRIPT_VERSION = "3"
ROLLING_TRANSITION_MS = 10
HEADING = re.compile(r"^(#{1,6}) +(.+)$")
TIMESTAMP = r"(?:(?:[0-9]{2,}):)?[0-5][0-9]:[0-5][0-9]\.[0-9]{3}"
TIMING = re.compile(rf"({TIMESTAMP})[ \t]+-->[ \t]+({TIMESTAMP})")
YOUTUBE_TIMING = re.compile(rf"{TIMING.pattern}[ \t]+(align:start position:0%)")
YOUTUBE_INLINE = re.compile(rf"<({TIMESTAMP})><c>([^<>]*)</c>")
YOUTUBE_HEADER = ["WEBVTT", "Kind: captions", "Language: en", ""]
CUE_ID = re.compile(r"[A-Za-z0-9_-]+")
CUE_ENTITY = re.compile(r"&(#(?:[xX][0-9a-fA-F]+|[0-9]+)|[A-Za-z][A-Za-z0-9]*);")
CUE_HINT = re.compile(r"\[[^\[\]]+\]")
CHUNKING_EXCLUDED_HINTS = {"[Music]", "[Applause]"}


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def source_lines(content, path):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path}: invalid UTF-8 at byte {error.start + 1}") from error
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def blocks(lines, start=0, preserve_blank_payload=False):
    block = []
    for number, original in enumerate(lines[start:], start + 1):
        line = original.rstrip(" \t")
        if line or (preserve_blank_payload and original):
            block.append((number, line))
        elif block:
            yield block
            block = []
    if block:
        yield block


def clean_article(lines):
    headings = []
    records = []
    paragraph = []

    def add_record(kind, block):
        records.append({
            "block_id": f"block-{len(records) + 1}",
            "kind": kind,
            "heading_path": [title for _, title in headings],
            "raw_lines": [block[0][0], block[-1][0]],
            "text": "\n".join(line for _, line in block),
        })

    for number, original in enumerate(lines, 1):
        line = original.rstrip(" \t")
        heading = HEADING.fullmatch(line)
        if paragraph and (not line or heading):
            add_record("paragraph", paragraph)
            paragraph = []
        if heading:
            level = len(heading[1])
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading[2]))
            add_record("heading", [(number, line)])
        elif line:
            paragraph.append((number, line))
    if paragraph:
        add_record("paragraph", paragraph)
    return records


def milliseconds(timestamp):
    clock, fraction = timestamp.split(".")
    seconds = 0
    for part in clock.split(":"):
        seconds = seconds * 60 + int(part)
    return seconds * 1000 + int(fraction)


def plain_cue_line(line, path, number, youtube, start, end):
    matches = list(YOUTUBE_INLINE.finditer(line)) if youtube else []
    times = [milliseconds(match[1]) for match in matches]
    if times != sorted(set(times)) or any(not start < time < end for time in times):
        raise ValueError(f"{path}:{number}: invalid inline timestamp")
    plain = YOUTUBE_INLINE.sub(r"\2", line) if youtube else line
    if "-->" in line or "<" in plain or ">" in plain:
        raise ValueError(f"{path}:{number}: unsupported cue text syntax")

    def decode(match):
        entity = match[1]
        if not entity.startswith("#") and entity + ";" not in html5:
            raise ValueError(f"{path}:{number}: unsupported cue entity {match[0]}")
        decoded = unescape(match[0])
        if not decoded or decoded == "\ufffd":
            raise ValueError(f"{path}:{number}: invalid cue entity {match[0]}")
        return decoded

    # Compare the time tags with the words they introduce, including their order.
    timed_words = tuple((time, " ".join(match[2].split())) for time, match in zip(times, matches))
    return " ".join(CUE_ENTITY.sub(decode, plain).split()), timed_words


def clean_transcript(lines, path, youtube=False):
    if lines[0] != "WEBVTT":
        raise ValueError(f"{path}:1: expected a bare WEBVTT header")
    if not youtube and (len(lines) < 2 or lines[1].strip()):
        raise ValueError(f"{path}:2: expected a blank line after WEBVTT")
    records = []
    display_lines = []
    previous_start = -1
    for block in blocks(lines, start=len(YOUTUBE_HEADER) if youtube else 2, preserve_blank_payload=youtube):
        first_line, first_text = block[0]
        if first_text and first_text.split(maxsplit=1)[0] in {"NOTE", "STYLE", "REGION"}:
            raise ValueError(f"{path}:{first_line}: unsupported WebVTT block")
        identifier = None
        timing_index = 0
        if CUE_ID.fullmatch(first_text):
            identifier = first_text
            timing_index = 1
        if timing_index >= len(block):
            raise ValueError(f"{path}:{first_line}: missing cue timing")
        timing_line, timing_text = block[timing_index]
        timing = (YOUTUBE_TIMING if youtube else TIMING).fullmatch(timing_text)
        if not timing:
            raise ValueError(f"{path}:{timing_line}: invalid or unsupported cue timing")
        start, end = map(milliseconds, timing.groups()[:2])
        if start >= end or start < previous_start:
            raise ValueError(f"{path}:{timing_line}: invalid cue interval or start order")
        payload = block[timing_index + 1:]
        if not payload:
            raise ValueError(f"{path}:{timing_line}: cue has no text")
        plain_lines = [plain_cue_line(line, path, number, youtube, start, end) for number, line in payload]
        plain_lines = [(line, times) for line, times in plain_lines if line]
        display_lines.append(plain_lines)
        records.append({
            "cue_id": f"cue-{len(records) + 1}",
            "source_cue_id": identifier,
            "start_ms": start,
            "end_ms": end,
            "raw_lines": [first_line, payload[-1][0]],
            "text": "\n".join(line for _, line in payload),
            "plain_text": " ".join(line for line, _ in plain_lines),
        })
        if youtube:
            records[-1]["cue_settings"] = timing[3]
        previous_start = start
    if records and not any(record["plain_text"] for record in records):
        raise ValueError(f"{path}: no content after cleaning")
    return records, display_lines


def rolling_reason(previous, current, prior_times, current_times):
    if prior_times and prior_times == current_times:
        return "same_word_timestamps"
    if not prior_times or current_times or previous["end_ms"] != current["start_ms"]:
        return None
    if current["end_ms"] - current["start_ms"] <= ROLLING_TRANSITION_MS:
        return "timed_line_to_short_transition"
    if previous["end_ms"] - previous["start_ms"] <= ROLLING_TRANSITION_MS:
        return "timed_line_carried_through_short_transition"
    return None


def merge_transcript(records, display_lines):
    segments = []
    removals = []
    doubts = []
    previous_lines = []
    for index, (cue, lines) in enumerate(zip(records, display_lines)):
        previous = records[index - 1] if index else None
        current_lines = []
        plain_offset = 0
        for text, times in lines:
            end = plain_offset + len(text)
            current_lines.append((text, times, {
                "cue_id": cue["cue_id"], "plain_range": [plain_offset, end],
                "start_ms": cue["start_ms"], "end_ms": cue["end_ms"],
            }))
            plain_offset = end + 1

        matched = 0
        if previous_lines and current_lines and cue["start_ms"] <= previous["end_ms"]:
            # Remove only whole-line copies, in adjacent suffix/prefix order.
            for count in range(min(len(previous_lines), len(current_lines)), 0, -1):
                if [item[0] for item in previous_lines[-count:]] == [item[0] for item in current_lines[:count]]:
                    matched = count
                    break

        mapped_lines = []
        for line_index, (text, times, source) in enumerate(current_lines):
            if line_index < matched:
                _, prior_times, prior_source, segment = previous_lines[-matched + line_index]
                reason = rolling_reason(previous, cue, prior_times, times)
                if (
                    reason is None
                    and len(current_lines) == 1
                    and previous["end_ms"] == cue["start_ms"]
                    and cue["end_ms"] - cue["start_ms"] == ROLLING_TRANSITION_MS
                    and not times
                    and not CUE_HINT.fullmatch(text)
                ):
                    reason = "single_line_exact_10ms_transition"
                if (
                    reason is None
                    and line_index == 0
                    and len(current_lines) == 2
                    and not times
                    and current_lines[1][1]
                    and previous["end_ms"] == cue["start_ms"]
                    and removals
                    and removals[-1]["reason"] == "single_line_exact_10ms_transition"
                    and removals[-1]["removed"] == prior_source
                ):
                    reason = "single_line_carried_through_10ms_transition"
                if reason:
                    segment["sources"].append(source)
                    removals.append({
                        "previous": prior_source, "removed": source, "reason": reason,
                        "retained": segment["sources"][0], "text": text,
                    })
                    mapped_lines.append((text, prior_times, source, segment))
                    continue
                if not (times and prior_times and times != prior_times):
                    doubts.append({
                        "previous": prior_source, "current": source,
                        "reason": "matching_line_without_sufficient_timing_evidence",
                    })
            segment = {"text": text, "sources": [source]}
            segments.append(segment)
            mapped_lines.append((text, times, source, segment))

        if not matched and previous_lines and current_lines and cue["start_ms"] <= previous["end_ms"]:
            prior_text, _, prior_source, _ = previous_lines[-1]
            text, _, source = current_lines[0]
            prior_words, words = prior_text.split(), text.split()
            if any(prior_words[-count:] == words[:count] for count in range(1, min(len(prior_words), len(words)) + 1)):
                doubts.append({"previous": prior_source, "current": source, "reason": "partial_line_overlap"})
        previous_lines = mapped_lines

    offset = 0
    for segment in segments:
        text = segment["text"]
        sources = segment["sources"]
        segment.update(
            char_range=[offset, offset + len(text)],
            start_ms=min(source["start_ms"] for source in sources),
            end_ms=max(source["end_ms"] for source in sources),
            kind="hint" if CUE_HINT.fullmatch(text) else "speech",
        )
        offset += len(text) + 1
    merged = " ".join(segment["text"] for segment in segments)
    chunking_spans = []
    excluded = []
    chunking_offset = 0
    for segment in segments:
        if segment["text"] in CHUNKING_EXCLUDED_HINTS:
            excluded.append(segment)
            continue
        end = chunking_offset + len(segment["text"])
        chunking_spans.append({**segment, "char_range": [chunking_offset, end]})
        chunking_offset = end + 1
    before = " ".join(cue["plain_text"] for cue in records if cue["plain_text"])
    return {
        "version": TRANSCRIPT_VERSION, "text": merged, "spans": segments,
        "removals": removals, "doubts": doubts,
        "chunking_input": {
            "text": " ".join(span["text"] for span in chunking_spans),
            "spans": chunking_spans,
            "excluded_markers": excluded,
        },
        "stats": {
            "cues": len(records), "plain_chars": len(before), "merged_chars": len(merged),
            "removed_chars": len(before) - len(merged), "removed_lines": len(removals),
            "doubts": len(doubts),
        },
    }


def validate_metadata(document, location):
    synthetic = document.get("synthetic")
    eligible = document.get("eligible_for_rag_quality_evaluation")
    if type(synthetic) is not bool or type(eligible) is not bool:
        raise ValueError(f"{location}: synthetic and evaluation eligibility must be boolean")
    if synthetic and eligible:
        raise ValueError(f"{location}: synthetic data must be excluded from RAG quality evaluation")

    for key in ("title", "publisher", "language", "acquisition_method", "source_version", "usage_terms"):
        if not isinstance(document.get(key), str) or not document[key].strip():
            raise ValueError(f"{location}: missing or invalid {key}")
    creator = document.get("creator")
    if not isinstance(creator, dict) or any(
        not isinstance(creator.get(key), str) or not creator[key].strip()
        for key in ("name", "role")
    ):
        raise ValueError(f"{location}: missing or invalid creator")
    if not synthetic:
        for key in ("source_url", "acquired_on", "usage_evidence_url", "acquisition_tool"):
            if not isinstance(document.get(key), str) or not document[key].strip():
                raise ValueError(f"{location}: missing or invalid {key}")
        if document.get("source_type") == "transcript":
            if document.get("caption_type") not in ("manual", "automatic", "unknown"):
                raise ValueError(f"{location}: invalid caption_type")
            if type(document.get("caption_is_translation")) is not bool and document.get(
                "caption_is_translation"
            ) != "unknown":
                raise ValueError(f"{location}: invalid caption_is_translation")
    status = document.get("review_status", "pending")
    method = document.get("review_method")
    if status not in ("pending", "reviewed", "needs_review"):
        raise ValueError(f"{location}: invalid review_status")
    if status == "reviewed" and method not in ("manual_full", "manual_sample"):
        raise ValueError(f"{location}: reviewed content requires a manual review_method")


def read_snapshot(corpus_dir, name, digest, location, label):
    if not isinstance(name, str) or Path(name).is_absolute():
        raise ValueError(f"{location}: expected a relative {label}_path")
    path = (corpus_dir / name).resolve()
    if not path.is_relative_to(corpus_dir / "raw"):
        raise ValueError(f"{location}: {label}_path must resolve inside raw/")
    content = path.read_bytes()
    if sha256(content) != digest:
        raise ValueError(f"{path}: {label} SHA-256 mismatch")
    return path, content


def review_fingerprint(document, cleaning_version=CLEANING_VERSION):
    inputs = {
        key: document.get(key) for key in (
            "source_type", "source_url", "source_version", "raw_sha256",
            "original_sha256", "acquisition_method", "acquisition_tool",
            "extraction_method", "extraction_boundary",
        )
    }
    inputs["cleaning_version"] = cleaning_version
    if document.get("source_type") == "transcript":
        inputs["transcript_version"] = TRANSCRIPT_VERSION
    return sha256(json.dumps(inputs, sort_keys=True).encode("utf-8"))


def content_changes(source_type, lines, records, cue_start=2):
    normalized = [line.rstrip(" \t") for line in lines]
    if source_type == "article":
        expected = [line for line in normalized if line]
    else:
        expected = []
        for block in blocks(lines, start=cue_start, preserve_blank_payload=cue_start != 2):
            timing_index = int(CUE_ID.fullmatch(block[0][1]) is not None)
            expected.extend(line for _, line in block[timing_index + 1:])
    actual = [line for record in records for line in record["text"].split("\n")]
    matches = True
    for record in records:
        start, end = record["raw_lines"]
        payload = record["text"].split("\n")
        source = normalized[start - 1:end]
        if source_type == "transcript":
            timing_index = int(record["source_cue_id"] is not None)
            source = source[timing_index + 1:]
        if not (1 <= start <= end <= len(lines)) or source != payload:
            matches = False
    return {
        "input_text_lines": len(expected),
        "output_text_lines": len(actual),
        "trailing_whitespace_lines": sum(a != b for a, b in zip(lines, normalized)),
        "text_matches_normalized_source": matches and expected == actual,
    }


def prepare_corpus(manifest_path, output_dir):
    documents = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(documents, list) or not documents:
        raise ValueError(f"{manifest_path}: expected a nonempty document list")

    corpus_dir = manifest_path.parent.resolve()
    prepared = {}
    source_paths = {manifest_path.resolve()}
    for index, document in enumerate(documents, 1):
        location = f"{manifest_path}: document {index}"
        if not isinstance(document, dict):
            raise ValueError(f"{location}: expected an object")
        doc_id = document.get("doc_id")
        if not isinstance(doc_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", doc_id):
            raise ValueError(f"{location}: invalid doc_id")
        if doc_id in prepared:
            raise ValueError(f"{location}: duplicate doc_id {doc_id}")
        validate_metadata(document, location)
        source_type = document.get("source_type")
        if source_type not in ("article", "transcript"):
            raise ValueError(f"{location}: invalid source_type")
        path, content = read_snapshot(
            corpus_dir, document.get("raw_path"), document.get("raw_sha256"), location, "raw"
        )
        source_paths.add(path)
        real_article = source_type == "article" and not document["synthetic"]
        if real_article:
            for key in ("extraction_method", "extraction_boundary"):
                if not isinstance(document.get(key), str) or not document[key].strip():
                    raise ValueError(f"{location}: missing or invalid {key}")
        if real_article or "original_path" in document or "original_sha256" in document:
            original, _ = read_snapshot(
                corpus_dir, document.get("original_path"), document.get("original_sha256"),
                location, "original",
            )
            source_paths.add(original)
        lines = source_lines(content, path)
        youtube = source_type == "transcript" and lines[:len(YOUTUBE_HEADER)] == YOUTUBE_HEADER
        cleaning_version = "2" if youtube else CLEANING_VERSION
        if source_type == "article":
            records = clean_article(lines)
        else:
            records, display_lines = clean_transcript(lines, path, youtube=youtube)
        if not records:
            raise ValueError(f"{path}: no content after cleaning")
        changes = content_changes(source_type, lines, records, cue_start=len(YOUTUBE_HEADER) if youtube else 2)
        changes["utf8_bom_removed"] = content.startswith(b"\xef\xbb\xbf")
        changes["newline_sequences_normalized"] = content.count(b"\r")
        fingerprint = review_fingerprint(document, cleaning_version)
        metadata = dict(document)
        metadata["validation_status"] = "passed" if changes["text_matches_normalized_source"] else "needs_review"
        metadata["review_fingerprint"] = fingerprint
        if not changes["text_matches_normalized_source"]:
            metadata.update(review_status="needs_review", review_method=None)
        elif document.get("review_fingerprint") != fingerprint:
            metadata.update(review_status="pending", review_method=None)
        else:
            metadata.setdefault("review_status", "pending")
            metadata.setdefault("review_method", None)
        output = {"metadata": metadata, "cleaning_version": cleaning_version, "records": records}
        if source_type == "transcript":
            output["transcript"] = merge_transcript(records, display_lines)
        if youtube:
            output["vtt_header"] = lines[:len(YOUTUBE_HEADER) - 1]
        prepared[doc_id] = (output, changes)

    outputs = {doc_id: output_dir / f"{doc_id}.json" for doc_id in prepared}
    for path in outputs.values():
        if path.resolve() in source_paths:
            raise ValueError(f"{path}: output would overwrite an input")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for doc_id, (output, changes) in prepared.items():
        content = (json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        path = outputs[doc_id]
        path.write_bytes(content)
        summary.append({
            "doc_id": doc_id, "file": path.name, "records": len(output["records"]), "sha256": sha256(content),
            "validation_status": output["metadata"]["validation_status"], "content_changes": changes,
        })
        if "transcript" in output:
            summary[-1]["transcript_stats"] = output["transcript"]["stats"]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = prepare_corpus(args.manifest, args.output_dir)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
