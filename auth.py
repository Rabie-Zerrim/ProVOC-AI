import re
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import JWT_SECRET, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, BFF_SHARED_SECRET
from database import get_db
from models import User, UserCredential


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RelayTokenRequest(BaseModel):
    user_id: str


# ─── Token helper ─────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None, extra_claims: dict = None):
    to_encode = data.copy()
    if extra_claims:
        to_encode.update(extra_claims)
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


# ─── Auth dependency ──────────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exc
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    if result.scalar_one_or_none() is None:
        # Relay-issued tokens carry a "relay": true claim — the user exists in
        # provoc_db (BFF side) not provoc_ai_db, so skip the local DB check.
        if payload.get("relay") is True:
            return user_id
        raise credentials_exc
    return user_id


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    if not _EMAIL_RE.match(body.email):
        raise HTTPException(status_code=422, detail="Invalid email format")

    existing = await db.execute(
        select(UserCredential).where(UserCredential.email == body.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        id=uuid.uuid4(),
        username=body.email,       # email used as username for uniqueness
        email=body.email,
        password="",               # credentials stored in UserCredential
        name=body.display_name,
    )
    db.add(user)
    await db.flush()

    credential = UserCredential(
        credential_id=uuid.uuid4(),
        user_id=user.id,
        email=body.email,
        password_hash=_hash_password(body.password),
    )
    db.add(credential)
    await db.commit()

    access_token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user.id),
    }


@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    result = await db.execute(
        select(UserCredential).where(UserCredential.email == body.email)
    )
    credential = result.scalar_one_or_none()
    if credential is None or not _verify_password(body.password, credential.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token({"sub": str(credential.user_id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(credential.user_id),
    }


@router.get("/me")
async def get_me(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    cred_result = await db.execute(
        select(UserCredential).where(UserCredential.user_id == uuid.UUID(user_id))
    )
    credential = cred_result.scalar_one_or_none()

    return {
        "user_id": str(user.id),
        "email": credential.email if credential else None,
        "display_name": user.name or user.username,
        "created_at": user.createdAt.isoformat() if user.createdAt else None,
    }


@router.post("/token/relay")
async def relay_token(
    body: RelayTokenRequest,
    x_bff_secret: str = Header(..., alias="X-BFF-Secret"),
):
    if not BFF_SHARED_SECRET or x_bff_secret != BFF_SHARED_SECRET:
        raise HTTPException(status_code=403, detail="Invalid service secret")

    access_token = create_access_token(
        {"sub": body.user_id},
        expires_delta=timedelta(minutes=30),
        extra_claims={"relay": True},
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 1800,
    }
