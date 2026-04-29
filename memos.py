from fastapi import APIRouter, Depends, HTTPException
import uuid
from database import get_milvus

router = APIRouter(prefix="/api/memos", tags=["memos"])
client = get_milvus()

@router.get("/")
async def get_memos(userId: str):
    """NO-DB MODE: Simule la récupération de mémos"""
    return []

@router.post("/")
async def create_memo(userId: str, content: str, color: str = "yellow"):
    """NO-DB MODE: Simule la création de mémo"""
    memo_id = str(uuid.uuid4())
    return {"id": memo_id, "content": content, "success": True}

@router.get("/search")
async def search_memos(userId: str, query: str):
    """NO-DB MODE: Recherche désactivée"""
    return []
