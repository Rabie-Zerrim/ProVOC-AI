from fastapi import APIRouter, Depends, HTTPException
import uuid
from database import get_milvus
from auth import oauth2_scheme # On devra ajouter cette dépendance

router = APIRouter(prefix="/api/lists", tags=["lists"])
client = get_milvus()

@router.get("/")
async def get_lists(userId: str):
    """Récupère toutes les listes d'un utilisateur depuis Milvus"""
    results = client.query(
        collection_name="users", # Pour l'instant on simule ou on crée une collection lists
        filter=f"userId == '{userId}'",
        output_fields=["id", "name", "color", "icon"]
    )
    return results

@router.post("/")
async def create_list(userId: str, name: str, color: str = "#3B82F6", icon: str = "📋"):
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
