"""Build traceable chunks from the two Week 2.2 pilot inputs."""

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .smoke_embedding import MODEL_ID, REVISION
else:
    from smoke_embedding import MODEL_ID, REVISION


PILOT_SOURCES = ("steezy-how-to-execute-movement", "youtube-hip-hop-bounce")
SETTINGS = {
    "version": "week2.2-pilot-1",
    "tokenizer": MODEL_ID,
    "revision": REVISION,
    "max_tokens": 512,
    "max_overlap_tokens": 64,
    "embedding_prefix": "title, optional subsection path, then blank line",
    "embedding_outer_whitespace": "strip",
    "article_boundaries": "section, block, sentence, token",
    "subtitle_boundaries": "retained cue, token",
}
SENTENCE_END = re.compile(r"""[.!?。！？]+["'”’)]*\s+""")


@dataclass
class Section:
    heading: tuple[str, ...]
    text: str
    units: list[tuple[int, int]]
    origins: list[dict]
    is_article: bool
    heading_block_ids: tuple[str, ...] = ()


def article_layout(records):
    """Keep source headings in an outline and group only body blocks for embedding."""
    headings, sections, stack = [], [], []
    for block in records:
        path = block["heading_path"]
        if block["kind"] == "heading":
            depth = len(path)
            if not 1 <= depth <= len(stack) + 1 or path[:-1] != [
                node["heading_path"][-1] for node in stack[:depth - 1]
            ]:
                raise ValueError("Invalid article heading hierarchy")
            del stack[depth - 1:]
            node = {
                **block,
                "parent_block_id": stack[-1]["block_id"] if stack else None,
                "body_block_ids": [],
            }
            stack.append(node)
            headings.append(node)
            continue
        if path != [node["heading_path"][-1] for node in stack]:
            raise ValueError("Article body heading path does not match its source headings")
        heading_ids = tuple(node["block_id"] for node in stack)
        if not sections or sections[-1][1] != heading_ids:
            sections.append((tuple(path), heading_ids, []))
        sections[-1][2].append(block)
        if stack:
            stack[-1]["body_block_ids"].append(block["block_id"])
    return headings, sections


def article_structure(document):
    headings, _ = article_layout(document["records"])
    metadata = document["metadata"]
    return {
        "source_id": metadata["doc_id"],
        "source_url": metadata["source_url"],
        "cleaning_version": document["cleaning_version"],
        "headings": headings,
    }


def article_sections(records):
    _, layout = article_layout(records)
    for heading, heading_ids, blocks in layout:
        parts, origins, units = [], [], []
        start = 0
        for index, block in enumerate(blocks):
            body = block["text"]
            end = start + len(body)
            separator = "\n\n" if index < len(blocks) - 1 else ""
            parts.append(body + separator)
            origins.append({
                "range": [start, end],
                **{key: block[key] for key in ("block_id", "kind", "raw_lines")},
            })
            units.append((start, end + len(separator)))
            start = units[-1][1]
        yield Section(heading, "".join(parts), units, origins, True, heading_ids)


def subtitle_section(records, transcript):
    if transcript["version"] != "3":
        raise ValueError("The subtitle pilot requires transcript v3")
    inputs = transcript["chunking_input"]
    text = inputs["text"]
    markers = {"[Music]", "[Applause]"}
    retained = [span for span in transcript["spans"] if span["text"] not in markers]
    if inputs["excluded_markers"] != [span for span in transcript["spans"] if span["text"] in markers]:
        raise ValueError("Unexpected excluded subtitle markers")
    if [item["text"] for item in retained] != [span["text"] for span in inputs["spans"]]:
        raise ValueError("Subtitle input differs from the retained v3 text")
    cues = {cue["cue_id"]: cue for cue in records}
    spans = inputs["spans"]
    origins, units = [], []
    cursor = 0
    for index, span in enumerate(spans):
        start, end = span["char_range"]
        sources = [
            {**source, "raw_lines": cues[source["cue_id"]]["raw_lines"]}
            for source in span["sources"]
        ]
        if start != cursor or text[start:end] != span["text"]:
            raise ValueError("Invalid subtitle projection range")
        if {**span, "char_range": retained[index]["char_range"]} != retained[index]:
            raise ValueError("Subtitle projection differs from v3 source mapping")
        for source in sources:
            left, right = source["plain_range"]
            if cues[source["cue_id"]]["plain_text"][left:right] != span["text"]:
                raise ValueError("Subtitle cue text does not match the retained span")
        origins.append({"range": [start, end], "cues": sources})
        if index + 1 < len(spans):
            if text[end:end + 1] != " ":
                raise ValueError("Unexpected subtitle span separator")
            cursor = end + 1
        else:
            cursor = end
        anchor = sources[0]["cue_id"]
        if index and anchor == origins[-2]["cues"][0]["cue_id"]:
            units[-1] = (units[-1][0], cursor)
        else:
            units.append((start, cursor))
    if cursor != len(text):
        raise ValueError("Subtitle span coverage is incomplete")
    return Section((), text, units, origins, False)


def token_count(tokenizer, text, *, special=True):
    return len(tokenizer(text, add_special_tokens=special, truncation=False)["input_ids"])


def token_pieces(text, start, end, fits, tokenizer):
    """Use tokenizer offsets to split original characters without decode/rewrite."""
    offsets = tokenizer(
        text[start:end], add_special_tokens=False, truncation=False,
        return_offsets_mapping=True,
    )["offset_mapping"]
    boundaries = sorted({start + right for _, right in offsets if right > 0} | {end})
    while start < end:
        cut = start
        for boundary in boundaries:
            if boundary <= start:
                continue
            if not fits(start, boundary):
                break
            cut = boundary
        if cut == start:
            raise ValueError("A token boundary cannot fit with the embedding prefix")
        yield start, cut
        start = cut


def fit_units(section, fits, tokenizer):
    for start, end in section.units:
        if fits(start, end):
            yield start, end
            continue
        boundaries = [start]
        if section.is_article:
            boundaries.extend(match.end() for match in SENTENCE_END.finditer(section.text, start, end))
        if boundaries[-1] != end:
            boundaries.append(end)
        for left, right in zip(boundaries, boundaries[1:]):
            if fits(left, right):
                yield left, right
            else:
                yield from token_pieces(section.text, left, right, fits, tokenizer)


def select_overlap(section, start, end, next_end, fits, tokenizer, overlap_limit):
    if section.is_article:
        candidates = {left for left, _ in section.units if start <= left < end}
        candidates.update(match.end() for match in SENTENCE_END.finditer(section.text, start, end))
        # A token fallback may leave an incomplete sentence at either edge.
        boundaries = {right for _, right in section.units}
        boundaries.update(match.end() for match in SENTENCE_END.finditer(section.text))
        if end not in boundaries:
            return end
    else:
        if end not in {right for _, right in section.units}:
            return end
        candidates = {left for left, _ in section.units if start <= left < end}
    for left in sorted(candidates):
        if left < end and token_count(tokenizer, section.text[left:end], special=False) <= overlap_limit:
            if fits(left, next_end):
                return left
    return end


def source_slices(section, start, end):
    slices = []
    for origin in section.origins:
        origin_start, origin_end = origin["range"]
        left, right = max(start, origin_start), min(end, origin_end)
        if left >= right:
            continue
        local_start, local_end = left - origin_start, right - origin_start
        item = {
            "body_range": [left - start, right - start],
            "source_text_range": [left, right],
        }
        if section.is_article:
            item.update(
                block_id=origin["block_id"], kind=origin["kind"], raw_lines=origin["raw_lines"],
                block_range=[local_start, local_end],
            )
        else:
            item["cues"] = [
                {
                    **cue,
                    "plain_range": [
                        cue["plain_range"][0] + local_start,
                        cue["plain_range"][0] + local_end,
                    ],
                }
                for cue in origin["cues"]
            ]
        slices.append(item)
    return slices


def chunk_section(section, prefix, tokenizer, settings):
    def embedding_text_for(start, end):
        # SentenceTransformers strips input strings before tokenizing documents.
        return (prefix + section.text[start:end]).strip()

    def fits(start, end):
        return token_count(tokenizer, embedding_text_for(start, end)) <= settings["max_tokens"]

    units = list(fit_units(section, fits, tokenizer))
    index = 0
    chunk_start = 0
    while index < len(units):
        new_start, end = units[index]
        index += 1
        while index < len(units) and fits(chunk_start, units[index][1]):
            end = units[index][1]
            index += 1
        body = section.text[chunk_start:end]
        embedding_text = embedding_text_for(chunk_start, end)
        count = token_count(tokenizer, embedding_text)
        if not body.strip() or new_start >= end or count > settings["max_tokens"]:
            raise ValueError("Invalid chunk body or token count")
        sources = source_slices(section, chunk_start, end)
        overlap_chars = new_start - chunk_start
        result = {
            "text": body,
            "embedding_text": embedding_text,
            "token_count": count,
            "source_text_range": [chunk_start, end],
            "new_body_range": [overlap_chars, len(body)],
            "overlap_chars": overlap_chars,
            "overlap_tokens": token_count(tokenizer, body[:overlap_chars], special=False)
            if overlap_chars else 0,
            "sources": sources,
        }
        if not section.is_article:
            cues = [cue for source in sources for cue in source["cues"]]
            result["time_range_ms"] = [
                min(cue["start_ms"] for cue in cues), max(cue["end_ms"] for cue in cues),
            ]
        yield result
        if index < len(units):
            chunk_start = select_overlap(
                section, new_start, end, units[index][1], fits, tokenizer,
                settings["max_overlap_tokens"],
            )


def build_chunks(payload, tokenizer, settings=SETTINGS):
    document = json.loads(payload)
    metadata = document["metadata"]
    transcript = document.get("transcript")
    if transcript is None:
        settings = {
            **settings,
            "version": "week2.2-article-headings-2",
            "article_heading_policy": "body only; heading path in embedding prefix",
        }
    sections = (
        [subtitle_section(document["records"], transcript)] if transcript is not None
        else article_sections(document["records"])
    )
    source_id, title = metadata["doc_id"], metadata["title"]
    digest = hashlib.sha256(payload).hexdigest()
    identity = hashlib.sha256(json.dumps([digest, settings], sort_keys=True).encode()).hexdigest()
    chunks = []
    for section_index, section in enumerate(sections, 1):
        heading = section.heading
        subsections = heading[1:] if heading and heading[0] == title else heading
        prefix = "\n".join((title, " > ".join(subsections))) if subsections else title
        new_text = []
        for chunk in chunk_section(section, prefix + "\n\n", tokenizer, settings):
            new_text.append(chunk["text"][chunk["overlap_chars"]:])
            chunks.append({
                "chunk_id": f"{source_id}:{identity[:16]}:{len(chunks) + 1:04d}",
                "source_id": source_id,
                "source_url": metadata["source_url"],
                "title": title,
                "cleaning_version": document["cleaning_version"],
                "transcript_version": transcript["version"] if transcript is not None else None,
                "input_sha256": digest,
                "raw_sha256": metadata["raw_sha256"],
                "chunking_settings": settings,
                "section_index": section_index,
                "heading_path": list(heading),
                **({"heading_block_ids": list(section.heading_block_ids)} if section.is_article else {}),
                **chunk,
            })
        if "".join(new_text) != section.text:
            raise ValueError("Chunk coverage differs from the cleaned input")
    if not chunks and transcript is not None:
        raise ValueError(f"No chunks for {source_id}")
    return chunks


def main():
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.input_dir.resolve() == args.output_dir.resolve():
        parser.error("--output-dir must be separate from --input-dir")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, local_files_only=True)
    if not tokenizer.is_fast:
        raise ValueError("The pilot requires tokenizer character offsets")
    inputs = {
        source: (args.input_dir / f"{source}.json").read_bytes()
        for source in PILOT_SOURCES
    }
    results = {source: build_chunks(payload, tokenizer) for source, payload in inputs.items()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source, chunks in results.items():
        output = args.output_dir / f"{source}.json"
        output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        document = json.loads(inputs[source])
        if "transcript" not in document:
            save_article_structure(args.output_dir, source, article_structure(document))
        print(f"{source}: {[chunk['token_count'] for chunk in chunks]}")


def save_article_structure(output_dir, source_id, structure):
    directory = output_dir / "article-structure"
    path = directory / f"{source_id}.json"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("Refusing to write article structure through a symlink")
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
