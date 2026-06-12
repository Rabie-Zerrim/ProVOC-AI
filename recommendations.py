from fastapi import APIRouter, Depends

from auth import get_current_user
from taste_engine import TasteEngine

router = APIRouter(tags=["recommendations"])


@router.get("/api/recommendations")
async def get_recommendations(
    current_user: str = Depends(get_current_user),
    limit: int = 5,
) -> list[dict]:
    taste = TasteEngine.get_instance()
    return taste.get_recommendations(current_user, limit)
