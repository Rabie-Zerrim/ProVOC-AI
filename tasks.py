from fastapi import APIRouter
import uuid
from database import get_milvus
from datetime import datetime

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
client = get_milvus()


@router.get("/")
async def get_tasks(userId: str, listId: str = None) -> list:
    """Get tasks for a user, optionally filtered by list ID."""
    filter_expr = f"userId == '{userId}'"
    if listId:
        filter_expr += f" and listId == '{listId}'"

    results = client.query(
        collection_name="tasks",
        filter=filter_expr
    )
    return results


@router.post("/")
async def create_task(userId: str, title: str, listId: str = None, priority: str = "medium") -> dict:
    task_id = str(uuid.uuid4())
    client.insert(
        collection_name="tasks",
        data=[{
            "id": task_id,
            "userId": userId,
            "listId": listId,
            "title": title,
            "priority": priority,
            "completed": False,
            "createdAt": str(datetime.utcnow()),
            "vector": [0.0, 0.0]  # Dummy vector for mock metadata storage
        }]
    )
    return {"id": task_id, "title": title}


@router.patch("/{task_id}")
async def update_task(task_id: str, updates: dict) -> dict:
    client.upsert(
        collection_name="tasks",
        data=[{"id": task_id, **updates}]
    )
    return {"success": True}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    client.delete(collection_name="tasks", filter=f"id == '{task_id}'")
    return {"success": True}
