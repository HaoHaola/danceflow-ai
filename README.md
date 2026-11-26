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
python -m pytest -m "not mysql"
```

The first command skips MySQL integration tests by default. The second selects
the same tests as the CI API job, including the offline corpus tests. See
[MySQL integration tests](#run-mysql-integration-tests) for the isolated test
database setup and the `RUN_MYSQL_TESTS=1` opt-in.

[GitHub Actions CI](.github/workflows/ci.yml) runs on pull requests targeting
`main`, pushes to `main`, and manual dispatch. The MySQL job uses an isolated
MySQL 8.4 service, runs `alembic upgrade head` and `alembic check`, and checks
the JUnit report for at least one test case and zero skips. CI is operational.
CD and actual deployment are pending.

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
