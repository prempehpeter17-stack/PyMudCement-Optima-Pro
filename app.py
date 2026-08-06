import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import asyncio
import base64
import re
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from database import init_db, AsyncSessionLocal, User
from security import get_password_hash, verify_password
from physics import DrillingHydraulicsEngine, WellSegment, NozzleInput, RheologyModel
from pdf_generator import generate_pdf_payload

============================================================================== LOGO SVG DEFINITION ============================================================================== 

LOGO_SVG = """






















































"""

def render_svg(svg_string: str, width: int = 50):
b64 = base64.b64encode(svg_string.encode('utf-8')).decode("utf-8")
return f''

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
try:
loop = asyncio.get_event_loop()
if loop.is_running():
raise RuntimeError()
except RuntimeError:
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
return loop.run_until_complete(coro)

try:
run_async(init_db())
except SQLAlchemyError as e:
st.error(f"Database Initialization Failed: {str(e)}")

============================================================================== APP LAYOUT & THEME ============================================================================== 

st.set_page_config(
page_title="PyMudCement Optima Pro",
page_icon="🛢️",
layout="wide",
initial_sidebar_state="expanded"
)

st.markdown("""

.brand-container { display: flex; align-items: center; gap: 18px; margin-bottom: 10px; } .brand-title { font-size: 2.2rem; font-weight: 800; font-family: 'Segoe UI', Roboto, sans-serif; line-height: 1.1; margin: 0; } .brand-title-blue { color: #0047AB; } .brand-title-gold { color: #D4AF37; } .brand-subtitle { font-size: 0.9rem; color: #CA8A04; font-weight: 700; letter-spacing: 2.5px; margin-top: 2px; } .brand-tagline { font-size: 0.72rem; color: #0F172A; font-weight: 600; letter-spacing: 3px; margin-top: 1px; } .card { background-color: #FFFFFF; border-radius: 8px; padding: 15px; border: 1px solid #E2E8F0; margin-bottom: 10px; } .badge-pass { background-color: #DCFCE7; color: #166534; padding: 4px 8px; border-radius: 4px; font-weight: 600; } .badge-warn { background-color: #FEF3C7; color: #92400E; padding: 4px 8px; border-radius: 4px; font-weight: 600; } .badge-fail { background-color: #FEE2E2; color: #991B1B; padding: 4px 8px; border-radius: 4px; font-weight: 600; } 

""", unsafe_allow_html=True)

if "authenticated" not in st.session_state:
st.session_state.authenticated = False
if "user_info" not in st.session_state:
st.session_state.user_info = None
if "failed_attempts" not in st.session_state:
st.session_state.failed_attempts = 0

============================================================================== AUTHENTICATION LOGIC ============================================================================== 

def validate_email(email: str) -> bool:
pattern = r"^[\w.-]+@[\w.-]+.\w+$"
return bool(re.match(pattern, email))

async def process_authentication(mode: str, username_val: str, password_val: str, email_val: str = None, company_val: str = None) -> Tuple[bool, Any]:
async with AsyncSessionLocal() as session:
if mode == "Register Account":
if not validate_email(email_val):
return False, "Invalid corporate email format."
if len(password_val) < 8:
return False, "Password must be at least 8 characters long."
try:
existing = await session.execute(
select(User).where(or_(User.username == username_val, User.email == email_val))
)
if existing.scalar_one_or_none():
return False, "Username or email already registered."

hashed_pw = get_password_hash(password_val) new_user = User( username=username_val, email=email_val, hashed_password=hashed_pw, company_name=company_val or CONFIG["DEFAULT_COMPANY"] ) session.add(new_user) await session.commit() return True, "Account registered successfully. Please log in." except IntegrityError: await session.rollback() return False, "Database constraint error: duplicate entry detected." except SQLAlchemyError as e: await session.rollback() return False, f"Database exception: {str(e)}" else: try: result = await session.execute(select(User).where(User.username == username_val)) user = result.scalar_one_or_none() if user and verify_password(password_val, user.hashed_password): st.session_state.failed_attempts = 0 return True, {"id": user.id, "username": user.username, "company": user.company_name} st.session_state.failed_attempts += 1 return False, "Invalid username or password." except SQLAlchemyError as e: return False, f"Authentication error: {str(e)}" 

if not st.session_state.authenticated:
st.markdown(f"""


{render_svg(LOGO_SVG, 85)}



PyMudCement


— OPTIMA PRO —


ENGINEERED FOR DRILLING EXCELLENCE




""", unsafe_allow_html=True) if st.session_state.failed_attempts >= 5: st.error("Account locked temporarily due to 5 consecutive failed login attempts. Please try again later.") st.stop() auth_mode = st.radio("Select Action", ["Login", "Register Account"], horizontal=True) with st.form("auth_form"): username = st.text_input("Username").strip() password = st.text_input("Password", type="password") email = st.text_input("Corporate Email").strip() if auth_mode == "Register Account" else None company = st.text_input("Company Name", value=CONFIG["DEFAULT_COMPANY"]).strip() if auth_mode == "Register Account" else None submit = st.form_submit_button("Submit") if submit: if not username or not password: st.error("Username and password are required.") else: success, response = run_async(process_authentication(auth_mode, username, password, email, company)) if auth_mode == "Register Account": if success: st.success(response) else: st.error(response) else: if success: st.session_state.authenticated = True st.session_state.user_info = response st.rerun() else: st.error(response) st.stop() ============================================================================== MAIN APPLICATION INTERFACE ============================================================================== 

st.markdown(f"""

{render_svg(LOGO_SVG, 70)} 

PyMudCement 

— OPTIMA PRO —

ENGINEERED FOR DRILLING EXCELLENCE

""", unsafe_allow_html=True) 

st.caption(f"Logged in as: {st.session_state.user_info['username']} | Organization: {st.session_state.user_info['company']}")
st.divider()

with st.sidebar:
st.markdown(f"""


{render_svg(LOGO_SVG, 42)}
Optima Controls


""", unsafe_allow_html=True) unit_system = st.selectbox("Unit System", ["API (Imperial)", "SI (Metric)"]) # Unit Conversion Multipliers is_si = unit_system == "SI (Metric)" total_depth_label = "Total Depth (m MD)" if is_si else "Total Depth (ft MD)" flow_rate_label = "Flow Rate (L/min)" if is_si else "Flow Rate (GPM)" mw_label = "Surface Mud Weight (kg/m³)" if is_si else "Surface Mud Weight (ppg)" total_depth_default = 3048.0 if is_si else CONFIG["DEFAULT_TOTAL_DEPTH"] flow_rate_default = 2082.0 if is_si else CONFIG["DEFAULT_FLOW_RATE"] surface_mw_default = 1498.0 if is_si else CONFIG["DEFAULT_SURFACE_MW"] total_depth = st.number_input(total_depth_label, value=total_depth_default, step=150.0) flow_rate = st.number_input(flow_rate_label, value=flow_rate_default, step=50.0) surface_mw = st.number_input(mw_label, value=surface_mw_default, step=1.0 if is_si else 0.1) rheology = st.selectbox("Rheology Model", [r.value for r in RheologyModel]) pv = st.number_input("Plastic Viscosity (cP)", value=CONFIG["DEFAULT_PV"], step=1.0) yp = st.number_input("Yield Point (lb/100ft²)", value=CONFIG["DEFAULT_YP"], step=1.0) st.subheader("Bit Nozzles (32nds in)") nozzle_input_str = st.text_input("Enter Nozzle Sizes (comma-separated)", value="12, 12, 12") if st.button("Log Out", use_container_width=True): st.session_state.authenticated = False st.session_state.user_info = None st.rerun() 

tabs = st.tabs(["📊 Hydraulics Matrix", "🎯 3D Trajectory (MCM)", "🤖 Multi-Factor Diagnostics", "📄 PDF Export"])

------------------------------------------------------------------------------ TAB 1: HYDRAULICS MATRIX ------------------------------------------------------------------------------ 

with tabs[0]:
st.subheader("Multi-Segment Wellbore Geometry")

if "segments" not in st.session_state: st.session_state["segments"] = pd.DataFrame([ {"Segment Name": "Surface Drill Pipe", "Length (ft)": 7000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 4.276, "Hole ID (in)": 12.25, "Mud Weight (ppg)": CONFIG["DEFAULT_SURFACE_MW"]}, {"Segment Name": "Heavy Weight Pipe", "Length (ft)": 2000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 3.000, "Hole ID (in)": 8.50, "Mud Weight (ppg)": CONFIG["DEFAULT_SURFACE_MW"]}, {"Segment Name": "Drill Collars / BHA", "Length (ft)": 1000.0, "Pipe OD (in)": 6.75, "Pipe ID (in)": 2.250, "Hole ID (in)": 8.50, "Mud Weight (ppg)": CONFIG["DEFAULT_SURFACE_MW"]} ]) edited_df = st.data_editor(st.session_state["segments"], num_rows="dynamic", use_container_width=True, key="segment_editor") st.session_state["segments"] = edited_df @st.cache_data(show_spinner=False) def compute_hydraulics_cached(flow, mw, pv_val, yp_val, rheo_model, seg_data_tuples, nozzles): engine = DrillingHydraulicsEngine( surface_mud_weight_ppg=mw, flow_rate_gpm=flow, total_depth_ft=sum(s[1] for s in seg_data_tuples), plastic_viscosity_cp=pv_val, yield_point_lb_100ft2=yp_val, rheology_model=RheologyModel(rheo_model) ) for name, length, od, id_pipe, hole, mw_seg in seg_data_tuples: engine.add_segment(WellSegment( name=name, length_ft=length, pipe_od_in=od, pipe_id_in=id_pipe, hole_id_in=hole, mud_weight_ppg=mw_seg, viscosity_cp=pv_val, yield_point_lb_100ft2=yp_val )) for n_size in nozzles: engine.add_nozzle(NozzleInput(size_in_32nds=n_size)) return engine.solve() if st.button("Run Engineering Calculations", type="primary"): try: seg_tuples = [ (str(r["Segment Name"]), float(r["Length (ft)"]), float(r["Pipe OD (in)"]), float(r["Pipe ID (in)"]), float(r["Hole ID (in)"]), float(r["Mud Weight (ppg)"])) for _, r in edited_df.iterrows() ] nozzles_list = [int(n.strip()) for n in nozzle_input_str.split(",") if n.strip().isdigit()] if not nozzles_list: nozzles_list = [12, 12, 12] results = compute_hydraulics_cached(flow_rate, surface_mw, pv, yp, rheology, tuple(seg_tuples), tuple(nozzles_list)) st.session_state.latest_results = results m1, m2, m3, m4 = st.columns(4) m1.metric("Bottomhole ECD", f"{results['equivalent_circulating_density_ecd_ppg']} ppg") m2.metric("Total SPP", f"{results['standpipe_pressure_spp_psi']} psi") m3.metric("Annular Pressure Drop", f"{results['total_annular_pressure_loss_psi']} psi") m4.metric("Bit Nozzle Loss", f"{results['bit_hydraulics']['bit_pressure_drop_psi']} psi") st.subheader("Segment Analytics Breakdown") st.dataframe(pd.DataFrame(results["segment_breakdown"]), use_container_width=True) except ValueError as ve: st.error(f"Value Configuration Error: {str(ve)}") except KeyError as ke: st.error(f"Missing Data Schema Key: {str(ke)}") except SQLAlchemyError as se: st.error(f"Database Error: {str(se)}") except Exception as e: st.error(f"Unexpected Engine Execution Failure: {str(e)}") ------------------------------------------------------------------------------ TAB 2: 3D TRAJECTORY (MINIMUM CURVATURE METHOD) ------------------------------------------------------------------------------ 

with tabs[1]:
st.subheader("3D Wellbore Survey Profile (Minimum Curvature Method)")

if "survey" not in st.session_state: st.session_state["survey"] = pd.DataFrame([ {"MD (ft)": 0.0, "Inc (deg)": 0.0, "Az (deg)": 0.0}, {"MD (ft)": 3000.0, "Inc (deg)": 0.0, "Az (deg)": 0.0}, {"MD (ft)": 6000.0, "Inc (deg)": 25.0, "Az (deg)": 45.0}, {"MD (ft)": total_depth, "Inc (deg)": 45.0, "Az (deg)": 60.0} ]) edited_survey = st.data_editor(st.session_state["survey"], num_rows="dynamic", use_container_width=True, key="survey_editor") st.session_state["survey"] = edited_survey def validate_survey_data(df: pd.DataFrame) -> Tuple[bool, str]: norm_df = df.copy() norm_df.columns = [str(c).strip().lower() for c in norm_df.columns] md_col = next((c for c in norm_df.columns if 'md' in c), None) inc_col = next((c for c in norm_df.columns if 'inc' in c), None) az_col = next((c for c in norm_df.columns if 'az' in c or 'azi' in c), None) if not md_col or not inc_col or not az_col: return False, "Required columns (MD, Inc, Az) missing in survey data." if norm_df[[md_col, inc_col, az_col]].isnull().any().any(): return False, "Survey data contains missing/null values." md_vals = norm_df[md_col].values inc_vals = norm_df[inc_col].values az_vals = norm_df[az_col].values if not np.all(np.diff(md_vals) > 0): return False, "Measured Depth (MD) must be strictly increasing." if not np.all((inc_vals >= 0.0) & (inc_vals <= 180.0)): return False, "Inclination values must remain between 0 and 180 degrees." if not np.all((az_vals >= 0.0) & (az_vals <= 360.0)): return False, "Azimuth values must remain between 0 and 360 degrees." return True, "" is_valid, err_msg = validate_survey_data(edited_survey) if not is_valid: st.error(f"Survey Validation Error: {err_msg}") else: def calculate_mcm(df: pd.DataFrame): norm_df = df.copy() norm_df.columns = [str(c).strip().lower() for c in norm_df.columns] md_col, inc_col, az_col = norm_df.columns[0], norm_df.columns[1], norm_df.columns[2] md = norm_df[md_col].values inc = np.radians(norm_df[inc_col].values) az = np.radians(norm_df[az_col].values) n = len(md) x, y, z = np.zeros(n), np.zeros(n), np.zeros(n) for i in range(1, n): d1 = md[i] - md[i-1] if d1 == 0: continue i1, i2 = inc[i-1], inc[i] a1, a2 = az[i-1], az[i] cos_dl = np.cos(i2 - i1) - (np.sin(i1) * np.sin(i2) * (1 - np.cos(a2 - a1))) cos_dl = np.clip(cos_dl, -1.0, 1.0) dl = np.arccos(cos_dl) rf = (2 / dl) * np.tan(dl / 2) if dl > 1e-6 else 1.0 dz = (d1 / 2) * (np.cos(i1) + np.cos(i2)) * rf dx = (d1 / 2) * (np.sin(i1) * np.sin(a1) + np.sin(i2) * np.sin(a2)) * rf dy = (d1 / 2) * (np.sin(i1) * np.cos(a1) + np.sin(i2) * np.cos(a2)) * rf z[i] = z[i-1] - dz x[i] = x[i-1] + dx y[i] = y[i-1] + dy return x, y, z x_coords, y_coords, z_coords = calculate_mcm(edited_survey) fig = go.Figure(data=[go.Scatter3d( x=x_coords, y=y_coords, z=z_coords, mode='lines+markers', line=dict(color='#2563EB', width=6), marker=dict(size=4, color='#F97316') )]) fig.update_layout( scene=dict( xaxis_title='Easting (ft)', yaxis_title='Northing (ft)', zaxis_title='True Vertical Depth (ft)' ), margin=dict(l=0, r=0, b=0, t=30), height=550 ) st.plotly_chart(fig, use_container_width=True) ------------------------------------------------------------------------------ TAB 3: MULTI-FACTOR AI DIAGNOSTICS ------------------------------------------------------------------------------ 

with tabs[2]:
st.subheader("🤖 Comprehensive Multi-Factor Diagnostic Engine")

if "latest_results" in st.session_state: res = st.session_state.latest_results ecd = res["equivalent_circulating_density_ecd_ppg"] spp = res["standpipe_pressure_spp_psi"] bit_dp = res["bit_hydraulics"]["bit_pressure_drop_psi"] bit_ratio = bit_dp / spp if spp > 0 else 0.0 ecd_status = "SAFE" if ecd <= CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "CRITICAL" bit_status = "OPTIMAL" if CONFIG["BIT_PRESSURE_RATIO_MIN"] <= bit_ratio <= CONFIG["BIT_PRESSURE_RATIO_MAX"] else "SUB-OPTIMAL" cleaning_status = "ADEQUATE" if flow_rate >= 450.0 else "RISK (Low Annular Velocity)" c1, c2, c3 = st.columns(3) with c1: st.markdown(f"**ECD Gradient Integrity**") badge_class = "badge-pass" if ecd_status == "SAFE" else "badge-fail" st.markdown(f'<span class="{badge_class}">{ecd_status}</span>', unsafe_allow_html=True) st.caption(f"Current ECD: {ecd} ppg | Limit: {CONFIG['ECD_FRACTURE_LIMIT_PPG']} ppg") with c2: st.markdown(f"**Bit Hydraulic Energy Ratio**") badge_class = "badge-pass" if bit_status == "OPTIMAL" else "badge-warn" st.markdown(f'<span class="{badge_class}">{bit_status}</span>', unsafe_allow_html=True) st.caption(f"Bit Ratio: {bit_ratio:.2%} | Target: 50% - 65%") with c3: st.markdown(f"**Hole Cleaning Transport**") badge_class = "badge-pass" if cleaning_status == "ADEQUATE" else "badge-warn" st.markdown(f'<span class="{badge_class}">{cleaning_status}</span>', unsafe_allow_html=True) st.caption(f"Flow Rate: {flow_rate} GPM equivalents") st.divider() st.markdown("### Engineering Recommendations") recs = [] if ecd_status == "CRITICAL": recs.append("• **Fracture Risk**: Lower pump flow rate or reduce yield point/PV via dilution to reduce total friction drop.") if bit_status == "SUB-OPTIMAL": recs.append("• **Nozzle Sizing**: Adjust bit nozzle total flow area (TFA) to match the target 50-65% SPP pressure drop window.") if cleaning_status != "ADEQUATE": recs.append("• **Cuttings Settling**: Increase GPM or augment mud yield point to prevent cuttings bed buildup in angled sections.") if not recs: st.success("All operational parameters fall within acceptable enterprise tolerances.") else: for rec in recs: st.write(rec) else: st.info("Run hydraulics calculation in Tab 1 to generate telemetry diagnostics.") ------------------------------------------------------------------------------ TAB 4: PDF EXPORT ------------------------------------------------------------------------------ 

with tabs[3]:
st.subheader("📄 Export Compliance Documentation")

if "latest_results" in st.session_state: if st.button("Generate Branded PDF Report", type="primary"): try: project_meta = { "name": "Deepwater Wilcox Target", "rig_name": "Rig-05 Executive", "company": st.session_state.user_info["company"] } ecd_val = st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"] diag_meta = { "severity": "GREEN" if ecd_val <= CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "RED", "matched_hazard": "Formation Fracturing Risk" if ecd_val > CONFIG["ECD_FRACTURE_LIMIT_PPG"] else "None", "detailed_diagnosis": f"Operating ECD calculated at {ecd_val} ppg." } pdf_buffer = generate_pdf_payload( project_meta, st.session_state.latest_results, diag_meta, engineer_name=st.session_state.user_info["username"] ) st.download_button( label="📥 Download PDF Document", data=pdf_buffer, file_name=f"PyMudCement_Report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf", mime="application/pdf" ) except KeyError as ke: st.error(f"Failed to resolve report schema key: {str(ke)}") except ValueError as ve: st.error(f"Value error generating PDF buffer: {str(ve)}") except Exception as e: st.error(f"Unexpected error producing PDF: {str(e)}") else: st.warning("Please compute hydraulics in Tab 1 prior to report generation.") 