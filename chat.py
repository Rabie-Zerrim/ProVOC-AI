import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from groq import Groq

from auth import get_current_user
from config import GROQ_API_KEY, ACCEPTED_LANGUAGES, LLM_MODEL
from prompts import REVIEW_ANALYSIS_PROMPT
from redis_client import get_session, save_session, delete_session

router = APIRouter(prefix="/api/chat", tags=["chat"])
_groq = Groq(api_key=GROQ_API_KEY)


# ─── Request models ───────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    review_id: str
    transcript: str
    listing_id: str
    language: str
    listing_context: dict


class MessageRequest(BaseModel):
    session_id: str
    message: str


class ApproveRequest(BaseModel):
    session_id: str


class EndRequest(BaseModel):
    session_id: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_system_prompt(listing_context: dict, language: str = "") -> str:
    business_name = listing_context.get("business_name", "Unknown Business")
    network_names = listing_context.get("network_names", [])
    network_prefs = listing_context.get("network_preferences", {})
    from config import LANGUAGE_NAMES
    lang_name = LANGUAGE_NAMES.get(language, language)
    context_block = (
        f"\n\nBUSINESS CONTEXT:\n"
        f"- Business Name: {business_name}\n"
        f"- Social Networks: {', '.join(network_names) if network_names else 'None specified'}\n"
        f"- Network Preferences: {network_prefs}\n"
        f"\nUSER LANGUAGE: {lang_name} — ALL your responses must be in {lang_name}.\n"
    )
    return REVIEW_ANALYSIS_PROMPT + context_block


def _call_groq(messages: list, temperature: float = 0.7, max_tokens: int = 1024) -> str:
    response = _groq.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _assert_session_owner(session: dict, user_id: str) -> None:
    session_owner = session.get("user_id")
    if session_owner and session_owner != user_id:
        raise HTTPException(status_code=403, detail="Session belongs to a different user")


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_session(
    body: StartSessionRequest,
    user_id: str = Depends(get_current_user),
):
    if body.language not in ACCEPTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Language must be one of: {', '.join(ACCEPTED_LANGUAGES)}",
        )

    system_prompt = _build_system_prompt(body.listing_context, body.language)

    try:
        initial_response = _call_groq([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": body.transcript},
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "review_id": body.review_id,
        "listing_id": body.listing_id,
        "detected_language": body.language,
        "listing_context": body.listing_context,
        "chat_history": [
            {"role": "system", "content": system_prompt},
            {"role": "assistant", "content": initial_response},
        ],
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_session(session_id, session)

    return {
        "session_id": session_id,
        "initial_response": initial_response,
        "detected_language": body.language,
    }


@router.post("/message")
async def send_message(
    body: MessageRequest,
    user_id: str = Depends(get_current_user),
):
    session = get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    _assert_session_owner(session, user_id)

    session["chat_history"].append({"role": "user", "content": body.message})

    try:
        reply = _call_groq(session["chat_history"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    session["chat_history"].append({"role": "assistant", "content": reply})
    save_session(body.session_id, session)

    return {"response": reply, "session_id": body.session_id}


@router.post("/approve")
async def approve_session(
    body: ApproveRequest,
    user_id: str = Depends(get_current_user),
):
    session = get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    _assert_session_owner(session, user_id)

    approval_prompt = (
        'Based on the conversation history, return ONLY a valid JSON object '
        '(no markdown, no explanation) with this exact structure:\n'
        '{\n'
        '  "improved_text": "The polished review text",\n'
        '  "rating": 4,\n'
        '  "sentiment": "Positive",\n'
        '  "tone": "Enthusiastic",\n'
        '  "key_points": ["Great service", "Good food", "Fair price"]\n'
        '}\n'
        'sentiment must be exactly one of: "Positive", "Negative", "Neutral"\n'
        'rating must be an integer between 1 and 5.'
    )

    try:
        raw = _call_groq(
            session["chat_history"] + [{"role": "user", "content": approval_prompt}],
            temperature=0.2,
            max_tokens=512,
        ).strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise HTTPException(status_code=422, detail="AI did not return valid JSON")
    try:
        result = json.loads(match.group())
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Failed to parse AI response as JSON")

    session["status"] = "approved"
    save_session(body.session_id, session)

    return result


@router.post("/end")
async def end_session(
    body: EndRequest,
    user_id: str = Depends(get_current_user),
):
    session = get_session(body.session_id)
    if session:
        _assert_session_owner(session, user_id)
    delete_session(body.session_id)
    return {"success": True}


@router.get("/session/{session_id}")
async def get_session_data(
    session_id: str,
    user_id: str = Depends(get_current_user),
):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session
