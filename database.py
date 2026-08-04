from datetime import datetime, timezone
import re
from typing import List, Optional, Dict, Any

from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, JSON, Boolean, Text, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./pymudcement.db"

# Create Async Engine
engine = create_async_engine(DATABASE_URL, echo=False)

# Enable Foreign Key Support for SQLite
@event.listens_for(engine.sync_engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)

class Base(DeclarativeBase):
    """Base model class for SQLAlchemy declarative mappings."""
    pass

# ==============================================================================
# USER MODEL
# ==============================================================================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="drilling_engineer", nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), default="Enterprise Hydrocarbons Corp", index=True, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_reset_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    projects: Mapped[List["Project"]] = relationship(
        "Project", back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    revoked_tokens: Mapped[List["RevokedToken"]] = relationship(
        "RevokedToken", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @validates("email")
    def validate_email(self, key: str, address: str) -> str:
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not address or not re.match(email_regex, address):
            raise ValueError(f"Invalid email address provided: {address}")
        return address

# ==============================================================================
# REVOKED TOKEN MODEL
# ==============================================================================

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="revoked_tokens")

# ==============================================================================
# AUDIT LOG MODEL
# ==============================================================================

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="audit_logs")

# ==============================================================================
# PROJECT MODEL
# ==============================================================================

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    well_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False, default="Unspecified Field")
    rig_name: Mapped[str] = mapped_column(String(100), nullable=False, default="Unspecified Rig")
    status: Mapped[str] = mapped_column(String(30), index=True, default="Planning", nullable=False)
    
    unit_system: Mapped[str] = mapped_column(String(20), default="Field US", nullable=False)
    mud_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_depth: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hole_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    trajectory_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    hydraulics_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    cement_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner: Mapped["User"] = relationship("User", back_populates="projects")

# ==============================================================================
# INITIALIZATION
# ==============================================================================

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
