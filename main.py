import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import config
from database import get_milvus
from auth import router as auth_router
from yelp import router as yelp_router
from lists import router as lists_router
from memos import router as memos_router
from tasks import router as tasks_router
from chat import router as chat_router
from transcription import router as transcription_router

milvus_client = get_milvus()

app = FastAPI(title="PV-AI Backend")

# CORS — registered before routers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    print(f"DEBUG: Incoming {request.method} to {request.url.path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    print(f"DEBUG: Finished {request.method} {request.url.path} in {process_time:.2f}s with status {response.status_code}")
    return response


@app.get("/")
async def root():
    return {"message": "PV-AI API", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health():
    from transcription import whisper_model

    # DB check
    if config.NO_DB_MODE:
        db_status = "mock"
    else:
        try:
            from database import engine
            from sqlalchemy import text
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:
            db_status = f"error: {exc}"

    # Redis check
    try:
        import redis as _redis
        r = _redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        r.ping()
        redis_status = "connected"
    except Exception as exc:
        redis_status = f"error: {exc}"

    # Whisper check
    whisper_status = "loaded" if whisper_model is not None else "not loaded"

    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "whisper": whisper_status,
        "mode": "NO_DB_MODE" if config.NO_DB_MODE else "live",
    }


# Register Routers
app.include_router(auth_router)
app.include_router(yelp_router)
app.include_router(lists_router)
app.include_router(memos_router)
app.include_router(tasks_router)
app.include_router(chat_router)
app.include_router(transcription_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
