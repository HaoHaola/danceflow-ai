# danceflow-ai
AI-Powered Street Dance Coaching and Crew Management Platform

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
reports whether `SELECT 1` returns `1`. The FastAPI endpoints and their tests
can run independently of MySQL and `.env`.

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

## Run tests

From `backend/`, activate `.venv` and install the development dependencies before running the tests.

```sh
python -m pytest
```

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

The regular pytest suite covers API behavior with a simulated Session. To
verify real MySQL behavior, run the following from the repository root in a
shell with Docker and the backend virtual environment already prepared.
The isolated Compose project uses port 13307 and retains its test volume.
Choose a fresh project name on each run because the generated passwords apply
only when MySQL initializes a new volume.

```sh
(
  set -e
  export COMPOSE_PROJECT_NAME="danceflow-df003-test-$(openssl rand -hex 4)"
  export MYSQL_DATABASE=danceflow_df003_test MYSQL_HOST_PORT=13307
  export MYSQL_USER=danceflow_test
  export MYSQL_PASSWORD="$(openssl rand -hex 24)"
  export MYSQL_ROOT_PASSWORD="$(openssl rand -hex 24)"
  trap 'docker compose --env-file .env.example down' EXIT
  docker compose --env-file .env.example up -d --wait --wait-timeout 90 mysql
  (
    cd backend
    .venv/bin/alembic upgrade head
    RUN_MYSQL_TESTS=1 .venv/bin/python -m pytest tests/test_users_mysql.py
  )
)
```
