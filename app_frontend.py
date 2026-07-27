import io
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional 

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field 

# Internal Engine & Helper Imports
from ai_engine import DrillingHydraulicsEngine, WellSegment, DiagnosticEngine
from pdf_generator import generate_hydraulics_pdf
from database import init_db
from routers.auth_routes import router as auth_router 

# Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PyMudCementOptimaPro.API") 

# Global Engine Instance Placeholder
ai_diagnostics: Optional[DiagnosticEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing PyMudCement Optima Pro engines and database setup...")
    await init_db()  # Ensures database tables are initialized on startup
    global ai_diagnostics
    ai_diagnostics = DiagnosticEngine(ecd_upper_threshold_delta=1.5, max_spp_limit=3500.0)
    yield
    logger.info("Shutting down PyMudCement Optima Pro services...")


# ------------------------------------------------------------------------------
# FastAPI App Initialization
# ------------------------------------------------------------------------------
app = FastAPI(
    title="PyMudCement Optima Pro API",
    description="Enterprise API engine providing drilling hydraulics calculations, AI telemetry diagnostics, and PDF reporting.",
    version="1.0.0",
    lifespan=lifespan
) 

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
) 

# Include Authentication Routes
app.include_router(auth_router) 

# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------
class WellSegmentSchema(BaseModel):
    name: str = Field(default="Drill Pipe", description="Name of the segment")
    top_md: float = Field(default=0.0, ge=0.0, description="Top Measured Depth (ft)")
    bottom_md: float = Field(default=7000.0, ge=0.0, description="Bottom Measured Depth (ft)")
    pipe_od: float = Field(default=5.0, gt=0.0, description="Pipe Outer Diameter (in)")
    pipe_id: float = Field(default=4.276, gt=0.0, description="Pipe Inner Diameter (in)")
    hole_id: float = Field(default=8.5, gt=0.0, description="Hole or Casing Inner Diameter (in)") 

class HydraulicsPayloadSchema(BaseModel):
    flow_rate_gpm: float = Field(default=450.0, gt=0.0, description="Flow Rate in GPM")
    total_depth_ft: float = Field(default=8000.0, gt=0.0, description="Total Depth / TVD in ft")
    surface_mud_weight_ppg: float = Field(default=10.0, gt=0.0, description="Surface Mud Weight in ppg")
    plastic_viscosity_cp: float = Field(default=20.0, ge=0.0, description="Plastic Viscosity in cP")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0.0, description="Yield Point in lb/100ft²")
    segments: Optional[List[WellSegmentSchema]] = Field(default=None, description="Optional custom well segments") 

# ------------------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------------------
@app.get("/", tags=["System Status"])
async def root():
    """Health check endpoint."""
    return {
        "system": "PyMudCement Optima Pro",
        "status": "OPERATIONAL",
        "version": "1.0.0"
    } 

@app.post("/api/v1/hydraulics/calculate", tags=["Hydraulics Engine"])
async def calculate_hydraulics(payload: HydraulicsPayloadSchema):
    """Executes wellbore hydraulics pressure loss calculations and runs AI hazard analysis."""
    try:
        engine = DrillingHydraulicsEngine(
            surface_mud_weight_ppg=payload.surface_mud_weight_ppg,
            flow_rate_gpm=payload.flow_rate_gpm,
            total_depth_ft=payload.total_depth_ft,
            plastic_viscosity_cp=payload.plastic_viscosity_cp,
            yield_point_lb_100ft2=payload.yield_point_lb_100ft2
        ) 

        # Build segments model
        if payload.segments:
            for seg in payload.segments:
                seg_length = max(0.0, seg.bottom_md - seg.top_md)
                engine.add_segment(WellSegment(
                    name=seg.name,
                    length_ft=seg_length,
                    pipe_od_in=seg.pipe_od,
                    pipe_id_in=seg.pipe_id,
                    hole_id_in=seg.hole_id,
                    mud_weight_ppg=payload.surface_mud_weight_ppg
                ))
        else:
            # Default single drill pipe segment fallback
            engine.add_segment(WellSegment(
                name="Default Drill String",
                length_ft=payload.total_depth_ft,
                pipe_od_in=5.0,
                pipe_id_in=4.276,
                hole_id_in=8.5,
                mud_weight_ppg=payload.surface_mud_weight_ppg
            )) 

        physics_results = engine.solve()
        
        # Run AI telemetry hazard diagnostics
        diagnostics = ai_diagnostics.analyze_telemetry(
            physics_metrics=physics_results,
            historical_esd=payload.surface_mud_weight_ppg
        ) 

        return {
            "physics_results": physics_results,
            "diagnostics": diagnostics
        } 

    except Exception as e:
        logger.error(f"Hydraulics calculation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculation Engine Failure: {str(e)}"
        ) 

@app.post("/api/v1/hydraulics/export-pdf", tags=["Reports"])
async def export_pdf_report(payload: HydraulicsPayloadSchema):
    """Generates and streams an official ReportLab PDF report containing hydraulics graphics and telemetry diagnosis."""
    try:
        # Run solver pipeline
        calc_response = await calculate_hydraulics(payload)
        physics_results = calc_response["physics_results"]
        diagnostics = calc_response["diagnostics"] 

        # Convert segment pydantic objects to dicts for report formatting
        segments_data = [seg.model_dump() for seg in payload.segments] if payload.segments else [] 

        # Build PDF stream
        pdf_buffer = generate_hydraulics_pdf(
            results=physics_results,
            diagnostic_report=diagnostics,
            executed_by="PyMudCement Automated Engine",
            segments=segments_data,
            pv=payload.plastic_viscosity_cp,
            yp=payload.yield_point_lb_100ft2
        ) 

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=PyMudCement_OptimaPro_Report.pdf"}
        ) 

    except Exception as e:
        logger.error(f"PDF Export failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF Generation Error: {str(e)}"
        )
