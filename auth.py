import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Import database models and session dependency from your unified database.py
from database import get_db, User

logger = logging.getLogger("pymudcement_optima")

# =====================================================================
# 1. Security Configuration
# =====================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_CHANGE_ME_IN_PRODUCTION_KEY_987654321")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme looking for Bearer token in the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

router = APIRouter()

# =====================================================================
# 2. Helper Functions (Hashing & Tokens)
# =====================================================================
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a raw password against its stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Generates a secure bcrypt hash from a raw password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encodes user identity payload into a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# =====================================================================
# 3. Pydantic Schemas for Auth Payloads
# =====================================================================
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")
    full_name: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None

# =====================================================================
# 4. Auth Dependencies (Protecting Endpoints)
# =====================================================================
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Decodes the incoming JWT token, validates claims, and retrieves the User
    from the database. Use this with Depends(get_current_user) to secure endpoints.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or token has expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except jwt.PyJWTError as exc:
        logger.warning(f"Failed JWT verification attempt: {exc}")
        raise credentials_exception

    result = await db.execute(select(User).where(User.email == token_data.email))
    user = result.scalars().first()

    if user is None:
        raise credentials_exception

    return user

# =====================================================================
# 5. Auth API Endpoints
# =====================================================================
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """Registers a new user with a hashed password in the database."""
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    existing_user = result.scalars().first()
   
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists."
        )

    # Hash password and store new user
    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(
        email=user_in.email,
        hashed_password=hashed_pwd,
        full_name=user_in.full_name,
        role="engineer"
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info(f"Registered new engineer account: {new_user.email}")
    return new_user

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticates user credentials using OAuth2 form fields (username=email, password).
    Returns a signed JWT bearer token.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate JWT access token with the user's email as subject ('sub')
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    logger.info(f"User logged in successfully: {user.email}")

    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
async def get_authenticated_user_profile(current_user: User = Depends(get_current_user)):
    """Returns the profile of the currently logged-in user."""
    return current_user