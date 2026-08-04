import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, ValidationError
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import User, RevokedToken, RefreshToken

# ==============================================================================
# ENVIRONMENT & SECRET ROTATION CONFIGURATION
# ==============================================================================

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("Critical Configuration Error: JWT_SECRET_KEY is missing.")

REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY")
if not REFRESH_SECRET_KEY:
    raise RuntimeError("Critical Configuration Error: JWT_REFRESH_SECRET_KEY is missing.")

PREVIOUS_SECRET_KEYS = [
    k.strip() for k in os.getenv("JWT_SECRET_KEYS_PREVIOUS", "").split(",") if k.strip()
]
PREVIOUS_REFRESH_SECRET_KEYS = [
    k.strip() for k in os.getenv("JWT_REFRESH_SECRET_KEYS_PREVIOUS", "").split(",") if k.strip()
]

ALGORITHM = "HS256"
AUDIENCE = "pymudcement-api"
ISSUER = "PyMudCement-Optima-Pro"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# Delegate truncation handling directly to Passlib/Bcrypt engine
pwd_context = CryptContext(
    schemes=["bcrypt"],
    bcrypt__truncate_error=False,
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLE_LEVELS: Dict[str, int] = {
    "viewer": 1,
    "drilling_engineer": 2,
    "manager": 3,
    "admin": 4
}

# ==============================================================================
# PYDANTIC TOKEN PAYLOAD SCHEMAS
# ==============================================================================

class AccessTokenPayload(BaseModel):
    sub: EmailStr
    username: str
    role: str
    company: str
    jti: str
    aud: str
    iss: str
    type: str
    iat: datetime
    exp: datetime


class RefreshTokenPayload(BaseModel):
    sub: EmailStr
    jti: str
    aud: str
    iss: str
    type: str
    iat: datetime
    exp: datetime

# ==============================================================================
# PASSWORD UTILITIES (NATIVE PASSLIB TRUNCATION)
# ==============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies plain text password against stored hash natively."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generates bcrypt hash natively using configured truncation settings."""
    return pwd_context.hash(password)

# ==============================================================================
# JWT ISSUANCE & DECODING
# ==============================================================================

def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> Tuple[str, str, datetime]:
    """Issues Access JWT containing iat, exp, aud, iss, and unique jti."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    payload = {
        "sub": user.email,
        "username": user.username,
        "role": user.role,
        "company": user.company_name,
        "jti": jti,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), jti, expire


def create_refresh_token(user: User, expires_delta: Optional[timedelta] = None) -> Tuple[str, str, datetime]:
    """Issues Refresh JWT signed with dedicated refresh key."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    
    payload = {
        "sub": user.email,
        "jti": jti,
        "aud": AUDIENCE,
        "iss": ISSUER,
        "iat": now,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, REFRESH_SECRET_KEY, algorithm=ALGORITHM), jti, expire


def _decode_jwt_with_keys(
    token: str, 
    primary_key: str, 
    fallback_keys: List[str]
) -> Dict[str, Any]:
    """Attempts JWT decoding across primary and historical rotated secret keys."""
    keys_to_try = [primary_key] + fallback_keys
    last_exception = None

    for key in keys_to_try:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=AUDIENCE,
                issuer=ISSUER
            )
        except JWTError as e:
            last_exception = e
            continue

    raise last_exception or JWTError("Signature validation failed across all key sets.")


def decode_access_token_with_rotation(token: str) -> Dict[str, Any]:
    """Decodes access token using active and fallback access keys."""
    return _decode_jwt_with_keys(token, SECRET_KEY, PREVIOUS_SECRET_KEYS)


def decode_refresh_token_with_rotation(token: str) -> Dict[str, Any]:
    """Decodes refresh token using active and fallback refresh keys."""
    return _decode_jwt_with_keys(token, REFRESH_SECRET_KEY, PREVIOUS_REFRESH_SECRET_KEYS)

# ==============================================================================
# PERSISTENCE & SESSION LIFECYCLE HELPERS
# ==============================================================================

async def store_refresh_token_session(
    db: AsyncSession,
    user_id: int,
    jti: str,
    expires_at: datetime
) -> RefreshToken:
    """Persists refresh token tracking record for rotation and theft detection."""
    refresh_session = RefreshToken(
        user_id=user_id,
        jti=jti,
        expires_at=expires_at,
        revoked=False
    )
    db.add(refresh_session)
    return refresh_session


async def purge_expired_revoked_tokens(db: AsyncSession) -> int:
    """Maintenance utility: Purges expired blacklisted access tokens from memory/DB."""
    now = datetime.now(timezone.utc)
    stmt = delete(RevokedToken).where(RevokedToken.expires_at < now)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount

# ==============================================================================
# ACCOUNT LOCKOUT PROTECTION
# ==============================================================================

def check_account_lockout(user: User) -> bool:
    """Checks if user account is locked, normalizing naive DB timestamps to UTC."""
    if not user.locked_until:
        return False

    lock_time = user.locked_until
    if lock_time.tzinfo is None:
        lock_time = lock_time.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) < lock_time


def record_failed_login(user: User):
    """Increments in-memory failed login counter and sets lockout threshold."""
    user.failed_login_attempts += 1
    if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)


def reset_failed_logins(user: User):
    """Resets failed login counters upon successful authentication."""
    user.failed_login_attempts = 0
    user.locked_until = None

# ==============================================================================
# DEPENDENCIES & AUTHORIZATION
# ==============================================================================

async def get_db():
    """Async database session dependency."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Validates JWT claims, checks indexed revocation status, and verifies user status."""
    generic_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        raw_payload = decode_access_token_with_rotation(token)
        payload = AccessTokenPayload(**raw_payload)

        if payload.type != "access":
            raise generic_credentials_exception

    except (JWTError, ValidationError):
        raise generic_credentials_exception

    # Fast indexed lookup on RevokedToken.jti
    revoked = await db.execute(select(RevokedToken).where(RevokedToken.jti == payload.jti))
    if revoked.scalars().first():
        raise generic_credentials_exception

    # User state checks
    result = await db.execute(select(User).where(User.email == payload.sub))
    user = result.scalars().first()

    if (
        user is None 
        or not user.is_active 
        or not user.email_verified 
        or check_account_lockout(user)
    ):
        raise generic_credentials_exception

    return user


def require_min_role(min_level_name: str):
    """Hierarchical RBAC permission enforcer."""
    min_level = ROLE_LEVELS.get(min_level_name)
    if min_level is None:
        raise ValueError(f"Configuration Error: Invalid role string specified '{min_level_name}'")

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_LEVELS.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for current permission level"
            )
        return current_user

    return role_checker
