import json
import os

import redis
from fastapi import HTTPException

SESSION_TTL = 1800  # 30 minutes

_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True,
)

_REDIS_UNAVAILABLE = HTTPException(
    status_code=503,
    detail="Redis unavailable — please check your Redis connection",
)


def get_session(session_id: str) -> dict | None:
    try:
        data = _client.get(f"session:{session_id}")
        return json.loads(data) if data else None
    except redis.exceptions.ConnectionError:
        raise _REDIS_UNAVAILABLE


def save_session(session_id: str, session: dict) -> None:
    try:
        _client.setex(f"session:{session_id}", SESSION_TTL, json.dumps(session))
    except redis.exceptions.ConnectionError:
        raise _REDIS_UNAVAILABLE


def delete_session(session_id: str) -> None:
    try:
        _client.delete(f"session:{session_id}")
    except redis.exceptions.ConnectionError:
        raise _REDIS_UNAVAILABLE
