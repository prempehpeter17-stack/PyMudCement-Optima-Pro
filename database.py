import os
from datetime import datetime
from typing import AsyncGenerator 

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker 

# Database URL configuration (defaults to async SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./pymudcement_optima.db") 

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
) 

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
) 

Base = declarative_base() 

# ------------------------------------------------------------------------------
# SQLAlchemy Models
# ------------------------------------------------------------------------------ 

class UserModel(Base):
    __tablename__ = "users" 

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="drilling_engineer", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow) 

    wells = relationship("WellModel", back_populates="owner", cascade="all, delete-orphan")


class WellModel(Base):
    __tablename__ = "wells" 

    id = Column(Integer, primary_key=True, index=True)
    well_name = Column(String(100), index=True, nullable=False)
    field_name = Column(String(100), nullable=True)
    operator = Column(String(100), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow) 

    owner = relationship("UserModel", back_populates="wells")
    runs = relationship("HydraulicsRunModel", back_populates="well", cascade="all, delete-orphan")


class HydraulicsRunModel(Base):
    __tablename__ = "hydraulics_runs" 

    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=True)
    flow_rate_gpm = Column(Float, nullable=False)
    total_depth_ft = Column(Float, nullable=False)
    surface_mud_weight_ppg = Column(Float, nullable=False)
    plastic_viscosity_cp = Column(Float, nullable=False)
    yield_point_lb_100ft2 = Column(Float, nullable=False)
    
    # Calculation Outputs
    ecd_ppg = Column(Float, nullable=False)
    spp_psi = Column(Float, nullable=False)
    annular_loss_psi = Column(Float, nullable=False)
    pipe_loss_psi = Column(Float, nullable=False)
    
    # Diagnostics & Geometry Data
    severity = Column(String(20), nullable=False)
    matched_hazard = Column(String(255), nullable=True)
    segments_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow) 

    well = relationship("WellModel", back_populates="runs") 

# ------------------------------------------------------------------------------
# Helpers & Dependency Injection
# ------------------------------------------------------------------------------ 

async def init_db():
    """Creates database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) 

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for providing an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
