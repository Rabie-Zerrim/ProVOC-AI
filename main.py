import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import config
from database import get_milvus
from langfuse_client import get_langfuse_client
from endpoints.v1.auth import router as auth_router
from endpoints.v1.yelp import router as yelp_router
from lists import router as lists_router
from memos import router as memos_router
from tasks import router as tasks_router
from endpoints.v1.chat import router as chat_router
from endpoints.v1.transcription import router as transcription_router

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
async def root() -> dict:
    return {"message": "PV-AI API", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health() -> dict:
    import asyncio
    import socket
    import threading
    from endpoints.v1.transcription import whisper_model

    def _redis_ping() -> str:
        # redis.Redis(socket_connect_timeout=N) does not reliably time out
        # on Windows (raw socket settimeout works; redis-py internals do not).
        # Use a raw socket so the 2 s limit is guaranteed.
        try:
            _redis_url = os.getenv("REDIS_URL")
            if _redis_url:
                from urllib.parse import urlparse as _up
                _p = _up(_redis_url)
                host, port, password = _p.hostname, _p.port, _p.password
            else:
                host = socket.gethostbyname(config.REDIS_HOST)
                port = config.REDIS_PORT
                password = config.REDIS_PASSWORD

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                s.connect((host, port))
                if password:
                    auth_cmd = f"*2\r\n$4\r\nAUTH\r\n${len(password)}\r\n{password}\r\n"
                    s.sendall(auth_cmd.encode())
                    auth_resp = s.recv(100)
                    if not auth_resp.startswith(b"+OK"):
                        return f"error: auth failed {auth_resp!r}"
                s.sendall(b"*1\r\n$4\r\nPING\r\n")
                response = s.recv(7)
                return "connected" if response == b"+PONG\r\n" else f"error: bad response {response!r}"
            finally:
                s.close()
        except socket.timeout:
            return "error: timeout"
        except ConnectionRefusedError:
            return "error: connection refused"
        except Exception as exc:
            return f"error: {exc}"

    def _db_ping_threaded() -> str:
        # asyncio.wait_for() cannot preempt a C-level socket connect on
        # Python 3.11+ because wait_for waits for cancellation to complete.
        # Run asyncpg in a daemon thread with a hard join timeout instead.
        if config.NO_DB_MODE:
            return "mock"
        result = {"value": "error: timeout"}

        def _run():
            import asyncio as _aio
            import asyncpg as _asyncpg
            loop = _aio.new_event_loop()
            try:
                async def _connect():
                    dsn = config.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
                    c = await _asyncpg.connect(dsn)
                    await c.close()
                    return "connected"
                result["value"] = loop.run_until_complete(_connect())
            except Exception as exc:
                result["value"] = f"error: {exc}"
            finally:
                loop.close()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=2.5)
        return result["value"]

    # Both checks run concurrently via asyncio.to_thread.
    # Wall time = max(2.5, 2) ≈ 2.5 s worst case.
    db_result, redis_result = await asyncio.gather(
        asyncio.to_thread(_db_ping_threaded),
        asyncio.to_thread(_redis_ping),
        return_exceptions=True,
    )

    db_status = db_result if isinstance(db_result, str) else f"error: {db_result}"
    redis_status = redis_result if isinstance(redis_result, str) else f"error: {redis_result}"
    whisper_status = "loaded" if whisper_model is not None else "not loaded"

    langfuse_status = "connected" if get_langfuse_client() else "disabled"

    return {
        "status": "ok",
        "db": db_status,
        "redis": redis_status,
        "whisper": whisper_status,
        "langfuse": langfuse_status,
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
