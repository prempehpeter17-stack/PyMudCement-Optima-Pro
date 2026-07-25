import os
import logging
from typing import AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

logger = logging.getLogger("pymudcement_optima")

# =====================================================================
# 1. Database Configuration & Connection Pool
# =====================================================================
# Default to async SQLite for local dev, or async PostgreSQL for production
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./pymudcement.db"
)
DB_ECHO = os.getenv("DB_ECHO", "False").lower() in ("true", "1", "t")

is_sqlite = DATABASE_URL.startswith("sqlite")

engine_kwargs = {
    "echo": DB_ECHO,
    "future": True,
}

if not is_sqlite:
    # Industrial PostgreSQL connection pooling parameters
    engine_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_pre_ping": True,  # Checks connection health prior to query execution
    })

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Essential for async field access after commit
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()

# =====================================================================
# 2. Database Models (Engineering & Core Schema)
# =====================================================================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="engineer")  # engineer, admin, auditor
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    field_name = Column(String(255), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="projects")
    wells = relationship("Well", back_populates="project", cascade="all, delete-orphan")

class Well(Base):
    __tablename__ = "wells"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    well_name = Column(String(255), nullable=False)
    target_depth_ft = Column(Float, nullable=False)
    casing_shoe_depth_ft = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="wells")
    hydraulics_runs = relationship("HydraulicsRun", back_populates="well", cascade="all, delete-orphan")

class HydraulicsRun(Base):
    __tablename__ = "hydraulics_runs"

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    run_label = Column(String(255), nullable=True)
    flow_rate_gpm = Column(Float, nullable=False)
    mud_weight_ppg = Column(Float, nullable=False)
    plastic_viscosity_cp = Column(Float, nullable=False)
    yield_point_lb_100ft2 = Column(Float, nullable=False)
   
    # Calculated Outputs
    total_annular_pressure_loss_psi = Column(Float, nullable=False)
    calculated_ecd_ppg = Column(Float, nullable=False)
    surface_spp_psi = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    well = relationship("Well", back_populates="hydraulics_runs")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(255), nullable=False)
    endpoint = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# =====================================================================
# 3. Initialization & Dependency Injection
# =====================================================================
async def init_db():
    """
    Creates all database tables automatically on startup.
    In production environments, manage schema updates with Alembic.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables successfully synchronized.")

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session per request.
    Automatically commits transactions or rolls back on exceptions.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(f"Database transaction rolled back due to error: {exc}")
            raise exc
        finally:
            await session.close()