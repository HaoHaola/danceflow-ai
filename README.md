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

## Run tests

From `backend/`, activate `.venv` and install the development dependencies before running the tests.

```sh
python -m pytest
```
