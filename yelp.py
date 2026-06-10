import json
import logging
import uuid
from datetime import datetime
from typing import List

import redis as _redis_lib
from fastapi import APIRouter, HTTPException
from groq import Groq
import groq as _groq_module

from config import GROQ_API_KEY, LLM_MODEL
from database import get_milvus
from prompts import REVIEW_ANALYSIS_PROMPT, REVIEW_INTERACTION_PROMPT, FINAL_REPORT_PROMPT
from redis_client import _client as _redis_client, save_session

router = APIRouter(prefix="/api/yelp", tags=["yelp"])
milvus_client = get_milvus()
client_groq = Groq(api_key=GROQ_API_KEY)

# ─── STATIC BUSINESSES ────────────────────────────────────────────────────────
STATIC_BUSINESSES = [
    {"id": "biz-mcdonalds-001", "name": "McDonalds Berges du Lac", "address": "Les Berges du Lac, Tunis", "category": "Burger", "rating": 4.5},
    {"id": "biz-mcdonalds-002", "name": "McDo La Marsa", "address": "La Marsa, Tunis", "category": "Fast Food", "rating": 4.2},
    {"id": "biz-starbucks-001", "name": "Starbucks Ennasr", "address": "Avenue Hedi Nouira, Tunis", "category": "Coffee", "rating": 4.8},
    {"id": "biz-pizzahut-001", "name": "Pizza Hut Ennasr", "address": "Ennasr 2, Tunis", "category": "Pizza", "rating": 3.9},
    {"id": "biz-kfc-001", "name": "KFC Tunis City", "address": "Tunis City Mall", "category": "Chicken", "rating": 4.1},
    {"id": "biz-plan-b-001", "name": "Plan B Lac 2", "address": "Lac 2, Tunis", "category": "Sandwich", "rating": 4.3}
]

# ─── ROUTES ───────────────────────────────────────────────────────────────────

@router.get("/search")
async def search_businesses(term: str = "", query: str = "") -> list:
    """Return the static business list, filtered by search term."""
    search_term = (term or query).lower()
    return [
        {
            "businessId": r["id"], "id": r["id"], "name": r["name"],
            "address": r["address"], "city": "Tunis", "category": r["category"],
            "phone": "+216 71 000 000", "rating": r["rating"],
            "imageUrl": "https://via.placeholder.com/150", "reviewCount": 100
        }
        for r in STATIC_BUSINESSES
        if not search_term or search_term in r["name"].lower() or search_term in r["category"].lower()
    ]


@router.post("/reviews")
async def create_review_session(businessData: dict) -> dict:
    """Create a review session (NO-DB: returns a random ID)."""
    review_id = str(uuid.uuid4())
    return {"_id": review_id, "id": review_id, "success": True}


@router.put("/reviews/{review_id}/transcription")
async def update_review_transcription(review_id: str, transcriptionData: dict) -> dict:
    """Find the Redis session for this review_id and persist the transcription data."""
    found_session = None
    try:
        for key in _redis_client.scan_iter("session:*"):
            raw = _redis_client.get(key)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if data.get("review_id") == review_id:
                found_session = data
                break
    except _redis_lib.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Redis unavailable — please check your Redis connection")

    if found_session is None:
        raise HTTPException(status_code=404, detail=f"No active session found for review_id '{review_id}'")

    found_session["voiceTranscription"] = transcriptionData.get("voiceTranscription", "")
    if transcriptionData.get("language"):
        found_session["detected_language"] = transcriptionData["language"]

    save_session(found_session["session_id"], found_session)

    return {"status": "updated", "review_id": review_id}


@router.post("/reviews/{review_id}/chat")
async def review_chat(review_id: str, chatData: dict) -> dict:
    """
    Full review workflow with Groq Llama:
    1. Entity / sentiment / rating extraction
    2. User validation
    3. Text improvement
    4. Final report
    """
    userMessage = chatData.get("message", "")
    history = chatData.get("history", [])  # list of {role, content}

    # Choose system prompt based on conversation stage
    is_initial = len(history) < 2
    if is_initial:
        system_prompt = REVIEW_ANALYSIS_PROMPT + "\n\n" + REVIEW_INTERACTION_PROMPT
    else:
        system_prompt = REVIEW_INTERACTION_PROMPT

    # Switch to final report prompt when user requests a report
    if any(kw in userMessage.lower() for kw in ["rapport", "report", "final", "تقرير", "relatorio"]):
        system_prompt = FINAL_REPORT_PROMPT

    try:
        response = client_groq.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": userMessage}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        assistantMessage = response.choices[0].message.content
        print(f"Groq responded: {assistantMessage[:60]}...")
        return {"success": True, "assistantMessage": assistantMessage, "usedFallback": False}

    except _groq_module.APIError as e:
        error_msg = str(e)
        print(f"Groq API error: {error_msg}")
        return {
            "success": True,
            "assistantMessage": f"AI Error: {error_msg[:120]}\n\nPlease check your GROQ_API_KEY in .env",
            "usedFallback": True,
            "fallbackReason": error_msg
        }


@router.get("/pending-reviews")
async def get_pending_reviews(userId: str = "test-user-id-001") -> list:
    """Return sessions with status 'pending' for the given user from Redis."""
    pending: list = []
    try:
        for key in _redis_client.scan_iter("session:*"):
            raw = _redis_client.get(key)
            if not raw:
                continue
            try:
                session = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if session.get("status") != "pending":
                continue
            if session.get("user_id") != userId:
                continue
            transcript = ""
            for msg in session.get("chat_history", []):
                if msg.get("role") == "user":
                    transcript = msg.get("content", "")
                    break
            pending.append({
                "review_id": session.get("review_id", ""),
                "session_id": session.get("session_id", ""),
                "transcript": transcript,
                "created_at": session.get("created_at", ""),
            })
    except _redis_lib.exceptions.ConnectionError:
        logging.warning("pending-reviews: Redis unavailable, returning empty list")
        return []
    return pending
