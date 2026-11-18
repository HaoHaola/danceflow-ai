# DanceFlow AI — Agent Instructions

## Project

DanceFlow AI is a street dance coaching and crew management platform.

MVP features:
- Personalized training plans
- Training history and progress
- Crew rehearsal scheduling
- Automated notifications
- Dance knowledge RAG
- Crew event management

Read docs/development-roadmap.md for the development roadmap.
Follow the current task's approved scope. The roadmap does not authorize
implementing future features automatically.

## Technology

- Backend: Python, FastAPI, Pydantic
- Database: MySQL, SQLAlchemy, Alembic
- RAG: Qdrant
- Agent workflows: LangChain, LangGraph
- Automation: n8n
- Frontend: Streamlit
- Deployment: Docker

Introduce dependencies only when the current task requires them.

## Implementation Rules

- Inspect existing code, Git status, and relevant instructions before editing.
- Preserve existing work and uncommitted changes.
- Before editing, explain which files will change and why.
- If the task is planning only, do not edit files.
- If implementation is authorized, implement within the approved scope.
- Prefer small, readable functions and simple project structures.
- Avoid unrelated refactoring and premature abstractions.
- Do not implement future roadmap features without a request.
- Clearly label placeholder behavior; do not present it as a completed feature.
- Do not commit, push, deploy, or run destructive database commands
  unless explicitly requested.

## API Conventions

- Use /api/v1 for business endpoints.
- Keep GET /health outside the versioned prefix.
- Define explicit Pydantic request and response models.
- Validate input at the API boundary.
- Use appropriate HTTP status codes.
- Keep business rules deterministic where possible.
- Do not introduce an LLM call for logic that ordinary Python can handle.

## Secrets and Configuration

- Never hardcode credentials or commit .env files.
- Do not print secrets in logs, tool output, or documentation.
- Use .env.example with placeholder values when configuration is introduced.
- Use synthetic data for development and tests.

## Testing

- Use pytest and FastAPI TestClient for API tests.
- Cover successful requests and meaningful validation failures.
- Run the tests relevant to each change.
- Report the exact commands and observed results.
- If a check cannot run, explain why; never claim it passed.

Once the backend skeleton exists:

- Run tests from backend/:
  python -m pytest

- Start the development server from backend/:
  python -m uvicorn app.main:app --reload

## Teaching and Handoff

Respond primarily in Traditional Chinese, keeping technical terms in English.

After each implementation:
1. Explain the goal and assumptions.
2. List changed files and the purpose of each.
3. Walk through the request and data flow.
4. Explain important functions and unfamiliar syntax.
5. Report tests run and results.
6. Describe limitations and relevant alternatives.
7. Explain what I should be able to describe in an interview.
8. Give one small exercise I can complete manually.

Explain why the design is appropriate, not only what the code does.