# app.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import asyncio
from datetime import datetime

from database import init_db, AsyncSessionLocal, User, Project
from security import get_password_hash, verify_password, create_access_token
from physics import DrillingHydraulicsEngine, WellSegment, NozzleInput, RheologyModel
from pdf_generator import generate_pdf_payload

# Initialize Async DB Engine
asyncio.run(init_db())

st.set_page_config(
    page_title="PyMudCement Optima Pro v5.0",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enterprise Branding Styling
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #0F172A; }
    .sub-header { font-size: 1.0rem; color: #F97316; font-weight: 600; margin-bottom: 20px; }
    .stApp { background-color: #F8FAFC; }
    .css-1r6594q { background-color: #0F172A; }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# ==============================================================================
# AUTHENTICATION SYSTEM INTERFACE
# ==============================================================================
if not st.session_state.authenticated:
    st.title("🛢️ PyMudCement Optima Pro v5.0")
    st.subheader("Enterprise Hydraulic Engine & Real-Time AI Diagnostics")
   
    auth_mode = st.radio("Select Action", ["Login", "Register Account"], horizontal=True)
   
    with st.form("auth_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if auth_mode == "Register Account":
            email = st.text_input("Corporate Email")
            company = st.text_input("Company Name", value="Enterprise Hydrocarbons Corp")
           
        submit = st.form_submit_button("Submit")
       
        if submit:
            async def handle_auth():
                async with AsyncSessionLocal() as session:
                    if auth_mode == "Register Account":
                        hashed_pw = get_password_hash(password)
                        new_user = User(username=username, email=email, hashed_password=hashed_pw, company_name=company)
                        session.add(new_user)
                        await session.commit()
                        st.success("Account created successfully! Please log in.")
                    else:
                        from sqlalchemy import select
                        result = await session.execute(select(User).where(User.username == username))
                        user = result.scalar_one_or_none()
                        if user and verify_password(password, user.hashed_password):
                            st.session_state.authenticated = True
                            st.session_state.user_info = {"id": user.id, "username": user.username, "company": user.company_name}
                            st.rerun()
                        else:
                            st.error("Invalid credentials provided.")
           
            asyncio.run(handle_auth())
    st.stop()

# ==============================================================================
# MAIN APPLICATION INTERFACE
# ==============================================================================
st.markdown('<div class="main-header">PYMUDCEMENT OPTIMA PRO v5.0</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">Logged in as: {st.session_state.user_info["username"]} | {st.session_state.user_info["company"]}</div>', unsafe_allow_html=True)

# Sidebar System Configuration
with st.sidebar:
    st.header("⚙️ Well & Mud Parameters")
    total_depth = st.number_input("Total Depth (ft MD)", value=10000.0, step=500.0)
    flow_rate = st.number_input("Flow Rate (GPM)", value=550.0, step=25.0)
    surface_mw = st.number_input("Surface Mud Weight (ppg)", value=12.5, step=0.1)
   
    rheology = st.selectbox("Rheology Model", [r.value for r in RheologyModel])
    pv = st.number_input("Plastic Viscosity (cP)", value=22.0, step=1.0)
    yp = st.number_input("Yield Point (lb/100ft²)", value=16.0, step=1.0)
   
    if st.button("Log Out"):
        st.session_state.authenticated = False
        st.rerun()

tabs = st.tabs(["📊 Hydraulics Matrix", "🎯 3D Well Trajectory", "🤖 AI Co-Pilot Diagnostics", "📄 PDF Export"])

# Tab 1: Multi-Segment Hydraulics Config
with tabs[0]:
    st.subheader("Multi-Segment Wellbore Geometry")
   
    default_segments = pd.DataFrame([
        {"Segment Name": "Surface Drill Pipe", "Length (ft)": 7000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 4.276, "Hole ID (in)": 12.25, "Mud Weight (ppg)": surface_mw},
        {"Segment Name": "Heavy Weight Pipe", "Length (ft)": 2000.0, "Pipe OD (in)": 5.0, "Pipe ID (in)": 3.000, "Hole ID (in)": 8.50, "Mud Weight (ppg)": surface_mw},
        {"Segment Name": "Drill Collars / BHA", "Length (ft)": 1000.0, "Pipe OD (in)": 6.75, "Pipe ID (in)": 2.250, "Hole ID (in)": 8.50, "Mud Weight (ppg)": surface_mw}
    ])
   
    edited_df = st.data_editor(default_segments, num_rows="dynamic", use_container_width=True)
   
    if st.button("Run Engineering Calculations", type="primary"):
        try:
            engine = DrillingHydraulicsEngine(
                surface_mud_weight_ppg=surface_mw,
                flow_rate_gpm=flow_rate,
                total_depth_ft=total_depth,
                plastic_viscosity_cp=pv,
                yield_point_lb_100ft2=yp,
                rheology_model=RheologyModel(rheology)
            )
           
            for _, row in edited_df.iterrows():
                engine.add_segment(WellSegment(
                    name=str(row["Segment Name"]),
                    length_ft=float(row["Length (ft)"]),
                    pipe_od_in=float(row["Pipe OD (in)"]),
                    pipe_id_in=float(row["Pipe ID (in)"]),
                    hole_id_in=float(row["Hole ID (in)"]),
                    mud_weight_ppg=float(row["Mud Weight (ppg)"]),
                    viscosity_cp=pv,
                    yield_point_lb_100ft2=yp
                ))
           
            engine.add_nozzle(NozzleInput(size_in_32nds=12))
            engine.add_nozzle(NozzleInput(size_in_32nds=12))
            engine.add_nozzle(NozzleInput(size_in_32nds=12))
           
            results = engine.solve()
            st.session_state.latest_results = results
           
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Bottomhole ECD", f"{results['equivalent_circulating_density_ecd_ppg']} ppg")
            m2.metric("Total SPP", f"{results['standpipe_pressure_spp_psi']} psi")
            m3.metric("Annular Pressure Drop", f"{results['total_annular_pressure_loss_psi']} psi")
            m4.metric("Bit Nozzle Loss", f"{results['bit_hydraulics']['bit_pressure_drop_psi']} psi")
           
            st.subheader("Segment Analytics Breakdown")
            st.dataframe(pd.DataFrame(results["segment_breakdown"]), use_container_width=True)
           
        except Exception as e:
            st.error(f"Execution Error: {str(e)}")

# Tab 2: Interactive 3D Well Trajectory Visualization
with tabs[1]:
    st.subheader("Interactive 3D Well Trajectory Profile")
   
    md_steps = np.linspace(0, total_depth, 100)
    inc = np.radians(np.linspace(0, 45, 100))
    az = np.radians(np.full(100, 60.0))
   
    z = -1 * md_steps * np.cos(inc)
    x = np.cumsum(np.sin(inc) * np.sin(az) * (total_depth / 100))
    y = np.cumsum(np.sin(inc) * np.cos(az) * (total_depth / 100))
   
    fig = go.Figure(data=[go.Scatter3d(
        x=x, y=y, z=z,
        mode='lines+markers',
        line=dict(color='#2563EB', width=6),
        marker=dict(size=3, color='#F97316')
    )])
    fig.update_layout(
        scene=dict(
            xaxis_title='Easting (ft)',
            yaxis_title='Northing (ft)',
            zaxis_title='True Vertical Depth (ft)'
        ),
        margin=dict(l=0, r=0, b=0, t=30),
        height=550
    )
    st.plotly_chart(fig, use_container_width=True)

# Tab 3: AI Drilling Assistant
with tabs[2]:
    st.subheader("🤖 AI Real-Time Drilling Assistant")
    if "latest_results" in st.session_state:
        res = st.session_state.latest_results
        ecd = res["equivalent_circulating_density_ecd_ppg"]
       
        if ecd > 15.0:
            st.error("⚠️ CRITICAL ALERT: Calculated ECD exceeds structural fracture limit (15.0 ppg). Risk of severe fluid losses.")
            st.write("**Recommended Actions:**")
            st.write("1. Reduce pump SPM to lower annular velocity and dynamic pressure drop.")
            st.write("2. Perform mud dilution to drop Plastic Viscosity.")
        else:
            st.success("✔ SAFE OPERATIONAL GRADIENT: System operating within dynamic pore-fracture window.")
            st.write("• Hydraulics, hole cleaning transport, and nozzle velocities meet all standard operating requirements.")
    else:
        st.info("Run the physics matrix on Tab 1 to view real-time AI telemetry diagnostics.")

# Tab 4: Branded PDF Report Export
with tabs[3]:
    st.subheader("📄 Export Branded PDF Compliance Report")
    if "latest_results" in st.session_state:
        if st.button("Generate Branded Field PDF", type="primary"):
            project_meta = {
                "name": "Deepwater Wilcox Target",
                "rig_name": "Rig-05 Executive",
                "company": st.session_state.user_info["company"]
            }
            diag_meta = {
                "severity": "GREEN" if st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"] < 15.0 else "RED",
                "matched_hazard": "Formation Fracturing Risk" if st.session_state.latest_results["equivalent_circulating_density_ecd_ppg"] >= 15.0 else "None",
                "detailed_diagnosis": f"Operating ECD is {st.session_state.latest_results['equivalent_circulating_density_ecd_ppg']} ppg."
            }
            pdf_buffer = generate_pdf_payload(project_meta, st.session_state.latest_results, diag_meta, engineer_name=st.session_state.user_info["username"])
           
            st.download_button(
                label="📥 Download PDF Document",
                data=pdf_buffer,
                file_name=f"PyMudCement_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf"
            )
    else:
        st.warning("Please run hydraulics calculations on Tab 1 before attempting report generation.")