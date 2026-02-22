"""
Security: JWT creation/validation, password hashing, PHI encryption.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets
import bcrypt

from jose import JWTError, jwt
from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from app.core.config import settings

# PHI encryption (application-level, before DB write)
_fernet = Fernet(settings.PHI_ENCRYPTION_KEY.encode()
                 if len(settings.PHI_ENCRYPTION_KEY) > 10
                 else Fernet.generate_key())


# ── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    role: str,
    extra: Optional[dict] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": secrets.token_hex(16),  # Unique token ID for revocation
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_magic_link_token(case_id: str) -> str:
    """Secure specialist access token for escalated cases."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.MAGIC_LINK_EXPIRE_MINUTES
    )
    payload = {
        "case_id": case_id,
        "type": "specialist_magic",
        "exp": expire,
        "jti": secrets.token_urlsafe(32),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_magic_token(token: str) -> dict:
    payload = decode_access_token(token)
    if payload.get("type") != "specialist_magic":
        raise HTTPException(status_code=403, detail="Invalid specialist token")
    return payload


# ── PHI Encryption ───────────────────────────────────────────────────────────

def encrypt_phi(plaintext: str) -> str:
    """Encrypt personally identifiable information before DB storage."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_phi(ciphertext: str) -> str:
    """Decrypt PHI for authorized access."""
    return _fernet.decrypt(ciphertext.encode()).decode()
