# ProVOC AI Sidecar (`pv-ai`)

FastAPI backend that handles the AI-heavy work for ProVOC:
- Speech-to-text transcription (Whisper / Groq Whisper API)
- Multi-turn AI review drafting (Groq LLaMA 3.3 70B)
- Redis-backed chat session management
- Personalised business recommendations (Zilliz Cloud / Milvus)
- Content moderation

This service is **internal only** — it is never called directly from the mobile app. All requests come from `pv-bff`, which authenticates them via a JWT relay mechanism.

---

## Table of contents

1. [Architecture role](#architecture-role)
2. [Tech stack](#tech-stack)
3. [Prerequisites](#prerequisites)
4. [Environment variables](#environment-variables)
5. [Running locally](#running-locally)
6. [API reference](#api-reference)
7. [AI components](#ai-components)
8. [Prompt management (Langfuse)](#prompt-management-langfuse)
9. [Recommendations engine](#recommendations-engine)
10. [Deployment (Railway)](#deployment-railway)
11. [Known issues and deferred items](#known-issues-and-deferred-items)

---

## Architecture role

```
pv-app  ──►  pv-bff  ──►  pv-ai
                │              │
                │          Groq API
                │          Redis
                │          Zilliz (Milvus)
                │          Langfuse
             Postgres
             Zembra API
             Google Places API
```

`pv-bff` authenticates to `pv-ai` via a shared-secret relay:

1. BFF calls `POST /api/auth/token/relay` with `X-BFF-Secret`.
2. pv-ai returns a 30-minute relay JWT (`"relay": true` claim).
3. BFF caches the token per user (25-minute TTL) and attaches it as `Authorization: Bearer` on all subsequent pv-ai calls.

---

## Tech stack

| Package | Version | Purpose |
|---|---|---|
| FastAPI | 0.110.0 | HTTP framework |
| uvicorn | 0.27.1 | ASGI server |
| pydantic | 2.6.1 | Request/response validation |
| groq | latest | LLaMA 3.3 70B inference + Whisper API |
| openai-whisper | latest | Local Whisper (fallback when Groq unavailable) |
| torch | 2.11.0 | PyTorch (CPU-only in production) |
| redis | latest | Chat session persistence |
| sqlalchemy | 2.0.40 | User DB (auth only) |
| alembic | latest | DB migrations |
| pymilvus | ≥2.4.0 | Milvus / Zilliz vector DB |
| sentence-transformers | ≥2.2.0 | `all-MiniLM-L6-v2` embeddings for recommendations |
| langfuse | ≥2.0.0 | Prompt management |
| python-jose | 3.3.0 | JWT signing/verification |
| passlib[bcrypt] | 1.7.4 | Password hashing |

---

## Prerequisites

- Python 3.11 (preferred; 3.12 has some `torch` compatibility notes)
- Docker Desktop — for Redis
- A Groq API key from [console.groq.com](https://console.groq.com)
- A Langfuse account (optional — falls back to hardcoded prompts)
- A Zilliz Cloud account (optional — recommendations return `[]` without it)

---

## Environment variables

Create a `.env` file in the project root. All variables are loaded by `config.py`.

| Variable | Required | Purpose |
|---|---|---|
| `JWT_SECRET` | Yes | JWT signing key — use a 64-char random string in production |
| `GROQ_API_KEY` | Yes | Groq inference (LLaMA + Whisper API) |
| `GROQ_WHISPER` | Yes | `true` → use Groq Whisper API (fast, recommended); `false` → use local Whisper |
| `REDIS_HOST` | Yes | Redis hostname (e.g. `localhost`) |
| `REDIS_PORT` | Yes | Redis port (default `6379`) |
| `REDIS_PASSWORD` | No | Redis auth password |
| `WHISPER_MODEL` | Yes | Base Whisper model size: `tiny`, `base`, `small` (used when `GROQ_WHISPER=false`) |
| `USE_FINETUNED_WHISPER` | No | `true` → load fine-tuned Whisper from `FINETUNED_WHISPER_PATH` (requires sufficient RAM) |
| `FINETUNED_WHISPER_PATH` | No | Path to fine-tuned model directory (e.g. `./whisper-provoc-small/final`) |
| `LLM_MODEL` | Yes | Groq model identifier (e.g. `llama-3.3-70b-versatile`) |
| `BFF_SHARED_SECRET` | Yes | Shared secret for the `POST /api/auth/token/relay` endpoint |
| `DATABASE_URL` | Yes | Async PostgreSQL connection string (asyncpg) |
| `DATABASE_URL_SYNC` | Yes | Sync connection string (Alembic) |
| `MILVUS_URI` | No | Zilliz/Milvus endpoint. Format: `https://<cluster>.zillizcloud.com?token=<api-key>`. Defaults to `http://localhost:19530` |
| `LANGFUSE_SECRET_KEY` | No | Langfuse API secret |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse API public key |
| `LANGFUSE_HOST` | No | Langfuse host (default: `https://cloud.langfuse.com`) |
| `ALLOWED_ORIGINS` | Yes | Comma-separated CORS origins — no spaces around commas |

> **Security note:** never commit a real `GROQ_API_KEY` to source control. The `.env` file is gitignored.

Generate a strong JWT secret:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Running locally

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux / macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Redis
docker run -d --name redis-pv-ai -p 6379:6379 redis:7-alpine

# 4. Apply database migrations
alembic upgrade head

# 5. Start the server (IPv6 bind required so pv-bff can reach it via localhost)
uvicorn main:app --host :: --port 5000

# Interactive API docs available at:
# http://localhost:5000/docs
```

> **Important — `--host ::`**: pv-bff on the same machine connects to pv-ai via `localhost`. On some systems, Node.js resolves `localhost` to `::1` (IPv6). Starting uvicorn with `--host ::` binds to both IPv4 and IPv6 and avoids 503 errors from pv-bff.

### Run the integration test suite

```bash
python verify.py
# Runs 5 checks: server + Redis reachable, chat/start, chat/message, chat/approve, expired session
```

---

## API reference

All endpoints are under the prefix `/api`. Full interactive docs at `/docs`.

### Auth

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | Public | Creates user in DB; returns JWT |
| `POST` | `/api/auth/login` | Public | Verifies bcrypt password; returns JWT |
| `GET` | `/api/auth/me` | Bearer JWT | Returns `user_id`, `email`, `display_name`, `avatar_data` |
| `POST` | `/api/auth/token/relay` | `X-BFF-Secret` header | Service-to-service relay: BFF provides its shared secret + `user_id`; returns a 30-min relay JWT |

### Transcription

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/health-check/transcribe` | Public | Returns Whisper status, device (cpu/cuda), mode |
| `POST` | `/api/transcribe` | Bearer JWT | Multipart audio upload → transcribed text + language |

The transcription priority order is: **Groq Whisper** (`GROQ_WHISPER=true`) → **fine-tuned local Whisper** (`USE_FINETUNED_WHISPER=true`) → **baseline local Whisper**.

When `GROQ_WHISPER=true` the local Whisper model is not loaded at startup, saving RAM and boot time.

### Chat

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/chat/start` | Bearer JWT | Start or resume a review session. Body: `{ session_id?, transcript, listing_context, language, previous_messages?, purpose?, conversation_summary? }` |
| `POST` | `/api/chat/message` | Bearer JWT | Send a chat turn. Body: `{ session_id, message, purpose? }` |
| `POST` | `/api/chat/approve` | Bearer JWT | Extract structured review from conversation; stores taste vector in Milvus |
| `POST` | `/api/chat/filter` | Bearer JWT | Content moderation. Body: `{ text }`. Returns `{ approved, warning?, reason?, suggestion? }` |
| `POST` | `/api/chat/end` | Bearer JWT | Delete the Redis session |
| `GET` | `/api/chat/session/:id` | Bearer JWT | Raw session data from Redis |

#### `purpose` field routing

| Endpoint | `purpose` value | Prompt used |
|---|---|---|
| `chat/start` | `"start"` (default) | `system-prompt` (Langfuse) |
| `chat/start` | `"regenerate"` | `chat-regenerate` (Langfuse) |
| `chat/message` | `"message"` (default) | `chat-message` (Langfuse, fetched per-request) |
| `chat/message` | `"rephrase"` | `chat-rephrase` (Langfuse, fetched per-request) |

### Recommendations

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/recommendations` | Bearer JWT | Personalised business recommendations via collaborative filtering. Returns `[]` if Milvus unavailable or user has no prior reviews |

---

## AI components

### Groq Whisper (production)

Model: `whisper-large-v3-turbo`. Enabled by `GROQ_WHISPER=true`.  
Transcription time in production: **~0.3 seconds** (vs 130–287 seconds for local Whisper on Railway's current CPU tier).  
Language normalisation is applied: Groq returns full names (`"English"`) which are mapped to codes (`"en"`).

### Fine-tuned Whisper small (`whisper-provoc-v1`)

Trained on 900 multilingual samples (EN/FR/ES, 300 each) from MLS.  
WER improvement on MLS dev split (clean audio):

| Language | Baseline WER | Fine-tuned WER | Improvement |
|---|---|---|---|
| EN | 19.18 % | 4.78 % | −14.4 pp |
| FR | 36.06 % | 20.67 % | −15.4 pp |
| ES | 24.12 % | 9.13 % | −15.0 pp |
| **Average** | **26.45 %** | **11.53 %** | **−56.4 % relative** |

Currently **disabled** in production (`USE_FINETUNED_WHISPER=false`) — Railway's current CPU tier causes OOM with the `small` model. Re-enable by upgrading the Railway plan and setting `USE_FINETUNED_WHISPER=true`.

### Groq LLaMA 3.3 70B

All chat, approve, and filter endpoints call the Groq API via `llama-3.3-70b-versatile` (configurable via `LLM_MODEL`). Redis sessions have a 30-minute TTL; each `save_session` call resets the clock.

---

## Prompt management (Langfuse)

All six prompts are registered in Langfuse under the `"production"` label:

| Langfuse key | Used by | Fetch strategy |
|---|---|---|
| `system-prompt` | `chat/start` (purpose=start) | Module-level constant (restart to pick up changes) |
| `chat-regenerate` | `chat/start` (purpose=regenerate) | Per-request via `get_prompt()` |
| `chat-message` | `chat/message` (purpose=message) | Per-request via `get_prompt()` |
| `chat-rephrase` | `chat/message` (purpose=rephrase) | Per-request via `get_prompt()` |
| `chat-resume` | `chat/start` when `conversation_summary` present | Per-request via `get_prompt()` |
| `chat-filter` | `chat/filter` | Per-request via `get_prompt()` |

Per-request prompts propagate within ~60 seconds of a Langfuse dashboard update. `system-prompt` requires a server restart.

If Langfuse is unreachable, all prompts fall back silently to hardcoded strings — the server always starts.

To register/update prompts:

```bash
python register_prompts.py
```

---

## Recommendations engine

`taste_engine.py` stores per-user taste vectors in Milvus and returns personalised recommendations via collaborative filtering.

- **Embedding model:** `all-MiniLM-L6-v2` (384-dimensional, loaded lazily)
- **Input:** `"{business_name} {business_type} {review_text}"` concatenation
- **Collection:** `taste_vectors` in Zilliz Cloud Serverless (EU Central)
- **Algorithm:** average user's 20 most recent vectors → cosine similarity against other users' reviews → deduplicate → return top N

A taste vector is stored automatically on every successful `chat/approve` call. If Milvus is unavailable, the store is silently skipped and recommendations return `[]`.

**Seeding demo data:**
```bash
python seed_recommendations.py   # clears collection and inserts 13 demo vectors
```

---

## Deployment (Railway)

The service is deployed via Dockerfile (Railpack was abandoned due to unresolved platform bugs with the `grpcio` pin in pymilvus 2.3.4 and a broken venv cache checksum).

Key Railway environment variables (values in Railway dashboard — not duplicated here):

`GROQ_API_KEY`, `GROQ_WHISPER`, `LLM_MODEL`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `JWT_SECRET`, `BFF_SHARED_SECRET`, `DATABASE_URL`, `DATABASE_URL_SYNC`, `MILVUS_URI`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_HOST`, `ALLOWED_ORIGINS`, `USE_FINETUNED_WHISPER`, `WHISPER_MODEL`

**Health check:**
```bash
curl https://provoc-ai-production.up.railway.app/health
# → { "status": "ok", "db": "connected", "redis": "connected", "whisper": "loaded", "langfuse": "connected", "mode": "live" }
```

---

## Known issues and deferred items

| Item | Status |
|---|---|
| Fine-tuned Whisper on Railway | Disabled — OOM on current CPU tier. Options: upgrade plan, quantize model (int8), or fine-tune a smaller base (`tiny`/`base`). Do not re-enable without addressing one of these. |
| Persistent chat history across sessions | Deferred. Only the final review text is saved, not the full conversation. Resuming an old review gives the AI no memory of the original chat. Fixing requires persisting conversation history and passing it as `previous_messages` on resume. |
| `purpose` field wiring from pv-bff | **Complete** as of 2026-06-24. pv-bff derives and forwards the correct `purpose` value on all `chat/start` and `chat/message` calls. |
| Langfuse prompt text for new prompts | `chat-message`, `chat-rephrase`, `chat-regenerate` were created this session — update with real tuned text in Langfuse dashboard. |
| `ai_engine.py` | Dead code. `extract_review_insights()` uses the cleaner `response_format=json_object` approach. Either integrate into `chat.py` or delete. |
| `REVIEW_INTERACTION_PROMPT` / `FINAL_REPORT_PROMPT` in `prompts.py` | Dead code — never imported anywhere. |
| No CI pipeline | `.github/workflows/` directory exists but is empty. |
