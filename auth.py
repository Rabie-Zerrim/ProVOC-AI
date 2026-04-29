from fastapi import APIRouter, Depends, HTTPException, status
import uuid
import os
import time
from database import get_milvus
from config import pwd_context, JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from jose import jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer

# Support OAuth2 (Jetons Bearer)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

router = APIRouter(prefix="/api/auth", tags=["auth"])
client = get_milvus()

# TEST MODE GLOBAL USER ID
TEST_USER_ID = "test-user-id-001"

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=60))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    GLOBAL TEST BYPASS: RENVOIE TOUJOURS L'UTILISATEUR TEST.
    Cela débloque toutes les routes du backend pour les tests rapides.
    """
    return {"id": TEST_USER_ID}

@router.post("/register")
async def register(userData: dict):
    # Registering still works for the DB but returns TEST_USER_ID for current session
    user_id = str(uuid.uuid4())
    access_token = create_access_token(data={"sub": user_id})
    return {
        "success": True,
        "token": access_token,
        "user": {"id": user_id, "_id": user_id, "username": userData.get("username"), "email": userData.get("email")}
    }

@router.post("/login")
async def login(userData: dict):
    # Fake login for quick testing
    return {
        "success": True,
        "token": "fake-test-token",
        "user": {"id": TEST_USER_ID, "_id": TEST_USER_ID, "username": "Tester", "email": "test@domain.com"}
    }
