import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, status, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Engine & DB Imports
from ai_engine import DrillingHydraulicsEngine, WellSegment, DiagnosticEngine
from pdf_generator import generate_hydraulics_pdf
from database import init_db, create_audit_log, UserModel
from auth import get_current_user
from router import router as auth_router

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PyMudCementOptimaPro.API")


# ==========================================
# Settings Configuration
# ==========================================
class Settings(BaseSettings):
    app_name: str = "PyMudCement Optima Pro"
    version: str = "1.0.0"
    environment: str = "production"
    engine_version: str = "DrillingHydraulicsEngine v2.1"
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "https://yourfrontend.com"
        ]
    )

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()

# Global Diagnostic Instance
ai_diagnostics: Optional[DiagnosticEngine] = None


# ==========================================
# Lifespan Management
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_diagnostics
    try:
        logger.info("Initializing PyMudCement Optima Pro engines...")
        await init_db()
        ai_diagnostics = DiagnosticEngine(
            ecd_upper_threshold_delta=1.5,
            max_spp_limit=3500.0
        )
        logger.info("Startup sequence completed successfully.")
    except Exception:
        logger.exception("Startup failure encountered during initialization")
        raise

    yield

    logger.info("Shutting down PyMudCement Optima Pro services...")


# ==========================================
# FastAPI App Initialization
# ==========================================
app = FastAPI(
    title=settings.app_name,
    description="Enterprise API engine providing drilling hydraulics calculations and reporting.",
    version=settings.version,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)


# ==========================================
# 3. Global Exception Handler
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled application error on path: %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# ==========================================
# Pydantic Input Schemas
# ==========================================
class WellSegmentSchema(BaseModel):
    name: str = Field(default="Drill Pipe", description="Name of the segment")
    top_md: float = Field(default=0.0, ge=0.0)
    bottom_md: float = Field(default=7000.0, ge=0.0)
    pipe_od: float = Field(default=5.0, gt=0.0, le=20.0)
    pipe_id: float = Field(default=4.276, gt=0.0, le=20.0)
    hole_id: float = Field(default=8.5, gt=0.0, le=36.0)

    @model_validator(mode="after")
    def validate_geometry_and_depth(self):
        if self.pipe_id >= self.pipe_od:
            raise ValueError("Pipe ID must be strictly smaller than Pipe OD")
        if self.bottom_md <= self.top_md:
            raise ValueError("Bottom MD must be greater than Top MD")
        return self


class ReportMetadata(BaseModel):
    company: str = Field(default="Global Energy Corp")
    well_name: str = Field(default="Well 101-A")
    engineer: str = Field(default="Lead Drilling Engineer")


class HydraulicsPayloadSchema(BaseModel):
    flow_rate_gpm: float = Field(default=450.0, gt=0.0, le=2000.0)
    total_depth_ft: float = Field(default=8000.0, gt=0.0, le=35000.0)
    surface_mud_weight_ppg: float = Field(default=10.0, ge=6.0, le=25.0)
    plastic_viscosity_cp: float = Field(default=20.0, ge=0.0, le=150.0)
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0.0, le=100.0)
    segments: Optional[List[WellSegmentSchema]] = None
    metadata: Optional[ReportMetadata] = None


# ==========================================
# 1. Strict Output Schemas (Strong OpenAPI Docs)
# ==========================================
class DiagnosticResponse(BaseModel):
    ecd_status: str
    warnings: List[str] = []
    recommendations: List[str] = []


class PhysicsResponse(BaseModel):
    ecd_ppg: float
    total_pressure_loss_psi: float
    annular_velocity_ft_min: float
    standpipe_pressure_psi: float


class HydraulicsResponse(BaseModel):
    request_id: str
    user: str
    physics_results: PhysicsResponse
    diagnostics: DiagnosticResponse


# ==========================================
# 7. Framework-Independent Service Layer
# ==========================================
def run_hydraulics_service(payload: HydraulicsPayloadSchema, request_id: str) -> dict:
    """Pure domain logic. Throws RuntimeError, not HTTPException."""
    logger.info(
        "REQUEST [%s]: Service started | Depth=%s ft | MW=%s ppg",
        request_id,
        payload.total_depth_ft,
        payload.surface_mud_weight_ppg
    )

    if ai_diagnostics is None:
        logger.error("REQUEST [%s]: Diagnostic Engine uninitialized", request_id)
        raise RuntimeError("Diagnostic Engine unavailable")

    engine = DrillingHydraulicsEngine(
        surface_mud_weight_ppg=payload.surface_mud_weight_ppg,
        flow_rate_gpm=payload.flow_rate_gpm,
        total_depth_ft=payload.total_depth_ft,
        plastic_viscosity_cp=payload.plastic_viscosity_cp,
        yield_point_lb_100ft2=payload.yield_point_lb_100ft2
    )

    if payload.segments:
        for seg in payload.segments:
            engine.add_segment(WellSegment(
                name=seg.name,
                length_ft=seg.bottom_md - seg.top_md,
                pipe_od_in=seg.pipe_od,
                pipe_id_in=seg.pipe_id,
                hole_id_in=seg.hole_id,
                mud_weight_ppg=payload.surface_mud_weight_ppg,
                viscosity_cp=payload.plastic_viscosity_cp,
                yield_point_lb_100ft2=payload.yield_point_lb_100ft2
            ))
    else:
        engine.add_segment(WellSegment(
            name="Default Drill String",
            length_ft=payload.total_depth_ft,
            pipe_od_in=5.0,
            pipe_id_in=4.276,
            hole_id_in=8.5,
            mud_weight_ppg=payload.surface_mud_weight_ppg,
            viscosity_cp=payload.plastic_viscosity_cp,
            yield_point_lb_100ft2=payload.yield_point_lb_100ft2
        ))

    physics_results = engine.solve()
    diagnostics = ai_diagnostics.analyze_telemetry(
        physics_metrics=physics_results,
        historical_esd=payload.surface_mud_weight_ppg
    )

    return {
        "physics_results": physics_results,
        "diagnostics": diagnostics
    }


# ==========================================
# 2 & 9. Health & System Diagnostics
# ==========================================
async def check_database_connection() -> bool:
    """Mock DB Ping check helper."""
    try:
        # e.g., await db.execute("SELECT 1")
        return True
    except Exception:
        return False


@app.get("/health", tags=["System Status"])
async def health_check():
    db_status = await check_database_connection()
    is_healthy = db_status and (ai_diagnostics is not None)
    
    return {
        "status": "healthy" if is_healthy else "degraded",
        "database": "connected" if db_status else "disconnected",
        "diagnostic_engine": bool(ai_diagnostics),
        "service": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "engine_version": settings.engine_version
    }


@app.get("/", tags=["System Status"])
async def root():
    return {"system": settings.app_name, "status": "OPERATIONAL", "version": settings.version}


# ==========================================
# Calculation & PDF Routes
# ==========================================
@app.post(
    "/api/v1/hydraulics/calculate",
    response_model=HydraulicsResponse,
    tags=["Hydraulics Engine"]
)
async def calculate_hydraulics(
    payload: HydraulicsPayloadSchema,
    current_user: UserModel = Depends(get_current_user)
):
    # 4. Clean 12-character Hex Request ID
    request_id = uuid.uuid4().hex[:12]

    try:
        results = run_hydraulics_service(payload, request_id)
        
        # 5. Persistent Audit Trail Logging
        await create_audit_log(
            user_id=current_user.id,
            action="HYDRAULICS_RUN",
            details={
                "request_id": request_id,
                "depth_ft": payload.total_depth_ft,
                "mud_weight_ppg": payload.surface_mud_weight_ppg
            }
        )

        return HydraulicsResponse(
            request_id=request_id,
            user=current_user.email,
            physics_results=results["physics_results"],
            diagnostics=results["diagnostics"]
        )

    except RuntimeError as re_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(re_err)
        )


@app.post("/api/v1/hydraulics/export-pdf", tags=["Reports"])
async def export_pdf_report(
    payload: HydraulicsPayloadSchema,
    current_user: UserModel = Depends(get_current_user)
):
    request_id = uuid.uuid4().hex[:12]

    try:
        results = run_hydraulics_service(payload, request_id)
        
        segments_data = [seg.model_dump() for seg in payload.segments] if payload.segments else []
        meta = payload.metadata or ReportMetadata()

        # Sanitization & RFC 5987 Encoding (Fix #6)
        safe_well_name = re.sub(r'[^a-zA-Z0-9_-]', '', meta.well_name.replace(" ", "_")) or "Well_Report"
        encoded_filename = quote(f"{safe_well_name}_Hydraulics_Report.pdf")

        pdf_buffer = generate_hydraulics_pdf(
            results=results["physics_results"],
            diagnostic_report=results["diagnostics"],
            executed_by=f"{meta.engineer} ({current_user.email})",
            company=meta.company,
            well_name=meta.well_name,
            segments=segments_data,
            pv=payload.plastic_viscosity_cp,
            yp=payload.yield_point_lb_100ft2
        )

        await create_audit_log(
            user_id=current_user.id,
            action="PDF_EXPORT",
            details={"request_id": request_id, "well_name": meta.well_name}
        )

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except RuntimeError as re_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(re_err)
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
