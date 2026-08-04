import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update

from database import get_db, UserModel, RefreshTokenModel, AuditLogModel
from auth import (
    UserCreate,
    UserResponse,
    TokenResponse,
    RefreshTokenRequest,
    get_password_hash,
    hash_token,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

logger = logging.getLogger(__name__)

# Security parameters
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# Constant-time dummy hash to prevent timing attacks on nonexistent accounts
DUMMY_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQOEg6Lruj3vjPGga31lW"

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"]
)


def stage_audit_event(
    db: AsyncSession,
    user_id: Optional[int],
    email: str,
    event_type: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
    status_code: int
) -> None:
    """Stages an audit log entry in the current unit of work without triggering premature commits."""
    audit_entry = AuditLogModel(
        user_id=user_id,
        email=email,
        event_type=event_type,
        ip_address=ip_address,
        user_agent=user_agent,
        status_code=status_code,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(audit_entry)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
async def register_user(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Registers a drilling engineer with privilege containment and atomic transaction safety."""
    normalized_email = user_data.email.lower().strip()

    result = await db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered."
        )

    new_user = UserModel(
        email=normalized_email,
        hashed_password=get_password_hash(user_data.password),
        role="drilling_engineer",
        is_active=True,
        is_verified=False,
        failed_login_attempts=0,
        locked_until=None
    )

    try:
        db.add(new_user)
        await db.flush()  # Assigns primary key user_id

        stage_audit_event(
            db=db,
            user_id=new_user.id,
            email=normalized_email,
            event_type="REGISTER_SUCCESS",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            status_code=201
        )
        await db.commit()
        await db.refresh(new_user)

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered."
        )
    except Exception:
        await db.rollback()
        logger.exception("Account registration pipeline failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process registration request."
        )

    return new_user


@router.post(
    "/login",
    response_model=TokenResponse
)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Mitigates timing leaks, handles account locks, tracks session devices, and issues tokens."""
    normalized_email = form_data.username.lower().strip()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    now_utc = datetime.now(timezone.utc)

    result = await db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    )
    user = result.scalars().first()

    # Timing Attack Mitigation: Execute bcrypt verify even if user doesn't exist
    target_hash = user.hashed_password if user else DUMMY_HASH
    password_valid = verify_password(form_data.password, target_hash)

    if not user or not password_valid:
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now_utc + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            
            stage_audit_event(
                db=db,
                user_id=user.id,
                email=normalized_email,
                event_type="LOGIN_FAILED",
                ip_address=client_ip,
                user_agent=user_agent,
                status_code=401
            )
            await db.commit()
        else:
            # Unauthenticated non-user attempt: stage audit in ephemeral state
            stage_audit_event(
                db=db,
                user_id=None,
                email=normalized_email,
                event_type="LOGIN_FAILED_UNKNOWN_USER",
                ip_address=client_ip,
                user_agent=user_agent,
                status_code=401
            )
            await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify lockout status
    if user.locked_until and user.locked_until > now_utc:
        stage_audit_event(
            db=db,
            user_id=user.id,
            email=normalized_email,
            event_type="LOGIN_LOCKED_OUT",
            ip_address=client_ip,
            user_agent=user_agent,
            status_code=403
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account temporarily locked. Please try again later."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended or disabled."
        )

    # Successful Login: Reset failure counters & register metadata
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now_utc
    user.last_login_ip = client_ip

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "user_id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    raw_refresh_token, token_jti = create_refresh_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    # Record Device & Session Context
    db_refresh_token = RefreshTokenModel(
        jti_hash=hash_token(token_jti),
        user_id=user.id,
        expires_at=now_utc + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
        ip_address=client_ip,
        user_agent=user_agent,
        last_used_at=now_utc
    )
    db.add(db_refresh_token)

    stage_audit_event(
        db=db,
        user_id=user.id,
        email=normalized_email,
        event_type="LOGIN_SUCCESS",
        ip_address=client_ip,
        user_agent=user_agent,
        status_code=200
    )
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post(
    "/refresh",
    response_model=TokenResponse
)
async def refresh_access_token(
    token_data: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Executes Refresh Token Rotation and triggers global session revocation if replay is detected."""
    payload = verify_refresh_token(token_data.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    raw_jti = payload.get("jti")
    user_id = payload.get("user_id")
    jti_hashed = hash_token(raw_jti)
    now_utc = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    stmt = select(RefreshTokenModel).where(
        RefreshTokenModel.jti_hash == jti_hashed,
        RefreshTokenModel.user_id == user_id
    )
    result = await db.execute(stmt)
    token_record = result.scalars().first()

    # SECURITY REPLAY DETECTED: Token exists but was previously revoked!
    if token_record and token_record.revoked:
        # Revoke ALL active sessions for this compromised user
        await db.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id)
            .values(revoked=True)
        )
        
        user = await db.get(UserModel, user_id)
        stage_audit_event(
            db=db,
            user_id=user_id,
            email=user.email if user else "UNKNOWN",
            event_type="REFRESH_TOKEN_REUSE_DETECTED",
            ip_address=client_ip,
            user_agent=user_agent,
            status_code=401
        )
        await db.commit()

        logger.warning(f"SECURITY BREACH: Refresh token reuse detected for User ID {user_id}. All sessions revoked.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security violation: Revoked token reused. All sessions invalidated."
        )

    if not token_record or token_record.expires_at < now_utc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or expired"
        )

    user = await db.get(UserModel, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive or removed"
        )

    # Rotate Token: Invalidate old token and generate replacement
    token_record.revoked = True

    new_access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "user_id": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    new_raw_refresh_token, new_token_jti = create_refresh_token(
        data={"sub": user.email, "user_id": user.id},
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )

    new_db_refresh_token = RefreshTokenModel(
        jti_hash=hash_token(new_token_jti),
        user_id=user.id,
        expires_at=now_utc + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked=False,
        ip_address=client_ip,
        user_agent=user_agent,
        last_used_at=now_utc
    )
    db.add(new_db_refresh_token)

    stage_audit_event(
        db=db,
        user_id=user.id,
        email=user.email,
        event_type="TOKEN_ROTATED",
        ip_address=client_ip,
        user_agent=user_agent,
        status_code=200
    )
    await db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_raw_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK
)
async def logout_user(
    token_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Revokes the current refresh token upon sign-out."""
    payload = verify_refresh_token(token_data.refresh_token)
    if payload:
        raw_jti = payload.get("jti")
        user_id = payload.get("user_id")
        jti_hashed = hash_token(raw_jti)

        stmt = select(RefreshTokenModel).where(
            RefreshTokenModel.jti_hash == jti_hashed,
            RefreshTokenModel.user_id == user_id,
            RefreshTokenModel.revoked.is_(False)
        )
        result = await db.execute(stmt)
        token_record = result.scalars().first()

        if token_record:
            token_record.revoked = True
            await db.commit()

    return {"detail": "Successfully logged out"}
