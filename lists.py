from fastapi import APIRouter
import uuid
from database import get_milvus
from auth import oauth2_scheme  # TODO: wire auth dependency

router = APIRouter(prefix="/api/lists", tags=["lists"])
client = get_milvus()


@router.get("/")
async def get_lists(userId: str) -> list:
    """Get all lists for a user."""
    results = client.query(
        collection_name="users",  # querying users collection until dedicated lists collection exists
        filter=f"userId == '{userId}'",
        output_fields=["id", "name", "color", "icon"]
    )
    return results


@router.post("/")
async def create_list(userId: str, name: str, color: str = "#3B82F6", icon: str = "📋") -> dict:
    list_id = str(uuid.uuid4())
    client.insert(
        collection_name="lists",
        data=[{
            "id": list_id,
            "userId": userId,
            "name": name,
            "color": color,
            "icon": icon
        }]
    )
    return {"id": list_id, "name": name}
