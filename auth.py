import os
from datetime import datetime, timedelta
from typing import Optional 

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select 

from database import get_db, UserModel 

# Secret Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "optimapro_super_secret_jwt_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 Hours 

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login") 

# ------------------------------------------------------------------------------
# Pydantic Authentication Schemas
# ------------------------------------------------------------------------------ 

class Token(BaseModel):
    access_token: str
    token_type: str 

class TokenData(BaseModel):
    email: Optional[str] = None 

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = "drilling_engineer" 

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str 

    class Config:
        from_attributes = True 

# ------------------------------------------------------------------------------
# Security Utility Functions
# ------------------------------------------------------------------------------ 

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a hashed stored password."""
    return pwd_context.verify(plain_password, hashed_password) 

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password) 

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encodes a JWT payload with an expiration timestamp."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt 

# ------------------------------------------------------------------------------
# User Verification & Auth Dependency
# ------------------------------------------------------------------------------ 

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserModel:
    """FastAPI Dependency for authenticating requests via JWT bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception 

    result = await db.execute(select(UserModel).where(UserModel.email == token_data.email))
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
        
    return user
