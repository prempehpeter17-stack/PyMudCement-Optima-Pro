import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Engine & DB Imports
from physics import DrillingHydraulicsEngine, WellSegment, DiagnosticEngine
from cementing_engine import PrimaryCementingInput, CementingEngine  # New import
from pdf_generator import generate_pdf_payload
from database import init_db, UserModel
from auth import get_current_user
from router import router as auth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PyMudCementOptimaPro.API")

ai_diagnostics: Optional[DiagnosticEngine] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing PyMudCement Optima Pro engines...")
    await init_db()
    global ai_diagnostics
    ai_diagnostics = DiagnosticEngine(ecd_upper_threshold_delta=1.5, max_spp_limit=3500.0)
    yield
    logger.info("Shutting down PyMudCement Optima Pro services...")

app = FastAPI(
    title="PyMudCement Optima Pro API",
    description="Enterprise API engine providing drilling hydraulics and cementing calculations.",
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

# Register Authentication Router
app.include_router(auth_router)

class WellSegmentSchema(BaseModel):
    name: str = Field(default="Drill Pipe", description="Name of the segment")
    top_md: float = Field(default=0.0, ge=0.0)
    bottom_md: float = Field(default=7000.0, ge=0.0)
    pipe_od: float = Field(default=5.0, gt=0.0)
    pipe_id: float = Field(default=4.276, gt=0.0)
    hole_id: float = Field(default=8.5, gt=0.0)

class HydraulicsPayloadSchema(BaseModel):
    flow_rate_gpm: float = Field(default=450.0, gt=0.0)
    total_depth_ft: float = Field(default=8000.0, gt=0.0)
    surface_mud_weight_ppg: float = Field(default=10.0, gt=0.0)
    plastic_viscosity_cp: float = Field(default=20.0, ge=0.0)
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0.0)
    segments: Optional[List[WellSegmentSchema]] = None

@app.get("/", tags=["System Status"])
async def root():
    return {"system": "PyMudCement Optima Pro", "status": "OPERATIONAL", "version": "1.0.0"}

@app.post("/api/v1/hydraulics/calculate", tags=["Hydraulics Engine"])
async def calculate_hydraulics(
    payload: HydraulicsPayloadSchema,
    current_user: UserModel = Depends(get_current_user)
):
    try:
        engine = DrillingHydraulicsEngine(
            surface_mud_weight_ppg=payload.surface_mud_weight_ppg,
            flow_rate_gpm=payload.flow_rate_gpm,
            total_depth_ft=payload.total_depth_ft,
            plastic_viscosity_cp=payload.plastic_viscosity_cp,
            yield_point_lb_100ft2=payload.yield_point_lb_100ft2
        )

        if payload.segments:
            for seg in payload.segments:
                seg_length = max(0.0, seg.bottom_md - seg.top_md)
                engine.add_segment(WellSegment(
                    name=seg.name,
                    length_ft=seg_length,
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

        return {"physics_results": physics_results, "diagnostics": diagnostics}

    except Exception as e:
        logger.error(f"Hydraulics calculation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Calculation Engine Failure: {str(e)}"
        )

@app.post("/api/v1/hydraulics/export-pdf", tags=["Reports"])
async def export_pdf_report(
    payload: HydraulicsPayloadSchema,
    current_user: UserModel = Depends(get_current_user)
):
    try:
        # Reuse the calculation endpoint
        calc_response = await calculate_hydraulics(payload, current_user=current_user)
        physics_results = calc_response["physics_results"]
        diagnostics = calc_response["diagnostics"]

        project_metadata = {
            "name": payload.segments[0].name if payload.segments else "Default Well",
            "rig_name": "Rig-05 Executive",
            "company": current_user.company_name,
        }

        # Generate PDF (cementing_results not provided here)
        pdf_buffer = generate_pdf_payload(
            project_metadata=project_metadata,
            physics_results=physics_results,
            diagnostic_results=diagnostics,
            engineer_name=current_user.email,
            cementing_results=None  # can be extended later
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

# --- New Cementing Endpoint ---
@app.post("/api/v1/cementing/design", tags=["Cementing Engine"])
async def design_cement_job(
    params: PrimaryCementingInput,
    current_user: UserModel = Depends(get_current_user)
):
    try:
        engine = CementingEngine()
        result = engine.design_primary_job(params)
        return result
    except Exception as e:
        logger.error(f"Cementing design failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cementing Engine Failure: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)