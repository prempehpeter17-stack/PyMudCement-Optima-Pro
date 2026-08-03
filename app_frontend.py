import streamlit as st
import requests 

# ------------------------------------------------------------------------------
# Page Configuration & Styling
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="PyMudCement Optima Pro",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded"
) 

# Custom Brand Styling Header matching Optima Pro Palette
logo_html = """
<div style="display: flex; align-items: center; gap: 16px; padding: 10px 0; font-family: 'Segoe UI', Roboto, sans-serif;">
    <svg width="50" height="50" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M 30 18 A 42 42 0 1 0 78 82 L 70 75 A 32 32 0 1 1 36 26 Z" fill="#334155" />
        <rect x="10" y="44" width="8" height="12" rx="2" fill="#334155" transform="rotate(-15 14 50)"/>
        <rect x="18" y="24" width="8" height="12" rx="2" fill="#334155" transform="rotate(-45 22 30)"/>
        <rect x="38" y="10" width="8" height="12" rx="2" fill="#334155" transform="rotate(-75 42 16)"/>
        <path d="M 50 8 C 25 35 20 60 38 80 C 22 65 30 40 50 8 Z" fill="url(#blueGrad)" />
        <path d="M 50 8 C 75 35 80 60 62 80 C 78 65 70 40 50 8 Z" fill="url(#goldGrad)" />
        <path d="M 62 80 C 72 70 72 55 58 45 C 50 60 52 75 62 80 Z" fill="#CBD5E1" />
        <path d="M 46 78 L 48 30 L 52 30 L 54 78 Z" fill="#0F172A" />
        <path d="M 44 78 L 56 78 M 46 65 L 54 65 M 47 50 L 53 50 M 48 38 L 52 38" stroke="#0F172A" stroke-width="2" />
        <defs>
            <linearGradient id="blueGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#0066FF" />
                <stop offset="100%" stop-color="#002B66" />
            </linearGradient>
            <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#D4AF37" />
                <stop offset="100%" stop-color="#AA7C11" />
            </linearGradient>
        </defs>
    </svg>
    <div>
        <div style="font-size: 24px; font-weight: 800; line-height: 1.1;">
            <span style="color: #0052CC;">PyMud</span><span style="color: #C59B27;">Cement</span>
        </div>
        <div style="font-size: 13px; font-weight: 700; color: #0052CC; letter-spacing: 2px;">
            OPTIMA <span style="color: #C59B27;">PRO</span>
        </div>
    </div>
</div>
"""
st.markdown(logo_html, unsafe_allow_html=True)
st.markdown("---") 

BACKEND_URL = "http://127.0.0.1:8000" 

# ------------------------------------------------------------------------------
# Sidebar Configuration Inputs
# ------------------------------------------------------------------------------
st.sidebar.header("⚙️ Simulation Parameters") 

# Drilling Hydraulics Inputs
flow_rate = st.sidebar.number_input("Flow Rate (GPM)", min_value=50.0, max_value=1200.0, value=450.0, step=10.0)
total_depth = st.sidebar.number_input("Total Depth / TVD (ft)", min_value=1000.0, max_value=30000.0, value=8000.0, step=100.0)
mud_weight = st.sidebar.number_input("Surface Mud Weight (ppg)", min_value=7.0, max_value=22.0, value=10.0, step=0.1) 

st.sidebar.markdown("---")
st.sidebar.header("🧪 Fluid Rheology (Bingham Plastic)")
pv = st.sidebar.number_input("Plastic Viscosity (cP)", min_value=1.0, max_value=100.0, value=20.0, step=1.0)
yp = st.sidebar.number_input("Yield Point (lb/100ft²)", min_value=0.0, max_value=80.0, value=15.0, step=1.0) 

# ------------------------------------------------------------------------------
# Multi-Segment Well Geometry Section
# ------------------------------------------------------------------------------
st.subheader("📐 Multi-Segment Wellbore Geometry") 

default_segments = [
    {"name": "Drill Pipe", "top_md": 0.0, "bottom_md": max(0.0, total_depth - 1000.0), "pipe_od": 5.0, "pipe_id": 4.276, "hole_id": 8.5},
    {"name": "BHA / HWDP", "top_md": max(0.0, total_depth - 1000.0), "bottom_md": total_depth, "pipe_od": 5.0, "pipe_id": 3.0, "hole_id": 8.5}
] 

segment_df = st.data_editor(
    default_segments,
    num_rows="dynamic",
    column_config={
        "name": st.column_config.TextColumn("Segment Name", required=True),
        "top_md": st.column_config.NumberColumn("Top MD (ft)", min_value=0.0, format="%.1f"),
        "bottom_md": st.column_config.NumberColumn("Bottom MD (ft)", min_value=0.0, format="%.1f"),
        "pipe_od": st.column_config.NumberColumn("Pipe OD (in)", min_value=1.0, format="%.3f"),
        "pipe_id": st.column_config.NumberColumn("Pipe ID (in)", min_value=0.5, format="%.3f"),
        "hole_id": st.column_config.NumberColumn("Hole / Casing ID (in)", min_value=1.0, format="%.3f"),
    },
    use_container_width=True
) 

# Build Payload
payload = {
    "flow_rate_gpm": flow_rate,
    "total_depth_ft": total_depth,
    "surface_mud_weight_ppg": mud_weight,
    "plastic_viscosity_cp": pv,
    "yield_point_lb_100ft2": yp,
    "segments": segment_df
} 

# ------------------------------------------------------------------------------
# Physics Execution & Dashboard Display
# ------------------------------------------------------------------------------
st.markdown("---")
col_calc, col_pdf = st.columns([1, 1]) 

with col_calc:
    run_btn = st.button("🚀 Run Hydraulics & AI Analysis", use_container_width=True) 

if run_btn or "physics_data" in st.session_state:
    if run_btn:
        try:
            res = requests.post(f"{BACKEND_URL}/api/v1/hydraulics/calculate", json=payload)
            if res.status_code == 200:
                st.session_state["physics_data"] = res.json()
            else:
                st.error(f"Engine Error: {res.text}")
        except Exception as e:
            st.error(f"Failed to connect to backend server at {BACKEND_URL}: {str(e)}") 

    if "physics_data" in st.session_state:
        data = st.session_state["physics_data"]
        physics = data.get("physics_results", {})
        diagnostics = data.get("diagnostics", {}) 

        st.subheader("📊 Physics & Telemetry Output")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Equivalent Circulating Density (ECD)", f"{physics.get('equivalent_circulating_density_ecd_ppg', 0.0):.2f} ppg")
        m2.metric("Standpipe Pressure (SPP)", f"{physics.get('standpipe_pressure_spp_psi', 0.0):.1f} psi")
        m3.metric("Annular Pressure Loss", f"{physics.get('total_annular_pressure_loss_psi', 0.0):.1f} psi")
        m4.metric("Pipe Pressure Loss", f"{physics.get('total_pipe_pressure_loss_psi', 0.0):.1f} psi") 

        st.markdown("---")
        st.subheader("🤖 AI Diagnostic & Hazard Mitigation Blueprint")
        
        severity = diagnostics.get("severity", "GREEN")
        if severity == "RED":
            st.error(f"**Hazard Alert:** {diagnostics.get('matched_hazard')}")
        elif severity == "YELLOW":
            st.warning(f"**Warning:** {diagnostics.get('matched_hazard')}")
        else:
            st.success("**Status:** Normal Operating Envelope") 

        st.write(f"**Diagnosis:** {diagnostics.get('detailed_diagnosis')}")
        st.write("**Action Blueprint:**")
        for rec in diagnostics.get("actionable_recommendations", []):
            st.write(f"- {rec}") 

# ------------------------------------------------------------------------------
# ReportLab PDF Export Trigger
# ------------------------------------------------------------------------------
with col_pdf:
    st.subheader("📄 Report Export")
    if st.button("📥 Generate Official PDF Report", use_container_width=True):
        try:
            pdf_res = requests.post(f"{BACKEND_URL}/api/v1/hydraulics/export-pdf", json=payload)
            if pdf_res.status_code == 200:
                st.download_button(
                    label="💾 Download Optima Pro Report (PDF)",
                    data=pdf_res.content,
                    file_name="PyMudCement_OptimaPro_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                st.success("PDF report generated successfully!")
            else:
                st.error(f"Failed to compile PDF: {pdf_res.text}")
        except Exception as e:
            st.error(f"Error connecting to backend export service: {str(e)}")
