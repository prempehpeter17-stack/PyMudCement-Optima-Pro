from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib
import os
from jose import JWTError, jwt

SECRET_KEY = "OPT-PRO-SECURE-KEY-PRODUCTION-ENV"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a salt$hash string using PBKDF2."""
    try:
        salt_hex, hash_hex = hashed_password.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
       
        new_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            100_000
        )
        return hashlib.compare_digest(new_hash, expected_hash)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hashes a password using PBKDF2-HMAC-SHA256 with a random 16-byte salt."""
    salt = os.urandom(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        100_000
    )
    return f"{salt.hex()}:${hash_bytes.hex()}"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a JWT access token with expiration time."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)