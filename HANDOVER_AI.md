
> **Audience:** Senior developer taking over this project with no prior context.
> **Date written:** 2026-05-19
> **Branch at time of writing:** `PV-121-implement-acceptable-language`
> **Last commit:** `95f764f — PV-121 Implement Acceptable Language`

---

## 1. PROJECT OVERVIEW

### What this project is

PV-AI is a FastAPI backend that powers a **voice-to-review** workflow. A user records a voice note about a restaurant or business; the backend transcribes it with Whisper, runs it through a Groq-hosted LLaMA model for analysis and text improvement, and stores the live chat session in Redis. The project also contains stub modules for task management, memos, and lists that are not yet wired to any real database.

### Tech stack — exact versions from `requirements.txt`

| Package | Version |
|---|---|
| fastapi | 0.110.0 |
| uvicorn | 0.27.1 |
| pydantic | 2.6.1 |
| python-jose[cryptography] | 3.3.0 |
| passlib[bcrypt] | 1.7.4 |
| python-multipart | 0.0.9 |
| openai-whisper | (no pin — latest at install time) |
| torch | (no pin — latest at install time) |
| python-dotenv | 1.0.1 |
| numpy | (no pin) |
| requests | (no pin) |
| groq | (no pin) |
| redis | (no pin) |
| sqlalchemy | (no pin) |
| alembic | (no pin) |

> `torch`, `openai-whisper`, `sqlalchemy`, and `alembic` have no pinned versions — this is a stability risk. Pinning them is a recommended next step.

### How to run locally

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and fill in environment variables
copy .env .env.local            # or create .env from the template below

# 4. Start Redis (see Section 12 for Docker command)

# 5. Start the server
uvicorn main:app --reload --port 5000

# Or use the __main__ entrypoint:
python main.py
```

The API will be available at `http://localhost:5000`.
Interactive docs are at `http://localhost:5000/docs`.

### Environment variables required

All variables are read in `config.py:1-27` via `python-dotenv`. The `.env` file (gitignored) currently contains:

| Variable | Current value in `.env` | Purpose |
|---|---|---|
| `JWT_SECRET` | `test-secret-key` | Signs JWT tokens — **must be a strong random string in production** |
| `OPENAI_API_KEY` | `test-key` | Declared but **not used anywhere** in the active codebase |
| `YELP_API_KEY` | `test-key` | Declared but **not used anywhere** — Yelp search is static data |
| `GROQ_API_KEY` | `gsk_Rx...` (real key committed) | Required for all chat and AI inference — **rotate this key immediately** |
| `REDIS_HOST` | `localhost` | Redis server hostname |
| `REDIS_PORT` | `6379` | Redis server port |
| `WHISPER_MODEL` | `tiny` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Groq model identifier — any Groq-hosted model name works here |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:19006` | Comma-separated list for CORS |

> **Security warning:** A real Groq API key was previously stored in the `.env` file. Because `.env` is in `.gitignore` it should not be in the remote repository, but you must regenerate this key as a precaution.

### Redis and database dependencies

| Dependency | Status | Notes |
|---|---|---|
| Redis | **Required at runtime** | Chat session state. App returns HTTP 503 if Redis is down. |
| PostgreSQL / any SQL DB | **Not connected** | `models.py` defines SQLAlchemy models but `database.py` returns a mock. `alembic` is installed but no migrations exist. |
| Milvus (vector DB) | **Mocked** | `database.py` provides `MockMilvusClient` — all data lives only in process memory. |

---

## 2. COMPLETED FEATURES

### `auth.py` — prefix `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | No | Accepts any JSON body, generates a UUID, returns a JWT. Does **not** persist the user. |
| POST | `/api/auth/login` | No | Returns a hardcoded `fake-test-token` and `TEST_USER_ID`. No password check. |
| POST | `/api/auth/token/relay` | X-BFF-Secret header | Service-to-service only. BFF passes its shared secret + a `user_id`; pv-ai issues a 30-min relay JWT with `"relay": true` claim. No DB lookup. |

**Dependencies:** `python-jose`, `passlib`, `MockMilvusClient`
**Auth bypass:** `get_current_user()` (`auth.py:26-28`) always returns `{"id": "test-user-id-001"}` regardless of token. This is global across all routers.

### `yelp.py` — prefix `/api/yelp`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/yelp/search` | No | Returns a filtered subset of 6 hardcoded Tunisian businesses. Supports `term` or `query` query params. |
| POST | `/api/yelp/reviews` | No | Generates a UUID review ID. Does **not** persist anything. |
| PUT | `/api/yelp/reviews/{review_id}/transcription` | No | Validates language (en/es/fr), echoes back the transcription data. Does not persist. |

**Dependencies:** `config.ACCEPTED_LANGUAGES`
**Data:** 6 static businesses hardcoded in `yelp.py:11-18` (McDonalds, Starbucks, Pizza Hut, KFC, Plan B — all in Tunis).

### `chat.py` — prefix `/api/chat`

This is the **primary production-quality module**.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/chat/start` | No | Validates language, optionally pre-populates chat history from `previous_messages`, calls Groq to generate initial review analysis, creates Redis session. Returns `session_id` and `initial_response`. |
| POST | `/api/chat/message` | No | Appends user message to Redis history, calls Groq for continuation, saves updated history. |
| POST | `/api/chat/approve` | No | Calls Groq with a JSON-extraction prompt over the full conversation history; parses result; makes a second Groq call for a plain-text conversation summary; marks session `approved` in Redis. Returns structured review object plus `conversation_summary`. |
| POST | `/api/chat/end` | No | Deletes the Redis session key. |
| GET | `/api/chat/session/{session_id}` | No | Returns the full raw session object from Redis. |

**Dependencies:** Groq API (real), Redis (real), `prompts.REVIEW_ANALYSIS_PROMPT`

### `transcription.py` — prefix `/api`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health-check/transcribe` | No | Returns Whisper status, device (cpu/cuda), and db_mode. |
| POST | `/api/transcribe` | No | Accepts a multipart audio file upload. Saves to temp file, runs Whisper, validates detected language, returns transcription text and language code. |

**Dependencies:** OpenAI Whisper (loaded at startup), PyTorch, `config.ACCEPTED_LANGUAGES`, `config.WHISPER_MODEL`

### `lists.py` — prefix `/api/lists`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/lists/` | No | Queries MockMilvusClient `users` collection. Returns in-process data only. |
| POST | `/api/lists/` | No | Inserts into MockMilvusClient `lists` collection. No persistence. |

**Dependencies:** `MockMilvusClient`

### `memos.py` — prefix `/api/memos`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/memos/` | No | Returns empty list `[]`. Always. |
| POST | `/api/memos/` | No | Returns a UUID and success flag. Does not persist. |
| GET | `/api/memos/search` | No | Returns empty list `[]`. Always. |

**Dependencies:** `MockMilvusClient` (imported but not used in the active code)

### `tasks.py` — prefix `/api/tasks`

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/tasks/` | No | Queries MockMilvusClient `tasks` collection with filter expression. In-process only. |
| POST | `/api/tasks/` | No | Inserts into MockMilvusClient. Includes dummy vector `[0.0, 0.0]`. |
| PATCH | `/api/tasks/{task_id}` | No | Upserts to MockMilvusClient. |
| DELETE | `/api/tasks/{task_id}` | No | Calls MockMilvusClient delete (no-op). |

**Dependencies:** `MockMilvusClient`

---

## 3. CURRENT FILE STRUCTURE

```
pv-ai/
├── main.py              # FastAPI app factory, CORS, request logging, router registration
├── config.py            # All env-var loading and shared constants
├── database.py          # MockMilvusClient — in-memory data store, no real DB
├── models.py            # SQLAlchemy ORM models (User, Task, List, Memo, YelpReview, etc.)
├── auth.py              # /api/auth router — register/login stubs + global auth bypass
├── yelp.py              # /api/yelp router — static business data + mock review records
├── chat.py              # /api/chat router — PRODUCTION: full Groq+Redis chat session flow
├── transcription.py     # /api router — PRODUCTION: Whisper speech-to-text
├── redis_client.py      # Redis CRUD helpers for session management
├── prompts.py           # All LLM prompt strings
├── ai_engine.py         # Standalone Groq extraction function — DEAD CODE (not imported)
├── lists.py             # /api/lists router — MockMilvusClient stub
├── memos.py             # /api/memos router — returns empty data, no persistence
├── tasks.py             # /api/tasks router — MockMilvusClient stub
├── verify.py            # End-to-end integration test script for the chat flow
├── requirements.txt     # Python dependencies
├── .env                 # Secrets and config (gitignored — contains real Groq key!)
├── sonar-project.properties  # SonarQube project key
├── .vscode/settings.json     # SonarLint connected mode config
├── .github/workflows/sonar.yml  # SonarQube scan on push to `dev`
├── test_english.mp3     # Test audio file
├── test_french.mp3      # Test audio file
├── test_spanish.mp3     # Test audio file
├── test_arabic.mp3      # Test audio file
└── test_transcribe.html # Frontend test harness for transcription (gitignored)
```

### Production quality vs stubs

| File | Quality | Notes |
|---|---|---|
| `chat.py` | Production | Full session lifecycle, error handling, Redis integration |
| `transcription.py` | Production | Real Whisper, temp file handling, language validation |
| `redis_client.py` | Production | Clean Redis wrapper with 503 on connection failure |
| `prompts.py` | Production | Prompts are functional; see fragility notes in Section 11 |
| `config.py` | Production | Clean env-var loading |
| `main.py` | Production | Proper middleware ordering, router registration |
| `auth.py` | Stub | Hardcoded TEST_USER_ID, no real password validation |
| `yelp.py` | Stub | Static data, no Yelp API calls, no DB persistence |
| `lists.py` | Stub | MockMilvusClient only, missing full CRUD |
| `memos.py` | Stub | Returns empty data everywhere |
| `tasks.py` | Partial stub | CRUD operations exist but backed by in-memory mock |
| `database.py` | Stub | MockMilvusClient only, no real DB connection |
| `models.py` | **Broken** | Imports `database.Base` which does not exist — will crash on import |
| `ai_engine.py` | Dead code | Defines `extract_review_insights()` but is never imported or called |

---

## 4. AI COMPONENTS

### 1. Whisper Speech-to-Text

- **File:** `transcription.py:14`
- **Model:** OpenAI Whisper, size configured by `WHISPER_MODEL` env var (default `tiny`)
- **Why:** Local, offline transcription that supports EN/FR/ES without external API calls
- **Input:** Audio file upload (`.webm` or any Whisper-supported format), optional `language` hint and `task` flag (`transcribe` or `translate`)
- **Output:** `{"success": true, "transcription": "...", "language": "en"}`
- **Limitations:**
  - The `tiny` model has significantly lower accuracy than `small`/`medium`/`large` — recommended upgrade to `small` for production
  - Model is loaded **at import time** (`transcription.py:14`); if loading fails, the entire app fails to start
  - Runs on CPU by default; CUDA is used automatically if available
  - Temporary file is written to the working directory as `temp_{uuid}.webm` — on Windows, this may conflict with antivirus scanners
  - Arabic test audio (`test_arabic.mp3`) is present, but Arabic is explicitly rejected at `transcription.py:56-60` (only en/es/fr allowed)

### 2. Groq LLaMA-3.3-70B — Review Analysis & Chat

- **File:** `chat.py:15`, `chat.py:56-63`
- **Model:** `llama-3.3-70b-versatile` (configurable via `LLM_MODEL` env var)
- **Why:** Fast inference via Groq API, no local GPU needed, high-quality instruction following
- **Input:** Full conversation history (`chat_history` array in OpenAI message format) plus a system prompt built from `REVIEW_ANALYSIS_PROMPT` and the listing context
- **Output:**
  - `/start`: Free-text AI response as initial review analysis
  - `/message`: Free-text AI continuation
  - `/approve`: Structured JSON `{improved_text, rating, sentiment, tone, key_points, conversation_summary}`
- **Limitations:**
  - The approve endpoint asks for JSON without enforcing `response_format: json_object` — relies on regex extraction and is fragile (see Section 11)
  - No retry logic on Groq 429 (rate limit) or 500 errors — any failure raises HTTP 502 immediately
  - `ai_engine.py` also instantiates a Groq client with a hardcoded model string `"llama-3.3-70b-versatile"` but is never called

### 3. `ai_engine.py` — Dead Code

- **File:** `ai_engine.py`
- **Model:** `llama-3.3-70b-versatile` (hardcoded at `ai_engine.py:7`, does not read from config)
- **Status:** Never imported or called from any router. Defines `extract_review_insights()` which uses `response_format={"type": "json_object"}` — a cleaner approach than the regex used in `chat.py`. This function should either be integrated into `chat.py` or deleted.

### 4. Whisper Small Fine-tuned — whisper-provoc-v1 ✅ COMPLETE

- **File:** `transcription.py` (loaded when `USE_FINETUNED_WHISPER=true`)
- **Training script:** `whisper_finetune.py`
- **Dataset:** MLS (Multilingual LibriSpeech) — EN/FR/ES — 300 samples per language (900 total)
- **Base model:** `openai/whisper-small`
- **GPU:** T4 on Kaggle — training time ~40 minutes
- **Steps:** 120 total, best checkpoint at step 60 (overfitting after step 60, handled by `load_best_model_at_end=True`)
- **Key fix:** Per-language tokenization — each sample tagged with its language token (`<|fr|>`, `<|es|>`, `<|en|>`) during training. Previous run had a bug where all samples were tokenized without a language tag, causing the model to forget French and Spanish.
- **MLflow run ID:** `f796b6a5972b45899f1701ee05ecf415`
- **Model saved at:** `./whisper-provoc-small/final` (set `FINETUNED_WHISPER_PATH` in `.env`)
- **Model zip downloaded:** `whisper-provoc-final-v2.zip` ✅
- **Registered in MLflow model registry as:** `whisper-provoc-v1`
- **Active:** `USE_FINETUNED_WHISPER=true` in `.env` — confirmed via `GET /api/health-check/transcribe`
- **Inference comparison script:** `whisper_inference_test.py` — loads MLS dev split (50 samples/lang, same eval set used during training) and compares WER between baseline and fine-tuned
- **MLflow server:** run standalone with `mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlflow-artifacts --host 0.0.0.0 --port 5001`

#### WER Results

**Kaggle training eval (harder/noisier samples):**

| | WER |
|---|---|
| Baseline | 70.18% |
| Fine-tuned | 55.19% |
| Relative improvement | 21.4% |

**Local verification — MLS dev split, clean audio (2026-05-22):**

| Language | Samples | Baseline WER | Fine-tuned WER | Delta |
|---|---|---|---|---|
| EN | 50 | 19.18% | 4.78% | -14.39% |
| FR | 50 | 36.06% | 20.67% | -15.39% |
| ES | 50 | 24.12% | 9.13% | -14.98% |
| **Average** | **150** | **26.45%** | **11.53%** | **-14.92%** |

**Relative improvement (local): 56.4%** — consistent ~15 point improvement across all 3 languages. No catastrophic forgetting observed.

#### Defense statement (verbatim)

> "By fine-tuning Whisper small on 900 multilingual audio samples across English, French and Spanish, we achieved a 56.4% relative WER reduction on the MLS dev split — from 26.45% to 11.53% — with consistent improvement of approximately 15 percentage points per language. On harder noisier samples the model achieves 21.4% relative improvement. Mild overfitting was observed after step 60 and handled automatically by saving the best checkpoint."

---

## 5. PROMPT ENGINEERING

All prompts live in `prompts.py`.

### `REVIEW_ANALYSIS_PROMPT` (`prompts.py:4-25`)

**Used by:** `chat.py:12` — imported as the system message for every chat session.

**What it does:** Sets the AI persona as a "Yelp review analyst expert". Instructs the model to extract restaurant name, sentiment, rating (explicit or inferred), and key points. Specifies a strict JSON response format. At the bottom of this prompt, `chat.py:43-53` appends a `BUSINESS CONTEXT` block with the business name, social networks, and network preferences from the request body.

**Language behavior:** The prompt is written in French but ends with the rule: *"Détectez la langue du texte et utilisez cette langue pour toute interaction future."* In practice the model mirrors the user's language (EN/FR/ES) because the conversation history carries language context across turns.

**Known fragility:**
- The prompt asks for strict JSON but does not enforce `response_format` at the API level in `/start` and `/message` — the AI may reply in prose on the first turn rather than JSON
- The `/approve` endpoint sends a separate JSON extraction prompt appended to the history (not part of this system prompt) and relies on regex to parse the result

### `REVIEW_INTERACTION_PROMPT` (`prompts.py:28-43`)

**Used by:** Nothing. This prompt is defined but **never imported or referenced** anywhere in the codebase. It was likely the original chat prompt before `chat.py` was refactored.

**What it does:** Step-by-step interaction flow: validate extracted data → ask user to confirm → offer to improve text → generate final report.

### `FINAL_REPORT_PROMPT` (`prompts.py:46-54`)

**Used by:** Nothing. Also dead code.

**What it does:** Asks the model to generate a final structured report with business name, sentiment, score, improved text, and advice.

### Language mirroring behaviour

The language is passed as a field (`body.language`) in the `/start` request and stored in the session as `detected_language`. It is not actively injected into the system prompt as an instruction — the model infers the reply language from the transcript text. This is reliable for EN/FR/ES but may fail for code-mixed or short inputs.

---

## 6. REDIS SESSION MANAGEMENT

**File:** `redis_client.py`

### Key format

```
session:{session_id}
```

Where `session_id` is a UUID4 string generated at `/api/chat/start`.

### TTL

1800 seconds (30 minutes) — defined at `redis_client.py:7`. Every `save_session` call resets the TTL via `SETEX`.

### Session data structure

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "review_id": "caller-provided string",
  "listing_id": "caller-provided string",
  "detected_language": "en",
  "listing_context": {
    "business_name": "McDonalds Berges du Lac",
    "network_names": ["yelp", "google"],
    "network_preferences": {"yelp": true, "google": false}
  },
  "chat_history": [
    {"role": "system", "content": "...full system prompt..."},
    {"role": "assistant", "content": "...initial AI response..."},
    {"role": "user", "content": "...user message..."},
    {"role": "assistant", "content": "...AI reply..."}
  ],
  "status": "active",
  "created_at": "2026-05-19T10:00:00+00:00"
}
```

After `/approve`, `status` changes to `"approved"`.

### CRUD operations

| Operation | Function | Redis command |
|---|---|---|
| Create | `save_session()` | `SETEX session:{id} 1800 {json}` |
| Read | `get_session()` | `GET session:{id}` |
| Update | `save_session()` (same function) | `SETEX session:{id} 1800 {json}` (overwrites and resets TTL) |
| Delete | `delete_session()` | `DEL session:{id}` |

### What happens when Redis is down

All three functions in `redis_client.py` catch `redis.exceptions.ConnectionError` and raise a pre-built `HTTPException(503, "Redis unavailable...")`. The connection is created at module import time (`redis_client.py:9-13`) — a connection failure at startup is silent until the first request hits a session operation.

There is **no reconnection logic** and **no fallback** (e.g., in-process dict). If Redis goes down mid-session, all active sessions are lost with a 503 response.

---

## 7. WHAT WORKS RIGHT NOW

### Verified working endpoints (tested by `verify.py`)

| Endpoint | Status |
|---|---|
| `GET /` | Working — returns app info |
| `GET /api/health-check/transcribe` | Working — returns Whisper ready status |
| `POST /api/chat/start` | Working — calls Groq, creates Redis session |
| `POST /api/chat/message` | Working — maintains conversation in Redis |
| `POST /api/chat/approve` | Working — extracts structured JSON from conversation |
| `POST /api/chat/end` | Working — deletes Redis key |
| `GET /api/chat/session/{id}` | Working — returns session data from Redis |
| `GET /api/yelp/search` | Working — returns static business list |
| `POST /api/yelp/reviews` | Working — returns UUID, no persistence |
| `PUT /api/yelp/reviews/{id}/transcription` | Working — validates language, echoes data |
| `POST /api/auth/register` | Working — returns token (fake, no DB) |
| `POST /api/auth/login` | Working — returns hardcoded fake token |
| `POST /api/transcribe` | Working — Whisper transcription (requires audio file) |

### Verified integrations

- **Groq API:** Real calls to `llama-3.3-70b-versatile`. Confirmed working via `verify.py` check sequence.
- **Redis:** Verified by `verify.py` — key creation, TTL check, status update, and key deletion all pass.
- **Whisper:** Loads at startup. Confirmed working via health check and transcription endpoint.

### Running `verify.py`

```bash
# With server and Redis both running:
python verify.py
python verify.py --base-url http://localhost:5000 --redis-host localhost --redis-port 6379
```

`verify.py` runs 5 sequential checks:
1. Pre-flight: server + Redis reachable
2. `POST /api/chat/start` — session creation, Redis key, TTL
3. `POST /api/chat/message` — AI response, history growth
4. `POST /api/chat/approve` — structured JSON output, Redis status update
5. Expired session → 404

Bonus checks: `GET /session/{id}`, `POST /end`, and post-delete 404 verification.

---

## 8. WHAT IS NOT DONE YET

### Still in mock mode

- **`database.py`** is entirely mocked. `MockMilvusClient` stores data in a Python dict that lives only for the process lifetime. No data survives a restart.
- **`lists.py`** and **`tasks.py`** read/write to this mock. All task and list data is lost on restart.
- **`memos.py`** doesn't even use the mock — it returns hardcoded empty responses.

### ~~Missing real auth wiring~~ — **COMPLETED 2026-05-19**

Real JWT authentication is now fully wired (branch `PV-121-implement-acceptable-language`):

- `POST /api/auth/register` — creates `User` + `UserCredential` in PostgreSQL, returns signed JWT.
- `POST /api/auth/login` — looks up `UserCredential` by email, bcrypt-verifies password, returns JWT.
- `GET /api/auth/me` — protected by `Depends(get_current_user)`, returns `user_id`, `email`, `display_name`, `created_at`.
- `get_current_user()` decodes the Bearer JWT, extracts `sub`, and verifies the user exists in DB. Returns `user_id` as `str`. Raises 401 on any failure.
- All five `/api/chat/*` endpoints require a valid Bearer token. `/message`, `/approve`, and `/end` also verify the token owner matches the session owner (403 on mismatch).
- `user_id` is stored in the Redis session at `/start` to enable ownership checks.
- Alembic migration `df705e498e8c` adds the `user_credentials` table.
- `verify.py` updated: registers a test user, acquires a real JWT, passes it to all chat requests, and tests 401/403 edge cases.

BFF → pv-ai auth is now fully wired via JWT relay using a shared secret. See `BFF_SHARED_SECRET` in `.env` and `POST /api/auth/token/relay` in `auth.py`.

### Missing features

- No Yelp API integration — the API key is set in `.env` but `yelp.py` uses a 6-item hardcoded list.
- No real business search (no external lookup, no radius, no category filtering).
- No review persistence — reviews created via `POST /api/yelp/reviews` are ephemeral.
- No user profile management (update email/password/avatar).
- No subtask, note, or session endpoints (models exist in `models.py` but no routers).
- No file upload for review audio linked to a review record.
- No notification or webhook system.
- No pagination on any list endpoint.

### Known architecture issues

- **`models.py` is broken:** It imports `from database import Base` at line 7 (implicit — actually it uses `Base` in class declarations), but `database.py` never defines or exports a `Base`. If any code attempts to `import models`, it will raise `ImportError`. Currently `models.py` is not imported by any router, so this is silent.
- **`ai_engine.py` is dead code:** Defines `extract_review_insights()` which uses the cleaner `response_format=json_object` approach but is never called.
- **`REVIEW_INTERACTION_PROMPT` and `FINAL_REPORT_PROMPT` are unused** (`prompts.py:28-54`).
- **`OPENAI_API_KEY` and `YELP_API_KEY` env vars** are declared and loaded but never read by any active code path.
- **`ai_engine.py:7` hardcodes the model name** instead of reading from `config.LLM_MODEL`.
- **No input validation on `user_id`** query parameters in `lists.py` and `tasks.py` — trivial to forge.

### Files that are stubs or dead code

| File | Classification |
|---|---|
| `database.py` | Stub — mock only |
| `models.py` | Broken stub — will crash on import |
| `ai_engine.py` | Dead code — never imported |
| `memos.py` | Stub — always returns empty/mock |
| `lists.py` | Partial stub — only 2 of the expected 5+ CRUD endpoints exist |
| `auth.py` | Stub — auth bypass, fake login |

---

## 9. NEXT STEPS IN PRIORITY ORDER

### 1. Rotate the Groq API key (immediate)

The key `gsk_Rx...` is in `.env`. Even though `.env` is gitignored, assume it may have been exposed. Generate a new key at `console.groq.com`.

**Files to touch:** `.env`
**Complexity:** Trivial

### 2. Fix `models.py` — add SQLAlchemy Base to `database.py`

`models.py` references `Base` from `database`. Add a proper `declarative_base()` to `database.py` so models can be imported without crashing. This unblocks the entire DB migration path.

**Files to touch:** `database.py`, `models.py`
**Complexity:** Low (5 lines)

```python
# database.py — add at top
from sqlalchemy.orm import declarative_base
Base = declarative_base()
```

### 3. Real database migration with Alembic

`alembic` and `sqlalchemy` are already installed. Wire `database.py` to a real PostgreSQL connection, create an `alembic.ini` and `alembic/env.py`, and generate the initial migration from the models defined in `models.py`.

**Files to touch:** `database.py`, new `alembic.ini`, new `alembic/env.py`, new `alembic/versions/`
**Complexity:** Medium

```bash
alembic init alembic
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

### 4. Real auth — wire JWT verification

Remove the TEST_USER_ID bypass in `get_current_user()`. Implement proper `verify_token()` that decodes the JWT and looks up the user in the DB. Apply `Depends(get_current_user)` to all protected routes (lists, tasks, memos, chat).

**Files to touch:** `auth.py`, `lists.py`, `tasks.py`, `memos.py`, `chat.py`
**Complexity:** Medium

### 5. Persist reviews to the database

Replace the no-op `POST /api/yelp/reviews` and `PUT /api/yelp/reviews/{id}/transcription` with real DB inserts using the `YelpReview` model. This enables review history and status tracking.

**Files to touch:** `yelp.py`, `database.py`
**Complexity:** Medium

### 6. Wire real Yelp API (or business search API)

Replace `STATIC_BUSINESSES` in `yelp.py` with calls to the Yelp Fusion API (or an equivalent). The key is already declared in `config.py`.

**Files to touch:** `yelp.py`, `config.py`
**Complexity:** Medium

### 7. Integrate `ai_engine.py` into `chat.py`

The `extract_review_insights()` function in `ai_engine.py` uses `response_format=json_object` which is safer than the regex approach in `chat.py`'s approve endpoint. Either:
- Merge this function into `chat.py` and use it in `/approve`
- Or delete `ai_engine.py` entirely and rewrite the approve logic with `response_format`

**Files to touch:** `ai_engine.py`, `chat.py`
**Complexity:** Low

### 8. Upgrade Whisper model for production accuracy — COMPLETE ✅

Fine-tuned model is live. `USE_FINETUNED_WHISPER=true` is set in `.env`. Model loaded from `./whisper-provoc-small/final`. Verified via health check (`"finetuned": true`) and `whisper_inference_test.py` (56.4% relative WER improvement on MLS dev split). See Section 4 for full results.

**Next AI task:** Llama 3.2 3B LoRA fine-tune (separate Colab/Kaggle notebook) — see item 12 below.

### 9. Implement missing CRUD endpoints for lists and tasks

`lists.py` is missing GET by ID, PUT, DELETE. `tasks.py` is missing GET by ID. `memos.py` needs real persistence. Implement these against the real DB (after step 3).

**Files to touch:** `lists.py`, `tasks.py`, `memos.py`
**Complexity:** Low per endpoint once DB is wired

### 10. Add Redis reconnection / fallback logic

`redis_client.py` raises 503 immediately on `ConnectionError`. Consider adding connection retry logic or a graceful degradation mode (e.g., reject new sessions but serve cached ones from an in-process fallback).

**Files to touch:** `redis_client.py`
**Complexity:** Low

### 11. MLflow experiment tracking (future)

If Whisper fine-tuning or LLaMA LoRA training is planned, set up MLflow for tracking experiments. This requires a separate MLflow server and changes to the training scripts (not yet in this repo).

**Complexity:** High — requires separate infrastructure

### 12. Llama LoRA fine-tuning (future)

Once sufficient review data is collected via the `/approve` flow, fine-tune the LLaMA model on domain-specific review data. This requires GPU infrastructure, training scripts, and a model registry.

**Complexity:** Very high — out of scope until data collection is running

### 13. Fallback router for Groq outages

Add a fallback to a local model (e.g., `ollama` with `llama3`) when the Groq API is unavailable. Gate the fallback via an env var `LLM_FALLBACK_MODEL`.

**Files to touch:** `chat.py`, `config.py`
**Complexity:** Medium

### 14. Pin all unpinned dependencies

`torch`, `openai-whisper`, `numpy`, `requests`, `groq`, `redis`, `sqlalchemy`, `alembic` have no pinned versions. Run `pip freeze > requirements.txt` after a clean install and commit pinned versions.

**Files to touch:** `requirements.txt`
**Complexity:** Trivial

---

## 10. ARCHITECTURE DECISIONS

### Why flat file structure was kept

The project is in early-stage development. A flat structure (all `.py` files at root) avoids import complexity and speeds up iteration. With fewer than 15 source files, a `src/` layout or package structure would add indirection without benefit. This should be revisited when the project grows beyond 20 files or when modules are shared across services.

### Why `chat.py` and `yelp.py` were separated

`yelp.py` handles **business lookup and review record creation** — its job is to return business data and issue review IDs. `chat.py` handles the **AI conversation loop** — Groq calls, session lifecycle, and JSON extraction. Keeping them separate means the Groq dependency is isolated: if the AI backend is replaced or upgraded, `yelp.py` is untouched. It also means the review flow can proceed without a working AI (e.g., for testing the business search UI alone).

### Why `transcription.py` was extracted

Whisper model loading is expensive (several seconds, significant RAM). Extracting it into its own module means the loading happens once at import time and is not tangled with the chat session logic. It also means the transcription endpoint can be deployed or scaled independently in a future microservices split.

### Why in-memory `USERS_DB` was chosen over a real DB for auth

The comment in `auth.py` is explicit: this is a **test bypass** (`TEST_USER_ID`) to enable rapid frontend and integration testing without requiring a live database. The full SQLAlchemy `User` model exists in `models.py`, and the password hashing context (`pwd_context`) is already configured in `config.py`. The intention is to replace the stub with real DB lookups once the database migration is complete (see Section 9, steps 2–4).

### Groq model configuration via `LLM_MODEL` env var

The model name is read from `config.LLM_MODEL` and used in `chat.py:57`. This means switching from `llama-3.3-70b-versatile` to another Groq-hosted model (e.g., `mixtral-8x7b-32768`) requires only an environment variable change and no code deployment. Note that `ai_engine.py:7` hardcodes the model name and does **not** read from config — this inconsistency must be fixed if `ai_engine.py` is ever used.

---

## 11. KNOWN FRAGILITY POINTS

### 1. JSON parsing in `/api/chat/approve` (high risk)

`chat.py:157`: `re.search(r'\{.*\}', raw, re.DOTALL)` — this regex extracts the first `{...}` block from the AI response. If the AI includes any JSON-like structure earlier in its response (e.g., inside a code block), this will extract the wrong object. If the AI wraps the output in markdown fences (` ```json `) the regex still works since `.*` matches newlines with `re.DOTALL`, but any nested `}` can break the greedy match.

**Fix:** Use `response_format={"type": "json_object"}` in the Groq call (already implemented in `ai_engine.py` — see Section 9 step 7).

### 2. CORS configuration

`main.py:25`: `os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")` — the CORS origin list is split on commas with no stripping of whitespace. If `ALLOWED_ORIGINS=http://localhost:3000, http://localhost:19006` (note the space), the second origin becomes `" http://localhost:19006"` (with a leading space) and CORS will fail silently for that origin.

**Fix (already applied):** In `main.py` around line 25, the line was changed to:
```python
[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
```
This strips whitespace from every origin before passing to CORSMiddleware.

### 3. Redis connection error handling

`redis_client.py:9-13`: The Redis client is created at module import time with no connection test. A `ConnectionError` is only raised when a session operation is attempted. There is no reconnection logic, health check, or graceful degradation. If Redis restarts mid-deployment, all subsequent session operations will 503 until the process is restarted.

### 4. Whisper model loading on startup

`transcription.py:14`: `whisper_model = whisper.load_model(WHISPER_MODEL).to(device)` — this runs at import time, before the FastAPI app is ready. If the model file is corrupt, not found, or if `torch` fails to load (e.g., CUDA driver mismatch), the entire application fails to start with a cryptic error. Consider wrapping this in a FastAPI `startup` event with proper error reporting.

### 5. `models.py` will crash on import

`models.py:7` uses `Base` from SQLAlchemy's `declarative_base()`, but `database.py` does not export it. Any attempt to `import models` raises `ImportError`. Currently harmless because no active file imports `models`, but dangerous if a developer adds a router that uses the models without fixing `database.py` first.

### 6. Real Groq API key in `.env`

The file `D:\pfe ai\pv-ai\.env` contains `GROQ_API_KEY=gsk_Rx...` (a live key). Even though `.gitignore` excludes `.env`, this key should be rotated. If this machine or IDE was ever connected to a cloud sync service or if `.env` was inadvertently included in any commit, the key is compromised.

### 7. No rate limiting or request validation

No rate limiting middleware is configured. The `/api/transcribe` endpoint accepts files of any size with no size limit. A large upload will hold a thread until Whisper finishes processing. Consider adding `python-multipart` upload size limits and a request rate limiter (e.g., `slowapi`).

### 8. `tasks.py:35` dummy vector

`"vector": [0.0, 0.0]` is inserted into the MockMilvusClient for every task. This will need to be removed or replaced with a real embedding when the real Milvus is wired up — inserting a 2-dimensional vector into a collection configured for 768/1536 dimensions will cause a schema mismatch error.

### 9. Relay endpoint security model

`POST /api/auth/token/relay` is protected only by a shared secret (`BFF_SHARED_SECRET`) in the `X-BFF-Secret` header. Keep this in mind:

- The secret must be kept out of source control. It lives in `.env` (gitignored). Copy it into the BFF `.env` as `PV_AI_BFF_SECRET` (or equivalent).
- The relay endpoint does **no DB lookup** — it unconditionally trusts the `user_id` supplied by the BFF. If the shared secret is ever compromised, an attacker can mint a pv-ai token for any user ID.
- Relay-issued JWTs carry `"relay": true` in the payload. `get_current_user()` uses this claim to skip the local DB lookup, so relay tokens only work for users that exist in the BFF's database (`provoc_db`), not necessarily in `provoc_ai_db`.
- The relay token expires in 30 minutes. The BFF should request a fresh token per user request or cache it for its lifetime.

---

## 12. ENVIRONMENT SETUP FROM SCRATCH

This section gets a new developer from zero to a running, tested instance.

### Prerequisites

- Python 3.10 or 3.11 (3.12 has some `torch` compatibility issues — prefer 3.11)
- Git
- Docker Desktop (for Redis)
- A Groq API key from `console.groq.com`

### Step 1 — Clone and enter the project

```bash
git clone <your-repo-url>
cd pv-ai
git checkout PV-121-implement-acceptable-language
```

### Step 2 — Create a Python virtual environment

```bash
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux / macOS:
source venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

> `torch` and `openai-whisper` are large. This will take 5–15 minutes on first install depending on internet speed and whether a CUDA-enabled build is needed.

### Step 4 — Start Redis via Docker

```bash
docker run -d --name redis-pv-ai -p 6379:6379 redis:7-alpine
```

Verify it is running:

```bash
docker ps | grep redis-pv-ai
# or
redis-cli ping   # should return PONG
```

### Step 5 — Create your `.env` file

Create `D:\pfe ai\pv-ai\.env` with the following content. Replace placeholder values:

```env
JWT_SECRET=replace-with-a-64-char-random-string
OPENAI_API_KEY=not-used-leave-as-is
YELP_API_KEY=not-used-leave-as-is
GROQ_API_KEY=gsk_your_actual_groq_key_here
REDIS_HOST=localhost
REDIS_PORT=6379
WHISPER_MODEL=tiny
LLM_MODEL=llama-3.3-70b-versatile
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:19006
```

Generate a strong `JWT_SECRET`:

```python
python -c "import secrets; print(secrets.token_hex(32))"
```

### Step 6 — Start the server

```bash
uvicorn main:app --reload --port 5000
```

Expected startup output:

```
Loading Whisper on cpu...
Backend running in NO-DATABASE mode
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:5000
```

### Step 7 — Verify the installation

Open a second terminal (with the venv activated):

```bash
python verify.py
```

Expected output if everything is working:

```
────────────────────────────────────────────────────────────
  Pre-flight: server + Redis reachable
────────────────────────────────────────────────────────────
  [PASS] Server reachable — HTTP 200
  [PASS] Redis reachable — localhost:6379

...

────────────────────────────────────────────────────────────
  Summary
────────────────────────────────────────────────────────────

  20/20 checks passed

  All checks passed.
```

### Step 8 — Explore the API docs

Open `http://localhost:5000/docs` in a browser. All endpoints are documented via FastAPI's auto-generated OpenAPI UI.

### Step 9 — Test transcription manually (optional)

```bash
curl -X POST http://localhost:5000/api/transcribe \
  -F "audio=@test_english.mp3" \
  -F "language=auto" \
  -F "task=transcribe"
```

Expected response:

```json
{
  "success": true,
  "transcription": "...",
  "language": "en"
}
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ImportError: cannot import name 'Base' from 'database'` | Something imported `models.py` | Do not import `models.py` until `database.py` is fixed (Section 9 step 2) |
| `ConnectionRefusedError` on Redis | Redis not running | Run Step 4 again |
| `AuthenticationError` from Groq | Invalid API key | Check `GROQ_API_KEY` in `.env` |
| `RuntimeError: CUDA error` | Wrong torch version for GPU | Use CPU: set `CUDA_VISIBLE_DEVICES=""` |
| App hangs at startup | Whisper model downloading | First run downloads the model (~75 MB for `tiny`); wait or check internet |
| 503 on chat endpoints | Redis down | Restart Docker container |
| CORS errors in browser | Origins mismatch | Update `ALLOWED_ORIGINS` in `.env` — no spaces around commas |

---

## 14. CHAT HISTORY RESUMPTION — `previous_messages` (added 2026-05-30)

### What changed

`POST /api/chat/start` now accepts an optional `previous_messages` field so a resumed session carries its prior AI context into the first Groq call.

### Files changed

**`chat.py`** — two edits, no other file touched.

**Edit 1 — `StartSessionRequest` model (line 27):** added one field:

```python
previous_messages: list[dict] = []   # each dict: { role: 'user'|'assistant', content: str }
```

Default is `[]`, so existing callers that omit the field get identical behaviour.

**Edit 2 — `start_session` handler (lines 92–108):** replaced the inline two-message list and the hardcoded `chat_history` list with logic that:

1. Builds `chat_history = [system_prompt]`.
2. If `previous_messages` is non-empty, extends `chat_history` with them (copies only `role` and `content`).
3. Calls Groq with `chat_history + [user(transcript)]` — includes full prior context.
4. Appends `user(transcript)` to `chat_history` **only** when resuming (non-empty case), then appends `assistant(initial_response)`.
5. Stores the resulting `chat_history` in the Redis session.

### Redis chat_history order

| Case | Stored order |
|---|---|
| New session (`previous_messages = []`) | `[system, assistant(initial_response)]` — **unchanged** |
| Resumed session (`previous_messages` non-empty) | `[system, ...previous_messages, user(transcript), assistant(initial_response)]` |

### What did NOT change

- `_call_groq` helper — untouched.
- `/message`, `/approve`, `/end`, `/session/{id}` endpoints — untouched.
- Redis session structure (keys) — untouched; only the contents of `chat_history` vary.
- All other files — untouched.

---

## 15. CONVERSATION SUMMARY IN `/approve` (added 2026-05-31)

### What changed

`POST /api/chat/approve` now makes a second Groq call after extracting the structured review JSON, generating a plain-text structured summary of the full conversation. The summary is appended to the response as `conversation_summary`.

### Files changed

**`chat.py`** — one block added, no other file touched.

**Addition — `approve_session` handler, after JSON parse, before `session["status"] = "approved"`:**

```python
summary_prompt = (
    'Summarize everything the user told you about '
    'their experience at this business. '
    ...
)

summary = _call_groq(
    session["chat_history"] + [{"role": "user", "content": summary_prompt}],
    temperature=0.1,
    max_tokens=300,
).strip()
```

The `return result` was replaced with an explicit dict that includes `conversation_summary`:

```python
return {
    "improved_text": result["improved_text"],
    "rating": result["rating"],
    "sentiment": result["sentiment"],
    "tone": result["tone"],
    "key_points": result["key_points"],
    "conversation_summary": summary,
}
```

### Summary prompt structure

The prompt instructs the model to produce a fixed-format bullet list:

```
- Overall sentiment: [Positive/Negative/Neutral]
- Star rating: [1-5]
- What they liked: [list or "nothing mentioned"]
- What they disliked: [list or "nothing mentioned"]
- Specific details mentioned: [parking, service, food quality, prices, atmosphere, staff names, wait times, etc]
- Tone preference: [Firm/Polite/Neutral]
- Goal: [Awareness/Praise/etc]
```

`temperature=0.1`, `max_tokens=300`. No `response_format` enforcement — plain text, not JSON.

### Cost note

Every `/approve` call now makes **two** Groq API calls instead of one. Both use `temperature=0.1`; the summary call caps at 300 tokens.

### What did NOT change

- `approval_prompt` and first Groq call — untouched.
- JSON parsing logic — untouched.
- Redis session structure — `conversation_summary` is **not** stored in Redis, only returned in the HTTP response.
- All other endpoints — untouched.

---

## 16. `context_note` INJECTION INTO SYSTEM PROMPT (added 2026-05-31)

### What changed

`_build_system_prompt()` in `chat.py` now appends a `USER CONTEXT` line to the system prompt when `listing_context` contains a `context_note` key. This means tag selections and pre-set ratings from the Smart Review flow reach the AI from the very first message, not just from conversation history.

### Files changed

**`chat.py`** — two lines added, no other file touched.

**Edit — `_build_system_prompt()` (lines 58–59), inserted before the `return`:**

```python
if listing_context.get('context_note'):
    context_block += f"\nUSER CONTEXT: {listing_context['context_note']}"
return REVIEW_ANALYSIS_PROMPT + context_block
```

### Exact lines changed

| File | Lines | Change |
|---|---|---|
| `chat.py` | 58–59 (inserted) | Added `context_note` guard and append before the existing `return` |

### Behaviour

- If `context_note` is absent or empty string, behaviour is **identical to before** — no extra line appended.
- If `context_note` is present, the system prompt gains a final line: `USER CONTEXT: <value>`.
- The caller (Smart Review flow) sets `context_note` to a human-readable summary of the user's tag selections and rating, e.g. `"User selected: Bad service, Cold food. Rating: 2 stars."`.

### What did NOT change

- All other fields read from `listing_context` — untouched.
- `_call_groq`, all endpoints, Redis structure — untouched.

---

## 17. `/health` ENDPOINT — REDIS TIMEOUT FIX (2026-06-01)

### Problem

`GET /health` was hanging for **22–25 seconds** before responding. Root cause was three layered issues, each masking the next:

1. **redis-py `socket_connect_timeout` does not reliably time out on Windows.** When the Redis host is `"localhost"`, Python's `socket.getaddrinfo` resolves it to both `::1` (IPv6) and `127.0.0.1` (IPv4). redis-py tries IPv6 first; the Windows OS TCP timeout for an unreachable IPv6 loopback is ~20 s. The `socket_connect_timeout` parameter only fires after the OS returns from `connect()`, not before. Measured: `redis.Redis(socket_connect_timeout=2).ping()` → 16.74 s. Raw `socket.socket(); sock.settimeout(2); sock.connect()` → 2.00 s exactly.

2. **`asyncio.wait_for()` does not preempt C-level socket operations on Python 3.11+.** In 3.11, `wait_for` was changed to wait for the inner task to acknowledge cancellation before raising `TimeoutError`. asyncpg's C-level connect does not respond to cancellation immediately, so `wait_for(asyncpg.connect(), timeout=2)` blocked for the full OS TCP timeout before raising.

3. **SQLAlchemy's `create_async_engine` has no `connect_timeout` set**, so the DB check also had no deadline.

### Fix applied

**File: `main.py` — `GET /health` handler (lines 48–120)**

| Check | Before | After |
|---|---|---|
| Redis | `redis.Redis(socket_connect_timeout=2).ping()` — 20 s+ | Raw `socket.socket(); settimeout(2); connect(); PING/PONG frame` — 2 s max |
| DB | `async with engine.connect()` — no timeout (20+ s) | `asyncpg.connect()` in a daemon thread; `thread.join(timeout=2.5)` provides the hard cap |
| Concurrency | Sequential — total = Redis_time + DB_time | `asyncio.gather(asyncio.to_thread(db_fn), asyncio.to_thread(redis_fn))` — both run concurrently, total = max(2.5, 2) |

**File: `redis_client.py` — module-level Redis client (lines 1–21)**

- Added `import socket`
- Added `_redis_host = socket.gethostbyname(os.getenv("REDIS_HOST", "localhost"))` to force IPv4 resolution before the client is created
- Added `socket_connect_timeout=2, socket_timeout=2` to the `redis.Redis(...)` constructor

### Measured results

| Call | Before | After |
|---|---|---|
| 1st after startup | 22–25 s | ~3.4 s (2 s Redis timeout + ~1.3 s first-request init) |
| 2nd+ | 22–25 s | ~2.1 s (2 s Redis timeout; ~0.1 s otherwise if Redis is up) |

When Redis is running, both the raw-socket PING and the asyncpg connect complete in <0.2 s, giving a total health response of <0.5 s.

### Why the daemon-thread approach for DB

`asyncio.to_thread` / `run_in_executor` submit to asyncio's thread pool, which works correctly. Inside the thread, creating a fresh `asyncio.new_event_loop()` and running `asyncpg.connect()` is necessary because asyncpg requires its own event loop context when called outside the main loop. The daemon thread is given a 2.5 s `join()` deadline; if asyncpg still hasn't connected by then, the function returns `"error: timeout"` and the daemon thread is silently abandoned (it will eventually complete or error on its own without blocking the server).

### Known limitation

`redis_client.py`'s production client (`_client`) still uses `redis.Redis` with `socket_connect_timeout=2, socket_timeout=2`. On Windows, these may not fire reliably (see above). In production on Railway (Linux), redis-py timeouts behave correctly. If session operations are slow on Windows during development, this is the cause — it does not affect Railway.

---

## 13. POST-DEMO BACKLOG

Small items to action after the demo, in no particular order.

### Substitute `[business name]` in the scope-restriction redirect sentence

**File:** `chat.py` — `_build_system_prompt()`
**Why:** `REVIEW_ANALYSIS_PROMPT` contains the literal text `[business name]` in the off-topic redirect instruction. The model infers the correct name from the BUSINESS CONTEXT block below it, but the substitution is implicit. One line makes it explicit before the string is sent to Groq.

```python
# In _build_system_prompt(), replace this:
return REVIEW_ANALYSIS_PROMPT + context_block

# With this:
system_prompt = REVIEW_ANALYSIS_PROMPT.replace(
    '[business name]', listing_context.get('business_name', 'this business')
)
return system_prompt + context_block
```

---

## 18. MILVUS STANDALONE — DOCKER SETUP (added 2026-06-12)

### What changed

Milvus vector database is now running as a real service instead of the in-process `MockMilvusClient`. It is the backing store for the recommendation engine (see Section 19).

### Infrastructure

**File:** `milvus-docker-compose.yml`

Three Docker services are brought up together:

| Container | Image | Role |
|---|---|---|
| `milvus-etcd` | `quay.io/coreos/etcd:v3.5.5` | Distributed coordination / metadata |
| `milvus-minio` | `minio/minio:RELEASE.2023-03-20T20-16-18Z` | Object storage for segments |
| `milvus-standalone` | `milvusdb/milvus:v2.3.4` | Vector DB engine |

**Ports exposed by `milvus-standalone`:**

| Port | Protocol | Purpose |
|---|---|---|
| `19530` | gRPC | pymilvus client connection |
| `9091` | HTTP | Health check endpoint |

**MinIO ports:** `9000` (S3 API), `9001` (web console)

Data volumes persist under `./volumes/etcd`, `./volumes/minio`, `./volumes/milvus` relative to the project directory.

### Starting and stopping Milvus

```bash
# Start (detached)
docker compose -f milvus-docker-compose.yml up -d

# Verify all three containers are healthy
docker compose -f milvus-docker-compose.yml ps

# Health check (wait ~90 s for milvus-standalone to pass)
curl http://localhost:9091/healthz
# Expected: {"status":"ok"}  or  OK

# Stop (preserves volumes)
docker compose -f milvus-docker-compose.yml down

# Stop and wipe all data (destructive)
docker compose -f milvus-docker-compose.yml down --volumes
```

### New Python dependencies

Added to `requirements.txt`:

```
pymilvus==2.3.4
sentence-transformers>=2.2.0
```

### pymilvus 2.3.4 API note

`MilvusClient` in pymilvus 2.3.4 does **not** have a `has_collection()` method (it was removed). Use `list_collections()` instead:

```python
# Wrong — AttributeError in 2.3.4
if not self._client.has_collection(COLLECTION_NAME):

# Correct
if COLLECTION_NAME not in self._client.list_collections():
```

This fix is already applied in `taste_engine.py:38`.

---

## 19. `taste_engine.py` — TASTE VECTOR ENGINE (added 2026-06-12)

### Overview

**File:** `taste_engine.py`

`TasteEngine` is a lazy-initialised singleton that stores per-user taste vectors in Milvus and uses collaborative filtering to recommend businesses.

### Class structure

```
TasteEngine
├── get_instance()         — singleton accessor
├── _init()                — lazy connect to Milvus + load encoder
├── _ensure_collection()   — creates "taste_vectors" if absent
├── store_review()         — embed + insert review into Milvus
└── get_recommendations()  — collaborative filtering query
```

### Embedding model

- **Model:** `all-MiniLM-L6-v2` (via `sentence-transformers`)
- **Dimension:** 384
- **Loaded:** lazily on first call to `_init()`, not at import time
- **Input to encoder:** `"{business_name} {business_type} {review_text}"` concatenated

### Milvus collection: `taste_vectors`

| Field | Type | Notes |
|---|---|---|
| `vector` | float[384] | Embedding of review text, COSINE metric |
| `user_id` | varchar | UUID string of the reviewer |
| `business_id` | varchar | Listing ID from the review session |
| `business_name` | varchar | Business name from listing context |
| `rating` | float | AI-extracted rating (1–5) |
| `review_text` | varchar | First 200 chars of the improved review text |

Collection is created automatically with `auto_id=True` on first `store_review` call if it does not exist.

### `store_review()` — taste_engine.py:47

Encodes `"{business_name} {business_type} {review_text}"` and inserts the resulting vector plus metadata into `taste_vectors`. Returns `True` on success, `False` on any failure (including Milvus unavailable).

### `get_recommendations()` — taste_engine.py:78

Collaborative filtering in six steps:

1. Query the current user's 20 most recent reviews from Milvus → collect their vectors and `reviewed_ids`
2. Average the vectors → `taste_vector` (mean of user's embedding history)
3. Query up to 100 rows where `user_id != current_user` (other users' reviews)
4. Deduplicate by `business_id`, discard any already in `reviewed_ids`
5. Score each candidate by cosine similarity to `taste_vector`
6. Sort descending, return top `limit` results as `list[dict]`

Returns `[]` gracefully at any step if Milvus is unavailable or the user has no prior reviews.

### Graceful degradation

`_init()` is wrapped in `try/except`. If Milvus is not running, `_initialized` stays `False` and both public methods return `False`/`[]` without raising. The server starts and operates normally without Milvus; the recommendation feature simply returns empty results.

---

## 20. `GET /api/recommendations` ENDPOINT (added 2026-06-12)

### Files changed

- **New file:** `recommendations.py` — router definition
- **`main.py`** — router registered at startup

### Route

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/recommendations` | Bearer JWT | Returns personalised business recommendations for the authenticated user |

### Request

No body. Optional query parameter:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int | 5 | Maximum number of recommendations to return |

### Response

```json
[
  {
    "business_name": "Bella Italia Tunis",
    "business_id": "ChIJbella1",
    "score": 0.649,
    "rating": 3.0
  }
]
```

Returns `[]` (HTTP 200) when:
- Milvus is unavailable (`_initialized = False`)
- The user has no prior reviews stored in Milvus
- No other-user reviews exist to compare against

### Auth

Uses `Depends(get_current_user)` — requires a valid Bearer JWT. Returns 401 if the token is absent or invalid. The `user_id` extracted from the JWT is passed directly to `TasteEngine.get_recommendations()`.

---

## 21. TASTE VECTOR PERSISTENCE IN `/api/chat/approve` (added 2026-06-12)

### What changed

`POST /api/chat/approve` now silently stores a taste vector in Milvus after the session is marked approved. This means every successful approve call automatically feeds the recommendation engine.

### Files changed

**`chat.py`** — one `try/except` block added after `save_session()`, before `return`. No other file touched.

**Addition — `approve_session` handler (`chat.py:267-278`):**

```python
try:
    from taste_engine import TasteEngine
    TasteEngine.get_instance().store_review(
        user_id=session.get("user_id", "unknown"),
        business_id=session.get("listing_id", ""),
        business_name=session.get("listing_context", {}).get("business_name", ""),
        review_text=result.get("improved_text", ""),
        rating=float(result.get("rating", 3)),
        business_type=session.get("listing_context", {}).get("business_type", ""),
    )
except Exception:
    pass  # taste engine is optional; never fail the approve response
```

### Behaviour

- If Milvus is running: the approved review's embedding is stored and becomes available to the recommendation engine immediately.
- If Milvus is down: the `except` silently swallows the error. The approve response (improved text, rating, sentiment, etc.) is returned normally — the caller never sees a 500 or 502.
- The `TasteEngine` import is deferred inside the `try` block so a broken `taste_engine.py` import also cannot crash the approve endpoint.

### What did NOT change

- The approve response payload — untouched.
- Redis session structure — untouched.
- All other endpoints — untouched.

---

## 22. KNOWN FRAGILITY #10 — `context_note` RATING MISMATCH (added 2026-06-12)

This is an addition to Section 11 (Known Fragility Points).

### 10. `context_note` rating hint is not enforced (medium risk)

When the caller sets `context_note` to a string like `"Rating: 5 stars"`, the AI sometimes ignores it and infers its own rating from the transcript text instead.

**Observed in `final_test.py` (2026-06-12):** `context_note='Rating: 5 stars'` → AI returned `rating: 3` with improved text describing a "mediocre experience", despite the transcript saying "coffee was excellent and the staff were friendly".

**Root cause:** `context_note` is appended as a single `USER CONTEXT:` line at the end of the system prompt (see Section 16). The AI treats it as advisory context, not as a hard constraint. When the transcript text carries a weaker sentiment signal than the stated rating, the model trusts its own inference.

**Fix options:**
1. Add an explicit instruction in the system prompt: *"If USER CONTEXT specifies a rating, use that exact rating — do not infer from text."*
2. Post-process the approve response: if `context_note` contains a rating, override `result["rating"]` after the Groq call.
3. Pass the pre-set rating as a separate field in the approve request body and enforce it server-side.

Option 2 is the safest short-term fix — it requires no prompt changes and never risks breaking the AI's text quality.

---

## 23. `final_test.py` — END-TO-END VERIFICATION SCRIPT (added 2026-06-12)

### What it is

**File:** `final_test.py`

An end-to-end smoke test that exercises the full stack in a single run: health check, BFF token relay, recommendations before and after a review, and the full chat approve flow.

### Prerequisites

- Server running on `http://127.0.0.1:5000`
- Redis running
- Milvus running (via `milvus-docker-compose.yml`)
- PostgreSQL connected (for JWT auth via relay)
- `BFF_SHARED_SECRET` set in `.env`

### What it tests

| Step | Check |
|---|---|
| 1 | `GET /health` — all subsystems green |
| 2 | `POST /api/auth/token/relay` — BFF shared secret issues a relay JWT |
| 3 | `GET /api/recommendations` — returns HTTP 200 (may be `[]` if no prior data) |
| 4 | `POST /api/chat/start` — session created, Groq responds |
| 5 | `POST /api/chat/approve` — structured review extracted, taste vector stored |
| 6 | `GET /api/recommendations` again — result after the new review is stored |

### Running it

```bash
# With server, Redis, Milvus, and DB all running:
python final_test.py
```

### Verified output (2026-06-12)

```
=== FINAL VERIFICATION TEST ===
1. Health: {'status': 'ok', 'db': 'connected', 'redis': 'connected', 'whisper': 'loaded', 'mode': 'live'}
2. Token: OK
3. Recommendations status: 200
   Result: [{'business_name': 'Bella Italia Tunis', 'business_id': 'ChIJbella1', 'score': 0.649, 'rating': 3.0}]
4. Chat start status: 200
5. Chat approve status: 200
   Review text: I visited Test Cafe and had a mediocre experience. The coffee was okay, but the
   Rating: 3
6. Recommendations after new review: [{'business_name': 'Bella Italia Tunis', 'business_id': 'ChIJbella1', 'score': 0.649, 'rating': 3.0}]
=== TEST COMPLETE ===
```

Steps 3 and 6 return the same result because `Bella Italia Tunis` was already in Milvus from prior data and the newly stored `Test Cafe` review belongs to `user1` — after approve, `Test Cafe` is excluded from that user's own recommendations.

---

## 24. LANGFUSE PROMPT MANAGEMENT (added 2026-06-12)

### What changed

All three LLM prompts in `prompts.py` are now connected to Langfuse for live editing without code deploys. The connection uses a singleton Langfuse client with fallback to hardcoded strings.

### New files

| File | Purpose |
|---|---|
| `langfuse_client.py` | Singleton Langfuse client + `get_prompt()` helper with fallback |
| `register_prompts.py` | One-time script to push all three prompts to Langfuse with `"production"` label |

### Modified files

| File | Change |
|---|---|
| `prompts.py` | Hardcoded strings renamed to `_*_FALLBACK`; wrapped with `get_prompt()` at module level |
| `config.py` | Added `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST` |
| `main.py` | `/health` now reports `"langfuse": "connected"` or `"disabled"` |
| `requirements.txt` | Added `langfuse>=2.0.0` (installed as 4.7.1 in venv) |
| `.env.example` | Added Langfuse credential placeholders |

### Registered prompt names in Langfuse

| Langfuse name | Variable in `prompts.py` | Used by |
|---|---|---|
| `system-prompt` | `REVIEW_ANALYSIS_PROMPT` | `chat.py:12` — system message for every chat session |
| `review-interaction` | `REVIEW_INTERACTION_PROMPT` | Currently dead code — defined for future use |
| `final-report` | `FINAL_REPORT_PROMPT` | Currently dead code — defined for future use |

All registered with label `"production"`.

### How prompts are loaded

Prompts are fetched from Langfuse at **import time** (when `prompts.py` is first imported). This means:

- **Server must be restarted** to pick up edits made in the Langfuse dashboard.
- If Langfuse is unavailable at startup (network error, wrong credentials), `get_prompt()` silently falls back to the hardcoded `_*_FALLBACK` string. The server starts normally.
- `register_prompts.py` only needs to be run once per environment, or whenever a new prompt is added.

### Re-registering prompts

```bash
# Run from the project root with venv activated:
venv\Scripts\python.exe register_prompts.py
```

### New environment variables required in `.env`

| Variable | Purpose | Example |
|---|---|---|
| `LANGFUSE_SECRET_KEY` | Langfuse API secret | `sk-lf-...` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse API public key | `pk-lf-...` |
| `LANGFUSE_HOST` | Langfuse host (default: cloud) | `https://cloud.langfuse.com` |

---

## 25. `start_provoc.py` — PERMANENT NGROK FIX (added 2026-06-12)

### What changed

`start_provoc.py` was fully rewritten to replace cloudflared with ngrok. Cloudflared was returning Error 1033 ("tunnel not found") frequently on this machine. ngrok is now the permanent solution.

### What was removed

- All cloudflared `subprocess.Popen` calls
- URL extraction regex (`re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', ...)`)
- All other cloudflared references

### What was added

1. `kill_port(5000)` and `kill_port(4040)` — kills any lingering uvicorn or ngrok processes before starting fresh. Uses `netstat -ano` + `taskkill /PID /F`.
2. `subprocess.Popen([NGROK_BIN, "http", "5000"])` — starts ngrok tunnel.
3. Retry loop (6 attempts × 2 s) to fetch the tunnel URL from `http://127.0.0.1:4040/api/tunnels`.
4. `NGROK_BIN` resolution — prefers `ngrok.exe` in the project directory, falls back to `shutil.which("ngrok")`.

### Chocolatey shim issue

The system ngrok at `C:\ProgramData\chocolatey\bin\ngrok.exe` is a Chocolatey shim pointing to a missing binary at `C:\ProgramData\chocolatey\lib\ngrok\tools\ngrok.exe`. `choco upgrade ngrok` also fails with an access denied error (`C:\ProgramData\chocolatey\lib\ngrok\.chocolateyPending` lock).

**Fix:** Standalone ngrok v3.39.7 was downloaded from the ngrok website directly into the project root as `ngrok.exe`. This file is gitignored (`.gitignore` entry: `ngrok.exe`). On a new machine, download from `https://ngrok.com/download` (ngrok v3, Windows 64-bit) and place `ngrok.exe` in the project root.

### UnicodeEncodeError note

On Windows terminals using `cp1252` encoding, `print("\n✅ ProVOC AI is ready!")` raises `UnicodeEncodeError: 'charmap' codec can't encode character '✅'`. The Railway URL update has already been sent by this point so the service is fully operational despite the console error. Fix: replace the emoji with `[OK]` in `start_provoc.py:126`, or run the terminal with `PYTHONIOENCODING=utf-8`.

### ngrok authentication requirement

ngrok v3 requires a one-time authentication: `ngrok config add-authtoken <token>`. The token is stored in `%APPDATA%\ngrok\ngrok.yml`. If ngrok is not authenticated, the tunnel API at `127.0.0.1:4040` returns an empty tunnels list and the script exits with `ERROR: Could not get tunnel URL`.

---

## 26. RECOMMENDATIONS DATA — RESEED (added 2026-06-12)

### Background

The initial Milvus seeding used placeholder `business_id` values (e.g., `"ChIJbella1"`) that do not match real Google Place IDs. This caused the recommendation engine to surface businesses that do not exist in the mobile app's business database.

### What was done

- **`fix_place_ids.py`** — one-shot script that replaces placeholder `business_id` values in the Milvus `taste_vectors` collection with real Google Place IDs by deleting and re-inserting the affected vectors.
- **`seed_recommendations.py`** — full reseed script that clears `taste_vectors` and inserts 13 reviews across multiple simulated users, using real Google Place IDs from the production restaurant database.

### Real account seeded

User `b009eaa2-fd6c-4b3e-bcf0-731ce237cf39` (the demo test account) has **5 recommendations** available after the reseed.

### How to reseed from scratch

```bash
# With Milvus running and venv activated:
venv\Scripts\python.exe seed_recommendations.py
```

> **Warning:** `seed_recommendations.py` clears the entire `taste_vectors` collection before re-inserting. Do not run against a production instance that has real user review data.

---

## 27. KNOWN STARTUP ISSUE — VENV IS REQUIRED (added 2026-06-12)

### Problem

`start_provoc.py` launches uvicorn via `sys.executable`, so uvicorn inherits the Python interpreter that ran the script. If the script is launched with system Python (`C:\Users\Rabie\AppData\Local\Programs\Python\Python311\python.exe`), the server fails immediately at startup:

```
ModuleNotFoundError: No module named 'pymilvus'
```

`pymilvus`, `sentence-transformers`, `langfuse`, and several other dependencies are only installed in the project venv (`D:\pfe ai\pv-ai\venv\`), not in system Python.

### Fix

Always run `start_provoc.py` from the activated venv:

```bash
cd "D:\pfe ai\pv-ai"
venv\Scripts\activate
python start_provoc.py
```

Or pass the venv interpreter explicitly:

```bash
"D:\pfe ai\pv-ai\venv\Scripts\python.exe" "D:\pfe ai\pv-ai\start_provoc.py"
```

### Milvus Docker containers

The three Milvus containers (`milvus-etcd`, `milvus-minio`, `milvus-standalone`) run independently via `milvus-docker-compose.yml` — they are not started by `start_provoc.py`. Start them separately before launching the server:

```bash
docker compose -f milvus-docker-compose.yml up -d
```

If Milvus is not running, `TasteEngine` gracefully degrades: `/api/recommendations` returns `[]` and `/api/chat/approve` silently skips the taste-vector write. The rest of the API is unaffected.

---

## 28. DEMO DAY — FULL STARTUP SEQUENCE (added 2026-06-12)

### Prerequisites

- Docker Desktop running
- ngrok authenticated (`ngrok config add-authtoken <token>`)
- `D:\pfe ai\pv-ai\ngrok.exe` present (standalone binary, not the broken Chocolatey shim)
- `.env` contains `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `DATABASE_URL`, `BFF_SHARED_SECRET`, `GROQ_API_KEY`

### Startup commands

```bash
# Step 1 — Start Milvus (if not already running)
docker compose -f milvus-docker-compose.yml up -d

# Step 2 — Activate venv and start the server + tunnel
cd "D:\pfe ai\pv-ai"
venv\Scripts\activate
python start_provoc.py
```

`start_provoc.py` will kill stale processes on ports 5000 and 4040, start uvicorn, start ngrok, update Railway `FASTAPI_URL`, print the tunnel URL, and hold until Ctrl+C.

### Health check

```bash
curl http://127.0.0.1:5000/health
```

Expected when everything is healthy:

```json
{"status": "ok", "db": "connected", "redis": "connected", "whisper": "loaded", "langfuse": "connected", "mode": "live"}
```

### Quick diagnostics

| Symptom | Likely cause | Fix |
|---|---|---|
| `langfuse: "disabled"` in health | Missing Langfuse credentials in `.env` | Add `LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY` from the Langfuse dashboard |
| `GET /api/recommendations` returns `[]` | Milvus not running or empty collection | Run `docker compose -f milvus-docker-compose.yml up -d`, then `python seed_recommendations.py` |
| `ModuleNotFoundError: pymilvus` on start | Script run with system Python, not venv | Run `venv\Scripts\activate` first, then `python start_provoc.py` |
| `ERROR: Could not get tunnel URL` | ngrok not authenticated or binary missing | Run `ngrok config add-authtoken <token>` or re-download `ngrok.exe` |
