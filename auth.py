import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, RevokedToken, AsyncSessionLocal

# Environment variable secret validation
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Critical Configuration Error: JWT_SECRET_KEY is not set.")

REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")
if not REFRESH_SECRET_KEY:
    raise RuntimeError("Critical Configuration Error: JWT_REFRESH_SECRET_KEY is not set.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_LEVELS: Dict[str, int] = {
    "viewer": 1,
    "drilling_engineer": 2,
    "manager": 3,
    "admin": 4
}

# ==============================================================================
# TYPED SCHEMAS
# ==============================================================================

class AccessTokenPayload(BaseModel):
    sub: EmailStr
    username: str
    role: str
    company: str
    jti: str
    type: str
    exp: datetime

class RefreshTokenPayload(BaseModel):
    sub: EmailStr
    jti: str
    type: str
    exp: datetime

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, description="Password must be at least 8 characters long")
    username: str = Field(min_length=3, max_length=50)
    company_name: Optional[str] = "Enterprise Hydrocarbons Corp"

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    company_name: str
    is_active: bool
    email_verified: bool

    class Config:
        from_attributes = True

# ==============================================================================
# UTILITIES & TOKEN ISSUANCE
# ==============================================================================

def truncate_password_bytes(password: str) -> str:
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(truncate_password_bytes(plain_password), hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(truncate_password_bytes(password))

def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user.email,
        "username": user.username,
        "role": user.role,
        "company": user.company_name,
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload = {
        "sub": user.email,
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM)

async def verify_refresh_token(token: str, db: AsyncSession) -> RefreshTokenPayload:
    """Decodes refresh JWT and validates signature, type, and database revocation state."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        raw_payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        payload = RefreshTokenPayload(**raw_payload)
        
        if payload.type != "refresh":
            raise credentials_exception
            
    except (JWTError, Exception):
        raise credentials_exception

    # Enforce Revocation Check
    revoked = await db.execute(select(RevokedToken).where(RevokedToken.jti == payload.jti))
    if revoked.scalars().first():
        raise credentials_exception

    return payload

async def remove_expired_tokens(db: AsyncSession) -> int:
    """Utility task to prune expired revoked token entries from database."""
    result = await db.execute(
        delete(RevokedToken).where(RevokedToken.expires_at < datetime.now(timezone.utc))
    )
    await db.commit()
    return result.rowcount

# ==============================================================================
# DEPENDENCIES & AUTHORIZATION
# ==============================================================================

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    generic_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        raw_payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        payload = AccessTokenPayload(**raw_payload)

        if payload.type != "access":
            raise generic_credentials_exception

    except (JWTError, Exception):
        raise generic_credentials_exception

    # Check for Token Revocation
    revoked = await db.execute(select(RevokedToken).where(RevokedToken.jti == payload.jti))
    if revoked.scalars().first():
        raise generic_credentials_exception

    # Fetch User
    result = await db.execute(select(User).where(User.email == payload.sub))
    user = result.scalars().first()

    if user is None or not user.is_active or not user.email_verified:
        raise generic_credentials_exception

    return user

def require_min_role(min_level_name: str):
    """Hierarchical RBAC check that fails loudly if given an invalid role name."""
    min_level = ROLE_LEVELS.get(min_level_name)
    if min_level is None:
        raise ValueError(f"Configuration Error: Invalid role check specified: {min_level_name}")

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_LEVELS.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for current permission level"
            )
        return current_user

    return role_checker
