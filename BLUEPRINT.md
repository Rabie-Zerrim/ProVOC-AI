# Focusaurus Backend Blueprint

## TL Summary — What Is This Project?

**Focusaurus** is an AI-powered voice review assistant. The idea is simple: instead of typing out a Yelp review, the user records their voice, and the app does the rest.

### The Flow

Imagine you just had lunch at a restaurant and want to leave a review — but you don't want to sit there typing a paragraph. Here's what happens instead:

**Step 1 — Pick the business**
The user opens the app and selects the restaurant they visited from a list. No searching on Yelp, no copy-pasting links. The business is already there.

**Step 2 — Record a voice note**
The user taps record and just talks — like leaving a voice message. *"The pizza was amazing, super crispy. Service was a bit slow but the staff were friendly. I'd give it a 4 out of 5."* That's it. No typing.

**Step 3 — Whisper transcribes and detects the language**
>  **Model: OpenAI Whisper `tiny`** — `main.py:33` loads the model, `main.py:122` runs the transcription
>  Files: `main.py:101-138`

The audio is sent to the backend where OpenAI Whisper (a speech recognition model) converts it to text. Whisper also automatically identifies the language the user spoke in — English, French, or Spanish. If the user speaks in any other language (Arabic, Hungarian, etc.), the system rejects it immediately with a clear message asking them to use a supported language. Nothing gets passed to the AI until the language is confirmed valid.
```
main.py:33  → whisper_model = whisper.load_model("tiny").to(device)
main.py:122 → result = whisper_model.transcribe(temp_filename, **options)
main.py:124 → detected_language = result.get("language", "unknown")
main.py:125 → if detected_language not in ACCEPTED_LANGUAGES: reject
config.py:19 → ACCEPTED_LANGUAGES = ["en", "es", "fr"]
```

**Step 4 — AI extracts the key information**
>  **Model: Groq Llama 3.3 70B** (`llama-3.3-70b-versatile`) — `chat.py:62-69`
>  Files: `chat.py:62-101`, `prompts.py:4-25`

The transcribed text is sent to Groq's hosted Llama 3.3 70B model. The prompt driving this step is `REVIEW_ANALYSIS_PROMPT` in `prompts.py:4`, injected with the listing context (business name, social networks, preferences). The AI reads the text and pulls out:
- The restaurant name
- The overall sentiment — Positive, Negative, or Neutral
- A predicted star rating (1–5) based on what was said, or the exact rating if the user mentioned one
- Key points — food quality, service, ambiance, price

The result is stored as the first assistant message in the Redis session's `chat_history`.
```
chat.py:44   → _build_system_prompt(listing_context) — injects business context into REVIEW_ANALYSIS_PROMPT
chat.py:62   → _call_groq([system, user: transcript]) — gets initial extraction response
chat.py:72   → save_session(session_id, session) — persists to Redis with 30-min TTL
prompts.py:4 → REVIEW_ANALYSIS_PROMPT — instructs AI to extract restaurant, sentiment, rating, entities
```

**Step 5 — AI confirms with the user and iterates**
>  **Model: Groq Llama 3.3 70B** — same model, full chat history passed on every turn
>  Files: `chat.py:84-103`

NestJS calls `POST /api/chat/message` for each follow-up user message. The full `chat_history` is sent to Groq on every call — this is what gives the AI memory across turns. The user can correct extracted info, ask for rewrites, or request more detail. The Redis TTL resets to 30 minutes on every message so inactive sessions expire cleanly.
```
chat.py:84   → session = get_session(session_id) — loads from Redis, 404 if expired
chat.py:88   → session["chat_history"].append({"role": "user", "content": message})
chat.py:91   → _call_groq(session["chat_history"]) — full history sent to Groq
chat.py:95   → save_session(session_id, session) — resets TTL, persists updated history
prompts.py:41 → "RÉPONDEZ TOUJOURS DANS LA MÊME LANGUE QUE L'UTILISATEUR" — language mirror rule
```

**Step 6 — Approve and get structured output**
>  **Model: Groq Llama 3.3 70B** — low temperature (0.2) for deterministic JSON
>  Files: `chat.py:106-145`

When NestJS calls `POST /api/chat/approve`, the backend sends a final structured-JSON extraction prompt appended to the existing history. The AI returns a strict JSON object — no markdown, no explanation. The backend regex-extracts the JSON, validates it, marks the session as `approved` in Redis, and returns the result to NestJS.
```
chat.py:113  → approval_prompt — asks AI for strict JSON: improved_text, rating, sentiment, tone, key_points
chat.py:121  → _call_groq(..., temperature=0.2) — low temp for consistent JSON output
chat.py:130  → re.search(r'\{.*\}', raw, re.DOTALL) — extracts JSON from response
chat.py:137  → session["status"] = "approved"
```

**Step 7 — Session cleanup**
`POST /api/chat/end` deletes the Redis key immediately. Sessions also auto-expire after 30 minutes of inactivity (TTL set via Redis `SETEX`). NestJS can also read the full session at any time via `GET /api/chat/session/{id}`.
```
chat.py:148  → delete_session(session_id) — removes Redis key
redis_client.py:11 → SESSION_TTL = 1800 — 30-minute auto-expiry
redis_client.py:19 → _client.setex(...) — TTL reset on every save
```

**Throughout all of this — the AI speaks the user's language.** A French speaker gets French responses. A Spanish speaker gets Spanish. The language detected at Step 3 drives the entire conversation automatically (`prompts.py:41`).

---

## What Was Built

### PV-121 — Multi-Language Support (English, French, Spanish)
Defined a single config constant `ACCEPTED_LANGUAGES = ["en", "es", "fr"]` in `config.py`. Every endpoint imports and validates against this list — no language string is hardcoded anywhere else. Adding a new language in the future means changing one line.

**Auto Language Detection**
The `/api/transcribe` endpoint accepts a `language` field that defaults to `"auto"`. When set to auto, no language hint is passed to Whisper and it detects from the audio itself. The detected language is returned so the frontend always knows what was spoken.

**Unsupported Language Rejection**
Post-transcription check: if the detected language is not in `ACCEPTED_LANGUAGES`, the API returns a clear error instead of silently passing bad data to the AI.

**Language Validation on All Endpoints**
The same guard is applied at: `POST /api/transcribe`, `PUT /api/yelp/reviews/{id}/transcription`, `POST /api/yelp/reviews/{id}/chat`, and `POST /api/chat/start`.

**Code Quality (same PR)**
- Replaced `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)`
- Renamed camelCase parameters to snake_case
- Moved blocking file I/O off the async event loop using `asyncio.to_thread()`
- SonarQube CI via GitHub Actions on `dev` branch

### PV-??? — Redis Chat Session Management
Added a proper server-side session layer so NestJS can open, use, and close AI sessions per review without managing any state itself.

**New endpoints (`chat.py`):**

| Endpoint | Purpose |
|---|---|
| `POST /api/chat/start` | Validate language, build system prompt with listing context, call Groq with transcript, store session in Redis, return `session_id` + `initial_response` |
| `POST /api/chat/message` | Load session (404 if missing/expired), append user message, call Groq with full history, append reply, reset TTL |
| `POST /api/chat/approve` | Send structured-JSON extraction prompt at temp=0.2, parse result, mark session `approved` |
| `POST /api/chat/end` | Delete Redis key immediately |
| `GET /api/chat/session/{id}` | Return full session data including `chat_history` |

**Redis session schema:**
```json
{
  "session_id": "uuid",
  "review_id": "str",
  "listing_id": "str",
  "detected_language": "en|es|fr",
  "listing_context": { "business_name": "...", "network_names": [...], "network_preferences": {} },
  "chat_history": [
    { "role": "system", "content": "REVIEW_ANALYSIS_PROMPT + listing context" },
    { "role": "assistant", "content": "initial extraction response" },
    { "role": "user", "content": "..." },
    ...
  ],
  "status": "active | approved",
  "created_at": "ISO timestamp"
}
```
Key pattern: `session:{session_id}` — TTL: 1800s, reset on every `POST /api/chat/message`.

---

## Technology Stack

| What | Tool |
|---|---|
| Speech-to-Text | OpenAI Whisper (tiny model, auto language detection) |
| AI Chat & Analysis | Groq Llama 3.3 70B (`llama-3.3-70b-versatile`) |
| Session Storage | Redis 7 (`redis-py` 7.4, key: `session:{id}`, TTL: 30 min) |
| Backend API | FastAPI 0.110 (Python 3.11, Windows venv) |
| Auth | JWT + bcrypt (`python-jose`, `passlib`) |
| Vector DB | Milvus (mocked, no-DB mode) |
| Supported Languages | English (`en`), French (`fr`), Spanish (`es`) |

---

## Directory Structure

Working directory: `D:\pfe ai\pv-ai\`

```
pv-ai/
├── main.py           # FastAPI app, Whisper loader, router registration
├── chat.py           # Redis-backed chat session endpoints (/api/chat/*)
├── redis_client.py   # Redis connection, get/save/delete session helpers
├── yelp.py           # Legacy Yelp review routes (/api/yelp/*)
├── auth.py           # JWT authentication (/api/auth/*)
├── tasks.py          # Task management routes (/api/tasks/*)
├── lists.py          # List management routes (/api/lists/*)
├── memos.py          # Memo management routes (/api/memos/*)
├── ai_engine.py      # Groq review insight extraction utility
├── models.py         # SQLAlchemy ORM models
├── database.py       # Mock Milvus client (no-DB mode)
├── config.py         # Env config, ACCEPTED_LANGUAGES, GROQ_API_KEY
├── prompts.py        # AI prompt templates (REVIEW_ANALYSIS_PROMPT, etc.)
├── verify.py         # Live integration test script (all 5 session checks)
├── requirements.txt  # Python dependencies
└── BLUEPRINT.md      # This file
```

## Commands

```powershell
# Working directory
cd "D:\pfe ai\pv-ai"

# Activate venv (Windows)
.\venv\Scripts\Activate.ps1

# Install dependencies
.\venv\Scripts\pip install -r requirements.txt

# Start Redis (Docker)
docker run -d --name redis-pv -p 6379:6379 redis:7-alpine

# Start server
$env:PYTHONIOENCODING="utf-8"
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 5000

# Run integration tests (server + Redis must be running)
.\venv\Scripts\python.exe verify.py
```

---

## Steps Applied

### Development Workflow

1. **Architecture Setup**
   - FastAPI with CORS enabled (wildcard for testing)
   - Modular router structure (auth, yelp, lists, memos, tasks, chat)
   - Mock database layer for zero-DB development

2. **AI Integration**
   - Whisper model loaded on startup (device detection CUDA/CPU)
   - Groq client initialized for chat completions
   - Prompt engineering in `prompts.py`

3. **Route Implementation**
   - `POST /api/transcribe` — Audio transcription with language detection
   - `POST /api/yelp/reviews/{id}/chat` — Legacy stateless chat
   - `POST /api/chat/start` — Open Redis session, get initial AI extraction
   - `POST /api/chat/message` — Send message, full history to Groq, reset TTL
   - `POST /api/chat/approve` — Structured JSON output, mark session approved
   - `POST /api/chat/end` — Delete session from Redis
   - `GET /api/chat/session/{id}` — Read full session + chat history
   - `GET|POST /api/tasks/*`, `/api/lists/*`, `/api/memos/*` — CRUD operations
   - `POST /api/auth/*` — JWT token generation

4. **Session Management (Redis)**
   - `redis_client.py` — thin wrapper: `get_session`, `save_session` (SETEX 1800s), `delete_session`
   - Sessions stored as JSON under key `session:{uuid}`
   - TTL resets to 30 min on every `/message` call
   - 404 returned if key is missing or expired

5. **Testing**
   - `verify.py` — 29-check integration test covering all 5 session lifecycle steps
   - Test user ID hardcoded for rapid iteration
   - Mock Milvus client returns empty lists/success responses

---

## Language Detection — Next Improvements

### 1. Confidence Score Threshold
Whisper returns a confidence score per segment. Right now we accept any detection above 0% confidence. The fix: reject transcriptions where the average confidence is below a threshold.
```python
avg_confidence = sum(s["avg_logprob"] for s in result["segments"]) / len(result["segments"])
if avg_confidence < -1.0:
    return {"success": False, "error": "Audio quality too low to detect language reliably."}
```

### 2. Upgrade Whisper Model Size
Currently using `tiny` for speed. Language detection accuracy improves significantly with a larger model:

| Model | Size | Detection Accuracy |
|---|---|---|
| tiny | 39M | ~80% |
| base | 74M | ~88% |
| small | 244M | ~93% |

Swap in `config.py`: `WHISPER_MODEL = "base"` and load it in `main.py`.

### 3. Detect Language Before Full Transcription
Whisper can run a fast language-detection-only pass before doing the full transcription. This saves time — if the language is unsupported, we reject early without wasting compute.
```python
audio = whisper.load_audio(temp_filename)
audio = whisper.pad_or_trim(audio)
mel = whisper.log_mel_spectrogram(audio).to(device)
_, probs = whisper_model.detect_language(mel)
detected = max(probs, key=probs.get)
if detected not in ACCEPTED_LANGUAGES:
    return {"success": False, "error": f"Language '{detected}' not supported."}
```

### 4. Language-Specific AI Prompts
Right now the AI uses the same prompt for all three languages. Next step: maintain a prompt variant per language in `prompts.py` so tone and style match local expectations.

### 5. Expand Supported Languages
Adding a new language requires one line change in `config.py`. Blockers:
- Whisper: supports it natively — no work needed
- Groq Llama 3.3: handles most major languages — no work needed
- Prompts: need a tone/style review per new language
- Frontend: dropdown needs the new option

Candidate next languages: **Arabic (ar)**, **Portuguese (pt)**, **Italian (it)**

### 6. User Language Preference
Store the user's preferred language in their profile. Use it as the default hint to Whisper instead of always starting from `"auto"`.

---

## Future Steps

### Priority Features

- [ ] **Database Integration** — Switch from mock to real Milvus/PostgreSQL
- [ ] **Production Auth** — Remove test bypass, implement proper JWT validation
- [ ] **Real Yelp API** — Replace static businesses with live Yelp data
- [ ] **Redis Persistence** — Configure Redis AOF/RDB for session durability across restarts
- [ ] **Session Auth** — Tie sessions to authenticated user IDs (prevent cross-user access)
- [ ] **Vector Search** — Enable semantic search in memos
- [ ] **WebSocket** — Real-time streaming of AI responses during chat

### Technical Debt

- [ ] Move test credentials to `.env`
- [ ] Add database migrations (Alembic)
- [ ] Implement rate limiting
- [ ] Set up CI/CD with SonarCloud
- [ ] Write unit tests for core routes
- [ ] Pin `openai` and other unpinned packages in `requirements.txt`

### Nice-to-Have

- [ ] Email notifications for task reminders
- [ ] Push notifications (Expo/Pushover)
- [ ] Export tasks to CSV/JSON
- [ ] Calendar integration (Google/Outlook)
- [ ] Mobile app (React Native/Flutter)
