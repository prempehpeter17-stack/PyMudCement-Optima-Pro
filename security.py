import hashlib
import hmac
import os
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt

SECRET_KEY = "OPT-PRO-SECURE-KEY-PRODUCTION-ENV"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hash string.
  
    Supports new PBKDF2 hashes (salt$hash) and falls back to legacy passlib/bcrypt.
    """
    try:
        # Check if hash is in new PBKDF2 format (salt$hash)
        if "$" in hashed_password and not hashed_password.startswith("$"):
            salt_hex, hash_hex = hashed_password.split("$", 1)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(hash_hex)
          
            new_hash = hashlib.pbkdf2_hmac(
                "sha256",
                plain_password.encode("utf-8"),
                salt,
                100_000
            )
            return hmac.compare_digest(new_hash, expected_hash)
      
        # Legacy passlib/bcrypt fallback
        import passlib.hash
        return passlib.hash.bcrypt.verify(plain_password, hashed_password)
    except Exception as e:
        traceback.print_exc()
        raise e

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