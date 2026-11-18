# DanceFlow AI — Development Roadmap

> **Project:** AI-powered Street Dance Coaching & Crew Management Platform  
> **Version:** 1.0 · Updated 2026-11-18  
> **Duration:** 8 weeks for a demonstrable MVP; advanced infrastructure and multimodal coaching are subsequent extensions  
> **Learning style:** Project-based learning + IBM RAG and Agentic AI coursework + supervised Codex collaboration  
> **Status:** Planning / early implementation

## 1. Goals and scope

### Product goal

Deliver a working application for individual dancers and street-dance crews with six capabilities:

1. **Personalized Training Plan:** create a feasible 7-day plan based on style, skill level, goals, and weekly availability.
2. **Training History & Progress:** log completed sessions, duration, subjective difficulty, and notes; visualize weekly progress.
3. **Crew Rehearsal Scheduling:** collect availability, rank candidate slots, prevent conflicts, and ask a crew admin to confirm.
4. **Automated Notifications:** notify members of new or updated events, and record delivery status and retries.
5. **Dance Knowledge RAG:** answer dance-technique questions with grounded source citations and measured retrieval quality.
6. **Crew Event Management:** create and update rehearsals, performances, workshops, and competitions; collect RSVPs.

### Engineering and job-preparation goal

Demonstrate competence in **Advanced RAG, measurable evaluation, LangGraph agents, secure REST APIs, async I/O, MySQL schema design, multi-tenant RBAC, n8n integration, reproducible deployment, model serving, and observability**. Build evidence through code, tests, architecture decisions, and benchmark reports rather than certificates alone.

### Deliberate non-goals for the 8-week MVP

- Real-time video pose coaching, full-body motion scoring, public social platform, payments, complex mobile app.
- Production microservices, gRPC/NATS, full ELK/Loki stack, GPU-dependent vLLM rollout, embedding model fine-tuning.
- A six-agent architecture solely because there are six user-facing features.

These are future options, not blockers for shipping the MVP.

## 2. Current knowledge and learning strategy

**Already completed in the IBM certificate:** RAG, Advanced RAG, and Vector Database modules. **Do not rewatch them by default.** Apply them directly in Dance Knowledge RAG and fill gaps only when implementation or evaluation exposes a concrete issue.

**Continue IBM learning:** Agent Fundamentals → LangChain/LangGraph → Multi-Agent and MCP topics relevant to the project; treat Capstone as an optional comparison or consolidation exercise. Course numbering, assignments, and content may change, so use the live Coursera syllabus when scheduling exact lessons.

**Time budget (planning assumption):** 12–15 hours/week, split approximately into 30% concepts/course, 50% coding and experimentation, 20% testing/review/documentation. Adjust weeks if the workload exceeds this budget; prioritize a working, tested vertical slice over checklist completion.

## 3. Architecture: start with a modular monolith

```text
Streamlit UI
    |
    v
FastAPI (authentication, validation, REST, RBAC)
    |-- application services (training, scheduling, events, notifications)
    |-- SQLAlchemy + MySQL (structured, tenant-scoped records)
    |-- LangGraph (state, intent routing, tool orchestration, approvals)
    |       |-- Qdrant + hybrid retrieval + reranking (dance knowledge)
    |       |-- read-only training/history/event tools
    |       `-- proposed write actions -> authorized backend service
    |-- n8n (webhooks, reminders, email / notification delivery)
    `-- structured logs, metrics, tests

LLM interface: start with one accessible provider; add Ollama / llama.cpp comparison later.
Docker Compose: local reproducibility; development and test data must be synthetic.
```

### Engineering decisions

- **FastAPI + Pydantic** for explicit API contracts and validation.
- **MySQL + SQLAlchemy + Alembic** for transactional relationships, schema migrations, and indexes; do not let the LLM write unrestricted SQL.
- **Qdrant** for vector retrieval; start from an explicit dense-search baseline before adding BM25/hybrid search and a Cross-Encoder reranker.
- **LangGraph** for state and explicit decision boundaries; deterministic scheduling rules live in tested Python services.
- **n8n** for reliable, inspectable integrations and scheduled delivery, not for core data authorization or business invariants.
- **RBAC and tenant isolation** belong at API/service/repository boundaries, including calls initiated by the agent.
- **MCP** is a later interoperability exercise: wrap one existing capability after the plain Python tool is tested.

## 4. Data model (initial)

| Table | Key fields / relationships | Notes |
| --- | --- | --- |
| `users` | `id`, `email`, `password_hash`, `dance_style`, `skill_level`, `goals`, `timezone` | Store password hashes, never plaintext. |
| `crews` | `id`, `name`, `created_by` | Crew is a tenant. |
| `crew_members` | `(crew_id, user_id)`, `role` | Roles: `owner`, `admin`, `member`; unique membership. |
| `training_plans` | `id`, `user_id`, `title`, `goal`, `start_date`, `end_date`, `status` | Plan ownership. |
| `training_sessions` | `id`, `plan_id`, `scheduled_at`, `duration_min`, `skill_focus` | Scheduled tasks. |
| `training_logs` | `id`, `user_id`, `session_id?`, `completed_at`, `actual_duration_min`, `difficulty`, `notes` | Optional session for freestyle/self-directed practice. |
| `availability_slots` | `id`, `crew_id`, `user_id`, `start_at`, `end_at` | Store UTC; display in user timezone. |
| `events` | `id`, `crew_id`, `type`, `title`, `start_at`, `end_at`, `location`, `status` | Rehearsal is a type of event. |
| `event_rsvps` | `(event_id, user_id)`, `response`, `responded_at` | One RSVP per user/event. |
| `notifications` | `id`, `event_id?`, `user_id`, `channel`, `status`, `scheduled_at`, `sent_at?`, `idempotency_key` | Prevent duplicate delivery; track retries. |
| `agent_runs` | `id`, `user_id`, `intent`, `status`, `tool_calls_json`, `started_at`, `completed_at` | Redact sensitive information. |
| `knowledge_documents` | `id`, `title`, `source_url?`, `version`, `ingested_at` | Qdrant payload references document and chunk IDs. |

Add foreign keys, unique constraints and key indexes as each table is implemented; write an Alembic migration rather than altering the database manually. For every crew-scoped read/write, check authorized membership and role. Treat cross-crew access as a critical failing test.

## 5. API contracts (target, add incrementally)

**Prefix:** `/api/v1`

| Domain | Initial endpoints |
| --- | --- |
| Health/auth/profile | `GET /health`, `POST /auth/register`, `POST /auth/login`, `GET/PATCH /users/me` |
| Training | `POST /training-plans/draft`, `POST /training-plans`, `GET /training-plans`, `POST /training-logs`, `GET /training-progress` |
| Crews | `POST /crews`, `GET /crews/{id}`, `GET/POST /crews/{id}/members`, `POST /crews/{id}/availability` |
| Scheduling/events | `POST /crews/{id}/rehearsal-suggestions`, `GET/POST /crews/{id}/events`, `PATCH /events/{id}`, `POST /events/{id}/rsvps` |
| Knowledge/agent | `POST /knowledge/search`, `POST /agent/chat`, `POST /agent/actions/{id}/confirm`, `GET /agent/runs/{id}` |
| Notifications | `GET /notifications`; internal webhook endpoint only with authentication / signature validation |

Use Pydantic request/response models, predictable error responses and OpenAPI/Swagger. Never use a client-provided user ID as proof of identity. Make writes transactional and external notifications retry-safe.

## 6. Eight-week delivery milestones

### Week 1 — Backend foundation, first vertical slice

**Study:** FastAPI routing, Pydantic validation, REST conventions, SQLAlchemy concepts, dependency injection, unit testing. IBM RAG materials only for reference.

**Build:** repository structure; `GET /health`; request and response schemas for a training-plan draft; MySQL local setup and first migration; initial tests; minimal `.env.example` and README setup.

**Codex tasks:** plan repo layout first; implement only the API skeleton after review; explain each created file and test.

**Acceptance:** service starts locally; `/docs` shows contract; invalid input returns 422; tests pass; no secrets in Git.

### Week 2 — Advanced Dance Knowledge RAG, implemented experimentally

**Study by doing:** document ingestion and chunking strategies; dense baseline; sparse/BM25 and hybrid retrieval; Reciprocal Rank Fusion; Cross-Encoder reranking; citation quality. No need to redo completed IBM courses.

**Build:** curate 20–40 licensed/owned short knowledge documents or carefully attributed notes; build ingestion; index in Qdrant; run dense and hybrid variants; create 30–50 labeled query/relevant-document examples; produce a reproducible baseline evaluation.

**Metrics:** Hit Rate@5, MRR@5, Recall@5 if judgments support it, P50/P95 retrieval latency; explicitly record dataset size, judgment method, embedding model and hardware. Distinguish retrieval metrics from answer quality.

**Acceptance:** source-linked answers; `evaluations/rag/` includes dataset, script, result table, and honest interpretation; no fabricated benchmark numbers.

### Week 3 — Personalized Coach, LangGraph and training history

**IBM focus:** Agent Fundamentals and LangChain/LangGraph agent topics.

**Build:** `get_user_profile`, `get_training_history`, `search_dance_knowledge` and `draft_training_plan` tools; LangGraph state and simple routing; plan generation to validated JSON; user approval before persisting; training log CRUD and progress summary.

**Acceptance:** a beginner and intermediate dancer each receive a feasible 7-day plan; duration constraints are met; tool errors have graceful handling; 15–20 agent test cases cover tool selection and invalid inputs.

### Week 4 — Crew scheduling, RBAC and authorization

**IBM focus:** LangGraph state/checkpointing, scoped tool calls; MCP fundamentals only if time permits.

**Build:** crew membership roles, availability slots, deterministic scheduling service, candidate-slot ranking, event proposal/confirmation; automated authorization checks on both API and agent tool paths.

**Security tests:** an authenticated Crew A member cannot read, propose a write, or modify Crew B resources; only authorized roles can create/edit events; reject unapproved actions.

**Acceptance:** a crew admin receives ranked slots, confirms one and creates a rehearsal; tenant-isolation tests pass. Optional: expose one read-only scheduling tool via MCP.

### Week 5 — Event management, n8n, small OCR/VLM proof of concept

**Study:** webhook triggers, retries, idempotency, event-driven workflow; document OCR and structured extraction at a high level.

**Build:** event create/edit/cancel, RSVPs and notifications via n8n; record delivery outcomes. Stretch goal: upload a dance-event flyer, parse title/date/location into a validated draft using OCR or VLM, and require user approval before event creation.

**Acceptance:** a confirmed rehearsal triggers one notification per recipient; a retried webhook does not cause duplicate sends. OCR demo must clearly mark unknown or low-confidence fields.

### Week 6 — Local inference and optional caching experiment

**Study:** Ollama/llama.cpp basics; prompt prefill vs decode; KV cache; quantization; TTFT and throughput. Read about vLLM architectural tradeoffs; no GPU deployment obligation on a Mac.

**Build:** configurable model-provider adapter; one suitable local model; benchmark fixed test prompts; optionally test Redis caching for a selected read-heavy endpoint, including invalidation behavior.

**Metrics:** TTFT (when available), output tokens/sec, P50/P95 latency, memory and task/tool-call success. Record model, quantization, hardware, warm-up and load conditions; do not claim a fair engine comparison if different models/hardware are used.

**Acceptance:** reproducible measurements and a short tradeoff report; app still works with the original provider.

### Week 7 — Reliability, evaluation and observability

**IBM focus:** capstone/advanced-agent lessons relevant to gaps; do not repeat solved material.

**Build:** unit + integration tests, structured logging and correlation/run IDs; RAG/agent regression suite; basic load test; failure handling for missing sources, model timeout, DB outage and rejected writes; lightweight performance summary.

**Acceptance:** tests pass in a clean environment; report explains quality, latency, errors and known limitations; secrets and personal details are redacted from logs.

### Week 8 — Deployment, CI and portfolio delivery

**Study:** Docker Compose, GitHub Actions, operational checks and engineering documentation.

**Build:** reproducible local stack (FastAPI, MySQL, Qdrant; n8n when needed), startup instructions, migrations, tests in CI, architecture diagram, screenshots/demo, evaluation reports, security notes, design decisions.

**Acceptance:** clone → configure `.env` → start containers → migrate DB → run tests → demonstrate the six MVP features, with documented gaps if any.

### If schedule slips

Ship in this order: **(1) training API → (2) evaluated RAG → (3) working coach → (4) crew/event workflows → (5) notifications + RBAC → (6) benchmark/observability**. Treat OCR/VLM, Redis and local-inference comparisons as optional if the six core features or tests are incomplete.

## 7. Codex collaboration protocol: learn every change

Codex is an **implementation partner**, not an authority on architecture or correctness. For each issue, use this bounded workflow:

1. **You define the outcome**: user story, explicit inputs/outputs, acceptance tests, allowed file scope and non-goals.
2. **Ask Codex to inspect and propose a plan only**: list files to change, dependencies, tradeoffs and potential risks. Do not edit yet.
3. **Review the plan yourself**: ask why the proposed pattern is needed and reject unnecessary abstraction.
4. **Authorize one small implementation step**: preferably one endpoint, one tool, or one test module per iteration; prevent broad refactors.
5. **Require evidence**: run appropriate tests and show results, errors and any commands not run.
6. **Review the diff** (`git diff`, `git status`): understand each added file, the execution/data flow and the reason for each dependency.
7. **Ask for a teaching handoff**: explain each changed module, important functions, alternatives and one mini-exercise you can complete without AI.
8. **Commit after approval**: use a focused Git commit message; no unattended push, secrets, deployments, or destructive DB commands.

### Required Codex handoff format

For every implementation, request:

- **Goal / assumptions**
- **Plan and why this design**
- **Files changed and purpose of each**
- **Request/data flow walkthrough**
- **Tests run and results** (or what could not be run)
- **Risks, limitations, alternatives**
- **What I should be able to explain in an interview**
- **One small exercise for me to do manually**

### Starter Codex prompt — planning only

```text
Read docs/development-roadmap.md and inspect the current repository.
We are starting Week 1 of DanceFlow AI.
Do not edit any files yet.
Propose the smallest FastAPI backend skeleton that supports GET /health
and a validated POST /api/v1/training-plans/draft placeholder.
Explain the responsibility of every proposed file, the request lifecycle,
why each dependency is necessary, and which pytest tests should be written.
Keep the design beginner-readable and avoid unnecessary abstractions.
Wait for my approval before implementation.
```

### Starter Codex prompt — one bounded implementation

```text
Implement only the approved Week 1 API skeleton.
Before changing files, summarize what you will do.
Use Python, FastAPI, Pydantic and pytest. Do not add an LLM provider or database
until the endpoint contracts and tests work.
Avoid editing unrelated files, touching secrets or making Git commits.
Afterward, run the relevant tests; give me a file-by-file explanation,
request-flow walkthrough, test results, tradeoffs and one manual exercise.
```

### Repository-level agent rules

Once the skeleton works, add a short `AGENTS.md` at the repo root with the scope, approved architecture, test commands and rules above so Codex gets the same expectations across sessions. Review changes to `AGENTS.md` like code. Keep approval/security protections enabled, and use a dedicated Git branch for substantial Codex tasks.

## 8. Definition of Done (DoD) for each feature

- [ ] User-facing acceptance criterion demonstrated with a repeatable example.
- [ ] API schemas, validation and error cases defined.
- [ ] Role checks and tenant isolation applied where relevant.
- [ ] At least one happy-path test and one failure/edge-case test.
- [ ] Logs avoid secrets and unnecessary personal data.
- [ ] Documentation and example command/request updated.
- [ ] Codex-generated diff inspected and explained in human terms.
- [ ] Feature committed to Git only after review.

## 9. Required portfolio evidence

- `docs/architecture.md`: context, components, trust boundaries and decisions.
- `docs/adr/`: brief architecture decision records (e.g. modular monolith vs microservices; Agent vs deterministic scheduler).
- `evaluations/rag/`: labeled set, metrics, baseline-vs-reranking comparison.
- `evaluations/agents/`: tool selection and task success/error cases.
- `evaluations/inference/`: exact model/hardware/settings and latency/throughput results.
- `tests/` or `backend/tests/`: runnable automated tests.
- `README.md`: setup, supported features, limitations, demo walkthrough and architecture image.

## 10. First issue: DF-001 — FastAPI foundation

**User story:** As a developer, I can start a local API, inspect the OpenAPI docs, and submit a validated training-plan draft request.

**Tasks:**

- [ ] Confirm project tree and Python environment.
- [ ] Implement `GET /health` returning a simple health status.
- [ ] Define `TrainingPlanDraftRequest` with dance style, level, goals, days/week (1–7) and minutes/session (>0).
- [ ] Implement `POST /api/v1/training-plans/draft` as a **placeholder**, without an LLM call or DB write.
- [ ] Add pytest tests for valid request, invalid days/week and health.
- [ ] Document local startup and test commands.
- [ ] Review Codex diff and write down how requests enter FastAPI and are validated by Pydantic.

**Done when:** local startup, Swagger docs and automated tests pass; you can independently explain routing, validation, response serialization and status codes.

## 11. Planned later extensions

- **Multimodal event ingestion:** flyer OCR/VLM → structured event draft → human confirmation.
- **Video coaching:** video upload → pose landmarks + audio onset/beat extraction → synchronized features → evidence-grounded LLM feedback; evaluate timing reliability and avoid overclaiming coaching accuracy.
- **Embedding fine-tuning:** domain queries, carefully labeled positives/hard negatives, train/validation/test split, compare retrieval quality with unchanged evaluation set.
- **Infrastructure:** Redis for justified caching, centralized Loki/ELK logs if operational need exists, gRPC/NATS only if service topology warrants them, GPU/vLLM benchmarks when appropriate hardware is available.

---

**Guiding principle:** Build the simplest correct end-to-end feature, measure it, understand every agent-written change, and only then add complexity.
