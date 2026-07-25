import time
import logging
import sys
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

# 1. Database Imports
from database import init_db, engine, get_db, User, HydraulicsRun

# 2. Physics Engine Imports (Linking physics.py)
from physics import (
    DrillingHydraulicsEngine,
    WellSegment,
    RheologyModel,
    NozzleInput
)

# 3. Authentication Imports (Linking auth.py)
import auth
from auth import get_current_user

# =====================================================================
# Logging & Lifespan Configuration
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("pymudcement_optima")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PyMudCement Optima API & initializing database...")
    await init_db()
    yield
    logger.info("Closing database connection pool...")
    await engine.dispose()

app = FastAPI(
    title="PyMudCement Optima API",
    description="Production-Grade Drilling Hydraulics & Dynamic Diagnostics Engine",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Authentication Router from auth.py
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication & Security"])

# =====================================================================
# API Schemas
# =====================================================================
class HydraulicsSolveRequest(BaseModel):
    well_id: Optional[int] = None
    flow_rate_gpm: float = Field(..., gt=0, description="Flow rate in GPM")
    total_depth_ft: float = Field(..., gt=0, description="Total depth in feet")
    surface_mud_weight_ppg: float = Field(..., gt=0, description="Surface mud weight in ppg")
    rheology_model: RheologyModel = Field(default=RheologyModel.BINGHAM_PLASTIC)
    nozzles: List[NozzleInput] = Field(default=[])
    segments: List[WellSegment]

# =====================================================================
# Linked Hydraulics Endpoint
# =====================================================================
@app.post("/api/v1/hydraulics/solve", tags=["Hydraulics & Physics Engine"])
async def solve_hydraulics(
    payload: HydraulicsSolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Protected route via JWT
):
    """
    Executes multi-segment hydraulics calculations using the physics engine in `physics.py`
    and persists the results to the database via `database.py`.
    """
    if not payload.segments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one well segment must be provided."
        )

    try:
        # 1. Instantiate Physics Engine from physics.py
        physics_engine = DrillingHydraulicsEngine(
            surface_mud_weight_ppg=payload.surface_mud_weight_ppg,
            flow_rate_gpm=payload.flow_rate_gpm,
            total_depth_ft=payload.total_depth_ft,
            rheology_model=payload.rheology_model
        )

        # 2. Add segments and bit nozzles to the physics engine
        for segment in payload.segments:
            physics_engine.add_segment(segment)

        for nozzle in payload.nozzles:
            physics_engine.add_nozzle(nozzle)

        # 3. Solve hydraulics calculations
        results = physics_engine.solve()

        # 4. Save results to the database using models in database.py
        if payload.well_id:
            hydraulics_record = HydraulicsRun(
                well_id=payload.well_id,
                run_label=f"Run - {payload.rheology_model.value}",
                flow_rate_gpm=payload.flow_rate_gpm,
                mud_weight_ppg=payload.surface_mud_weight_ppg,
                plastic_viscosity_cp=payload.segments[0].viscosity_cp,
                yield_point_lb_100ft2=payload.segments[0].yield_point_lb_100ft2,
                total_annular_pressure_loss_psi=results["total_annular_pressure_loss_psi"],
                calculated_ecd_ppg=results["bottomhole_ecd_ppg"],
                surface_spp_psi=results["standpipe_pressure_spp_psi"]
            )
            db.add(hydraulics_record)
            await db.commit()

        return {
            "status": "success",
            "executed_by": current_user.email,
            "data": results
        }

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.error(f"Hydraulics solve failed: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while computing wellbore physics."
        )