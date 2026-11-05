# SkillBridge AI — Phase 4 Implementation Plan

## Top-Level Overview

Phase 4 transforms SkillBridge AI from a rule-based prototype into a production-ready, AI-powered platform in four areas:

1. **AI/LLM Integration** — Replace the rule-based `career_assistant.py` and static roadmap with IBM watsonx.ai foundation model calls, with a rule-based fallback when the API is unavailable.
2. **Candidate Profiles and Authentication** — Add registration, login, session management, per-user data isolation, and privacy/consent notices.
3. **Resume Intelligence and RAG** — Chunk uploaded resumes, embed them using watsonx.ai, store vectors in a local SQLite-friendly store (or ChromaDB), and retrieve relevant context to ground AI career recommendations.
4. **Production Hardening** — Structured logging, input validation, Docker/CI-CD, WCAG 2.1 AA accessibility improvements, and a clear privacy notice.

### Invariants

- All existing Phase 1–3 routes, tests (`test_phase1.py`, `test_phase2.py`, `test_phase3.py`), database records, and agent APIs must continue to work without modification.
- The rule-based assistant and roadmap remain as the fallback path used when the AI is unavailable or API keys are not configured.
- No external API calls may be made without a valid `WATSONX_API_KEY` being present in the environment.

---

## Required IBM watsonx Credentials

To use watsonx.ai you will need:

| Credential | Where to obtain | Environment variable |
|---|---|---|
| API key | IBM Cloud → Manage → Access → API keys | `WATSONX_API_KEY` |
| Project ID | watsonx.ai studio → Manage → General → Project ID | `WATSONX_PROJECT_ID` |
| Service URL | Region-specific, e.g. `https://us-south.ml.cloud.ibm.com` | `WATSONX_URL` |

**⚠️ Verified model status (as of November 2026):**

| Role | Recommended model ID | Status | Notes |
|---|---|---|---|
| Text generation | `ibm/granite-4-h-small` | ✅ Active, multitenant | 30B param, Class 18 input / Class 5 output, 131k context |
| Embeddings | `ibm/granite-embedding-278m-multilingual` | ✅ Active, multitenant | 768-dim, 512 token limit, 12 languages incl. English, Class C1 |

**Models that must NOT be used** (deprecated/withdrawn by the plan's execution date):
- `ibm/granite-3-3-8b-instruct` — deprecated 24 Nov 2025, withdrawn 22 Feb 2026
- `ibm/granite-3-8b-instruct` — deprecated 24 Nov 2025, withdrawn 22 Feb 2026
- `ibm/slate-125m-english-rtrvr` — withdrawn 12 Nov 2025
- `ibm/slate-125m-english-rtrvr-v2` — deprecated 8 May 2026, withdrawn 8 Aug 2026
- `ibm/granite-embedding-107m-multilingual` — withdrawn 12 Nov 2025

**Lite plan quota (verified):**
- 300,000 tokens/month free; rate-limited to 2 inference requests/second
- A typical career guidance call: ~300–800 tokens (input prompt + output)
- Embedding one 3-page resume in chunks (~1,500 tokens): counts toward the 300k quota
- 300k tokens ÷ ~600 tokens/call ≈ 500 free AI guidance calls per month on the Lite plan
- Essentials plan: pay-as-you-go at $0.0001 × model_multiplier per RU (1 RU = 1,000 tokens). Granite 4 Small input Class 18 = $0.0018/1k input tokens. 1,000 calls × ~600 tokens ≈ $1.08 input cost — extremely low for a demo app.

**Configuration env vars (model IDs overridable at runtime):**

---

## Dependency Map

```
Step 1  (AI client wrapper)         — no codebase dependencies; standalone new module
Step 2  (Auth DB + routes)          — depends on existing init_db() pattern
Step 3  (Auth UI)                   — depends on Step 2
Step 4  (AI career assistant)       — depends on Step 1; career_assistant.py becomes fallback
Step 5  (AI roadmap)                — depends on Step 1; roadmap_agent.py becomes fallback
Step 6  (Resume chunking + embed)   — depends on Step 1; resume_parser.py stays unchanged
Step 7  (RAG retrieval)             — depends on Steps 2 + 6 (user context + embeddings)
Step 8  (Per-user data isolation)   — depends on Steps 2 + 3 (auth session)
Step 9  (Privacy notice)            — depends on Step 3 (UI)
Step 10 (Production hardening)      — independent; can run alongside any step
Step 11 (Phase 4 test suite)        — depends on all prior steps
```

Sequencing constraint: Steps 1 → 2 → 3 must complete before any AI features surface to authenticated users. Steps 4–8 can then proceed in parallel workstreams.

---

## Sub-Tasks

---

### Sub-Task 1 — AI Client Wrapper Module

**Status**: `[x] done`

**Intent**

Create a single, thin wrapper (`agents/ai_client.py`) that encapsulates all watsonx.ai SDK calls. Every other agent that needs AI will import only this wrapper. This isolates the IBM SDK dependency, makes the fallback toggle trivial, and keeps credentials handling in one place.

**Expected Outcomes**

- New file `agents/ai_client.py` with two public functions: `generate_text(prompt, max_tokens)` and `embed_texts(texts)`.
- Both functions return `None` when `WATSONX_API_KEY` is absent or the call fails, triggering caller-side fallback.
- No existing file is modified.
- `ibm-watsonx-ai` added to `requirements.txt`.

**Todo List**

1. Add `ibm-watsonx-ai>=1.0` to `requirements.txt`.
2. Create `agents/ai_client.py`:
   - Read `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL` from `os.environ`.
   - If any env var is missing, set `_AI_AVAILABLE = False` and log a warning.
   - Implement `generate_text(prompt: str, max_tokens: int = 512) -> str | None` using `ModelInference` from `ibm_watsonx_ai.foundation_models`. Wrap in try/except; return `None` on any error.
   - Implement `embed_texts(texts: list[str]) -> list[list[float]] | None` using `Embeddings` from `ibm_watsonx_ai.foundation_models`. Wrap in try/except; return `None` on any error.
   - Expose `is_available() -> bool` for callers to check before calling.
3. Create `.env.example` in project root documenting all four env vars (`SECRET_KEY`, `WATSONX_API_KEY`, `WATSONX_PROJECT_ID`, `WATSONX_URL`) with placeholder values and instructions.

**Relevant Context**

- IBM SDK pattern from docs: `ModelInference(model_id=..., credentials={"apikey":..., "url":...}, project_id=...)`.
- Embedding pattern: `Embeddings(model_id="ibm/granite-embedding-278m-multilingual", credentials=..., project_id=...)` — this is the current non-deprecated replacement; do NOT use `slate-125m-english-rtrvr` (withdrawn Nov 2025).
- Default chat model: `ibm/granite-4-h-small` (active multitenant, Nov 2026) — do NOT use `granite-3-3-8b-instruct` (withdrawn Feb 2026).
- Both model IDs are read from `WATSONX_CHAT_MODEL` / `WATSONX_EMBED_MODEL` env vars at runtime so they can be updated without code changes.
- Existing `agents/__init__.py` is empty — no import changes needed there.

---

### Sub-Task 2 — Authentication Database Tables and Backend

**Status**: `[ ] pending`

**Intent**

Add `users` table and update `applications`/`candidates`/`roadmaps` tables to carry a `user_id` foreign key. Extend `init_db()` using the existing `_safe_add_column()` pattern so existing records are preserved. Implement Flask-Login or manual session-based auth routes.

**Expected Outcomes**

- `users` table created with `id`, `email` (unique), `password_hash`, `display_name`, `created_at`, `consent_given` (INTEGER 0/1), `consent_at` (TIMESTAMP).
- `applications` table gains `user_id` column (nullable for legacy rows).
- `candidates` table gains `user_id` column.
- `roadmaps` table gains `user_id` column.
- Flask routes added: `GET/POST /register`, `GET/POST /login`, `GET /logout`.
- Passwords hashed with `werkzeug.security.generate_password_hash` (pbkdf2:sha256, already a dependency).
- Sessions use Flask's existing signed cookie mechanism (`SECRET_KEY` env var).
- All new routes return appropriate flash messages on success/error.
- No existing routes or tests broken.

**Todo List**

1. In `app.py` → `init_db()`:
   - Add `CREATE TABLE IF NOT EXISTS users` statement.
   - Call `_safe_add_column()` to add `user_id` (INTEGER DEFAULT NULL) to `applications`, `candidates`, `roadmaps`.
2. Add helper `get_current_user_id() -> int | None` that reads `session.get("user_id")`.
3. Add `/register` route (GET renders form, POST validates + inserts user + sets session).
4. Add `/login` route (GET renders form, POST checks credentials + sets session).
5. Add `/logout` route (GET clears session, redirects to `/`).
6. Add `consent_given` flag check on registration: user must tick a checkbox before account is created.

**Relevant Context**

- `werkzeug.security` is already installed (Werkzeug ≥3.0 in `requirements.txt`).
- Existing `get_db()` returns a `sqlite3.Connection`; same pattern applies.
- `_safe_add_column(conn, table, column, definition)` handles idempotent migration.
- Existing `SECRET_KEY` env var already used in `app.py` — sessions work out of the box.

---

### Sub-Task 3 — Authentication UI Templates

**Status**: `[ ] pending`

**Intent**

Add `login.html` and `register.html` templates that extend `base.html`. Update the topbar in `base.html` to show Login/Register links when logged out, and a username + Logout link when logged in. Add the consent checkbox to the register form.

**Expected Outcomes**

- `templates/login.html` renders a clean login form (email, password, submit).
- `templates/register.html` renders a registration form (display name, email, password, confirm password, consent checkbox with privacy notice link).
- `base.html` topbar conditionally shows auth links without breaking existing nav.
- Flash messages already in `base.html` handle login/register feedback.
- Existing pages render identically when user is not logged in (no regressions).

**Todo List**

1. Create `templates/login.html` extending `base.html` with a centred card form.
2. Create `templates/register.html` extending `base.html` with card form + consent checkbox.
3. Edit `templates/base.html` topbar: add a Jinja2 `{% if session.user_id %}` block showing "Hi, <name> | Logout", else "Login | Register" links.
4. Add minimal CSS to `static/css/style.css` for `.auth-card`, `.auth-form`, `.consent-row` if not already covered by `.card` and `.form-row`.

**Relevant Context**

- `base.html` is 35 lines; topbar section is the first 12 lines. The nav links pattern uses `<a href="...">` anchors.
- Existing CSS card/form styles (`.card`, `.form-row`, `.form-group`, `.button`) should cover most needs.
- Flash categories `success`/`error` already styled in `.flash.success` / `.flash.error`.

---

### Sub-Task 4 — AI-Powered Career Assistant

**Status**: `[ ] pending`

**Intent**

Create `agents/ai_career_assistant.py` that calls `ai_client.generate_text()` with a structured prompt. Update the `/assistant` route in `app.py` to call the AI assistant first; if `is_available()` is false or the call returns `None`, fall through to the existing `career_reply()` function.

**Expected Outcomes**

- New `agents/ai_career_assistant.py` with `ai_career_reply(message, language, user_context=None) -> str | None`.
- `/assistant` route transparently uses AI when available, rule-based when not.
- Response quality improves with AI: answers are contextual, not template-matched.
- Kannada language hint passed to the model via system prompt.
- Existing `test_phase2.py` career assistant tests still pass (they test the rule-based path which is now the fallback).

**Todo List**

1. Create `agents/ai_career_assistant.py`:
   - Import `ai_client`.
   - Build a system prompt: "You are a career guidance assistant for fresh graduates in Bengaluru, India. Be concise, practical, and encouraging. Reply in {language}."
   - Build a user prompt including the candidate's message and optionally their skills list.
   - Call `ai_client.generate_text(full_prompt, max_tokens=400)`.
   - Return the response string, or `None` on failure.
2. In `app.py` `/assistant` route:
   - Try `ai_career_assistant.ai_career_reply(message, language)`.
   - If result is `None`, call existing `career_reply(message, language)` as fallback.
   - Add `"source": "ai"` or `"source": "rule_based"` field to JSON response for transparency.
3. Update `/health` endpoint `phase` field to `"4"` and add `"ai_available": ai_client.is_available()`.

**Relevant Context**

- Existing `/assistant` route is in `app.py` ~line 200; accepts `{"message":..., "language":...}`.
- `career_reply()` is imported from `agents.career_assistant`.
- Adding `"source"` to the JSON response is additive — existing tests only check `"reply"` key.

---

### Sub-Task 5 — AI-Enhanced Roadmap Generator

**Status**: `[ ] pending`

**Intent**

Create `agents/ai_roadmap_agent.py` that uses watsonx.ai to produce a personalized learning roadmap narrative given a candidate's current skills, target job, and missing skills list. The existing `roadmap_agent.generate_roadmap()` output (structured steps with days/resources) remains the primary structured data; the AI adds a short personalized "coaching note" to each step and a summary paragraph.

**Expected Outcomes**

- New `agents/ai_roadmap_agent.py` with `enhance_roadmap(roadmap_dict, current_skills, job_title) -> dict`.
- The function adds a `"coaching_note"` field to each step in `roadmap_dict["ordered_steps"]`.
- Adds a `"ai_summary"` string field to the roadmap dict.
- Returns the dict unchanged (no coaching notes) if AI is unavailable.
- `/api/roadmap` and `/api/pipeline` routes call `enhance_roadmap()` after existing pipeline.
- Existing pipeline tests still pass (they check structural keys, not coaching notes).

**Todo List**

1. Create `agents/ai_roadmap_agent.py`:
   - Build a single prompt listing all missing skills + job title, asking for a short coaching note per skill and an overall summary.
   - Parse the AI response into per-skill notes (simple line-by-line or structured JSON request in the prompt).
   - Return enhanced roadmap dict or original if AI unavailable/fails.
2. In `app.py`, in `/api/roadmap` and `/api/pipeline` routes, call `enhance_roadmap()` on the result before returning JSON.
3. In `dashboard.html` roadmap section, optionally render `coaching_note` per step if present.

**Relevant Context**

- `roadmap_agent.generate_roadmap()` returns `{"ordered_steps": [{"skill":..., "stage":..., ...}], ...}`.
- The structured data (days, resources, exercises) stays from the rule-based catalog — AI only adds narrative notes.
- `dashboard.html` already renders `.roadmap-step-body` per step; coaching note can be a `<p class="muted">` inside.

---

### Sub-Task 6 — Resume Chunking and Embedding Storage

**Status**: `[ ] pending`

**Intent**

After a resume is uploaded and parsed, chunk its text and embed each chunk using watsonx.ai's `ibm/slate-125m-english-rtrvr` model. Store embeddings in a new `resume_chunks` SQLite table (using JSON-serialized vectors). This is the RAG data preparation step — retrieval comes in Sub-Task 7.

**Expected Outcomes**

- New `utils/embeddings.py` with `chunk_text(text, chunk_size=400, overlap=50) -> list[str]` and `embed_and_store(candidate_id, resume_filename, chunks) -> None`.
- New `resume_chunks` DB table: `id`, `candidate_id`, `resume_filename`, `chunk_index`, `chunk_text`, `embedding_json` (TEXT, JSON array of floats), `created_at`.
- `/resume` route calls `embed_and_store()` after skill extraction when AI is available and a `candidate_id` is in session.
- Resume files continue to be saved in `uploads/` unchanged.
- If AI unavailable, embedding step is skipped silently; existing skill extraction still works.

**Todo List**

1. Add `resume_chunks` table to `init_db()` in `app.py`.
2. Create `utils/embeddings.py`:
   - `chunk_text(text, chunk_size=400, overlap=50) -> list[str]`: splits text into overlapping character windows.
   - `embed_and_store(candidate_id, resume_filename, chunks, db_conn)`: calls `ai_client.embed_texts(chunks)`, serializes vectors to JSON, inserts rows into `resume_chunks`.
3. In `/resume` route in `app.py`, after existing `extract_skills()` call:
   - If `ai_client.is_available()` and `session.get("user_id")`:
     - Chunk the extracted text.
     - Call `embed_and_store()`.

**Relevant Context**

- `extract_resume_text()` in `utils/resume_parser.py` returns a plain string — use that as the chunking input.
- `ai_client.embed_texts(texts)` returns `list[list[float]]` or `None`.
- SQLite stores JSON as TEXT; use `json.dumps()` / `json.loads()` for serialization.
- `candidate_id` will need to be looked up or created from `session["user_id"]` — cross-reference the `candidates` table.

---

### Sub-Task 7 — RAG Retrieval for Grounded Recommendations

**Status**: `[ ] pending`

**Intent**

When a logged-in user requests career guidance or a roadmap, retrieve the top-k most relevant chunks from their stored resume embeddings using cosine similarity, and inject them as context into the AI prompt. This grounds the AI's advice in the candidate's actual experience.

**Expected Outcomes**

- New `utils/retrieval.py` with `retrieve_relevant_chunks(query_text, candidate_id, top_k=3) -> list[str]`.
- `ai_career_assistant.ai_career_reply()` accepts an optional `resume_context` parameter and includes chunks in the prompt.
- `ai_roadmap_agent.enhance_roadmap()` uses retrieved context when available.
- Retrieval falls back gracefully to no context if no chunks are stored for the user.
- Candidates can only retrieve their own chunks (filtered by `candidate_id`).

**Todo List**

1. Create `utils/retrieval.py`:
   - `retrieve_relevant_chunks(query_text, candidate_id, top_k=3, db_conn) -> list[str]`:
     - Embed `query_text` via `ai_client.embed_texts([query_text])`.
     - Load all `resume_chunks` rows for `candidate_id`.
     - Compute cosine similarity between query vector and each stored embedding.
     - Return `chunk_text` for top-k most similar chunks.
     - Return `[]` if AI unavailable or no chunks stored.
2. Update `ai_career_assistant.ai_career_reply()` to accept and include `resume_context: list[str]`.
3. In `/assistant` route, call `retrieve_relevant_chunks()` before calling AI, pass to `ai_career_reply()`.
4. Add cosine similarity helper (pure Python, no extra deps): `cosine_sim(a, b) -> float`.

**Relevant Context**

- Cosine similarity: `dot(a,b) / (norm(a) * norm(b))` — implementable in ~5 lines of pure Python with `math` stdlib only.
- The `resume_chunks` table is defined in Sub-Task 6.
- Data isolation: always filter DB query by `candidate_id` derived from `session["user_id"]`.

---

### Sub-Task 8 — Per-User Data Isolation

**Status**: `[ ] pending`

**Intent**

Ensure all data-writing routes (`/apply/<job_id>`, `/application/<app_id>/status`, `/api/pipeline`) stamp records with the current user's ID and that data-reading routes filter by it. Anonymous users retain full read access to job matching and skill analysis (stateless routes). Only application saving and tracker viewing are gated behind login.

**Expected Outcomes**

- `/apply/<job_id>`: requires login (redirect to `/login` if not); stamps `user_id` on `applications` row.
- `/tracker`: requires login; query filters `applications WHERE user_id = ?`.
- `/application/<app_id>/status`: validates `user_id` matches record owner before updating.
- `/dashboard`: if logged in, pre-populates skills from user's `candidates` row.
- Stateless API routes (`/api/match`, `/api/skill-gap`, `/api/roadmap`, `/api/pipeline`, `/assistant`, `/resume`) remain accessible without login.

**Todo List**

1. Add `@login_required` decorator (simple helper that checks `session.get("user_id")`, redirects to `/login?next=...` if absent).
2. Apply decorator to `/apply/<job_id>`, `/tracker`, `/application/<app_id>/status`.
3. In `/apply/<job_id>`: add `user_id=session["user_id"]` to the INSERT.
4. In `/tracker` GET: add `WHERE user_id = ?` filter.
5. In `/application/<app_id>/status` PATCH: add ownership check before UPDATE.
6. In `/dashboard`: if `session.get("user_id")`, look up most recent `candidates` row for that user and pre-fill `?skills=` param.

**Relevant Context**

- `applications` table already has `candidate_name`, `job_id`, `status`, `notes`, `created_at` — just needs `user_id` stamped (from Sub-Task 2 migration).
- `/tracker` currently queries `SELECT * FROM applications` — add `WHERE user_id = session_user_id` filter.
- The `next` redirect pattern: after login, send user back to the page they tried to reach.

---

### Sub-Task 9 — Privacy Notice and Consent

**Status**: `[ ] pending`

**Intent**

Add a standalone privacy notice page. Surface a consent banner on first visit. Ensure registration requires explicit consent before account creation (checkbox in the register form from Sub-Task 3). Add a clear "Demo data" disclaimer to job listings.

**Expected Outcomes**

- New `templates/privacy.html` extending `base.html` describing: what data is collected, how resumes are processed, that job listings are fictional, that data is stored locally, and how to delete an account.
- New `GET /privacy` route in `app.py`.
- On `index.html` and `jobs.html`, demo data disclaimer banner is visible.
- Cookie/consent banner in `base.html` appears on first visit (localStorage flag); links to `/privacy`.
- Register form has required consent checkbox that links to `/privacy`.

**Todo List**

1. Create `templates/privacy.html` with structured sections: Data Collected, How Resumes Are Used, AI Processing, Demo Data Notice, Data Deletion, Contact.
2. Add `GET /privacy` route in `app.py`.
3. Add consent banner HTML to `base.html` (hidden by default; shown via JS if `localStorage.getItem("sb_consent")` is null).
4. Add JS in `app.js` to show/hide consent banner and set `sb_consent` flag on dismiss.
5. Add "Demo job listings — fictional data" banner to `templates/jobs.html` (a styled `.flash.info` or dedicated `.demo-notice` element).
6. Ensure the register form consent checkbox (from Sub-Task 3) links to `/privacy` in a `target="_blank"` anchor.

**Relevant Context**

- `base.html` footer already exists — consent banner can be a fixed-bottom strip appended before `</body>`.
- `localStorage` is already used for language preference (`sb_lang`) — same pattern applies.
- `.flash.info` CSS class is already defined in `style.css`.

---

### Sub-Task 10 — Production Hardening

**Status**: `[ ] pending`

**Intent**

Add structured logging, input validation improvements, a `Dockerfile`, a GitHub Actions CI workflow, and targeted WCAG 2.1 AA accessibility fixes. None of these changes touch the business logic or break existing tests.

**Expected Outcomes**

- `Dockerfile` that runs the Flask app with Gunicorn on port 8080.
- `.github/workflows/ci.yml` that installs deps and runs all three test files on push.
- `logging` module configured in `app.py` with structured format (timestamp, level, message).
- Input validation tightened in API routes: max skill-string length, sanitize name fields.
- Accessibility: `<label for=...>` on all form inputs in templates; `aria-label` on icon buttons; `alt` text on any images; colour contrast verified against design tokens (existing token `--blue: #315ce8` on white passes AA).
- All three existing test files still pass.

**Todo List**

1. Create `Dockerfile`:
   - Base: `python:3.11-slim`
   - `COPY requirements.txt .` → `pip install`
   - `COPY . .`
   - `ENV FLASK_ENV=production`
   - `CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]`
   - Add `gunicorn>=21` to `requirements.txt`.
2. Create `.github/workflows/ci.yml`:
   - Trigger: push + pull_request on `main`.
   - Job: `ubuntu-latest`, Python 3.11, install deps, run `python tests/test_phase1.py && python tests/test_phase2.py && python tests/test_phase3.py`.
3. In `app.py`, add `logging.basicConfig()` at top with format `%(asctime)s %(levelname)s %(name)s: %(message)s`.
4. Add `logger = logging.getLogger(__name__)` and replace bare `print()` statements with `logger.info()` / `logger.error()`.
5. In API routes, add length checks: skill strings ≤1000 chars, name fields ≤200 chars; return 400 with JSON error on violation.
6. Audit all 4 template forms for missing `<label for="...">` associations and add where absent.
7. Add `role="main"` and `aria-label` to primary content areas in `base.html`.

**Relevant Context**

- `app.py` currently uses `app.run(debug=True)` at the bottom — Gunicorn ignores this but it should be guarded with `if __name__ == "__main__":`.
- The CI workflow only needs to run the existing test files — no new test runner setup required.
- Accessibility audit targets: `templates/index.html`, `templates/jobs.html`, `templates/dashboard.html`, `templates/tracker.html`.

---

### Sub-Task 11 — Phase 4 Test Suite

**Status**: `[ ] pending`

**Intent**

Create `tests/test_phase4.py` that covers all new Phase 4 functionality: AI client fallback, authentication routes, data isolation, RAG retrieval, privacy notice, and production endpoint changes.

**Expected Outcomes**

- `tests/test_phase4.py` passes with `python tests/test_phase4.py`.
- Covers: AI client returns `None` gracefully when no API key set; register/login/logout cycle; duplicate email rejected; unauthenticated `/apply` redirects to login; `/tracker` only returns current user's applications; `/privacy` route returns 200; `/health` reports `phase: "4"`.
- All existing Phase 1–3 tests still pass unchanged.

**Todo List**

1. Create `tests/test_phase4.py` with test runner matching existing style (plain `assert` statements, `print("PASS")`).
2. Test AI client: import `ai_client`; assert `is_available()` is `False` when env vars absent; assert `generate_text("hello")` returns `None`.
3. Test auth: register new user → login → check session → logout → check session cleared.
4. Test duplicate email: register same email twice → second attempt returns error response.
5. Test auth guard: `POST /apply/<job_id>` without session → 302 redirect to `/login`.
6. Test data isolation: register two users, each saves an application → verify `/tracker` shows only own applications.
7. Test `/privacy` returns 200 with "privacy" keyword in body.
8. Test `/health` returns `phase: "4"` and `ai_available` key in JSON.

**Relevant Context**

- Existing tests use `app.test_client()` from Flask; same pattern applies.
- `test_phase2.py` tests `/application/<id>/status` and `/dashboard` — ensure those tests still pass after the `user_id` ownership check (legacy rows with `user_id = NULL` should be treated as accessible to any session for backward compat, OR the test seeds its own app row).
- Consider whether test_phase2's application tests need a session fixture for the new ownership check.

---

## Security Risks and Mitigations

| Risk | Mitigation |
|---|---|
| API key exposure | Loaded from env vars only; never committed; `.env.example` contains only placeholders; `.gitignore` excludes `.env` |
| SQL injection | All DB queries already use parameterised `?` placeholders — maintain this pattern |
| Weak passwords | `werkzeug.security.generate_password_hash` with pbkdf2:sha256; enforce minimum 8-char password in form validation |
| Session fixation | Call `session.clear()` before setting new `user_id` on login |
| File upload abuse | Existing extension whitelist + 5 MB limit already in place; also validate MIME type in Sub-Task 6 |
| Resume data leakage | `resume_chunks` always filtered by `candidate_id`; `candidate_id` derived from authenticated `session["user_id"]` only |
| CSRF | Flask sessions use HMAC-signed cookies; for full protection consider adding `flask-wtf` CSRF tokens in a later phase |
| Insecure defaults | `SECRET_KEY` must be overridden in production; log a startup warning if it equals the hardcoded dev value |

---

## Configuration Reference (`.env.example`)

```
# Flask
SECRET_KEY=change-me-in-production

# IBM watsonx.ai (required for AI features; app runs in rule-based mode without these)
WATSONX_API_KEY=your-ibm-cloud-api-key
WATSONX_PROJECT_ID=your-watsonx-project-id
WATSONX_URL=https://us-south.ml.cloud.ibm.com

# Override default model IDs (defaults shown; verified active as of Nov 2026)
# Do NOT use deprecated models: granite-3-3-8b-instruct, granite-3-8b-instruct,
# slate-125m-english-rtrvr, slate-125m-english-rtrvr-v2, granite-embedding-107m-multilingual
WATSONX_CHAT_MODEL=ibm/granite-4-h-small
WATSONX_EMBED_MODEL=ibm/granite-embedding-278m-multilingual
```

---

## File Change Summary

| File | Action | Sub-Tasks |
|---|---|---|
| `requirements.txt` | Add `ibm-watsonx-ai>=1.0`, `gunicorn>=21` | 1, 10 |
| `agents/ai_client.py` | **New** — watsonx.ai SDK wrapper | 1 |
| `.env.example` | **New** — env var documentation | 1 |
| `agents/ai_career_assistant.py` | **New** — AI-powered assistant | 4 |
| `agents/ai_roadmap_agent.py` | **New** — AI roadmap enhancer | 5 |
| `utils/embeddings.py` | **New** — chunking + embedding storage | 6 |
| `utils/retrieval.py` | **New** — cosine similarity RAG retrieval | 7 |
| `app.py` | Extend `init_db()`, add auth routes, update existing routes | 2, 8, 9, 10 |
| `templates/base.html` | Add auth nav links, consent banner | 3, 9 |
| `templates/login.html` | **New** | 3 |
| `templates/register.html` | **New** | 3 |
| `templates/privacy.html` | **New** | 9 |
| `templates/jobs.html` | Add demo data disclaimer banner | 9 |
| `templates/dashboard.html` | Render AI coaching notes if present | 5 |
| `static/css/style.css` | Add `.auth-card`, `.consent-banner`, `.demo-notice` if needed | 3, 9 |
| `static/js/app.js` | Add consent banner show/hide logic | 9 |
| `Dockerfile` | **New** | 10 |
| `.github/workflows/ci.yml` | **New** | 10 |
| `tests/test_phase4.py` | **New** | 11 |

**Files that must NOT be modified** (Phase 1–3 invariants):
`agents/orchestrator.py`, `agents/job_matcher.py`, `agents/skill_analyzer.py`, `agents/roadmap_agent.py`, `agents/career_assistant.py`, `utils/resume_parser.py`, `tests/test_phase1.py`, `tests/test_phase2.py`, `tests/test_phase3.py`
