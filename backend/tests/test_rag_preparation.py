import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


RAG_DIR = Path(__file__).resolve().parents[2] / "evaluations" / "rag"


@pytest.fixture
def corpus(tmp_path):
    return shutil.copytree(RAG_DIR / "corpus", tmp_path / "corpus")


def run_preparation(corpus, output):
    return subprocess.run(
        [
            sys.executable, str(RAG_DIR / "prepare_corpus.py"),
            "--manifest", str(corpus / "manifest.json"), "--output-dir", str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def save_manifest(corpus, documents):
    (corpus / "manifest.json").write_text(json.dumps(documents), encoding="utf-8")


def replace_raw(corpus, doc_id, content):
    documents = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    document = next(item for item in documents if item["doc_id"] == doc_id)
    (corpus / document["raw_path"]).write_bytes(content)
    document["raw_sha256"] = hashlib.sha256(content).hexdigest()
    save_manifest(corpus, documents)


def test_prepare_corpus_is_reproducible_and_traceable(corpus, tmp_path):
    before = {path: path.read_bytes() for path in corpus.rglob("*") if path.is_file()}
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run_preparation(corpus, first_dir)
    second = run_preparation(corpus, second_dir)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert len(json.loads(first.stdout)) == 2

    for entry in json.loads(first.stdout):
        output = (first_dir / entry["file"]).read_bytes()
        assert output == (second_dir / entry["file"]).read_bytes()
        assert hashlib.sha256(output).hexdigest() == entry["sha256"]
        cleaned = json.loads(output)
        metadata = cleaned["metadata"]
        assert metadata["synthetic"] is True
        assert metadata["eligible_for_rag_quality_evaluation"] is False
        assert cleaned["cleaning_version"] == "1"
        assert "sha256" not in cleaned
        assert metadata["raw_sha256"] == hashlib.sha256(before[corpus / metadata["raw_path"]]).hexdigest()
        assert entry["records"] == len(cleaned["records"])
        assert entry["validation_status"] == metadata["validation_status"] == "passed"
        assert entry["content_changes"]["text_matches_normalized_source"] is True

    article_output = json.loads((first_dir / "synthetic-groove.json").read_bytes())
    assert article_output["metadata"]["review_status"] == "reviewed"
    assert article_output["metadata"]["review_method"] == "manual_full"
    article = article_output["records"]
    assert article[2] == {
        "block_id": "block-3",
        "kind": "paragraph",
        "heading_path": ["Synthetic Groove Practice", "Weight Shift"],
        "raw_lines": [5, 5],
        "text": "Shift your weight slowly on counts 1 and 3.",
    }
    assert article[-1]["text"] == "- Keep the movement small.\n- Repeat for two eight-counts."
    transcript = json.loads((first_dir / "synthetic-counts.json").read_bytes())["records"]
    assert transcript[0] == {
        "cue_id": "cue-1", "source_cue_id": "intro", "start_ms": 0, "end_ms": 2000,
        "raw_lines": [3, 6], "text": "[Music]\nCount 5, 6, 7, 8.",
        "plain_text": "[Music] Count 5, 6, 7, 8.",
    }
    assert [(cue["start_ms"], cue["end_ms"]) for cue in transcript] == [
        (0, 2000), (1500, 3000), (3000, 4000),
    ]
    assert transcript[1]["text"] == transcript[2]["text"] == "Count 5, 6, 7, 8."
    assert {path: path.read_bytes() for path in before} == before


def test_normalizes_whitespace_without_losing_source_locations(corpus, tmp_path):
    replace_raw(corpus, "synthetic-groove", b"\xef\xbb\xbf# Heading \r\n \t\r\nCount 1, 2. \t\r\n")
    result = run_preparation(corpus, tmp_path / "clean")
    assert result.returncode == 0
    cleaned = json.loads((tmp_path / "clean" / "synthetic-groove.json").read_bytes())
    assert cleaned["metadata"]["review_status"] == "pending"
    assert cleaned["metadata"]["review_method"] is None
    records = cleaned["records"]
    assert [(record["raw_lines"], record["text"]) for record in records] == [
        ([1, 1], "# Heading"), ([3, 3], "Count 1, 2."),
    ]


@pytest.mark.parametrize("index", [0, 1])
def test_accepts_real_metadata_without_awarding_review_or_eligibility(corpus, tmp_path, index):
    documents = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    document = documents[index]
    # Exercise real-document metadata with the existing self-authored bytes.
    document.update(
        synthetic=False,
        source_url="https://example.invalid/lesson",
        acquired_on="2026-11-21",
        usage_evidence_url="unknown",
        acquisition_tool="offline test fixture",
        validation_status="not_run",
    )
    if index == 1:
        document.update(caption_type="manual", caption_is_translation=False)
    else:
        document.update(
            original_path=document["raw_path"],
            original_sha256=document["raw_sha256"],
            extraction_method="identity for offline test",
            extraction_boundary="whole fixture",
        )
    save_manifest(corpus, [document])
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    metadata = json.loads((output / f"{document['doc_id']}.json").read_bytes())["metadata"]
    assert metadata["synthetic"] is False
    assert metadata["eligible_for_rag_quality_evaluation"] is False
    assert metadata["validation_status"] == "passed"
    assert metadata["review_status"] == "pending"
    assert metadata["review_method"] is None


def test_original_snapshot_hash_is_checked(corpus, tmp_path):
    documents = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    original = corpus / "raw" / "original.html"
    original.write_bytes(b"<p>Original snapshot</p>")
    documents[0].update(
        original_path="raw/original.html",
        original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
    )
    save_manifest(corpus, documents)
    assert run_preparation(corpus, tmp_path / "first").returncode == 0
    original.write_bytes(b"<p>Modified snapshot</p>")
    result = run_preparation(corpus, tmp_path / "second")
    assert result.returncode == 1
    assert "original SHA-256 mismatch" in result.stderr


@pytest.mark.parametrize(("change", "message"), [
    ("missing", "synthetic-groove.md"),
    ("duplicate", "duplicate doc_id synthetic-groove"),
    ("checksum", "raw SHA-256 mismatch"),
    ("eligibility", "excluded from RAG quality evaluation"),
    ("metadata", "missing or invalid title"),
    ("review", "requires a manual review_method"),
    ("empty", "no content after cleaning"),
])
def test_reports_input_validation_errors(corpus, tmp_path, change, message):
    documents = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    raw = corpus / documents[0]["raw_path"]
    if change == "missing":
        raw.unlink()
    elif change == "duplicate":
        save_manifest(corpus, [*documents, documents[0]])
    elif change == "checksum":
        raw.write_bytes(b"changed")
    elif change == "eligibility":
        documents[0]["eligible_for_rag_quality_evaluation"] = True
        save_manifest(corpus, documents)
    elif change == "metadata":
        documents[0].pop("title")
        save_manifest(corpus, documents)
    elif change == "review":
        documents[0]["review_method"] = "automatic"
        save_manifest(corpus, documents)
    else:
        replace_raw(corpus, documents[0]["doc_id"], b" \n")
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 1
    assert message in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(("cue", "line", "message"), [
    ("00:01.000 --> 00:00.000\nCount.", 3, "invalid cue interval"),
    ("00:00.000 --> 00:02.000 line:10%\nCount.", 3, "unsupported cue timing"),
    ("NOTE this is a comment", 3, "unsupported WebVTT block"),
    ("STYLE\n::cue { color: red; }", 3, "unsupported WebVTT block"),
    ("REGION\nid:practice", 3, "unsupported WebVTT block"),
    ("00:00.000 --> 00:02.000\n<v Teacher>Count.", 4, "unsupported cue text syntax"),
])
def test_webvtt_rejects_invalid_or_unsupported_syntax(corpus, tmp_path, cue, line, message):
    replace_raw(corpus, "synthetic-counts", f"WEBVTT\n\n{cue}\n".encode())
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 1
    assert f"synthetic-counts.vtt:{line}:" in result.stderr
    assert message in result.stderr
    assert not output.exists()


YOUTUBE_HEADER = "WEBVTT\nKind: captions\nLanguage: en\n\n"
YOUTUBE_TIMING = "00:00:00.000 --> 00:00:02.000 align:start position:0%"


def test_youtube_webvtt_preserves_observed_fields(corpus, tmp_path):
    markup = "Count<00:00:01.000><c> 1 &amp; 2</c>"
    content = (
        f"{YOUTUBE_HEADER}{YOUTUBE_TIMING}\n \n{markup}\n\n"
        "00:00:02.000 --> 00:00:02.010 align:start position:0%\n \n \n"
    ).encode()
    replace_raw(corpus, "synthetic-counts", content)
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    cleaned = json.loads((output / "synthetic-counts.json").read_bytes())
    assert cleaned["cleaning_version"] == "2"
    assert cleaned["vtt_header"] == YOUTUBE_HEADER.splitlines()[:3]
    speech, blank = cleaned["records"]
    assert speech == {
        "cue_id": "cue-1", "source_cue_id": None, "start_ms": 0, "end_ms": 2000,
        "raw_lines": [5, 7], "text": f"\n{markup}", "cue_settings": "align:start position:0%",
        "plain_text": "Count 1 & 2",
    }
    assert blank["raw_lines"] == [9, 11]
    assert blank["text"] == "\n"
    assert blank["plain_text"] == ""
    assert cleaned["metadata"]["validation_status"] == "passed"
    assert (corpus / "raw/synthetic-counts.vtt").read_bytes() == content


@pytest.mark.parametrize(("payload", "message"), [
    (" \n ", "no content after cleaning"),
    ("Count<00:00:02.000><c> one</c>", "invalid inline timestamp"),
    ("<v Teacher>Count.", "unsupported cue text syntax"),
    ("Count &madeup;", "unsupported cue entity"),
])
def test_youtube_webvtt_rejects_invalid_input(corpus, tmp_path, payload, message):
    replace_raw(corpus, "synthetic-counts", f"{YOUTUBE_HEADER}{YOUTUBE_TIMING}\n{payload}\n".encode())
    result = run_preparation(corpus, tmp_path / "clean")
    assert result.returncode == 1
    assert message in result.stderr


def test_rolling_transcript_preserves_repeated_counts_and_records_sources(corpus, tmp_path):
    cue_bodies = [
        ("00:00:00.000", "00:00:02.000", "[Music]\n  Count<00:00:01.000><c> 1 &#x1F3B5;</c>"),
        ("00:00:02.000", "00:00:02.010", "Count 1 🎵\n "),
        ("00:00:02.010", "00:00:04.000", "Count 1 🎵\nNew step"),
        ("00:00:04.000", "00:00:06.000", "Count<00:00:05.000><c> 1 🎵</c>"),
        ("00:00:05.000", "00:00:07.000", "Count<00:00:06.000><c> 1 🎵</c>"),
        ("00:00:05.500", "00:00:07.500", "Count<00:00:06.000><c> 1 🎵</c>"),
        ("00:00:07.500", "00:00:08.000", "1 🎵 keep it"),
        ("00:00:08.000", "00:00:08.010", " "),
        ("00:00:08.010", "00:00:09.000", "1 🎵 keep it"),
    ]
    vtt = YOUTUBE_HEADER + "\n\n".join(
        f"{start} --> {end} align:start position:0%\n{body}"
        for start, end, body in cue_bodies
    ) + "\n"
    replace_raw(corpus, "synthetic-counts", vtt.encode())
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    cleaned = json.loads((output / "synthetic-counts.json").read_bytes())
    transcript = cleaned["transcript"]
    assert transcript["text"] == "[Music] Count 1 🎵 New step Count 1 🎵 Count 1 🎵 1 🎵 keep it 1 🎵 keep it"
    assert [item["removed"]["cue_id"] for item in transcript["removals"]] == ["cue-2", "cue-3", "cue-6"]
    assert transcript["removals"][-1]["reason"] == "same_word_timestamps"
    assert [item["current"]["cue_id"] for item in transcript["doubts"]] == ["cue-7"]
    assert transcript["stats"]["doubts"] == 1
    marker = transcript["spans"][0]
    assert marker["kind"] == "hint"
    chunking_input = transcript["chunking_input"]
    assert chunking_input["text"] == transcript["text"].removeprefix("[Music] ")
    assert chunking_input["excluded_markers"] == [marker]
    for span in chunking_input["spans"]:
        start, end = span["char_range"]
        assert chunking_input["text"][start:end] == span["text"]
    copied = transcript["spans"][1]
    assert (copied["start_ms"], copied["end_ms"]) == (0, 4000)
    assert [item["cue_id"] for item in copied["sources"]] == ["cue-1", "cue-2", "cue-3"]
    for span in transcript["spans"]:
        start, end = span["char_range"]
        assert transcript["text"][start:end] == span["text"]
        for source in span["sources"]:
            record = next(cue for cue in cleaned["records"] if cue["cue_id"] == source["cue_id"])
            start, end = source["plain_range"]
            assert record["plain_text"][start:end] == span["text"]


def test_untimed_repeats_are_kept_and_previous_review_is_invalidated(corpus, tmp_path):
    documents = json.loads((corpus / "manifest.json").read_bytes())
    documents[1].update(review_status="reviewed", review_method="manual_sample", review_fingerprint="old")
    save_manifest(corpus, documents)
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    cleaned = json.loads((output / "synthetic-counts.json").read_bytes())
    transcript = cleaned["transcript"]
    assert transcript["text"].count("Count 5, 6, 7, 8.") == 3
    assert transcript["stats"]["removed_lines"] == 0
    assert transcript["stats"]["doubts"] == 2
    assert cleaned["metadata"]["review_status"] == "pending"


def test_untimed_10ms_roll_preserves_original_cue_and_following_source(corpus, tmp_path):
    content = (
        "WEBVTT\n\n"
        "08:45.580 --> 08:46.260\nCount one\n  step   back\n\n"
        "08:46.260 --> 08:46.270\nstep back\n\n"
        "08:46.270 --> 08:51.150\nstep back\nCount again\n"
    ).encode()
    replace_raw(corpus, "synthetic-counts", content)
    first, second = tmp_path / "first", tmp_path / "second"
    run_first, run_second = run_preparation(corpus, first), run_preparation(corpus, second)
    assert run_first.returncode == run_second.returncode == 0
    assert run_first.stdout == run_second.stdout
    output = (first / "synthetic-counts.json").read_bytes()
    assert output == (second / "synthetic-counts.json").read_bytes()
    assert (corpus / "raw/synthetic-counts.vtt").read_bytes() == content

    cleaned = json.loads(output)
    assert cleaned["records"][1]["text"] == "step back"
    transcript = cleaned["transcript"]
    assert transcript["version"] == "3"
    assert transcript["text"] == "Count one step back step back Count again"
    removal, = transcript["removals"]
    assert removal["reason"] == "single_line_exact_10ms_transition"
    assert removal["retained"]["cue_id"] == removal["previous"]["cue_id"] == "cue-1"
    assert removal["removed"]["cue_id"] == "cue-2"
    first_copy, later_copy = [span for span in transcript["spans"] if span["text"] == "step back"]
    assert first_copy["sources"] == [removal["retained"], removal["removed"]]
    assert (first_copy["start_ms"], first_copy["end_ms"]) == (525580, 526270)
    assert later_copy["sources"][0]["cue_id"] == "cue-3"
    doubt, = transcript["doubts"]
    assert doubt["previous"] == removal["removed"]
    assert doubt["current"] == later_copy["sources"][0]


@pytest.mark.parametrize(("previous", "start", "end", "current", "intervening"), [
    ("five six", "00:02.000", "00:03.000", "five six", ""),  # spoken again
    ("step back", "00:02.001", "00:02.011", "step back", ""),  # time gap
    ("step back", "00:02.000", "00:02.009", "step back", ""),  # shorter
    ("step back", "00:02.000", "00:02.011", "step back", ""),  # longer
    ("step back", "00:02.000", "00:02.010", "back", ""),  # partial
    ("step back", "00:02.000", "00:02.010", "step back\nCount again", ""),
    ("[Music]", "00:02.000", "00:02.010", "[Music]", ""),
    ("step back", "00:02.000", "00:02.010", "step back", "00:02.000 --> 00:02.005\nPause\n\n"),
])
def test_untimed_10ms_roll_requires_exact_adjacent_speech_line(
    corpus, tmp_path, previous, start, end, current, intervening
):
    content = f"WEBVTT\n\n00:00.000 --> 00:02.000\n{previous}\n\n{intervening}{start} --> {end}\n{current}\n"
    replace_raw(corpus, "synthetic-counts", content.encode())
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    transcript = json.loads((output / "synthetic-counts.json").read_bytes())["transcript"]
    assert transcript["removals"] == []
    assert transcript["spans"][-1]["text"] == current.splitlines()[-1]


@pytest.mark.parametrize(("start", "first_line", "carried"), [
    ("00:08:46.270", "step back", True),
    ("00:08:46.270", "step<00:08:46.500><c> back</c>", False),
    ("00:08:46.271", "step back", False),
])
def test_carry_after_recognized_10ms_transition(corpus, tmp_path, start, first_line, carried):
    content = (
        YOUTUBE_HEADER
        + "00:08:45.580 --> 00:08:46.260 align:start position:0%\nCount one\nstep back\n\n"
        + "00:08:46.260 --> 00:08:46.270 align:start position:0%\nstep back\n \n\n"
        + f"{start} --> 00:08:51.150 align:start position:0%\n{first_line}\n"
        + "raise<00:08:47.050><c> arm</c>\n"
    ).encode()
    replace_raw(corpus, "synthetic-counts", content)
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    document = json.loads((output / "synthetic-counts.json").read_bytes())
    assert document["records"][2]["text"] == f"{first_line}\nraise<00:08:47.050><c> arm</c>"
    assert (corpus / "raw/synthetic-counts.vtt").read_bytes() == content
    transcript = document["transcript"]
    assert transcript["spans"][-1]["text"] == "raise arm"
    assert transcript["spans"][-1]["sources"][0]["plain_range"] == [10, 19]
    assert transcript["spans"][-1]["sources"][0]["cue_id"] == "cue-3"
    if carried:
        assert transcript["text"] == "Count one step back raise arm"
        assert [source["cue_id"] for source in transcript["spans"][1]["sources"]] == ["cue-1", "cue-2", "cue-3"]
        second_removal = transcript["removals"][1]
        assert second_removal["reason"] == "single_line_carried_through_10ms_transition"
        assert second_removal["retained"]["cue_id"] == "cue-1"
        assert second_removal["previous"]["cue_id"] == "cue-2"
        assert second_removal["removed"]["plain_range"] == [0, 9]
        assert transcript["doubts"] == []
    else:
        assert transcript["text"] == "Count one step back step back raise arm"
        assert len(transcript["removals"]) == 1


def test_chunking_input_excludes_only_whole_marker_lines(corpus, tmp_path):
    content = (
        "WEBVTT\n\n"
        "00:00.000 --> 00:02.000\n[Applause]\nraise arm\n\n"
        "00:02.000 --> 00:04.000\n[Music] keep going\n[Other]\n"
    )
    replace_raw(corpus, "synthetic-counts", content.encode())
    output = tmp_path / "clean"
    result = run_preparation(corpus, output)
    assert result.returncode == 0, result.stderr
    document = json.loads((output / "synthetic-counts.json").read_bytes())
    derived = document["transcript"]["chunking_input"]
    assert derived["text"] == "raise arm [Music] keep going [Other]"
    marker, = derived["excluded_markers"]
    assert marker["text"] == "[Applause]"
    assert marker["sources"][0]["cue_id"] == "cue-1"
    assert document["records"][0]["text"] == "[Applause]\nraise arm"
