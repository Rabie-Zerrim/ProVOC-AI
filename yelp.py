from fastapi import APIRouter, HTTPException
from typing import List, Optional
import uuid
from datetime import datetime
from database import get_milvus
import os
from groq import Groq
from config import GROQ_API_KEY
from prompts import REVIEW_ANALYSIS_PROMPT, REVIEW_INTERACTION_PROMPT, FINAL_REPORT_PROMPT

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
async def search_businesses(term: str = "", query: str = ""):
    """Renvoie la liste statique filtrée"""
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
async def create_review_session(businessData: dict):
    """Crée une session de review (NO-DB: retourne un ID aléatoire)"""
    review_id = str(uuid.uuid4())
    return {"_id": review_id, "id": review_id, "success": True}


@router.put("/reviews/{review_id}/transcription")
async def update_review_transcription(review_id: str, transcriptionData: dict):
    """Met à jour la transcription (NO-DB: retourne succès simulé)"""
    return {
        "success": True,
        "_id": review_id,
        "voiceTranscription": transcriptionData.get("voiceTranscription", "")
    }


@router.post("/reviews/{review_id}/chat")
async def review_chat(review_id: str, chatData: dict):
    """
    Workflow complet avec Groq Llama 3:
    1. Extraction entités / sentiment / rating
    2. Validation avec l'utilisateur
    3. Amélioration du texte
    4. Rapport final
    """
    userMessage = chatData.get("message", "")
    history = chatData.get("history", [])  # list of {role, content}

    # ── Choix du system prompt selon l'étape de la conversation
    is_initial = len(history) < 2
    if is_initial:
        system_prompt = REVIEW_ANALYSIS_PROMPT + "\n\n" + REVIEW_INTERACTION_PROMPT
    else:
        system_prompt = REVIEW_INTERACTION_PROMPT

    # ── Détection si l'user demande un rapport final
    if any(kw in userMessage.lower() for kw in ["rapport", "report", "final", "تقرير", "relatorio"]):
        system_prompt = FINAL_REPORT_PROMPT

    try:
        response = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": userMessage}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        assistantMessage = response.choices[0].message.content
        print(f"✅ Groq responded: {assistantMessage[:60]}...")
        return {"success": True, "assistantMessage": assistantMessage, "usedFallback": False}

    except Exception as e:
        error_msg = str(e)
        print(f"❌ GROQ ERROR: {error_msg}")
        return {
            "success": True,
            "assistantMessage": f"⚠️ Erreur IA: {error_msg[:120]}\n\nVérifiez votre GROQ_API_KEY dans .env",
            "usedFallback": True,
            "fallbackReason": error_msg
        }


@router.get("/pending-reviews")
async def get_pending_reviews(userId: str = "test-user-id-001"):
    """NO-DB MODE: Retourne une liste vide"""
    return []
