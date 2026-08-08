import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "optima_pro_super_secret_jwt_key_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hash string (PBKDF2 format: salt$hash)."""
    try:
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
        # Fallback for legacy (should not happen)
        return False
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
    return f"{salt.hex()}${hash_bytes.hex()}"

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)