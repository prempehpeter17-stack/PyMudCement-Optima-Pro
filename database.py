from datetime import datetime, timezone
import re
from typing import List, Optional, Dict, Any

from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, JSON, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validater
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

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), default="Engineer", nullable=False
    )
    company_name: Mapped[str] = mapped_column(
        String(100), default="Enterprise Hydrocarbons Corp", index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Passive deletes hand off cascade execution directly to DB (ondelete="CASCADE")
    projects: Mapped[List["Project"]] = relationship(
        "Project", 
        back_populates="owner", 
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    @validater("email")
    def validate_email(self, key: str, address: str) -> str:
        """Model-level validation for valid corporate email formats."""
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not address or not re.match(email_regex, address):
            raise ValueError(f"Invalid email address provided: {address}")
        return address

# ==============================================================================
# PROJECT MODEL (ENGINEERING & HYDRAULICS BACKEND)
# ==============================================================================

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )
    well_name: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )
    field_name: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False, default="Unspecified Field"
    )
    rig_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Unspecified Rig"
    )
    status: Mapped[str] = mapped_column(
        String(30), index=True, default="Planning", nullable=False
    )
    
    # Engineering Telemetry & Unit Tracking
    unit_system: Mapped[str] = mapped_column(
        String(20), default="Field US", nullable=False
    )
    mud_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    total_depth: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    hole_size: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )

    # Structured Domain Payload Schemas
    trajectory_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    hydraulics_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    cement_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    # Audit & Soft Deletion Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Foreign Key & Relationship Mapping
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    owner: Mapped["User"] = relationship(
        "User", back_populates="projects"
    )

# ==============================================================================
# DATABASE INITIALIZATION
# ==============================================================================

async def init_db():
    """Initializes schema tables asynchronously."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
