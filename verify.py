"""
Run this after starting the server and Redis:
    python verify.py [--base-url http://localhost:5000] [--redis-host localhost]

All checks are run in sequence and results printed as a table.
"""
import argparse
import json
import subprocess
import sys
import time
import uuid

import redis
import requests

# ─── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:5000")
parser.add_argument("--redis-host", default="localhost")
parser.add_argument("--redis-port", type=int, default=6379)
args = parser.parse_args()

BASE = args.base_url.rstrip("/")
results: list[tuple[str, bool, str]] = []

TEST_EMAIL = "verify-bot@provoc.test"
TEST_EMAIL_2 = "verify-bot-2@provoc.test"
TEST_PASSWORD = "VerifyPass123!"
TEST_DISPLAY = "Verify Bot"


def check(label: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append((label, passed, detail))
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print(f"\n{'-'*60}")
    print(f"  {title}")
    print(f"{'-'*60}")


# ─── 0. Connectivity pre-checks ───────────────────────────────────────────────
section("Pre-flight: server + Redis reachable")

try:
    r = requests.get(f"{BASE}/", timeout=5)
    check("Server reachable", r.status_code < 500, f"HTTP {r.status_code}")
except Exception as e:
    check("Server reachable", False, str(e))
    print("\n  Server is not running — start it first, then re-run verify.py")
    sys.exit(1)

try:
    rc = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
    rc.ping()
    check("Redis reachable", True, f"{args.redis_host}:{args.redis_port}")
except Exception as e:
    check("Redis reachable", False, str(e))
    print("\n  Redis is not running — start it first, then re-run verify.py")
    sys.exit(1)


# ─── A. Auth: register ────────────────────────────────────────────────────────
section("Auth A — POST /api/auth/register creates a real user")

reg_resp = requests.post(f"{BASE}/api/auth/register", json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "display_name": TEST_DISPLAY,
}, timeout=30)

token = None
user_id_reg = None
already_registered = False

if reg_resp.status_code == 201:
    reg_body = reg_resp.json()
    token = reg_body.get("access_token")
    user_id_reg = reg_body.get("user_id")
    check("HTTP 201", True, "got 201")
    check("access_token present", bool(token), token[:20] + "…" if token else "missing")
    check("token_type == bearer", reg_body.get("token_type") == "bearer",
          reg_body.get("token_type"))
    check("user_id present", bool(user_id_reg), user_id_reg or "missing")
elif reg_resp.status_code == 409:
    already_registered = True
    check("HTTP 201 or 409 (already registered)", True,
          "got 409 — user exists, proceeding to login")
else:
    check("HTTP 201", False, f"got {reg_resp.status_code}")
    print(f"    Response: {reg_resp.text[:200]}")

# Duplicate register -> 409 (passes whether first call was 201 or 409)
dup_resp = requests.post(f"{BASE}/api/auth/register", json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
    "display_name": TEST_DISPLAY,
}, timeout=30)
check("Duplicate email -> 409", dup_resp.status_code == 409,
      f"got {dup_resp.status_code}")


# ─── B. Auth: login ───────────────────────────────────────────────────────────
section("Auth B — POST /api/auth/login returns real JWT")

login_resp = requests.post(f"{BASE}/api/auth/login", json={
    "email": TEST_EMAIL,
    "password": TEST_PASSWORD,
}, timeout=30)
check("HTTP 200", login_resp.status_code == 200, f"got {login_resp.status_code}")

if login_resp.status_code == 200:
    login_body = login_resp.json()
    token = login_body.get("access_token")  # always use fresh token from login
    login_user_id = login_body.get("user_id")
    if user_id_reg is None:
        user_id_reg = login_user_id  # populate from login when register was 409
    check("access_token present", bool(token), token[:20] + "…" if token else "missing")
    if not already_registered:
        check("user_id matches register", login_user_id == user_id_reg,
              login_user_id)
    else:
        check("user_id present in login response", bool(login_user_id),
              login_user_id or "missing")
else:
    print(f"    Response: {login_resp.text[:200]}")

bad_login = requests.post(f"{BASE}/api/auth/login", json={
    "email": TEST_EMAIL, "password": "wrongpassword",
}, timeout=30)
check("Wrong password -> 401", bad_login.status_code == 401,
      f"got {bad_login.status_code}")


# ─── C. Auth: /me ─────────────────────────────────────────────────────────────
section("Auth C — GET /api/auth/me")

if token:
    me_resp = requests.get(f"{BASE}/api/auth/me",
                           headers={"Authorization": f"Bearer {token}"}, timeout=10)
    check("HTTP 200 with valid token", me_resp.status_code == 200,
          f"got {me_resp.status_code}")
    if me_resp.status_code == 200:
        me_body = me_resp.json()
        check("user_id matches", me_body.get("user_id") == user_id_reg,
              me_body.get("user_id"))
        check("email matches", me_body.get("email") == TEST_EMAIL,
              me_body.get("email"))
        check("display_name present", bool(me_body.get("display_name")),
              me_body.get("display_name") or "missing")
    else:
        print(f"    Response: {me_resp.text[:200]}")
else:
    check("GET /me with token", False, "skipped — no token")

no_token_resp = requests.get(f"{BASE}/api/auth/me", timeout=10)
check("GET /me without token -> 401", no_token_resp.status_code == 401,
      f"got {no_token_resp.status_code}")


# ─── D. Chat: 401 without token ───────────────────────────────────────────────
section("Auth D — POST /api/chat/start returns 401 without token")

no_auth_start = requests.post(f"{BASE}/api/chat/start", json={
    "review_id": "test-review-001",
    "transcript": "Test transcript",
    "listing_id": "biz-001",
    "language": "en",
    "listing_context": {"business_name": "Test Biz", "network_names": [], "network_preferences": {}},
}, timeout=10)
check("POST /chat/start without token -> 401", no_auth_start.status_code == 401,
      f"got {no_auth_start.status_code}")


# ─── Build auth header for remaining chat checks ──────────────────────────────
auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

start_payload = {
    "review_id": "test-review-001",
    "transcript": "I visited McDonalds last night. The burger was amazing but the fries were cold. Overall 4/5.",
    "listing_id": "biz-mcdonalds-001",
    "language": "en",
    "listing_context": {
        "business_name": "McDonalds Berges du Lac",
        "network_names": ["yelp", "google"],
        "network_preferences": {"yelp": True, "google": False},
    },
}


# ─── 1. Start session ─────────────────────────────────────────────────────────
section("Check 1 — POST /api/chat/start returns session_id and initial_response")

resp = requests.post(f"{BASE}/api/chat/start", json=start_payload,
                     headers=auth_headers, timeout=30)
check("HTTP 200", resp.status_code == 200, f"got {resp.status_code}")

session_id = None
if resp.status_code == 200:
    body = resp.json()
    session_id = body.get("session_id")
    initial_response = body.get("initial_response")
    check("session_id present", bool(session_id), session_id or "missing")
    check("initial_response present", bool(initial_response),
          (initial_response or "")[:80] + "…" if initial_response else "missing")
    check("detected_language == 'en'", body.get("detected_language") == "en",
          body.get("detected_language"))
else:
    print(f"    Response: {resp.text[:200]}")
    check("session_id present", False, "skipped — bad status")


# ─── 2. Redis key exists ───────────────────────────────────────────────────────
section("Check 2 — Redis key session:{session_id} exists with correct data")

if session_id:
    key = f"session:{session_id}"
    raw = rc.get(key)
    check("Key exists in Redis", raw is not None, key)
    if raw:
        data = json.loads(raw)
        check("status == 'active'", data.get("status") == "active", data.get("status"))
        check("user_id stored in session", bool(data.get("user_id")),
              data.get("user_id") or "missing")
        check("chat_history has system + assistant", len(data.get("chat_history", [])) >= 2,
              f"{len(data.get('chat_history', []))} messages")
        ttl = rc.ttl(key)
        check("TTL set (<=1800s)", 0 < ttl <= 1800, f"TTL={ttl}s")
else:
    check("Key exists in Redis", False, "skipped — no session_id")


# ─── 3. Send message ──────────────────────────────────────────────────────────
section("Check 3 — POST /api/chat/message returns AI response and updates history")

if session_id:
    msg_payload = {"session_id": session_id, "message": "Can you improve my review text?"}
    resp = requests.post(f"{BASE}/api/chat/message", json=msg_payload,
                         headers=auth_headers, timeout=30)
    check("HTTP 200", resp.status_code == 200, f"got {resp.status_code}")
    if resp.status_code == 200:
        body = resp.json()
        ai_response = body.get("response", "")
        check("response present", bool(ai_response),
              (ai_response[:80] + "…") if ai_response else "missing")
        check("session_id echoed", body.get("session_id") == session_id)

        raw = rc.get(f"session:{session_id}")
        if raw:
            data = json.loads(raw)
            history_len = len(data.get("chat_history", []))
            check("chat_history grew to >=4 messages", history_len >= 4,
                  f"{history_len} messages")
    else:
        print(f"    Response: {resp.text[:200]}")
else:
    check("POST /api/chat/message", False, "skipped — no session_id")


# ─── 4. Approve ───────────────────────────────────────────────────────────────
section("Check 4 — POST /api/chat/approve returns structured JSON")

if session_id:
    resp = requests.post(f"{BASE}/api/chat/approve", json={"session_id": session_id},
                         headers=auth_headers, timeout=30)
    check("HTTP 200", resp.status_code == 200, f"got {resp.status_code}")
    if resp.status_code == 200:
        body = resp.json()
        check("improved_text present", bool(body.get("improved_text")),
              (body.get("improved_text") or "missing")[:80])
        check("rating is int 1-5",
              isinstance(body.get("rating"), int) and 1 <= body["rating"] <= 5,
              str(body.get("rating")))
        check("sentiment in enum",
              body.get("sentiment") in ("Positive", "Negative", "Neutral"),
              body.get("sentiment"))
        check("tone present", bool(body.get("tone")), body.get("tone") or "missing")
        check("key_points is list", isinstance(body.get("key_points"), list),
              str(body.get("key_points", [])))

        raw = rc.get(f"session:{session_id}")
        if raw:
            data = json.loads(raw)
            check("Redis status == 'approved'", data.get("status") == "approved",
                  data.get("status"))
    else:
        print(f"    Response: {resp.text[:200]}")
else:
    check("POST /api/chat/approve", False, "skipped — no session_id")


# ─── 5. Expired / deleted session -> 404 ──────────────────────────────────────
section("Check 5 — Deleted Redis key returns 404 on /message")

if session_id:
    rc.delete(f"session:{session_id}")
    check("Key manually deleted", rc.get(f"session:{session_id}") is None,
          "confirmed gone")

    resp = requests.post(f"{BASE}/api/chat/message",
                         json={"session_id": session_id, "message": "hello"},
                         headers=auth_headers, timeout=10)
    check("POST /message -> 404", resp.status_code == 404, f"got {resp.status_code}")
    if resp.status_code == 404:
        detail = resp.json().get("detail", "")
        check("detail mentions expired/not found",
              "not found" in detail.lower() or "expired" in detail.lower(), detail)
else:
    check("Expired session 404", False, "skipped — no session_id")


# ─── E. Ownership check: wrong user gets 403 ──────────────────────────────────
section("Auth E — wrong user token returns 403 on /message")

# Register (or login) a second user
reg2 = requests.post(f"{BASE}/api/auth/register", json={
    "email": TEST_EMAIL_2, "password": TEST_PASSWORD, "display_name": "Second User",
}, timeout=30)
if reg2.status_code == 201:
    token2 = reg2.json().get("access_token")
elif reg2.status_code == 409:
    login2 = requests.post(f"{BASE}/api/auth/login", json={
        "email": TEST_EMAIL_2, "password": TEST_PASSWORD,
    }, timeout=30)
    token2 = login2.json().get("access_token") if login2.status_code == 200 else None
else:
    token2 = None

if token and token2:
    # User 1 starts a session
    start2 = requests.post(f"{BASE}/api/chat/start", json=start_payload,
                           headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if start2.status_code == 200:
        sid_owner = start2.json()["session_id"]
        # User 2 tries to send a message in user 1's session -> 403
        intruder = requests.post(f"{BASE}/api/chat/message",
                                 json={"session_id": sid_owner, "message": "hi"},
                                 headers={"Authorization": f"Bearer {token2}"},
                                 timeout=10)
        check("Wrong-user /message -> 403", intruder.status_code == 403,
              f"got {intruder.status_code}")
        # Clean up
        rc.delete(f"session:{sid_owner}")
    else:
        check("Wrong-user /message -> 403", False, "skipped — could not start session")
else:
    check("Wrong-user /message -> 403", False, "skipped — could not register second user")


# ─── Bonus: /end and /session/{id} ────────────────────────────────────────────
section("Bonus — /end and /session/{id}")

resp2 = requests.post(f"{BASE}/api/chat/start", json=start_payload,
                      headers=auth_headers, timeout=30)
if resp2.status_code == 200:
    sid2 = resp2.json()["session_id"]

    resp_get = requests.get(f"{BASE}/api/chat/session/{sid2}",
                            headers=auth_headers, timeout=10)
    check("GET /session/{id} -> 200", resp_get.status_code == 200,
          f"got {resp_get.status_code}")
    if resp_get.status_code == 200:
        check("session data has chat_history", "chat_history" in resp_get.json())

    resp_end = requests.post(f"{BASE}/api/chat/end", json={"session_id": sid2},
                             headers=auth_headers, timeout=10)
    check("POST /end -> success:true",
          resp_end.status_code == 200 and resp_end.json().get("success") is True)
    check("Key gone after /end", rc.get(f"session:{sid2}") is None, "confirmed deleted")

    resp_miss = requests.get(f"{BASE}/api/chat/session/{sid2}",
                             headers=auth_headers, timeout=10)
    check("GET /session after /end -> 404", resp_miss.status_code == 404,
          f"got {resp_miss.status_code}")
else:
    check("Second start session", False, f"HTTP {resp2.status_code}")


# ─── F. Alembic migration check ───────────────────────────────────────────────
section("Alembic F — migration at head")

try:
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True, text=True, timeout=15,
    )
    output = proc.stdout + proc.stderr
    check("alembic current contains (head)", "(head)" in output, output.strip()[:120])
except Exception as e:
    check("alembic current", False, str(e))
    
# ─── Summary ──────────────────────────────────────────────────────────────────
section("Summary")
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n  {passed}/{total} checks passed\n")
if passed < total:
    print("  FAILED checks:")
    for label, ok, detail in results:
        if not ok:
            print(f"    FAIL: {label}" + (f" ({detail})" if detail else ""))
    sys.exit(1)
else:
    print("  All checks passed.")
