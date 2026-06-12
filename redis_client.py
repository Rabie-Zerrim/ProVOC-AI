import json
import os
import socket
from urllib.parse import urlparse

import redis
from fastapi import HTTPException

SESSION_TTL = 1800  # 30 minutes

_redis_url = os.getenv("REDIS_URL")
if _redis_url:
    _parsed = urlparse(_redis_url)
    _redis_host = _parsed.hostname
    _redis_port = _parsed.port
    _redis_password = _parsed.password
    _redis_username = _parsed.username
else:
    # gethostbyname forces IPv4 resolution so "localhost" does not resolve to
    # ::1 on Windows, where an unreachable IPv6 loopback causes a ~20 s OS
    # TCP timeout that bypasses socket_connect_timeout.
    _redis_host = socket.gethostbyname(os.getenv("REDIS_HOST", "localhost"))
    _redis_port = int(os.getenv("REDIS_PORT", 6379))
    _redis_password = os.getenv("REDIS_PASSWORD") or None
    _redis_username = None

_client = redis.Redis(
    host=_redis_host,
    port=_redis_port,
    password=_redis_password,
    username=_redis_username,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
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
