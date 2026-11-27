# DanceFlow AI

DanceFlow AI is a street dance coaching and crew management platform in development.
The current backend supports local user creation and lookup, as well as saving and
reading weekly training plans. The training-plan draft endpoint is a placeholder.

## Project progress

| Milestone | Delivered |
| --- | --- |
| DF-001–DF-004 | FastAPI health and draft endpoints, local MySQL and Alembic migrations, user creation and lookup, and weekly training plan APIs. |
| DF-005 | GitHub Actions CI added an API job and separate MySQL 8.4 matrix jobs for the DF-003 and DF-004 integration suites. |
| DF-005.1 | Shared MySQL fixtures and a single MySQL integration job. The API job runs all tests without the `mysql` marker, including offline corpus tests. |
| Week 2.1 | Collected and cleaned 10 STEEZY articles and English automatic captions from 5 Ceech lessons. All 15 local outputs passed automated validation. |
| Week 2.2 | Finalized 154 chunks, approved the 30-question retrieval set, and completed Qwen model selection and the local embedding smoke test. |
| Week 2.3 | Embedded and ingested 154 chunks. The 30-question exact dense baseline retrieved a complete minimum evidence plan for 29 questions at top 5. |
| Week 2.4 | Selected exact dense top-10 → Qwen3-Reranker-0.6B with `evidence-v2` → top-5 after comparing instruction variants and BGE on the same 30 development questions. |
| Week 2.5 | Verified OpenAI connectivity and the local RAG CLI. Reviewed both modes for five pilot questions and connected the FastAPI RAG endpoint to a single-question Streamlit interface. |

See the [development progress](docs/progress.md) for milestone history and the
[roadmap](docs/development-roadmap.md) for planned capabilities.

## Run the DF-001 backend

Run the following commands from the repository root. The backend was tested with Python 3.13.

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload
```

Once the server starts, use Swagger UI to inspect the API and try requests. [Open Swagger UI](http://127.0.0.1:8000/docs)

Run the following examples in a separate terminal.

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/training-plans/draft \
  -H 'Content-Type: application/json' \
  -d '{"dance_style":"popping","level":"beginner","goals":["improve hits"],"days_per_week":3,"minutes_per_session":30}'
```

The draft example returns `status: "placeholder"`, a message stating that AI generation is pending, and `weekly_minutes: 90`. Invalid requests return HTTP 422.

## Run MySQL locally (DF-002)

From the repository root, create `.env` from `.env.example` if you do not already
have one. Replace both placeholder passwords with distinct local development
passwords. Compose and the connection check also honor exported variables, which
take precedence over `.env`.

```sh
cp -n .env.example .env
docker compose config --quiet
docker compose up -d --wait --wait-timeout 90 mysql
docker compose ps mysql
```

The health check waits for MySQL to respond on its container TCP port. From
`backend/`, activate the virtual environment and verify the application user's
credentials and database through the published host port.

```sh
python -m pip install -r requirements-dev.txt
python -m app.db
```

The check connects to `127.0.0.1` on `MYSQL_HOST_PORT` (default `3307`) and
reports whether `SELECT 1` returns `1`. The health and draft endpoints and the
non-MySQL test suite can run without MySQL and `.env`. User and saved-plan
endpoints require the migrated database.

From the repository root, use `docker compose stop mysql` to stop the service
or `docker compose down` to remove the container and network while retaining
the named volume. Run the same `docker compose up` command to start it again.
MySQL stores its data in the `mysql_data` volume at `/var/lib/mysql`. The
image creates the application database and user when the volume is first
initialized. Changes to initialization credentials in `.env` do not update
accounts stored in an existing volume.

## Apply database migrations

From `backend/`, install the updated dependencies and verify the connection.
Alembic uses the same local database settings as the connection check.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m app.db
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic heads
.venv/bin/alembic check
```

The first upgrade creates `users` and records its revision in
`alembic_version`. Compare the revision IDs from `current` and `heads`, and use
`SHOW CREATE TABLE users` to inspect the columns and `uq_users_email`.
`users.created_at` stores UTC in a MySQL `DATETIME` column, which carries no
time-zone information. The shared engine sets the MySQL session time zone to
`+00:00` on each new connection, so the database's `CURRENT_TIMESTAMP` default
produces UTC for inserts through that engine. Other clients must also use a UTC
session when relying on that default.

For future model changes, start from a database at the current revision and
run `.venv/bin/alembic revision --autogenerate -m "describe the change"`.
Review the generated `upgrade()` and `downgrade()` before running
`upgrade head`. Use `upgrade head --sql` to preview SQL on an empty database
path without opening a connection. An online upgrade modifies the schema and
revision history, and MySQL DDL can implicitly commit. Downgrading the first
revision drops `users` and its data.

## Run tests and CI

From `backend/`, activate `.venv` and install the development dependencies before running the tests.

```sh
python -m pytest
PYTHON_DOTENV_DISABLED=1 python -m pytest -m "not mysql"
```

The first command skips MySQL integration tests by default. The second selects
the same tests as the CI API job with local dotenv loading disabled. It includes offline corpus and RAG CLI tests. See
[MySQL integration tests](#run-mysql-integration-tests) for the isolated test
database setup and the `RUN_MYSQL_TESTS=1` opt-in.

[GitHub Actions CI](.github/workflows/ci.yml) runs on pull requests targeting
`main`, pushes to `main`, and manual dispatch. The MySQL job uses an isolated
MySQL 8.4 service, runs `alembic upgrade head` and `alembic check`, and checks
the JUnit report for at least one test case and zero skips. The Week 2.4–2.5 changes were verified locally. Pushing the feature branch alone does not trigger a remote run. CD and deployment are pending.

## Create and look up a local user (DF-003)

With MySQL running and the migrations applied, start FastAPI and try:

```sh
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H 'Content-Type: application/json' \
  -d '{"email":"Dancer@example.com"}'
curl http://127.0.0.1:8000/api/v1/users/1
```

Use the ID returned by POST in the GET request. POST returns 201 after commit,
409 for a duplicate email, and 422 for invalid input. GET returns 404 if the
user is absent. Both responses represent `created_at` as ISO 8601 UTC with a
`Z` suffix.

Email validation trims surrounding whitespace and normalizes the domain.
The existing MySQL collation controls uniqueness, including case-insensitive
comparison under the current default collation. These endpoints are for local
development. Formal account policies and email ownership verification are
outside the current implementation.

## Save and read weekly training plans (DF-004)

In Swagger UI at `/docs`, use `POST /api/v1/users` to create a local
user or reuse an existing user ID. Submit the following JSON to
`POST /api/v1/training-plans`, replacing `user_id` with that ID.

```json
{
  "user_id": 1,
  "title": "Weekly Popping basics",
  "dance_style": "Popping",
  "level": "beginner",
  "goals": ["Hit on beat"],
  "sessions": [
    {"day_of_week": 1, "duration_minutes": 20, "focus": "Hit", "instructions": "Repeat for four eight-counts."}
  ]
}
```

POST returns 201 after saving the plan and sessions together. Read the full
result at `GET /api/v1/training-plans/{plan_id}`. Sessions are returned in
input order. Monday is day 1, and multiple sessions can share a weekday.
The plan repeats weekly. A user ID selects the owner record for local
development. There is currently no caller authentication.

`GET /api/v1/users/{user_id}/training-plans` returns `items`, `limit`, and
`offset`. Each item contains the complete plan and its sessions. The page is
ordered by descending plan ID, with limit 10 by default (range 1–20) and
offset 0 by default (range 0–10000). A missing user or plan returns 404.
An existing user with no results on the page receives 200 and an empty list.

## Run MySQL integration tests

The default pytest run skips tests marked `mysql`. Set `RUN_MYSQL_TESTS=1`
to enable them. The fixture requires an explicitly configured loopback port,
a non-root test account, and a database named `danceflow_<name>_test`. It
checks the connected database, UTC session, and Alembic heads before testing.
Each test reserves its own synthetic user emails and cleans up committed
sessions, plans, and users belonging to those emails after the test.

Run from the repository root with Docker and the backend virtual environment
ready. Pick an unused port and a fresh Compose project name for the isolated
test instance. The command leaves the test volume in place.

```sh
(
  set -e
  export COMPOSE_PROJECT_NAME="danceflow-mysql-test-$(openssl rand -hex 4)"
  export MYSQL_DATABASE=danceflow_local_test MYSQL_HOST_PORT=13309
  export MYSQL_USER=danceflow_test
  export MYSQL_PASSWORD="$(openssl rand -hex 24)"
  export MYSQL_ROOT_PASSWORD="$(openssl rand -hex 24)"
  trap 'docker compose --env-file .env.example down' EXIT
  docker compose --env-file .env.example up -d --wait --wait-timeout 90 mysql
  (
    cd backend
    .venv/bin/python -m alembic upgrade head
    .venv/bin/python -m alembic check
    RUN_MYSQL_TESTS=1 .venv/bin/python -m pytest -m mysql
  )
)
```

With the same test container and environment, either test file can also run
on its own from `backend/`.

```sh
RUN_MYSQL_TESTS=1 .venv/bin/python -m pytest tests/test_users_mysql.py
RUN_MYSQL_TESTS=1 .venv/bin/python -m pytest tests/test_training_plans_mysql.py
```

## Local RAG preparation

The selected corpus contains **10 STEEZY articles and 5 Ceech lessons**.
Articles retain their original block and heading structure. Caption
preparation uses transcript v3 to remove adjacent rolling duplicates. The
derived chunking input excludes whole-line `[Music]` and `[Applause]` markers
while retaining cue timestamps and line references. ASR omissions and
transcription errors remain as captured, and a full listening review of every
video is outside this baseline.

**Current input** is `evaluations/rag/local/week2.1/clean-v3-baseline/`.
**Current chunks** are in
`evaluations/rag/local/week2.2/batch-headings-v2/` (154 total, 136 article
and 18 video, zero heading-only). The earlier 179-chunk batch was removed locally. Its results are recorded in the [RAG report](evaluations/rag/report.md). Third-party snapshots, captions,
clean JSON, chunks and model cache are stored in the Git-ignored
`evaluations/rag/local/` directory.

Article chunks carry the title and source heading hierarchy in
`embedding_text`. Video chunks combine adjacent retained cues. Both use a
512-token limit for the full embedding input and a 64-token overlap budget.
The pilot and the full batch passed body coverage, source traceability,
token limit and deterministic rerun checks.

### Run the embedding smoke test and chunking

From the repository root, set up the separate RAG environment and cache the
pinned Qwen revision once.

```sh
backend/.venv/bin/python -m venv evaluations/rag/local/.embedding-venv
evaluations/rag/local/.embedding-venv/bin/python -m pip install \
  -r evaluations/rag/requirements-embedding.txt
export HF_HUB_CACHE=evaluations/rag/local/hf-cache
evaluations/rag/local/.embedding-venv/bin/hf download \
  Qwen/Qwen3-Embedding-0.6B --revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
```

With the cache present, run the smoke test offline. The tokenizer-only
chunking commands also require the selected local clean corpus and its
validation summary.

```sh
export HF_HUB_OFFLINE=1
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/smoke_embedding.py
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_pilot.py \
  --input-dir evaluations/rag/local/week2.1/clean-v3-baseline \
  --output-dir evaluations/rag/local/week2.2/pilot-headings-v2
evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/chunk_batch.py \
  --baseline-root evaluations/rag/local/week2.1 \
  --output-dir evaluations/rag/local/week2.2/batch-headings-v2
```

The smoke test passed on CPU with float32 and normalized 1024-dimensional
vectors. Chinese and English queries use a retrieval instruction, while
English documents use their text directly. The smoke test confirms the
embedding path runs. Retrieval quality remains unmeasured. See the
[model comparison, full instruction and smoke results](evaluations/rag/report.md#week-21--embedding-選型與本機-smoke-test)
and the [chunking settings and comparison](evaluations/rag/report.md#week-22--文章標題改為正文的階層前綴).

### Verify the approved retrieval set

`week2.2-retrieval-set-v1` contains 30 approved questions (15 Traditional
Chinese and 15 English) and 61 evidence entries. The Git-ignored
`evaluations/rag/local/week2.2/retrieval-pilot-v1/` directory contains
`dataset.json` and the human-readable `review.md`. Use the original approved
local copies, along with the clean inputs and the chunk batch reproduced by
the commands above. The release lock records hashes for both annotation
files and the chunk summary.

```sh
python3 -B evaluations/rag/validate_retrieval_pilot.py
```

The existing API CI job runs RAG preparation, chunking and annotation-validator
unit tests using synthetic fixtures and a substitute token counter. The
cached Qwen tokenizer check and the approved dataset validation run locally.
See the [RAG report](evaluations/rag/report.md) for the locked versions and checks.

### Run batch document embedding

From the repository root, use the cached model and the locked local inputs
described above.

```sh
HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1 \
  evaluations/rag/local/.embedding-venv/bin/python -B evaluations/rag/embed_batch.py
```

The command verifies the release lock, source snapshots, chunk IDs, and full
token counts before encoding. It writes `vectors.json` and `manifest.json`
under `evaluations/rag/local/week2.3/embeddings/<fingerprint>/`. Each row of the
vector matrix maps to the same index in the manifest's `chunk_ids`. A repeat
run verifies and reuses the artifact for the same inputs and settings.

The local run verified 154 normalized float32 vectors with 1024 dimensions.

### Run Qdrant locally and import the document vectors

Run from the repository root with the existing local `.env` configured as in
[the MySQL setup](#run-mysql-locally-df-002). Compose resolves the required
MySQL variables even when starting Qdrant by itself. Qdrant uses REST at
`127.0.0.1:6333` and stores its data in the `qdrant_data` named volume.

```sh
docker compose config --quiet
docker compose up -d --no-deps qdrant
curl -fsS --retry 15 --retry-all-errors --retry-delay 1 http://127.0.0.1:6333/readyz
```

To start both services, or to restart Qdrant alone, use the respective command.

```sh
docker compose up -d --wait --wait-timeout 90 mysql qdrant
docker compose restart --no-deps qdrant
```

Install the pinned client in the existing RAG environment. Set
`artifact_dir` to the exact path printed by the embedding CLI for the locked
batch.

```sh
rag_python=evaluations/rag/local/.embedding-venv/bin/python
"$rag_python" -m pip install -r evaluations/rag/requirements-qdrant.txt
artifact_dir="evaluations/rag/local/week2.3/embeddings/<fingerprint>"
"$rag_python" -B evaluations/rag/ingest_qdrant.py --artifact "$artifact_dir"
```

The import checks the artifact, collection version, and vector settings before
upsert. It then verifies the exact count and compares every UUID, payload and
vector. Run the same command to reimport, or add `--verify-only` after Qdrant is
ready following a restart to check the stored collection without upserting.

To trace the first row, run this read-only example with the same variables.
It prints the original chunk ID, Qdrant UUID, and source URL.

```sh
"$rag_python" -B - "$artifact_dir" <<'PY'
import json
import sys
from contextlib import closing
from pathlib import Path
from qdrant_client import QdrantClient
from evaluations.rag.ingest_qdrant import COLLECTION, URL, point_id

manifest = json.loads((Path(sys.argv[1]) / "manifest.json").read_bytes())
chunk_id = manifest["chunk_ids"][0]
with closing(QdrantClient(url=URL)) as client:
    row, = client.retrieve(COLLECTION, ids=[point_id(chunk_id)], with_payload=True)
assert row.payload["chunk_id"] == chunk_id
print(chunk_id, row.id, row.payload["source_url"])
PY
```

The Qdrant integration tests use temporary synthetic collections on the
running localhost server. Run them explicitly from the repository root.

```sh
"$rag_python" -m pip install 'pytest>=8.3,<10'
"$rag_python" -B -m pytest -p no:cacheprovider evaluations/rag/integration/test_qdrant_ingestion.py
```

The API CI job collects offline tests from `backend/`. A separate Qdrant CI job
starts Qdrant 1.16.3 and runs the synthetic integration suite from the repository
root. It checks the JUnit report for at least one test case and zero skips.
The Qdrant job requires only the pinned client and pytest, and includes a
fixed-vector exact query test. The workflow steps passed locally. The
GitHub Actions run is pending.

### Run the exact dense retrieval baseline

With Qdrant ready and the locked document vectors already ingested, run from
the repository root with the same `artifact_dir` and `rag_python` as above.

```sh
HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1 \
  "$rag_python" -B evaluations/rag/evaluate_dense.py --artifact "$artifact_dir"
```

The CLI checks the locked inputs and stored collection, encodes the approved
queries using the existing instruction, and checks Qdrant exact top-5 results
against local dot products. Each run writes a new timestamped JSON file under
the Git-ignored `evaluations/rag/local/week2.3/dense/` with per-question results,
source pointers, and latency.

The first run found a member of a minimum evidence plan for 29 of 30
questions and retrieved a complete plan for 29 of 30. See the
[RAG report](evaluations/rag/report.md) for language breakdown, the missed
case, and measurement limits.

For the post-baseline diagnostic on the same locked set, add `--diagnose`.

```sh
HF_HUB_CACHE=evaluations/rag/local/hf-cache HF_HUB_OFFLINE=1 \
  "$rag_python" -B evaluations/rag/evaluate_dense.py --artifact "$artifact_dir" --diagnose
```

This writes a separate `diagnostics-*.json` with k=3, 5, and 10 prefix metrics,
candidate text token counts, and the complete Arm Wave ranking. It is an
exploratory analysis of the baseline questions.

### Run the Qwen reranker development evaluation

Start Qdrant and keep the locked document vectors in the baseline collection.
Use the existing RAG virtual environment. Download the pinned model and
tokenizer into the ignored local cache once.

```sh
export HF_HUB_CACHE=evaluations/rag/local/hf-cache
evaluations/rag/local/.embedding-venv/bin/hf download \
  Qwen/Qwen3-Reranker-0.6B --revision e61197ed45024b0ed8a2d74b80b4d909f1255473 \
  config.json tokenizer.json tokenizer_config.json chat_template.jinja model.safetensors
```

From the repo root, point the runner at the locked embedding artifact and the
two original dense output files.

```sh
dense_dir=evaluations/rag/local/week2.3/dense
artifact_dir=evaluations/rag/local/week2.3/embeddings/cb6d84b8fdaf7a6b14e0c0398a32acdcea45936ed668ab9ed40ac97701203f14
HF_HUB_OFFLINE=1 evaluations/rag/local/.embedding-venv/bin/python -B \
  evaluations/rag/evaluate_reranker.py --artifact "$artifact_dir" \
  --baseline "$dense_dir/baseline-20261124T165129014791Z.json" \
  --diagnostics "$dense_dir/diagnostics-20261125T160435584392Z.json"
```

The runner defaults to Apple MPS with float32. Use `--smoke-only` for the
synthetic bilingual smoke check, or `--device cpu` for an explicit CPU run.
It verifies the saved rankings against live exact top-10 queries, scores
each candidate pool once per timed query, and applies the evidence metrics
to the first round only. The timestamped JSON in the Git-ignored
`evaluations/rag/local/week2.3/reranker/` directory contains per-query scores,
timings, and selected text volumes. This evaluation reuses the baseline
questions for development.

#### Compare the evidence-v1 instruction

Use the same cached model, artifact, and dense output paths as above. Supply
the original default reranker result. This mode uses the verified saved
top-10 candidates and measures only the rerank stage.

```sh
default_result=evaluations/rag/local/week2.3/reranker/development-20261125T163120818499Z.json
HF_HUB_OFFLINE=1 evaluations/rag/local/.embedding-venv/bin/python -B \
  evaluations/rag/evaluate_reranker.py --instruction evidence-v1 \
  --artifact "$artifact_dir" --baseline "$dense_dir/baseline-20261124T165129014791Z.json" \
  --diagnostics "$dense_dir/diagnostics-20261125T160435584392Z.json" \
  --default-result "$default_result"
```

The timestamped `evidence-v1-*.json` keeps all seven variants, per-query
ranking and changes, and timing samples. The instruction was designed after
inspecting baseline failures, so this comparison uses the development set.

### Week 2.4 retrieval decision

The CLI uses **exact dense top-10 → Qwen3-Reranker-0.6B with `evidence-v2` → top-5**.
The historical exact dense top-5 baseline remains reproducible above. Member hit
means retrieving any member of a minimum sufficient evidence set. Completion
means retrieving all members of at least one such set. Partial evidence is
tracked separately.

| Top-5 output | Member hit / completion | Rerank P50 / P95, ms | Selected characters / proxy tokens per question |
| --- | --- | --- | --- |
| Historical dense | 29/30 / 29/30 | — | 5,018.6 / 1,153.6 |
| Qwen default instruction | 29/30 / 29/30 | 1,380.38 / 2,293.21 | 4,961.7 / 1,143.7 |
| Qwen evidence-v1 | 29/30 / 29/30 | 1,517.45 / 2,422.48 | 4,958.9 / 1,139.3 |
| Qwen evidence-v2 | 30/30 / 30/30 | 1,628.00 / 2,371.71 | 5,229.1 / 1,203.7 |
| BGE v2-m3 | 29/30 / 29/30 | 624.16 / 1,076.44 | 5,585.6 / 1,289.8 |

Evidence-v2 moved the Arm Wave evidence from rank 6 to 5. Evidence-v3 tied it
at top-5 with no observed retrieval gain. BGE reranked faster in its measured
run, selected more text, and missed that Arm Wave evidence at top-5. These are
development-set retrieval results. The latency figures come from separate runs,
and proxy tokens measure selected text volume. Generation quality and actual API
usage are measured separately. [Experiment details](evaluations/rag/report.md)

### Week 2.5 OpenAI smoke test

Set `OPENAI_API_KEY` in the Git-ignored repository-root `.env` and use
`OPENAI_MODEL=gpt-6.1-terra`. The shared dotenv loader gives an existing
environment variable priority over the file. From `backend/` with dependencies
installed, run `.venv/bin/python -m app.smoke_openai`. It uses Responses,
reasoning effort `none`, 256 output tokens, a 30-second timeout, and zero retries.
It prints the model, answer, usage, and elapsed time. A missing key exits before
a request. API errors expose the HTTP status and exception type. The user
confirmed the live smoke test succeeded.

### Week 2.5 single-question RAG

Run from the repository root with the existing Qdrant collection, locked
embedding artifact, and cached Qwen models. Install the backend requirements
into the existing embedding environment to share the OpenAI SDK and dotenv.

```sh
rag_python=evaluations/rag/local/.embedding-venv/bin/python
"$rag_python" -m pip install -r backend/requirements.txt
docker compose start qdrant
export PYTHONPATH=backend
export HF_HUB_CACHE=evaluations/rag/local/hf-cache
export HF_HUB_OFFLINE=1
artifact_dir=evaluations/rag/local/week2.3/embeddings/cb6d84b8fdaf7a6b14e0c0398a32acdcea45936ed668ab9ed40ac97701203f14
question='我做 bounce 時看起來很僵硬，練習時應該注意哪些身體動作？'
"$rag_python" -B -m evaluations.rag.answer --artifact "$artifact_dir" --question "$question" --dry-run
```

The dry run prints the top-five context and source lookup after exact dense
top-10 and Qwen reranking with `evidence-v2`. Use `--device cpu` when MPS is
unavailable. For one live run, set `OPENAI_API_KEY` in the repository-root
`.env` and repeat the last command without `--dry-run`. The JSON output
includes the answer status, model, usage, and stage timings. An incomplete
answer or an unknown source ID produces a nonzero exit status. Citation ID
validation checks membership in the lookup table. Claim support requires
reviewing each claim against the cited text.

### Week 2.5 five-question generation pilot

The user approved `week2.5-generation-pilot-v1-approved.1`. All ten requests
completed, one RAG and one LLM-only run per question, using `gpt-6.1-terra`.
Both modes use reasoning effort `none`, up to 1,500 output tokens, a 60-second
timeout, and zero retries. LLM-only sends the original question and response
instructions without retrieval or search tools. It can run from the repo root
with `PYTHONPATH=backend backend/.venv/bin/python -m evaluations.rag.answer
--mode llm-only --question 'Your question'` on one shell line.

The CLI reports API status and error type without exposing headers or
credentials. An empty or truncated answer returns a nonzero exit status. RAG
keeps source IDs, full chunk text, and available heading or time metadata.
The number check verifies membership in the source table. Claim support requires
human review. Offline validation yielded 151 passed and 5 MySQL tests deselected.

Local review files under `evaluations/rag/local/week2.5/`

- `generation-pilot-v1/review.md` and `generation-pilot-v1.lock.json` for the approved rubric and hashes.
- `generation-pairs-v1-approved.1/review.md` for all ten answers, sources and timings, plus one JSON per mode and question in the same folder.

ChatGPT assisted the review and the user confirmed the results. All ten
answers received 2/2/2 for correctness, relevance/completeness, and
actionability. In this pilot the scores show no quality gain from RAG. The RAG
answers provide traceable sources, and specific supplemental examples still
require attribution checks. The local pair directory contains `scores-v1.json`
and the scored `review.md`. The approved rubric and original responses were preserved.
The 30-question generation run is pending.
See the [RAG report](evaluations/rag/report.md).

### Run the Week 2.5 RAG HTTP endpoint

Use the existing embedding virtual environment to serve FastAPI and the RAG
models in one process. A fresh environment also needs the locked corpus and
embedding artifact, the Qwen embedding and reranker model caches, and the
existing Qdrant collection. See the preparation, ingestion, and reranker
sections above. Set `OPENAI_API_KEY` in the repo-root `.env`.

From the repository root:

```sh
rag_python=evaluations/rag/local/.embedding-venv/bin/python
"$rag_python" -m pip install -r backend/requirements.txt \
  -r evaluations/rag/requirements-embedding.txt -r evaluations/rag/requirements-qdrant.txt
docker compose start qdrant
export PYTHONPATH=backend
export HF_HUB_CACHE="$PWD/evaluations/rag/local/hf-cache"
export HF_HUB_OFFLINE=1
export RAG_ARTIFACT="$PWD/evaluations/rag/local/week2.3/embeddings/cb6d84b8fdaf7a6b14e0c0398a32acdcea45936ed668ab9ed40ac97701203f14"
export RAG_RERANKER_DEVICE=mps
"$rag_python" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Set `RAG_RERANKER_DEVICE=cpu` when MPS is unavailable. Open
`http://127.0.0.1:8765/docs`, expand `POST /api/v1/knowledge/ask`, then choose
**Try it out** and **Execute**. The curl equivalent is:

```sh
curl http://127.0.0.1:8765/api/v1/knowledge/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"我做 bounce 時看起來很僵硬，練習時應該注意哪些身體動作？"}'
```

Each valid request can use the OpenAI API. The first request verifies the local
artifacts and Qdrant collection and loads the embedding encoder and reranker. Later requests reuse the
models within the same worker process. Requests to that service run serially
on FastAPI worker threads. The ordinary backend can start without RAG
dependencies, Qdrant, or an OpenAI key.

The API accepts a nonblank question of at most 2,000 characters after trimming.
The existing 512-token check includes the embedding query prompt and special
tokens. It returns HTTP 422 for invalid input, 503 for unavailable runtime or
configuration, 502 for upstream failures or invalid answers, and 504 for
upstream timeouts. Success includes an answer, citation-to-source mapping, model,
usage, and stage timings.

Observed locally: 167 offline tests passed and five MySQL tests were deselected.
Swagger and the OpenAPI route were verified. A single HTTP request returned 200,
using 2,457 input and 393 output tokens, in 23.099 seconds client wall time.
The raw response is saved at `evaluations/rag/local/week2.5/api-smoke-v1.json`.
Remote CI for the endpoint is pending. See the Streamlit section for the subsequent cold and warm HTTP measurements.

### Run the Week 2.5 Streamlit interface

Start Qdrant and the FastAPI service first using the commands above. Then, from
the repository root, in another terminal:

```sh
python3 -m venv frontend/.venv
frontend/.venv/bin/python -m pip install -r frontend/requirements.txt
export DANCEFLOW_API_BASE_URL=http://127.0.0.1:8765
frontend/.venv/bin/python -m streamlit run frontend/app.py \
  --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. The interface accepts Traditional Chinese and English
questions. Submit the form to see the answer and its cited sources. Other
retrieved sources and execution details have separate expanders. The last
successful result stays in Session State for ordinary reruns. Submitting a new
question clears the previous result before validation and any HTTP request.

Set `DANCEFLOW_API_BASE_URL` in the frontend process environment when the API
runs at a different address. The default is `http://127.0.0.1:8765`. The frontend
uses a 120-second HTTP timeout and makes one request per valid submission.
OpenAI configuration stays in the backend. No key is needed in the frontend.

From `frontend/`, install `requirements-dev.txt` and run
`.venv/bin/python -m pytest` for the mocked AppTest suite. The frontend CI job
runs this suite with its own dependencies.

Locally, nine mocked AppTests and 167 non-MySQL backend tests passed. AppTest
also submitted two live requests against one backend process, and the hosted
Streamlit page returned HTTP 200. The first and subsequent frontend HTTP calls
took 21.645 and 8.932 seconds. They used different questions. The smoke test
checked rendered elements with AppTest. Browser interaction was not tested.
Results are saved in
`evaluations/rag/local/week2.5/streamlit-smoke-v1.json`. Remote CI is pending.
