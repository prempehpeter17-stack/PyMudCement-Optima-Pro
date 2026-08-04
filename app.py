import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import init_db, AsyncSessionLocal, User
from security import get_password_hash, verify_password
from physics import DrillingHydraulicsEngine, WellSegment, NozzleInput, RheologyModel
from pdf_generator import generate_pdf_payload

============================================================================== CONFIGURATION & CONSTANTS ============================================================================== 

CONFIG = {
"DEFAULT_TOTAL_DEPTH": 10000.0,
"DEFAULT_FLOW_RATE": 550.0,
"DEFAULT_SURFACE_MW": 12.5,
"DEFAULT_PV": 22.0,
"DEFAULT_YP": 16.0,
"ECD_FRACTURE_LIMIT_PPG": 15.0,
"BIT_PRESSURE_RATIO_MIN": 0.50,
"BIT_PRESSURE_RATIO_MAX": 0.65,
"DEFAULT_COMPANY": "Enterprise Hydrocarbons Corp"
}

============================================================================== SAFE ASYNC RUNNER FOR STREAMLIT ============================================================================== 

def run_async(coro):
"""Executes async coroutines safely within Streamlit's execution thread."""
try:
loop = asyncio.get_running_loop()
except RuntimeError:
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
return loop.run_until_complete(coro)

Initialize DB safely on boot 

try:
run_async(init_db())
except SQLAlchemyError as e:
st.error(f"Database Initialization Failed: {str(e)}")

============================================================================== APP LAYOUT & THEME ============================================================================== 

st.set_page_config(
page_title="PyMudCement Optima Pro v5.0",
page_icon="🛢️",
layout="wide",
initial_sidebar_state="expanded"
)

st.markdown("""

.main-header { font-size: 2.2rem; font-weight: 700; color: #0F172A; margin-bottom: 0px; } .sub-header { font-size: 0.95rem; color: #F97316; font-weight: 600; margin-bottom: 25px; } .card { background-color: #FFFFFF; border-radius: 8px; padding: 15px; border: 1px solid #E2E8F0; margin-bottom: 10px; } .badge-pass { background-color: #DCFCE7; color: #166534; padding: 4px 8px; border-radius: 4px; font-weight: 600; } .badge-warn { background-color: #FEF3C7; color: #92400E; padding: 4px 8px; border-radius: 4px; font-weight: 600; } .badge-fail { background-color: #FEE2E2; color: #991B1B; padding: 4px 8px; border-radius: 4px; font-weight: 600; } 

""", unsafe_allow_html=True)

Session State 

if "authenticated" not in st.session_state:
st.session_state.authenticated = False
if "user_info" not in st.session_state:
st.session_state.user_info = None

============================================================================== AUTHENTICATION LOGIC ============================================================================== 

async def process_authentication(mode: str, username_val: str, password_val: str, email_val: str = None, company_val: str = None) -> Tuple[bool, Any]:
async with AsyncSessionLocal() as session:
if mode == "Register Account":
try:
existing = await session.execute(
select(User).where(or_(User.username == username_val, User.email == email_val))
)
if existing.scalar_one_or_none():
return False, "Username or email already registered."

hashed_pw = get_password_hash(password_val) new_user = User( username=username_val, email=email_val, hashed_password=hashed_pw, company_name=company_val or CONFIG["DEFAULT_COMPANY"] ) session.add(new_user) await session.commit() return True, "Account registered successfully. Please log in." except IntegrityError: await session.rollback() return False, "Database constraint error: duplicate entry detected." except SQLAlchemyError as e: await session.rollback() return False, f"Database exception: {str(e)}" else: try: result = await session.execute(select(User).where(User.username == username_val)) user = result.scalar_one_or_none() if user and verify_password(password_val, user.hashed_password): return True, {"id": user.id, "username": user.username, "company": user.company_name} return False, "Invalid username or password." except SQLAlchemyError as e: return False, f"Authentication error: {str(e)}" 

if not st.session_state.authenticated:
st.title("🛢️ PyMudCement Optima Pro v5.0")
st.subheader("Enterprise Hydraulic Engine & Real-Time Diagnostics")

auth_mode = st.radio("Select Action", ["Login", "Register Account"], horizontal=True) with st.form("auth_form"): username = st.text_input("Username").strip() password = st.text_input("Password", type="password") email = st.text_input("Corporate Email").strip() if auth_mode == "Register Account" else None company = st.text_input("Company Name", value=CONFIG["DEFAULT_COMPANY"]).strip() if auth_mode == "Register Account" else None submit = st.form_submit_button("Submit") if submit: if not username or not password: st.error("Username and password are required.") else: success, response = run_async(process_authentication(auth_mode, username, password, email, company)) if auth_mode == "Register Account": if success: st.success(response) else: st.error(response) else: if success: st.session_state.authenticated = True st.session_state.user_info = response st.rerun() else: st.error(response) st.stop() ============================================================================== MAIN APPLICATION INTERFACE ============================================================================== 

st.markdown('

PYMUDCEMENT OPTIMA PRO v5.0

', unsafe_allow_html=True)
st.markdown(f'

Logged in as: {st.session_state.user_info["username"]} | {st.session_state.user_info["company"]}

', unsafe_allow_html=True) 

with st.sidebar:
st.header("⚙️ Well Configuration")
unit_system = st.selectbox("Unit System", ["API (Imperial)", "SI (Metric)"])

total_depth = st.number_input("Total Depth (ft MD)", value=CONFIG["DEFAULT_TOTAL_DEPTH"], step=500.0) flow_rate = st.number_input("Flow Rate (GPM)", value=CONFIG["DEFAULT_FLOW_RATE"], step=25.0) surface_mw = st.number_input("Surface Mud Weight (ppg)", value=CONFIG["DEFAULT_SURFACE_MW"], step=0.1) rheology = st.selectbox("Rheology Model", [r.value for r in RheologyModel]) pv = st.number_input("Plastic Viscosity (cP)", value=CONFIG["DEFAULT_PV"], step=1.0) yp = st.number_input("Yield Point (lb/100ft²)", value=CONFIG["DEFAULT_YP"], step=1.0) if st.button("Log Out"): st.session_state.authenticated = False st.session_state.user_info = None st.rerun() 

tabs = st.tabs(["📊 Hydraulics Matrix", "🎯 3D Trajectory (MCM)", "🤖 Multi-Factor Diagnostics", "📄 PDF Export"])

------------------------------------------------------------------------------ TAB 1: HYDRAULICS MATRIX ------------------------------------------------------------------------------ 

with tabs[0]:
st.subheader("Multi-Segment Wellbore Geometry")

default_segments = pd.DataFrame([ {"Segment Name": "Surface Drill Pipe", "Length (ft)": 7000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 4.276, "Hole ID (in)": 12.25, "Mud Weight (ppg)": surface_mw}, {"Segment Name": "Heavy Weight Pipe", "Length (ft)": 2000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 3.000, "Hole ID (in)": 8.50, "Mud Weight (ppg)": surface_mw}, {"Segment Name": "Drill Collars / BHA", "Length (ft)": 1000.0, "Pipe OD (in)": 6.75, "Pipe ID (in)": 2.250, "Hole ID (in)": 8.50, "Mud Weight (ppg)": surface_mw} ]) edited_df = st.data_editor(default_segments, num_rows="dynamic", use_container_width=True) if st.button("Run Engineering Calculations", type="primary"): try: engine = DrillingHydraulicsEngine( surface_mud_weight_ppg=surface_mw, flow_rate_gpm=flow_rate, total_depth_ft=total_depth, plastic_viscosity_cp=pv, yield_point_lb_100ft2=yp, rheology_model=RheologyModel(rheology) ) for _, row in edited_df.iterrows(): engine.add_segment(WellSegment( name=str(row["Segment Name"]), length_ft=float(row["Length (ft)"]), pipe_od_in=float(row["Pipe OD (in)"]), pipe_id_in=float(row["Pipe ID (in)"]), hole_id_in=float(row["Hole ID (in)"]), mud_weight_ppg=float(row["Mud Weight (ppg)"]), viscosity_cp=pv, yield_point_lb_100ft2=yp )) engine.add_nozzle(NozzleInput(size_in_32nds=12)) engine.add_nozzle(NozzleInput(size_in_32nds=12)) engine.add_nozzle(NozzleInput(size_in_32nds=12)) results = engine.solve() st.session_state.latest_results = results m1, m2, m3, m4 = st.columns(4) m1.metric("Bottomhole ECD", f"{results['equivalent_circulating_density_ecd_ppg']} ppg") m2.metric("Total SPP", f"{results['standpipe_pressure_spp_psi']} psi") m3.metric("Annular Pressure Drop", f"{results['total_annular_pressure_loss_psi']} psi") m4.metric("Bit Nozzle Loss", f"{results['bit_hydraulics']['bit_pressure_drop_psi']} psi") st.subheader("Segment Analytics Breakdown") st.dataframe(pd.DataFrame(results["segment_breakdown"]), use_container_width=True) except (ValueError, TypeError, KeyError) as e: st.error(f"Input/Calculation Error: {str(e)}") except Exception as e: st.error(f"Engine Execution Failure: {str(e)}") ------------------------------------------------------------------------------ TAB 2: 3D TRAJECTORY (MINIMUM CURVATURE METHOD) ------------------------------------------------------------------------------ 

with tabs[1]:
st.subheader("3D Wellbore Survey Profile (Minimum Curvature Method)")

survey_data = pd.DataFrame([ {"MD (ft)": 0.0, "Inc (deg)": 0.0, "Az (deg)": 0.0}, {"MD (ft)": 3000.0, "Inc (deg)": 0.0, "Az (deg)": 0.0}, {"MD (ft)": 6000.0, "Inc (deg)": 25.0, "Az (deg)": 45.0}, {"MD (ft)": total_depth, "Inc (deg)": 45.0, "Az (deg)": 60.0} ]) st.write("Survey Data Import") edited_survey = st.data_editor(survey_data, num_rows="dynamic", use_container_width=True) def calculate_mcm(df: pd.DataFrame): md = df["MD (ft)"].values inc = np.radians(df["Inc (deg)"].values) az = np.radians(df["Az (deg)"].values) n = len(md) x, y, z = np.zeros(n), np.zeros(n), np.zeros(n) for i in range(1, n): d1 = md[i] - md[i-1] if d1 == 0: continue i1, i2 = inc[i-1], inc[i] a1, a2 = az[i-1], az[i] # Dogleg angle calculation cos_dl = np.cos(i2 - i1) - (np.sin(i1) * np.sin(i2) * (1 - np.cos(a2 - a1))) cos_dl = np.clip(cos_dl, -1.0, 1.0) dl = np.arccos(cos_dl) rf = (2 / dl) * np.tan(dl / 2) if dl > 1e-6 else 1.0 dz = (d1 / 2) * (np.cos(i1) + np.cos(i2)) * rf dx = (d1 / 2) * (np.sin(i1) * np.sin(a1) + np.sin(i2) * np.sin(a2)) * rf dy = (d1 / 2) * (np.sin(i1) * np.cos(a1) + np.sin(i2) * np.cos(a2)) * rf z[i] = z[i-1] - dz # TVD subsea convention x[i] = x[i-1] + dx # Easting y[i] = y[i-1] + dy # Northing return x, y, z x_coords, y_coords, z_coords = calculate_mcm(edited_survey) fig = go.Figure(data=[go.Scatter3d( x=x_coords, y=y_coords, z=z_coords, mode='lines+markers', line=dict(color='#2563EB', width=6), marker=dict(size=4, color='#F97316') )]) fig.update_layout( scene=dict( xaxis_title='Easting (ft)', yaxis_title='Northing (ft)', zaxis_title='True Vertical Depth (ft)' ), margin=dict(l=0, r=0, b=0, t=30), height=550 ) st.plotly_chart(fig, use_container_width=True) ------------------------------------------------------------------------------ TAB 3: MULTI-FACTOR AI DIAGNOSTICS ------------------------------------------------------------------------------ 

with tabs[2]:
st.subheader("🤖 Multi-Factor Diagnostic Engine")

if "latest_results" in st.session_state: res = st.session_state.latest_results ecd = res["equivalent_circulating_density_ecd_ppg"] spp = res["standpipe_pressure_spp_psi"] bit_dp = res["bit_hydraulics"]["bit_pressure_drop_psi"] bit_ratio = bit_dp / spp if spp > 0 else 0.0 # Multi-Factor Evaluations ecd_status = "SAFE" if ecd <= CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "CRITICAL" bit_status = "OPTIMAL" if CONFIG["BIT_PRESSURE_RATIO_MIN"] <= bit_ratio <= CONFIG["BIT_PRESSURE_RATIO_MAX"] else "SUB-OPTIMAL" cleaning_status = "ADEQUATE" if flow_rate >= 450.0 else "RISK (Low Annular Velocity)" c1, c2, c3 = st.columns(3) with c1: st.markdown(f"**ECD Gradient Integrity**") badge_class = "badge-pass" if ecd_status == "SAFE" else "badge-fail" st.markdown(f'<span class="{badge_class}">{ecd_status}</span>', unsafe_allow_html=True) st.caption(f"Current ECD: {ecd} ppg | Limit: {CONFIG['ECD_FRACTURE_LIMIT_PPG']} ppg") with c2: st.markdown(f"**Bit Hydraulic Energy Ratio**") badge_class = "badge-pass" if bit_status == "OPTIMAL" else "badge-warn" st.markdown(f'<span class="{badge_class}">{bit_status}</span>', unsafe_allow_html=True) st.caption(f"Bit Ratio: {bit_ratio:.2%} | Target: 50% - 65%") with c3: st.markdown(f"**Hole Cleaning Transport**") badge_class = "badge-pass" if cleaning_status == "ADEQUATE" else "badge-warn" st.markdown(f'<span class="{badge_class}">{cleaning_status}</span>', unsafe_allow_html=True) st.caption(f"Flow Rate: {flow_rate} GPM") st.divider() st.markdown("### Engineering Recommendations") recs = [] if ecd_status == "CRITICAL": recs.append("• **Fracture Risk**: Lower pump flow rate or reduce yield point/PV via dilution to reduce total friction drop.") if bit_status == "SUB-OPTIMAL": recs.append("• **Nozzle Sizing**: Adjust bit nozzle total flow area (TFA) to match the target 50-65% SPP pressure drop window.") if cleaning_status != "ADEQUATE": recs.append("• **Cuttings Settling**: Increase GPM or augment mud yield point to prevent cuttings bed buildup in angled sections.") if not recs: st.success("All operational parameters fall within acceptable enterprise tolerances.") else: for rec in recs: st.write(rec) else: st.info("Run hydraulics calculation in Tab 1 to generate telemetry diagnostics.") ------------------------------------------------------------------------------ TAB 4: PDF EXPORT ------------------------------------------------------------------------------ 

with tabs[3]:
st.subheader("📄 Export Compliance Documentation")

if "latest_results" in st.session_state: if st.button("Generate Branded PDF Report", type="primary"): try: project_meta = { "name": "Deepwater Wilcox Target", "rig_name": "Rig-05 Executive", "company": st.session_state.user_info["company"] } ecd_val = st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"] diag_meta = { "severity": "GREEN" if ecd_val <= CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "RED", "matched_hazard": "Formation Fracturing Risk" if ecd_val > CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "None", "detailed_diagnosis": f"Operating ECD calculated at {ecd_val} ppg." } pdf_buffer = generate_pdf_payload( project_meta, st.session_state.latest_results, diag_meta, engineer_name=st.session_state.user_info["username"] ) st.download_button( label="📥 Download PDF Document", data=pdf_buffer, file_name=f"PyMudCement_Report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf", mime="application/pdf" ) except (KeyError, ValueError) as e: st.error(f"Failed to generate report schema: {str(e)}") except Exception as e: st.error(f"Unexpected error producing PDF: {str(e)}") else: st.warning("Please compute hydraulics in Tab 1 prior to report generation.") 