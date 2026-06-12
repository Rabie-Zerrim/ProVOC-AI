"""
Full API test suite for pv-ai.
Usage: python test_all.py
"""
import os
import uuid

import requests

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:5000"


def _read_env() -> dict:
    env = {}
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = _read_env()
BFF_SECRET = ENV.get("BFF_SHARED_SECRET", "")

# ── State shared between tests ────────────────────────────────────────────────

_token: str = ""
_session_id: str = ""

# ── Helpers ───────────────────────────────────────────────────────────────────

passed = 0
failed = 0


def _ok(name: str, summary: str) -> None:
    global passed
    passed += 1
    print(f"✅ PASS — {name} — {summary}")


def _fail(name: str, error: str) -> None:
    global failed
    failed += 1
    print(f"❌ FAIL — {name} — {error}")


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_health():
    name = "Health endpoint"
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
        r.raise_for_status()
        data = r.json()
        whisper_ok = data.get("whisper") not in (None, "error", False)
        status_ok = data.get("status") in ("ok", "degraded", True) or "whisper" in data
        if status_ok or whisper_ok:
            _ok(name, f"status={data.get('status')} whisper={data.get('whisper')}")
        else:
            _fail(name, f"unexpected body: {data}")
    except Exception as e:
        _fail(name, str(e))


def test_relay_token():
    global _token
    name = "Auth relay token"
    try:
        r = requests.post(
            f"{BASE_URL}/api/auth/token/relay",
            json={"user_id": str(uuid.uuid4())},
            headers={"X-BFF-Secret": BFF_SECRET},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("access_token", "")
        if token:
            _token = token
            _ok(name, f"token received ({len(token)} chars), expires_in={data.get('expires_in')}")
        else:
            _fail(name, f"no access_token in response: {data}")
    except Exception as e:
        _fail(name, str(e))


def test_chat_start():
    global _session_id
    name = "Chat start"
    if not _token:
        _fail(name, "skipped — no token from relay test")
        return
    try:
        payload = {
            "review_id": str(uuid.uuid4()),
            "listing_id": str(uuid.uuid4()),
            "transcript": "The food was really good but the service was a bit slow.",
            "language": "en",
            "listing_context": {
                "business_name": "Test Restaurant",
                "network_names": ["yelp", "google"],
                "network_preferences": {"yelp": True, "google": False},
            },
        }
        r = requests.post(
            f"{BASE_URL}/api/chat/start",
            json=payload,
            headers=_auth_headers(),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        sid = data.get("session_id", "")
        if sid:
            _session_id = sid
            _ok(name, f"session_id={sid[:8]}… language={data.get('detected_language')}")
        else:
            _fail(name, f"no session_id in response: {data}")
    except Exception as e:
        _fail(name, str(e))


def test_chat_message():
    name = "Chat message"
    if not _session_id:
        _fail(name, "skipped — no session_id from start test")
        return
    try:
        payload = {
            "session_id": _session_id,
            "message": "Tell me about my experience",
        }
        r = requests.post(
            f"{BASE_URL}/api/chat/message",
            json=payload,
            headers=_auth_headers(),
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        reply = data.get("response", "")
        if reply:
            preview = reply[:80].replace("\n", " ")
            _ok(name, f"assistant replied: {preview!r}")
        else:
            _fail(name, f"no response field: {data}")
    except Exception as e:
        _fail(name, str(e))


def test_chat_approve():
    name = "Chat approve"
    if not _session_id:
        _fail(name, "skipped — no session_id from start test")
        return
    try:
        r = requests.post(
            f"{BASE_URL}/api/chat/approve",
            json={"session_id": _session_id},
            headers=_auth_headers(),
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        review_text = data.get("improved_text", "")
        rating = data.get("rating")
        if review_text and rating is not None:
            preview = review_text[:60].replace("\n", " ")
            _ok(name, f"review_text={preview!r} rating={rating}")
        else:
            _fail(name, f"missing improved_text or rating: {data}")
    except Exception as e:
        _fail(name, str(e))


def test_transcription_health():
    name = "Transcription health"
    try:
        r = requests.get(f"{BASE_URL}/api/health-check/transcribe", timeout=10)
        r.raise_for_status()
        data = r.json()
        whisper_loaded = data.get("whisper_loaded") or data.get("whisper") not in (None, False, "error")
        if whisper_loaded:
            _ok(name, f"whisper_loaded={data.get('whisper_loaded')} device={data.get('device')}")
        else:
            _fail(name, f"whisper not loaded: {data}")
    except Exception as e:
        _fail(name, str(e))


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nRunning pv-ai API tests against {BASE_URL}\n")

    test_health()
    test_relay_token()
    test_chat_start()
    test_chat_message()
    test_chat_approve()
    test_transcription_health()

    total = passed + failed
    print(f"\nPASSED: {passed}/{total}")
    print(f"FAILED: {failed}/{total}")
