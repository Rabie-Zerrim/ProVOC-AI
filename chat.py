import json
import re
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from groq import Groq

from auth import get_current_user
from config import GROQ_API_KEY, ACCEPTED_LANGUAGES, LLM_MODEL
from langfuse_client import get_prompt
from prompts import (
    REVIEW_ANALYSIS_PROMPT,
    _CHAT_MESSAGE_PROMPT_FALLBACK,
    _CHAT_REPHRASE_PROMPT_FALLBACK,
    _CHAT_REGENERATE_PROMPT_FALLBACK,
    _CHAT_RESUME_PROMPT_FALLBACK,
)
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
    previous_messages: list[dict] = []
    purpose: Literal["start", "regenerate"] = "start"
    conversation_summary: Optional[str] = None


class MessageRequest(BaseModel):
    session_id: str
    message: str
    purpose: Literal["message", "rephrase"] = "message"


class ApproveRequest(BaseModel):
    session_id: str


class EndRequest(BaseModel):
    session_id: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _build_context_block(listing_context: dict, language: str = "") -> str:
    business_name = listing_context.get("business_name", "Unknown Business")
    network_names = listing_context.get("network_names", [])
    network_prefs = listing_context.get("network_preferences", {})
    from config import LANGUAGE_NAMES
    lang_name = LANGUAGE_NAMES.get(language, language)
    return (
        f"\n\nBUSINESS CONTEXT:\n"
        f"- Business Name: {business_name}\n"
        f"- Social Networks: {', '.join(network_names) if network_names else 'None specified'}\n"
        f"- Network Preferences: {network_prefs}\n"
        f"\nUSER LANGUAGE: {lang_name} — ALL your responses must be in {lang_name}.\n"
    )


def _build_system_prompt(
    listing_context: dict,
    language: str = "",
    prompt_template: str = REVIEW_ANALYSIS_PROMPT,
) -> str:
    return prompt_template + _build_context_block(listing_context, language)


def _call_groq(
    messages: list,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    response_format: dict | None = None,
) -> str:
    kwargs: dict = dict(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = _groq.chat.completions.create(**kwargs)
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

    if body.conversation_summary:
        resume_template = get_prompt("chat-resume", _CHAT_RESUME_PROMPT_FALLBACK)
        system_prompt = (
            resume_template
            .replace("{{business_name}}", body.listing_context.get("business_name", ""))
            .replace("{{conversation_summary}}", body.conversation_summary)
            .replace("{{review_text}}", body.transcript)
            .replace("{{language}}", body.language)
        )
    else:
        prompt_template = (
            get_prompt("chat-regenerate", _CHAT_REGENERATE_PROMPT_FALLBACK)
            if body.purpose == "regenerate"
            else REVIEW_ANALYSIS_PROMPT
        )
        system_prompt = _build_system_prompt(body.listing_context, body.language, prompt_template)

    chat_history: list[dict] = [{"role": "system", "content": system_prompt}]
    if body.previous_messages:
        chat_history.extend(
            {"role": m["role"], "content": m["content"]}
            for m in body.previous_messages
        )

    print("=== CHAT START ===")
    print(f"previous_messages count: {len(body.previous_messages)}")
    print(f"transcript: {body.transcript[:200]}")
    for i, msg in enumerate(chat_history):
        print(f"  [{i}] {msg['role']}: {msg['content'][:100]}")
    print("==================")
    try:
        initial_response = _call_groq(
            chat_history + [{"role": "user", "content": body.transcript}]
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    if body.previous_messages:
        chat_history.append({"role": "user", "content": body.transcript})
    chat_history.append({"role": "assistant", "content": initial_response})

    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "user_id": user_id,
        "review_id": body.review_id,
        "listing_id": body.listing_id,
        "detected_language": body.language,
        "listing_context": body.listing_context,
        "chat_history": chat_history,
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

    prompt_template = (
        get_prompt("chat-rephrase", _CHAT_REPHRASE_PROMPT_FALLBACK)
        if body.purpose == "rephrase"
        else get_prompt("chat-message", _CHAT_MESSAGE_PROMPT_FALLBACK)
    )
    call_system_prompt = _build_system_prompt(
        session.get("listing_context", {}),
        session.get("detected_language", ""),
        prompt_template,
    )
    call_messages = (
        [{"role": "system", "content": call_system_prompt}]
        + session["chat_history"][1:]
        + [{"role": "user", "content": body.message}]
    )

    try:
        reply = _call_groq(call_messages)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    session["chat_history"].append({"role": "user", "content": body.message})
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
        'IMPORTANT: Read the ENTIRE conversation above carefully. '
        'The user described their ACTUAL experience including any '
        'complaints, problems, or negative aspects. '
        'You MUST reflect exactly what the user said — '
        'do NOT make the review more positive than what was discussed. '
        'If the user mentioned bad service, include bad service. '
        'If the user mentioned good food, include good food. '
        'Use the rating the user gave or inferred from the conversation. '
        'Return ONLY a valid JSON object with no markdown, '
        'no explanation, no code fences:\n'
        '{\n'
        '  "improved_text": "The honest review based on what user said",\n'
        '  "rating": 3,\n'
        '  "sentiment": "Negative",\n'
        '  "tone": "Firm",\n'
        '  "key_points": ["actual point 1", "actual point 2"]\n'
        '}\n'
        'sentiment must be exactly one of: Positive, Negative, Neutral\n'
        'rating must be an integer between 1 and 5 matching the conversation.\n'
        'Do NOT default to 5 stars or positive sentiment unless the user '
        'explicitly said they had a great experience.'
    )

    print("=== CHAT APPROVE ===")
    for i, msg in enumerate(session['chat_history']):
        print(f"  [{i}] {msg['role']}: {msg['content'][:100]}")
    print("approval_prompt:", approval_prompt[:200])
    print("====================")
    print(f"[approve] session_id: {body.session_id}")
    print(f"[approve] chat_history length: {len(session['chat_history'])}")
    print(f"[approve] chat_history: {session['chat_history']}")
    try:
        raw = _call_groq(
            session["chat_history"] + [{"role": "user", "content": approval_prompt}],
            temperature=0.1,
            max_tokens=512,
            response_format={"type": "json_object"},
        ).strip()
        print(f"[approve] raw response: {raw[:500]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error: {e}")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            raise HTTPException(status_code=422, detail="AI did not return valid JSON")
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail="Failed to parse AI response as JSON")

    summary_prompt = (
        'Summarize everything the user told you about '
        'their experience at this business. '
        'Be specific and include ALL details mentioned. '
        'Structure it like this:\n'
        '- Overall sentiment: [Positive/Negative/Neutral]\n'
        '- Star rating: [1-5]\n'
        '- What they liked: [list or "nothing mentioned"]\n'
        '- What they disliked: [list or "nothing mentioned"]\n'
        '- Specific details mentioned: [parking, service, '
        'food quality, prices, atmosphere, staff names, '
        'wait times, etc]\n'
        '- Tone preference: [Firm/Polite/Neutral]\n'
        '- Goal: [Awareness/Praise/etc]\n'
        'Be factual. Only include what the user actually '
        'said. Do not add anything they did not mention. '
        'Return only the structured summary, nothing else.'
    )

    try:
        summary = _call_groq(
            session["chat_history"] + [
                {"role": "user", "content": summary_prompt}
            ],
            temperature=0.1,
            max_tokens=300,
        ).strip()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Groq API error (summary): {e}")

    session["status"] = "approved"
    save_session(body.session_id, session)

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

    return {
        "improved_text": result["improved_text"],
        "rating": result["rating"],
        "sentiment": result["sentiment"],
        "tone": result["tone"],
        "key_points": result["key_points"],
        "conversation_summary": summary,
    }


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
